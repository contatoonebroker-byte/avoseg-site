"""Microfone, detecção de fim de fala e reprodução de áudio."""
from __future__ import annotations

import queue
import time

import numpy as np

SAMPLE_RATE = 16000
BLOCK = 1280  # 80 ms, tamanho esperado pelo openWakeWord


class MicStream:
    """Fluxo contínuo do microfone: 16 kHz, mono, int16, blocos de 80 ms."""

    def __init__(self) -> None:
        import sounddevice as sd

        self._q: queue.Queue[np.ndarray] = queue.Queue()
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            blocksize=BLOCK, callback=self._on_audio,
        )

    def _on_audio(self, indata, frames, time_info, status) -> None:
        self._q.put(indata[:, 0].copy())

    def __enter__(self) -> "MicStream":
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stream.stop()
        self._stream.close()

    def read(self, timeout: float = 1.0) -> np.ndarray | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush(self) -> None:
        """Descarta o que foi captado enquanto o Jarvis falava."""
        while not self._q.empty():
            self._q.get_nowait()


def rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))


class NoiseTracker:
    """Estima o ruído de fundo enquanto o Jarvis espera a hotword (ninguém falando).

    Assim o detector de fala não precisa se calibrar depois do bipe, quando você
    já pode estar falando.
    """

    def __init__(self, initial: float = 100.0) -> None:
        self.value = initial

    def update(self, block: np.ndarray) -> None:
        level = rms(block)
        if level < self.value * 2.5 + 50:  # ignora picos (fala, batidas)
            self.value = 0.98 * self.value + 0.02 * level


class Endpointer:
    """Decide quando o usuário começou e terminou de falar (por energia).

    Com `noise` conhecido o limiar já vale desde o primeiro bloco. Sem ele,
    calibra o ruído de fundo nos primeiros blocos.
    """

    def __init__(self, silence_s: float = 0.8, min_threshold: float = 300.0,
                 calibration_blocks: int = 4, noise: float | None = None) -> None:
        self.silence_blocks = max(1, int(silence_s * SAMPLE_RATE / BLOCK))
        self.min_threshold = min_threshold
        self._noise: list[float] = []
        if noise is None:
            self._calib_left = calibration_blocks
            self.threshold = min_threshold
        else:
            self._calib_left = 0
            self.threshold = max(min_threshold, noise * 3.5)
        self.speaking = False
        self._quiet = 0

    @property
    def off_threshold(self) -> float:
        """Histerese: depois que começou a fala, só conta como silêncio abaixo de ~60% do limiar.
        Assim o final fraco das palavras não corta a frase."""
        return self.threshold * 0.6

    def feed(self, block: np.ndarray) -> bool:
        """Devolve True quando a fala terminou."""
        level = rms(block)
        if self._calib_left > 0:
            self._calib_left -= 1
            self._noise.append(level)
            if self._calib_left == 0:
                self.threshold = max(self.min_threshold, float(np.mean(self._noise)) * 3)
            return False
        if level >= self.threshold or (self.speaking and level >= self.off_threshold):
            self.speaking = True
            self._quiet = 0
        elif self.speaking:
            self._quiet += 1
            return self._quiet >= self.silence_blocks
        return False


def record_utterance(mic: MicStream, start_timeout: float | None = None,
                     max_seconds: float = 45.0, noise: float | None = None,
                     silence_s: float = 0.8, min_threshold: float = 300.0,
                     on_speech=None, on_quiet=None) -> np.ndarray | None:
    """Grava até o usuário parar de falar. None se ninguém falar dentro do prazo.

    `on_speech` é chamado uma vez, assim que a fala começa (ex.: abaixar a música).
    `on_quiet` recebe cada bloco sem fala (para acompanhar o ruído de fundo).
    """
    ep = Endpointer(silence_s, min_threshold, noise=noise)
    preroll: list[np.ndarray] = []
    frames: list[np.ndarray] = []
    t0 = time.monotonic()
    started = False
    while time.monotonic() - t0 < max_seconds:
        block = mic.read()
        if block is None:
            continue
        done = ep.feed(block)
        if ep.speaking:
            frames.append(block)
            if not started:
                started = True
                frames = preroll + frames
                if on_speech:
                    on_speech()
        else:
            preroll = (preroll + [block])[-6:]
            if on_quiet:
                on_quiet(block)
            if start_timeout is not None and time.monotonic() - t0 > start_timeout:
                return None
        if done:
            break
    return np.concatenate(frames) if frames else None


def play(samples: np.ndarray, sample_rate: int, blocking: bool = True) -> None:
    import sounddevice as sd

    sd.play(samples, sample_rate)
    if blocking:
        sd.wait()


def chime() -> None:
    """Bipe curto e discreto que indica 'estou ouvindo'."""
    t = np.linspace(0, 0.12, int(0.12 * 24000), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 880 * t) * np.linspace(1, 0, t.size)
    play((tone * 32767).astype(np.int16), 24000)
