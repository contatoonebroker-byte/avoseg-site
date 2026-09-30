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

    def __init__(self, data: np.ndarray, rate: int, volume: float = 0.9, on_level=None) -> None:
        from .beat import BeatAnalyzer

        self.data, self.rate = data, rate
        self.on_level = on_level  # recebe {"bands", "bass", "beat"} ~30x/s
        self._beat = BeatAnalyzer(rate)
        self._last_level = 0.0
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
        if self.on_level is not None:  # analisa a música original: o holograma pulsa mesmo com volume baixo
            now = time.monotonic()
            if now - self._last_level >= 0.033:
                self._last_level = now
                out = self._beat.process(chunk, now)
                if out:
                    self.on_level(out)
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
                 lead: float = 7.0, tail: float = 1.0, duck: float = 0.25,
                 bed: float = 0.10, after: float = 10.0, speech_level: float = 0.03,
                 on_level=None, sleep=time.sleep) -> None:
        self.state_file = Path(state_file)
        self.audio_file = audio_file
        self.spotify_uri = spotify_uri
        self.seconds = seconds  # duração máxima do trecho de música
        self.user_name = user_name
        self.spotify = spotify
        self.lead, self.tail, self.duck = lead, tail, duck
        self.bed, self.after, self.speech_level = bed, after, speech_level
        self.on_level = on_level
        self._sleep = sleep
        self._player = None
        self._timer: threading.Timer | None = None

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
        player = MusicPlayer(data[: int(self.seconds * rate)], rate, on_level=self.on_level)
        player.start()
        return player

    @property
    def bed_active(self) -> bool:
        return self._player is not None

    def run(self, speak, on_ending=None) -> None:
        """Música entra, abaixa para a saudação e passa a tocar baixinho ao fundo.

        `on_ending` (ex.: bipe de "estou ouvindo") é chamado logo depois da saudação; a música
        segue em volume de fundo por `after` segundos e só então some com fade-out.
        """
        self.mark_played()
        player = self._player = self._start_music()
        try:
            if player:
                self._sleep(self.lead)
                player.set_volume(self.duck, 1.2)
            speak(self.greeting())
            if player:
                self._sleep(self.tail)
        except BaseException:
            self.end_music()
            raise
        if player:
            player.set_volume(self.bed, 1.0)
            self._timer = threading.Timer(self.after, self.end_music)
            self._timer.daemon = True
            self._timer.start()
        if on_ending:
            on_ending()

    def speech_started(self) -> None:
        """Você começou a falar: a música quase some para não atrapalhar a escuta."""
        if self._player:
            self._player.set_volume(self.speech_level, 0.25)

    def speech_ended(self) -> None:
        """Você terminou de falar: a música volta ao volume de fundo."""
        if self._player:
            self._player.set_volume(self.bed, 1.0)

    def end_music(self) -> None:
        """Encerra a música com fade-out (sem bloquear)."""
        player, self._player = self._player, None
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if player:
            player.fade_out(2.5, block=False)
