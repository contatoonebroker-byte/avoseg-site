"""Fundo de imagem por IA (opcional). Só a imagem: o texto da arte continua sendo desenhado pelo Jarvis.

Provedor suportado: OpenAI (modelo de imagem configurável). Precisa de OPENAI_API_KEY e IMAGE_PROVIDER=openai.
Cada imagem gerada é cobrada pela OpenAI; o Jarvis só gera quando você pede ("com foto por IA").
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

OPENAI_URL = "https://api.openai.com/v1/images/generations"

REGRAS = (
    "Fotografia editorial realista, luz natural, composição limpa com bastante espaço livre na parte inferior "
    "para colocar um título. NÃO inclua texto, letras, números, logotipos, marcas, placas legíveis nem telas com "
    "conteúdo. Pessoas, se houver, em cena natural e sem rostos de celebridades. Paleta com tons de azul-marinho."
)


def build_prompt(briefing_visual: str, tema: str = "") -> str:
    base = briefing_visual.strip() or tema.strip() or "cena profissional relacionada a seguros"
    return f"{base}. {REGRAS}"


def generate_background(prompt: str, provider: str, api_key: str, model: str = "gpt-image-1",
                        size: str = "1024x1536", timeout: int = 180) -> bytes:
    """Devolve os bytes da imagem (PNG). Levanta RuntimeError com mensagem clara se falhar."""
    if provider != "openai":
        raise RuntimeError("Gerador de imagem não configurado (IMAGE_PROVIDER=openai e OPENAI_API_KEY no .env).")
    if not api_key:
        raise RuntimeError("Falta a OPENAI_API_KEY no .env.")
    body = json.dumps({"model": model, "prompt": prompt, "size": size, "n": 1}).encode()
    req = urllib.request.Request(OPENAI_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.load(e).get("error", {}).get("message", "")
        except Exception:
            pass
        raise RuntimeError(f"A OpenAI recusou o pedido (HTTP {e.code}): {detail[:200]}") from e
    except Exception as e:
        raise RuntimeError(f"Não consegui falar com a OpenAI: {e}") from e
    item = (data.get("data") or [{}])[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        with urllib.request.urlopen(item["url"], timeout=timeout) as r:
            return r.read()
    raise RuntimeError("A OpenAI não devolveu imagem.")
