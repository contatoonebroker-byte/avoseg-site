from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = Path(os.environ.get("JARVIS_STATE_FILE", Path.home() / ".jarvis_state.json"))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # dotenv é opcional
        return
    load_dotenv(ROOT / ".env")


DEFAULT_WHISPER_PROMPT = (
    "Conversa com o assistente Jarvis, em português do Brasil. Comandos comuns: Jarvis, anota esta ideia; "
    "anota que preciso ligar para o contador; registra no diário; lembre que eu prefiro; o que eu anotei sobre frota; "
    "crie um post para a Avoseg; Avogroup; seguro de frota; apólice; indique e ganhe; Sorocaba; Instagram; "
    "temporizador; toca uma música."
)


@dataclass(frozen=True)
class Config:
    model: str
    user_name: str
    city: str
    brain_dir: str
    marketing_model: str
    image_provider: str
    openai_key: str
    openai_image_model: str
    eleven_key: str
    eleven_voice: str
    eleven_model: str
    whisper_model: str
    whisper_language: str
    whisper_backend: str
    whisper_prompt: str
    wakeword_model: str
    wakeword_threshold: float
    intro_audio_file: str
    intro_spotify_uri: str
    intro_seconds: float
    intro_lead: float
    intro_tail: float
    intro_duck: float
    intro_bed: float
    intro_after: float
    silence_s: float
    conversation_minutes: float
    follow_up_s: float
    hud_enabled: bool
    hud_host: str
    hud_port: int
    hud_auto_open: bool

    @property
    def spotify_enabled(self) -> bool:
        return bool(os.environ.get("SPOTIPY_CLIENT_ID") and os.environ.get("SPOTIPY_CLIENT_SECRET"))

    @classmethod
    def load(cls) -> "Config":
        _load_env()
        env = os.environ.get
        return cls(
            model=env("JARVIS_MODEL", "claude-opus-5-5"),
            user_name=env("JARVIS_USER_NAME", "senhor"),
            city=env("JARVIS_CITY", "Sorocaba"),
            brain_dir=env("JARVIS_BRAIN_DIR", str(Path.home() / "JarvisBrain")),
            marketing_model=env("JARVIS_MARKETING_MODEL", "claude-opus-5-5"),
            image_provider=env("IMAGE_PROVIDER", "none"),
            openai_key=env("OPENAI_API_KEY", ""),
            openai_image_model=env("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            eleven_key=env("ELEVENLABS_API_KEY", ""),
            eleven_voice=env("ELEVENLABS_VOICE_ID", ""),
            eleven_model=env("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
            whisper_model=env("WHISPER_MODEL", "small"),
            whisper_language=env("WHISPER_LANGUAGE", "pt"),
            whisper_backend=env("WHISPER_BACKEND", "auto"),
            whisper_prompt=env("WHISPER_PROMPT", DEFAULT_WHISPER_PROMPT),
            wakeword_model=env("WAKEWORD_MODEL", "hey_jarvis"),
            wakeword_threshold=float(env("WAKEWORD_THRESHOLD", "0.5")),
            intro_audio_file=env("INTRO_AUDIO_FILE", "assets/intro.mp3"),
            intro_spotify_uri=env("INTRO_SPOTIFY_URI", ""),
            intro_seconds=float(env("INTRO_SECONDS", "40")),
            intro_lead=float(env("INTRO_LEAD_SECONDS", "7")),
            intro_tail=float(env("INTRO_TAIL_SECONDS", "1")),
            intro_duck=float(env("INTRO_DUCK_LEVEL", "0.25")),
            intro_bed=float(env("INTRO_BED_LEVEL", "0.10")),
            intro_after=float(env("INTRO_AFTER_SECONDS", "10")),
            silence_s=float(env("SILENCE_SECONDS", "0.6")),
            conversation_minutes=float(env("CONVERSATION_MINUTES", "5")),
            follow_up_s=float(env("FOLLOW_UP_SECONDS", "8")),
            hud_enabled=env("HUD", "1") == "1",
            hud_host=env("HUD_HOST", "127.0.0.1"),
            hud_port=int(env("HUD_PORT", "8765")),
            hud_auto_open=env("HUD_AUTO_OPEN", "1") == "1",
        )
