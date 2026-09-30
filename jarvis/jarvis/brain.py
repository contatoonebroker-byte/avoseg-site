"""Interpretação de comandos: Claude com tool use."""
from __future__ import annotations

import re

from .tools import Tool

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


class SentenceSplitter:
    """Recebe texto em pedaços e entrega frases completas (frases curtas grudam na seguinte)."""

    def __init__(self, emit, min_len: int = 24, first_min_len: int = 12) -> None:
        # a 1ª frase sai mais cedo (começa a falar antes); as seguintes grudam se forem muito curtas
        self.emit, self.min_len, self.buf = emit, min_len, ""
        self._limit = min(first_min_len, min_len)

    def feed(self, chunk: str) -> None:
        self.buf += chunk
        parts = _SENTENCE_END.split(self.buf)
        pending = ""
        for sentence in parts[:-1]:
            pending = f"{pending} {sentence}".strip()
            if len(pending) >= self._limit:
                self.emit(pending)
                self._limit = self.min_len
                pending = ""
        self.buf = f"{pending} {parts[-1]}" if pending else parts[-1]

    def flush(self) -> None:
        if self.buf.strip():
            self.emit(self.buf.strip())
        self.buf = ""

SYSTEM_TEMPLATE = """Você é JARVIS, o assistente pessoal de voz do {user}: elegante, \
eficiente, com um toque discreto de humor britânico e total lealdade.

Suas respostas serão FALADAS em voz alta em português do Brasil. Portanto:
- Seja breve: uma ou duas frases, no máximo três.
- Nada de markdown, listas, emojis ou símbolos; escreva números e horários como se fala.
- Trate o usuário por "{user}". Ele mora em {city}; use essa cidade quando perguntar do tempo sem citar outra.
- Use as ferramentas quando precisar de dados reais (data, hora, música, etc.) e nunca invente resultados.
- Antes de qualquer ação irreversível (enviar ou apagar algo), peça confirmação.
- Se não entender o comando (a transcrição de voz pode ter erros), peça para repetir."""

SECOND_BRAIN_PROMPT = """

Second Brain (a memória permanente do {user}, uma extensão da mente dele):
- Quando ele pedir para anotar, lembrar, registrar uma ideia, decisão, tarefa, reunião ou algo sobre alguém, use a \
ferramenta anotar, escolhendo você mesmo título curto, área e tags. Confirme em uma frase curta o que guardou e, se houver, \
com o que conectou.
- Ao receber um bloco "[Notas relevantes]" junto do pedido, use-o como memória do {user}: cite o que ele já anotou quando \
ajudar ("você tinha anotado que..."), sem ler as notas inteiras em voz alta.
- Para perguntas como "o que decidi sobre X?" ou "o que combinei com Fulano?", use buscar_notas e ler_nota.
- Preferências e fatos duradouros sobre ele vão para lembrar_sobre_mim.
- Marketing: para posts, ideias de conteúdo e calendário das empresas (Avoseg, Avogroup), use criar_post, \
ideias_de_conteudo e planejar_calendario. O resultado completo fica na tela e no Second Brain: fale só o gancho e o \
essencial, e ofereça ler a legenda. Se faltar o perfil de marca, faça poucas perguntas e salve com definir_marca."""

MAX_HISTORY = 24  # mensagens mantidas na conversa
MAX_TOOL_ROUNDS = 6


class Brain:
    def __init__(self, client, model: str, tools: list[Tool], user_name: str = "senhor",
                 city: str = "Sorocaba", profile_provider=None, context_provider=None) -> None:
        self.client = client
        self.model = model
        self.tools = {t.name: t for t in tools}
        self.tool_schemas = [t.schema() for t in tools]
        self.system = SYSTEM_TEMPLATE.format(user=user_name, city=city)
        if "anotar" in self.tools:
            self.system += SECOND_BRAIN_PROMPT.format(user=user_name)
        self.profile_provider = profile_provider    # () -> texto do perfil do usuário (Second Brain)
        self.context_provider = context_provider    # (texto) -> notas relevantes para este pedido
        self.messages: list[dict] = []

    def _trim(self) -> None:
        """Corta o histórico só em início de turno, para não separar tool_use de tool_result."""
        while len(self.messages) > MAX_HISTORY:
            self.messages.pop(0)
            while self.messages and not self._is_user_text(self.messages[0]):
                self.messages.pop(0)

    @staticmethod
    def _is_user_text(msg: dict) -> bool:
        return msg["role"] == "user" and isinstance(msg["content"], str)

    def _run_tool(self, name: str, args: dict) -> tuple[str, bool]:
        tool = self.tools.get(name)
        if tool is None:
            return f"Ferramenta desconhecida: {name}", True
        try:
            return str(tool.func(**args)), False
        except Exception as e:
            return f"Erro ao executar {name}: {e}", True

    def _create(self, kwargs: dict, on_text=None):
        """Chamada à API; com `on_text`, usa streaming e entrega o texto conforme chega."""
        if on_text is None:
            return self.client.messages.create(**kwargs)
        with self.client.messages.stream(**kwargs) as stream:
            for chunk in stream.text_stream:
                on_text(chunk)
            return stream.get_final_message()

    def ask(self, text: str, on_sentence=None) -> str:
        """Responde ao comando. Com `on_sentence`, cada frase é entregue assim que fica pronta
        (para começar a falar antes de a resposta inteira terminar)."""
        content = text
        if self.context_provider:
            try:
                extra = self.context_provider(text)
            except Exception:
                extra = ""
            if extra:
                content = f"{text}\n\n[Notas relevantes do Second Brain]\n{extra}"
        self.messages.append({"role": "user", "content": content})
        self._trim()
        for _ in range(MAX_TOOL_ROUNDS):
            system = self.system
            if self.profile_provider and (profile := self.profile_provider()):
                system += f"\n\nSobre o usuário (do perfil no Second Brain):\n{profile}"
            kwargs = dict(model=self.model, max_tokens=1024, system=system, messages=self.messages)
            if not self.model.startswith("claude-haiku"):  # Haiku 4.5 não aceita o parâmetro effort
                kwargs["output_config"] = {"effort": "low"}
            if self.tool_schemas:
                kwargs["tools"] = self.tool_schemas
            splitter = SentenceSplitter(on_sentence) if on_sentence else None
            resp = self._create(kwargs, splitter.feed if splitter else None)
            if splitter:
                splitter.flush()
            self.messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason == "refusal":
                return "Sinto muito, não posso ajudar com isso."
            if resp.stop_reason != "tool_use":
                return " ".join(b.text for b in resp.content if b.type == "text").strip()

            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    out, is_err = self._run_tool(block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": out, "is_error": is_err})
            self.messages.append({"role": "user", "content": results})
        return "Não consegui concluir o pedido a tempo."
