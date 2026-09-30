"""Fala -> texto com faster-whisper (local)."""
from __future__ import annotations

import numpy as np


class Transcriber:
    def __init__(self, model_size: str = "small", language: str = "pt") -> None:
        from faster_whisper import WhisperModel

        self.language = language
        # device/compute_type "auto": usa GPU NVIDIA se houver, senão CPU (int8)
        self._model = WhisperModel(model_size, device="auto", compute_type="auto")

    def transcribe(self, audio: np.ndarray) -> str:
        samples = audio.astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(
            samples, language=self.language, beam_size=5, vad_filter=True,
        )
        return " ".join(s.text.strip() for s in segments).strip()
