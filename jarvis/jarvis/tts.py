"""Texto -> voz com ElevenLabs (áudio em streaming, começa a tocar no primeiro pedaço).

Se o ElevenLabs não estiver configurado ou falhar, usa a voz do macOS (`say`)
como reserva, para o assistente nunca ficar mudo nem travar.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading

PCM_RATE = 24000
PREBUFFER_BYTES = 6000  # ~125 ms de áudio antes de começar, para não picotar
FALLBACK_VOICE = "Luciana"  # português do Brasil


class Clip:
    """Uma frase a ser falada; o áudio chega pedaço a pedaço em `q` (None = fim)."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.q: queue.Queue = queue.Queue()
        self.error: Exception | None = None
        self.fetching = False


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

    # --- reserva: voz do macOS ---
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

    # --- pipeline: baixar (em segundo plano) e tocar ---
    def prepare(self, text: str) -> Clip:
        """Começa a baixar o áudio já, sem esperar a vez de tocar (a próxima frase fica pronta)."""
        clip = Clip(text)
        if self._client and text:
            clip.fetching = True
            threading.Thread(target=self._fetch, args=(clip,), daemon=True).start()
        return clip

    def _fetch(self, clip: Clip) -> None:
        try:
            for chunk in self._client.text_to_speech.convert(
                voice_id=self.voice_id, text=clip.text, model_id=self.model_id,
                output_format=f"pcm_{PCM_RATE}",
            ):
                if chunk:
                    clip.q.put(chunk)
        except Exception as e:  # rede, plano, chave, cota...
            clip.error = e
        finally:
            clip.q.put(None)

    def _play_stream(self, clip: Clip) -> bool:
        """Toca os pedaços conforme chegam. Devolve True se chegou a tocar algo."""
        stream, buf = None, b""

        def write(data: bytes) -> bytes:
            nonlocal stream
            if stream is None:
                import sounddevice as sd

                stream = sd.RawOutputStream(samplerate=PCM_RATE, channels=1, dtype="int16")
                stream.start()
            usable = len(data) - len(data) % 2
            stream.write(data[:usable])
            return data[usable:]

        try:
            while True:
                chunk = clip.q.get()
                if chunk is None:
                    break
                buf += chunk
                if stream is not None or len(buf) >= PREBUFFER_BYTES:
                    buf = write(buf)
            if len(buf) >= 2:
                write(buf)
            return stream is not None
        finally:
            if stream is not None:
                stream.stop()  # espera terminar de tocar o que já foi enviado
                stream.close()

    def play(self, clip: Clip) -> None:
        print(f"JARVIS: {clip.text}")
        if not clip.text:
            return
        if not clip.fetching:
            self._fallback(clip.text)
            return
        played = self._play_stream(clip)
        if clip.error is not None:
            if not self._warned:
                print(f"[tts] ElevenLabs falhou ({self._reason(clip.error)}). Usando a voz do sistema.")
                self._warned = True
            if not played:
                self._fallback(clip.text)

    def say(self, text: str) -> None:
        self.play(self.prepare(text))


class SpeechQueue:
    """Fala as frases em ordem numa thread própria, enquanto o Claude ainda está respondendo.

    O áudio de cada frase começa a ser baixado assim que ela chega (`put`), então enquanto uma
    toca a seguinte já está pronta.
    """

    def __init__(self, speaker, on_start=None, lock=None) -> None:
        self._speaker = speaker
        self._on_start = on_start
        self._lock = lock or threading.Lock()
        self._q: queue.Queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while True:
            clip = self._q.get()
            try:
                with self._lock:
                    if self._on_start:
                        self._on_start(getattr(clip, "text", clip))
                    self._speaker.play(clip)
            except Exception as e:
                print(f"[fala] {e}")
            finally:
                self._q.task_done()

    def put(self, text: str) -> None:
        self._q.put(self._speaker.prepare(text))

    def wait(self) -> None:
        self._q.join()
