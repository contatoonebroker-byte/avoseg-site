"""Introdução do primeiro comando do dia: música + saudação."""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np

from .audio import play


class DailyIntro:
    def __init__(self, state_file: Path, audio_file: str = "", spotify_uri: str = "",
                 seconds: float = 15.0, user_name: str = "senhor", spotify=None) -> None:
        self.state_file = Path(state_file)
        self.audio_file = audio_file
        self.spotify_uri = spotify_uri
        self.seconds = seconds
        self.user_name = user_name
        self.spotify = spotify  # objeto com play_uri()/pause(), opcional

    # --- controle de "já tocou hoje?" ---
    def _last_date(self) -> str | None:
        try:
            return json.loads(self.state_file.read_text()).get("last_intro_date")
        except (OSError, ValueError):
            return None

    def should_play(self, today: date | None = None) -> bool:
        return self._last_date() != (today or date.today()).isoformat()

    def mark_played(self, today: date | None = None) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps({"last_intro_date": (today or date.today()).isoformat()})
        )

    # --- conteúdo ---
    def greeting(self, now: datetime | None = None) -> str:
        hour = (now or datetime.now()).hour
        period = "Bom dia" if hour < 12 else "Boa tarde" if hour < 18 else "Boa noite"
        return f"{period}, {self.user_name}. Todos os sistemas estão online. Como posso ajudar?"

    def play_music(self) -> None:
        if self.spotify_uri and self.spotify is not None:
            self.spotify.play_uri(self.spotify_uri)
            time.sleep(self.seconds)
            self.spotify.pause()
            return
        path = Path(self.audio_file)
        if not path.is_file():
            return  # sem música configurada: segue só com a saudação
        import soundfile as sf

        data, rate = sf.read(str(path), dtype="float32", always_2d=True)
        data = data[: int(self.seconds * rate)]
        fade = min(len(data), int(rate * 2))
        data[-fade:] *= np.linspace(1, 0, fade)[:, None]
        play(data, rate)

    def run(self, speak) -> None:
        """Toca a música, fala a saudação e registra que o dia já teve introdução."""
        self.mark_played()
        try:
            self.play_music()
        finally:
            speak(self.greeting())
