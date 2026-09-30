"""Texto -> voz com ElevenLabs (streaming PCM).

Se o ElevenLabs não estiver configurado ou falhar, usa a voz do macOS (`say`)
como reserva, para o assistente nunca ficar mudo nem travar.
"""
from __future__ import annotations

import subprocess
import sys

import numpy as np

from .audio import play

PCM_RATE = 24000
FALLBACK_VOICE = "Luciana"  # português do Brasil


class Speaker:
    def __init__(self, api_key: str, voice_id: str, model_id: str) -> None:
        self.voice_id = voice_id
        self.model_id = model_id
        self._client = None
        self._warned = False
        if api_key and voice_id:
            from elevenlabs.client import ElevenLabs

            self._client = ElevenLabs(api_key=api_key)
        else:
            print("[tts] ELEVENLABS_API_KEY/ELEVENLABS_VOICE_ID ausentes: usando a voz do sistema.")

    def _fallback(self, text: str) -> None:
        if sys.platform == "darwin":
            subprocess.run(["say", "-v", FALLBACK_VOICE, text], check=False)

    @staticmethod
    def _reason(e: Exception) -> str:
        body = getattr(e, "body", None)
        detail = body.get("detail") if isinstance(body, dict) else None
        if isinstance(detail, dict) and detail.get("message"):
            return f"{getattr(e, 'status_code', '')} {detail['message']}".strip()
        return str(e)[:200]

    def say(self, text: str) -> None:
        print(f"JARVIS: {text}")
        if not text:
            return
        if not self._client:
            self._fallback(text)
            return
        try:
            chunks = self._client.text_to_speech.convert(
                voice_id=self.voice_id, text=text, model_id=self.model_id,
                output_format=f"pcm_{PCM_RATE}",
            )
            pcm = b"".join(chunks)
            if len(pcm) % 2:
                pcm = pcm[:-1]
            play(np.frombuffer(pcm, dtype=np.int16), PCM_RATE)
        except Exception as e:  # rede, plano, chave, cota...
            if not self._warned:
                print(f"[tts] ElevenLabs falhou ({self._reason(e)}). Usando a voz do sistema.")
                self._warned = True
            self._fallback(text)
