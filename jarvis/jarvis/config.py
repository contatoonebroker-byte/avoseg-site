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


@dataclass(frozen=True)
class Config:
    model: str
    user_name: str
    eleven_key: str
    eleven_voice: str
    eleven_model: str
    whisper_model: str
    whisper_language: str
    whisper_backend: str
    wakeword_model: str
    wakeword_threshold: float
    intro_audio_file: str
    intro_spotify_uri: str
    intro_seconds: float

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
            eleven_key=env("ELEVENLABS_API_KEY", ""),
            eleven_voice=env("ELEVENLABS_VOICE_ID", ""),
            eleven_model=env("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
            whisper_model=env("WHISPER_MODEL", "small"),
            whisper_language=env("WHISPER_LANGUAGE", "pt"),
            whisper_backend=env("WHISPER_BACKEND", "auto"),
            wakeword_model=env("WAKEWORD_MODEL", "hey_jarvis"),
            wakeword_threshold=float(env("WAKEWORD_THRESHOLD", "0.5")),
            intro_audio_file=env("INTRO_AUDIO_FILE", "assets/intro.mp3"),
            intro_spotify_uri=env("INTRO_SPOTIFY_URI", ""),
            intro_seconds=float(env("INTRO_SECONDS", "15")),
        )
