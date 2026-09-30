"""Introdução do primeiro comando do dia: música entra, abaixa para a voz, some no fim."""
from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np


class MusicPlayer:
    """Toca um arquivo em segundo plano com volume ajustável (rampa suave)."""

    def __init__(self, data: np.ndarray, rate: int, volume: float = 0.9) -> None:
        self.data, self.rate = data, rate
        self.pos = 0
        self.gain = self.target = volume
        self.slew = 1.0  # variação de ganho por segundo
        self.done = threading.Event()
        self._stream = None

    def set_volume(self, level: float, seconds: float = 1.0) -> None:
        self.slew = abs(level - self.gain) / max(seconds, 0.01)
        self.target = level

    def fill(self, frames: int) -> np.ndarray:
        """Próximo bloco de áudio já com o envelope de volume aplicado."""
        chunk = self.data[self.pos:self.pos + frames]
        n = len(chunk)
        self.pos += n
        if n == 0:
            return chunk
        step = self.slew * n / self.rate
        g0 = self.gain
        g1 = min(self.target, g0 + step) if self.target > g0 else max(self.target, g0 - step)
        self.gain = g1
        return chunk * np.linspace(g0, g1, n, dtype=np.float32)[:, None]

    def _callback(self, outdata, frames, time_info, status) -> None:
        import sounddevice as sd

        chunk = self.fill(frames)
        n = len(chunk)
        outdata[:n] = chunk
        if n < frames:
            outdata[n:] = 0
            raise sd.CallbackStop
        if self.target == 0 and self.gain <= 0.001:
            raise sd.CallbackStop

    def start(self) -> None:
        import sounddevice as sd

        self._stream = sd.OutputStream(
            samplerate=self.rate, channels=self.data.shape[1], dtype="float32",
            callback=self._callback, finished_callback=self.done.set,
        )
        self._stream.start()

    def fade_out(self, seconds: float = 2.5, block: bool = True) -> None:
        self.set_volume(0.0, seconds)

        def finish() -> None:
            self.done.wait(seconds + 1.0)
            self.stop()

        if block:
            finish()
        else:  # o fade segue sozinho; quem chamou já pode continuar (ex.: bipe)
            threading.Thread(target=finish, daemon=True).start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class SpotifyMusic:
    """Mesma interface do MusicPlayer, mas controlando o Spotify."""

    def __init__(self, spotify, uri: str) -> None:
        self.sp = spotify
        self.base = spotify.get_volume()
        spotify.play_uri(uri)

    def set_volume(self, level: float, seconds: float = 1.0) -> None:
        self.sp.set_volume(int(self.base * level))

    def fade_out(self, seconds: float = 2.5, block: bool = True) -> None:
        self.sp.pause()
        self.sp.set_volume(self.base)


class DailyIntro:
    def __init__(self, state_file: Path, audio_file: str = "", spotify_uri: str = "",
                 seconds: float = 40.0, user_name: str = "senhor", spotify=None,
                 lead: float = 7.0, tail: float = 5.0, duck: float = 0.25,
                 sleep=time.sleep) -> None:
        self.state_file = Path(state_file)
        self.audio_file = audio_file
        self.spotify_uri = spotify_uri
        self.seconds = seconds  # duração máxima do trecho de música
        self.user_name = user_name
        self.spotify = spotify
        self.lead, self.tail, self.duck = lead, tail, duck
        self._sleep = sleep

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

    def _start_music(self):
        if self.spotify_uri and self.spotify is not None:
            return SpotifyMusic(self.spotify, self.spotify_uri)
        path = Path(self.audio_file)
        if not path.is_file():
            return None  # sem música configurada: segue só com a saudação
        import soundfile as sf

        data, rate = sf.read(str(path), dtype="float32", always_2d=True)
        player = MusicPlayer(data[: int(self.seconds * rate)], rate)
        player.start()
        return player

    def run(self, speak, on_ending=None) -> None:
        """Música entra, abaixa para a saudação, continua ao fundo e some suavemente.

        `on_ending` é chamado assim que o fade-out começa (ex.: bipe de "estou ouvindo"),
        sem esperar a música acabar.
        """
        self.mark_played()
        player = self._start_music()
        try:
            if player:
                self._sleep(self.lead)
                player.set_volume(self.duck, 1.2)
            speak(self.greeting())
            if player:
                self._sleep(self.tail)
        finally:
            if player:
                player.fade_out(2.5, block=False)
        if on_ending:
            on_ending()
