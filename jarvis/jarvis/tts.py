"""Texto -> voz com ElevenLabs (streaming PCM). Sem chave, apenas imprime."""
from __future__ import annotations

import numpy as np

from .audio import play

PCM_RATE = 24000


class Speaker:
    def __init__(self, api_key: str, voice_id: str, model_id: str) -> None:
        self.voice_id = voice_id
        self.model_id = model_id
        self._client = None
        if api_key and voice_id:
            from elevenlabs.client import ElevenLabs

            self._client = ElevenLabs(api_key=api_key)
        else:
            print("[tts] ELEVENLABS_API_KEY/ELEVENLABS_VOICE_ID ausentes: só texto.")

    def say(self, text: str) -> None:
        print(f"JARVIS: {text}")
        if not self._client or not text:
            return
        chunks = self._client.text_to_speech.convert(
            voice_id=self.voice_id, text=text, model_id=self.model_id,
            output_format=f"pcm_{PCM_RATE}",
        )
        pcm = b"".join(chunks)
        if len(pcm) % 2:
            pcm = pcm[:-1]
        play(np.frombuffer(pcm, dtype=np.int16), PCM_RATE)
