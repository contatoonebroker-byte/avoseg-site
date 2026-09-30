"""Confere o arquivo .env sem mostrar segredos: só se cada variável existe, o tamanho e erros comuns."""
from __future__ import annotations

import difflib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

SECRETS = {"ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "OPENAI_API_KEY", "SPOTIPY_CLIENT_SECRET"}
KNOWN = [
    "ANTHROPIC_API_KEY", "JARVIS_MODEL", "JARVIS_USER_NAME", "JARVIS_CITY", "JARVIS_BRAIN_DIR", "JARVIS_MARKETING_MODEL",
    "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "ELEVENLABS_MODEL", "WHISPER_MODEL", "WHISPER_LANGUAGE",
    "WHISPER_BACKEND", "WHISPER_PROMPT", "SILENCE_SECONDS", "CONVERSATION_MINUTES", "FOLLOW_UP_SECONDS",
    "OPENAI_API_KEY", "OPENAI_IMAGE_MODEL", "IMAGE_PROVIDER", "SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET",
    "SPOTIPY_REDIRECT_URI", "HUD", "HUD_HOST", "HUD_PORT", "HUD_AUTO_OPEN", "WAKEWORD_MODEL", "WAKEWORD_THRESHOLD",
    "INTRO_AUDIO_FILE", "INTRO_SPOTIFY_URI", "INTRO_SECONDS", "INTRO_LEAD_SECONDS", "INTRO_TAIL_SECONDS",
    "INTRO_DUCK_LEVEL", "INTRO_BED_LEVEL", "INTRO_AFTER_SECONDS",
]


def mask(name: str, value: str) -> str:
    if name in SECRETS:
        return f"{len(value)} caracteres, começa com '{value[:3]}'" if value else "VAZIA"
    return value if len(value) <= 40 else value[:37] + "..."


def check(path: Path, want: tuple[str, ...] = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")) -> list[str]:
    """Devolve linhas de relatório. Não imprime valores de chaves."""
    if not path.exists():
        return [f"✗ Não achei o arquivo {path}. Rode: cp .env.example .env"]
    found: dict[str, str] = {}
    out: list[str] = []
    for n, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            m = re.match(r"#\s*([A-Z][A-Z0-9_]+)\s*=", line)
            if m and m.group(1) in want:
                out.append(f"! Linha {n}: {m.group(1)} está COMENTADA (começa com #). Apague o # do começo.")
            continue
        m = re.match(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_ ]*?)\s*(=)\s*(.*)$", line)
        if not m:
            out.append(f"! Linha {n}: não entendi (falta o '='): {line[:20]}...")
            continue
        name, value = m.group(1).strip(), m.group(3).strip()
        if name != name.upper():
            out.append(f"! Linha {n}: o nome '{name}' deve ficar em MAIÚSCULAS.")
        name = name.upper()
        if re.search(r"\s", m.group(1).strip()):
            out.append(f"! Linha {n}: há espaço dentro do nome da variável.")
        if name in found:
            out.append(f"! {name} aparece mais de uma vez (vale a última, linha {n}).")
        if value[:1] in "\"'" and value[-1:] in "\"'" and len(value) > 1:
            out.append(f"! Linha {n}: {name} está entre aspas. Funciona, mas o mais seguro é sem aspas.")
            value = value[1:-1]
        found[name] = value
        if name not in KNOWN:
            close = difflib.get_close_matches(name, KNOWN, n=1, cutoff=0.75)
            if close:
                out.append(f"✗ Linha {n}: '{name}' não existe. Você quis dizer {close[0]}?")
    for name in want:
        if name not in found:
            close = [k for k in found if difflib.SequenceMatcher(None, k, name).ratio() > 0.75]
            dica = f" (achei '{close[0]}', que não é o mesmo nome)" if close else ""
            out.append(f"✗ {name} NÃO está no .env{dica}. Acrescente a linha {name}=valor no final do arquivo.")
        elif not found[name]:
            out.append(f"✗ {name} está no arquivo, mas VAZIA. Cole o valor logo depois do '='.")
        else:
            out.append(f"✓ {name}: {mask(name, found[name])}")
            if name.endswith("_API_KEY") and re.search(r"\s", found[name]):
                out.append(f"! {name} tem espaço no meio do valor: confira se colou a chave inteira e só ela.")
    return out


def test_openai(key: str, model: str = "gpt-image-1", opener=urllib.request.urlopen) -> list[str]:
    """Verifica a chave e o acesso ao modelo de imagem SEM gerar imagem (não tem custo)."""
    out = []
    for path, label in (("/v1/models", "chave da OpenAI"), (f"/v1/models/{model}", f"acesso ao modelo {model}")):
        req = urllib.request.Request("https://api.openai.com" + path, headers={"Authorization": f"Bearer {key}"})
        try:
            opener(req, timeout=20)
            out.append(f"✓ {label}: ok")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.load(e).get("error", {}).get("message", "")
            except Exception:
                pass
            out.append(f"✗ {label}: HTTP {e.code} {detail[:180]}")
        except Exception as e:
            out.append(f"✗ {label}: sem conexão com a OpenAI ({e})")
    return out
