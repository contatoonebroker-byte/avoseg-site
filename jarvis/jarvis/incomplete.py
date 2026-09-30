"""Detecta quando uma frase parece ter sido cortada no meio (para esperar a continuação)."""
from __future__ import annotations

import re

from .secondbrain.store import norm

# palavras que quase nunca terminam uma frase em português
CONECTIVOS = {
    "que", "de", "do", "da", "dos", "das", "para", "pra", "pro", "com", "sem", "sobre", "e", "ou", "mas", "a", "o",
    "as", "os", "um", "uma", "uns", "umas", "no", "na", "nos", "nas", "em", "por", "pelo", "pela", "como", "se",
    "entao", "tipo", "meu", "minha", "meus", "minhas", "seu", "sua", "nosso", "nossa", "ao", "aos", "ate", "entre",
    "quando", "onde", "qual", "porque", "tambem", "depois", "antes",
}
# verbos de comando que precisam de complemento ("anota" sozinho não diz o quê)
VERBOS_COMANDO = {
    "anota", "anote", "anotar", "registra", "registre", "registrar", "lembra", "lembre", "lembrar", "guarda", "guarde",
    "crie", "cria", "criar", "faca", "faz", "escreve", "escreva", "monte", "monta", "me", "manda", "mande", "busca",
    "busque", "procura", "procure", "mostre", "mostra", "abre", "abra", "toca", "toque", "coloca", "coloque",
}


def looks_incomplete(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    if re.search(r"[,:;…\-–]\s*$", text) or text.endswith("..."):
        return True
    words = re.findall(r"[a-z0-9]+", norm(text))
    if not words:
        return False
    if words[-1] in CONECTIVOS:
        return True
    return len(words) <= 2 and words[0] in VERBOS_COMANDO
