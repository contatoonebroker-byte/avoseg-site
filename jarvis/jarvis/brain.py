"""Interpretação de comandos: Claude com tool use."""
from __future__ import annotations

from .tools import Tool

SYSTEM_TEMPLATE = """Você é JARVIS, o assistente pessoal de voz do {user}: elegante, \
eficiente, com um toque discreto de humor britânico e total lealdade.

Suas respostas serão FALADAS em voz alta em português do Brasil. Portanto:
- Seja breve: uma ou duas frases, no máximo três.
- Nada de markdown, listas, emojis ou símbolos; escreva números e horários como se fala.
- Trate o usuário por "{user}". Ele mora em {city}; use essa cidade quando perguntar do tempo sem citar outra.
- Use as ferramentas quando precisar de dados reais (data, hora, música, etc.) e nunca invente resultados.
- Antes de qualquer ação irreversível (enviar ou apagar algo), peça confirmação.
- Se não entender o comando (a transcrição de voz pode ter erros), peça para repetir."""

MAX_HISTORY = 24  # mensagens mantidas na conversa
MAX_TOOL_ROUNDS = 6


class Brain:
    def __init__(self, client, model: str, tools: list[Tool], user_name: str = "senhor",
                 city: str = "Sorocaba") -> None:
        self.client = client
        self.model = model
        self.tools = {t.name: t for t in tools}
        self.tool_schemas = [t.schema() for t in tools]
        self.system = SYSTEM_TEMPLATE.format(user=user_name, city=city)
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

    def ask(self, text: str) -> str:
        self.messages.append({"role": "user", "content": text})
        self._trim()
        for _ in range(MAX_TOOL_ROUNDS):
            kwargs = dict(
                model=self.model, max_tokens=1024, system=self.system,
                messages=self.messages, output_config={"effort": "low"},
            )
            if self.tool_schemas:
                kwargs["tools"] = self.tool_schemas
            resp = self.client.messages.create(**kwargs)
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
