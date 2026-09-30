"""Reconhece o nome "Jarvis" numa transcrição (o Whisper às vezes escreve Jarbas, Garvis...)."""
from __future__ import annotations

import difflib
import re
import unicodedata

NAME = "jarvis"
ALIASES = {"jarvis", "jarves", "jarvi", "jarvs", "jarviz", "garvis", "gervis", "jarbas", "jarbis",
           "yarvis", "darvis", "charvis", "jarvez"}
GREETINGS = {"hey", "ei", "ey", "oi", "ola", "ok", "opa", "e"}


def _norm(word: str) -> str:
    word = unicodedata.normalize("NFKD", word.lower())
    return re.sub(r"[^a-z]", "", "".join(c for c in word if not unicodedata.combining(c)))


def find_name(text: str) -> str | None:
    """Se o nome aparece, devolve o resto do comando ("" se só chamaram pelo nome). Senão, None."""
    words = text.split()
    for i, w in enumerate(words):
        n = _norm(w)
        if len(n) >= 4 and (n in ALIASES or difflib.SequenceMatcher(None, n, NAME).ratio() >= 0.8):
            rest = words[:i] + words[i + 1:]
            if i > 0 and _norm(words[i - 1]) in GREETINGS:  # "hey Jarvis", "ei, Jarvis"
                rest.pop(i - 1)
            return " ".join(rest).strip(" ,.!?;:-")
    return None
