"""Hotword offline com openWakeWord (modelo pré-treinado 'hey_jarvis')."""
from __future__ import annotations

from .audio import MicStream


class WakeWord:
    def __init__(self, model_name: str = "hey_jarvis", threshold: float = 0.5) -> None:
        import openwakeword
        from openwakeword.model import Model

        openwakeword.utils.download_models([model_name])  # só baixa se faltar
        self.name = model_name
        self.threshold = threshold
        self._model = Model(wakeword_models=[model_name], inference_framework="onnx")

    def wait(self, mic: MicStream) -> None:
        """Bloqueia até ouvir a hotword."""
        self._model.reset()
        while True:
            block = mic.read()
            if block is None:
                continue
            scores = self._model.predict(block)
            if max(scores.values(), default=0.0) >= self.threshold:
                return
