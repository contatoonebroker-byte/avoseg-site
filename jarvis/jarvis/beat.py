"""Análise em tempo real da música: espectro em bandas e detecção de batida."""
from __future__ import annotations

import time

import numpy as np

BANDS = 32


class BeatAnalyzer:
    def __init__(self, rate: int) -> None:
        self.rate = rate
        self._peak = np.full(BANDS, 1e-6)
        self._bass_avg = 0.0
        self._bass_peak = 1e-6
        self._last_beat = 0.0
        self._n = 0
        self._masks: list[np.ndarray] = []
        self._window = np.ones(1)

    def _prepare(self, n: int) -> None:
        freqs = np.fft.rfftfreq(n, 1.0 / self.rate)
        edges = np.geomspace(40, min(12000, self.rate / 2 * 0.95), BANDS + 1)
        idx = np.digitize(freqs, edges) - 1
        self._masks = [np.where(idx == b)[0] for b in range(BANDS)]
        self._window = np.hanning(n)
        self._n = n

    def process(self, samples: np.ndarray, now: float | None = None) -> dict | None:
        """samples: float32 (n,) ou (n, canais). Devolve bandas 0-1, grave 0-1 e se houve batida."""
        mono = samples.mean(axis=1) if samples.ndim == 2 else samples
        mono = mono[:2048]
        if len(mono) < 256:
            return None
        if len(mono) != self._n:
            self._prepare(len(mono))
        now = time.monotonic() if now is None else now
        spec = np.abs(np.fft.rfft(mono * self._window))
        bands = np.array([spec[m].mean() if len(m) else 0.0 for m in self._masks])
        self._peak = np.maximum(self._peak * 0.998, bands)
        norm = np.sqrt(np.clip(bands / (self._peak + 1e-9), 0, 1))

        bass = float(bands[:4].sum())
        self._bass_peak = max(self._bass_peak * 0.998, bass)
        beat = (bass > 1.35 * self._bass_avg and bass > 0.25 * self._bass_peak
                and now - self._last_beat > 0.22)
        if beat:
            self._last_beat = now
        self._bass_avg = 0.9 * self._bass_avg + 0.1 * bass
        return {"bands": [round(float(x), 2) for x in norm],
                "bass": round(min(1.0, bass / self._bass_peak), 2), "beat": bool(beat)}
