"""Arte completa por IA: o texto que o Claude escreveu vai DENTRO do pedido e a OpenAI desenha a imagem com ele.

O Jarvis não escreve nada por cima da imagem da IA (só o logo, num canto reservado, e o rodapé legal, em uma faixa
própria no slide final). Provedor suportado: OpenAI (modelo de imagem configurável). Cada imagem é cobrada pela OpenAI.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

OPENAI_URL = "https://api.openai.com/v1/images/generations"
MAX_SLIDES_IA = 8  # trava de custo: cada slide é uma imagem cobrada

FUNCOES = {
    "capa": "CAPA impactante de um carrossel: o título bem grande e dominante, com uma imagem de fundo forte e "
            "relacionada ao tema",
    "conteudo": "slide de CONTEÚDO de um carrossel: layout limpo e bem organizado, o título em destaque e o texto "
                "de apoio logo abaixo, com boa legibilidade",
    "cta": "slide FINAL de chamada para ação: o título como pergunta ou convite e um BOTÃO bem destacado com o "
           "texto indicado",
}


def build_slide_prompt(slide: dict, post: dict, brand, idx: int, total: int) -> str:
    """Pedido à IA para UM slide, com os textos exatos que o Claude escreveu."""
    tipo = slide.get("tipo", "conteudo")
    textos = []
    if slide.get("kicker"):
        textos.append(f'- Rótulo pequeno, em caixa alta: "{slide["kicker"]}"')
    textos.append(f'- Título grande: "{slide.get("titulo", "")}"')
    if slide.get("texto"):
        textos.append(f'- {"Texto do botão" if tipo == "cta" else "Texto de apoio"}: "{slide["texto"]}"')
    visual = (post.get("briefing_visual") or post.get("titulo_interno") or "cena profissional de seguros").strip()
    serie = (f"Este é o slide {idx + 1} de {total} de uma mesma série: mantenha a MESMA identidade visual em todos."
             if total > 1 else "")
    return (
        f"Crie a arte de um post para Instagram de uma corretora de seguros brasileira: {FUNCOES.get(tipo, FUNCOES['conteudo'])}. "
        f"Estilo editorial moderno e profissional. Paleta da marca: azul-marinho {brand.navy}, azul {brand.blue}, "
        f"dourado {brand.gold} e branco. Cena/ideia visual de fundo: {visual}. {serie}\n\n"
        "Escreva EXATAMENTE os textos abaixo, em português do Brasil, com ortografia e acentuação perfeitas, em letras "
        "grandes e muito legíveis (alto contraste com o fundo; use um degradê escuro suave atrás do texto se precisar). "
        "Não altere, não traduza e não invente nenhuma palavra:\n"
        + "\n".join(textos) +
        "\n\nREGRAS: não escreva NENHUM outro texto, número, palavra, slogan, marca d'água, selo, logotipo ou endereço de "
        "rede social. Mantenha todo o texto dentro da área central, com margem de 12% em todos os lados. Deixe o canto "
        "superior esquerdo livre (sem texto) para o logotipo e deixe a faixa do rodapé sem texto."
    )


def generate_image(prompt: str, provider: str, api_key: str, model: str = "gpt-image-1",
                   size: str = "1024x1536", quality: str = "medium", timeout: int = 240) -> bytes:
    """Devolve os bytes da imagem (PNG). Levanta RuntimeError com mensagem clara se falhar."""
    if provider != "openai":
        raise RuntimeError("Gerador de imagem não configurado (falta a OPENAI_API_KEY no .env).")
    if not api_key:
        raise RuntimeError("Falta a OPENAI_API_KEY no .env.")

    def call(include_quality: bool) -> dict:
        payload = {"model": model, "prompt": prompt, "size": size, "n": 1}
        if include_quality and quality:
            payload["quality"] = quality
        req = urllib.request.Request(OPENAI_URL, data=json.dumps(payload).encode(), method="POST", headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)

    try:
        try:
            data = call(True)
        except urllib.error.HTTPError as e:
            detail = _detail(e)
            if e.code == 400 and "quality" in detail.lower():
                data = call(False)            # modelo que não aceita o parâmetro: tenta sem
            else:
                raise RuntimeError(f"A OpenAI recusou o pedido (HTTP {e.code}): {detail[:200]}") from e
    except RuntimeError:
        raise
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"A OpenAI recusou o pedido (HTTP {e.code}): {_detail(e)[:200]}") from e
    except Exception as e:
        raise RuntimeError(f"Não consegui falar com a OpenAI: {e}") from e
    item = (data.get("data") or [{}])[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        with urllib.request.urlopen(item["url"], timeout=timeout) as r:
            return r.read()
    raise RuntimeError("A OpenAI não devolveu imagem.")


def _detail(e: urllib.error.HTTPError) -> str:
    try:
        return json.load(e).get("error", {}).get("message", "")
    except Exception:
        return ""
