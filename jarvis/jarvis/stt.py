"""Fala -> texto, tudo local.

- Mac com Apple Silicon: mlx-whisper (usa o chip M1/M2/M3, bem mais rápido)
- Demais: faster-whisper (usa GPU NVIDIA se houver, senão CPU)
"""
from __future__ import annotations

import platform
import re
import sys

import numpy as np

from .secondbrain.store import norm

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
                 backend: str = "auto", prompt: str = "") -> None:
        self.language = language
        self.prompt = prompt.strip()  # vocabulário do dia a dia: ajuda o Whisper em palavras curtas como "anota"
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

    def _clean(self, text: str) -> str:
        """Descarta o texto se for só um pedaço do próprio vocabulário (o Whisper às vezes
        "repete" o prompt quando ouve ruído)."""
        text = text.strip()
        flat = re.sub(r"[^a-z0-9 ]", "", norm(text))
        if flat and self.prompt and flat in re.sub(r"[^a-z0-9 ]", "", norm(self.prompt)):
            return ""
        return text

    def transcribe(self, audio: np.ndarray) -> str:
        samples = audio.astype(np.float32) / 32768.0
        extra = {"initial_prompt": self.prompt} if self.prompt else {}
        if self.backend == "mlx":
            out = self._mlx.transcribe(samples, path_or_hf_repo=self._repo,
                                       language=self.language, **extra)
            return self._clean(out["text"])
        segments, _ = self._model.transcribe(
            samples, language=self.language, beam_size=5, vad_filter=True, **extra,
        )
        return self._clean(" ".join(s.text.strip() for s in segments))
