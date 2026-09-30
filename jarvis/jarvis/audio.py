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


class Endpointer:
    """Decide quando o usuário começou e terminou de falar (por energia).

    Calibra o ruído de fundo nos primeiros blocos e usa um limiar acima dele.
    """

    def __init__(self, silence_s: float = 0.9, min_threshold: float = 250.0,
                 calibration_blocks: int = 4) -> None:
        self.silence_blocks = int(silence_s * SAMPLE_RATE / BLOCK)
        self.min_threshold = min_threshold
        self._calib_left = calibration_blocks
        self._noise: list[float] = []
        self.threshold = min_threshold
        self.speaking = False
        self._quiet = 0

    def feed(self, block: np.ndarray) -> bool:
        """Devolve True quando a fala terminou."""
        level = rms(block)
        if self._calib_left > 0:
            self._calib_left -= 1
            self._noise.append(level)
            if self._calib_left == 0:
                self.threshold = max(self.min_threshold, float(np.mean(self._noise)) * 3)
            return False
        if level >= self.threshold:
            self.speaking = True
            self._quiet = 0
        elif self.speaking:
            self._quiet += 1
            return self._quiet >= self.silence_blocks
        return False


def record_utterance(mic: MicStream, start_timeout: float | None = None,
                     max_seconds: float = 20.0) -> np.ndarray | None:
    """Grava até o usuário parar de falar. None se ninguém falar dentro do prazo."""
    ep = Endpointer()
    preroll: list[np.ndarray] = []
    frames: list[np.ndarray] = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < max_seconds:
        block = mic.read()
        if block is None:
            continue
        done = ep.feed(block)
        if ep.speaking:
            frames.append(block)
        else:
            preroll = (preroll + [block])[-4:]
            if start_timeout is not None and time.monotonic() - t0 > start_timeout:
                return None
        if ep.speaking and len(frames) == 1:
            frames = preroll + frames
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
