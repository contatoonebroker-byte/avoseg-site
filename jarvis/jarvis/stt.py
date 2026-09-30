"""Fala -> texto, tudo local.

- Mac com Apple Silicon: mlx-whisper (usa o chip M1/M2/M3, bem mais rápido)
- Demais: faster-whisper (usa GPU NVIDIA se houver, senão CPU)
"""
from __future__ import annotations

import platform
import sys

import numpy as np

MLX_MODELS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
}


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def mlx_repo(model_size: str) -> str:
    return MLX_MODELS.get(model_size, model_size)  # aceita também um repo HF completo


class Transcriber:
    def __init__(self, model_size: str = "small", language: str = "pt",
                 backend: str = "auto") -> None:
        self.language = language
        if backend == "auto":
            backend = "mlx" if is_apple_silicon() else "faster"
        self.backend = backend
        if backend == "mlx":
            import mlx_whisper

            self._mlx = mlx_whisper
            self._repo = mlx_repo(model_size)
            # aquece o modelo (baixa na primeira vez) para o 1º comando não demorar
            self._mlx.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo=self._repo)
        else:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(model_size, device="auto", compute_type="auto")

    def transcribe(self, audio: np.ndarray) -> str:
        samples = audio.astype(np.float32) / 32768.0
        if self.backend == "mlx":
            out = self._mlx.transcribe(samples, path_or_hf_repo=self._repo,
                                       language=self.language)
            return out["text"].strip()
        segments, _ = self._model.transcribe(
            samples, language=self.language, beam_size=5, vad_filter=True,
        )
        return " ".join(s.text.strip() for s in segments).strip()
