"""JARVIS: hotword -> escuta -> Whisper -> Claude -> voz."""
from __future__ import annotations

import threading

import anthropic

from jarvis import audio
from jarvis.brain import Brain
from jarvis.config import STATE_FILE, Config
from jarvis.intro import DailyIntro
from jarvis.stt import Transcriber
from jarvis.tools import build_tools
from jarvis.tts import Speaker
from jarvis.wakeword import WakeWord

FOLLOW_UP_S = 6.0  # janela para continuar a conversa sem repetir a hotword


def main() -> None:
    cfg = Config.load()
    speak_lock = threading.Lock()

    def say(text: str) -> None:
        with speak_lock:
            speaker.say(text)

    speaker = Speaker(cfg.eleven_key, cfg.eleven_voice, cfg.eleven_model)
    tools = build_tools(cfg, notify=say)
    brain = Brain(anthropic.Anthropic(), cfg.model, tools, cfg.user_name)

    spotify = None
    if cfg.spotify_enabled and cfg.intro_spotify_uri:
        from jarvis.tools.spotify import Spotify

        spotify = Spotify()
    intro = DailyIntro(STATE_FILE, cfg.intro_audio_file, cfg.intro_spotify_uri,
                       cfg.intro_seconds, cfg.user_name, spotify)

    print("Carregando modelos...")
    stt = Transcriber(cfg.whisper_model, cfg.whisper_language, cfg.whisper_backend)
    wake = WakeWord(cfg.wakeword_model, cfg.wakeword_threshold)

    print(f"Pronto. Diga a hotword ({cfg.wakeword_model}). Ctrl+C para sair.")
    with audio.MicStream() as mic:
        while True:
            wake.wait(mic)
            timeout = None  # primeira fala após a hotword: espera sem pressa
            while True:
                if timeout is None:
                    audio.chime()  # só após a hotword; nos acompanhamentos fica em silêncio
                mic.flush()
                clip = audio.record_utterance(mic, start_timeout=timeout or 8.0)
                if clip is None:
                    break
                text = stt.transcribe(clip)
                if not text:
                    break
                print(f"VOCÊ: {text}")
                if intro.should_play():
                    intro.run(say)
                try:
                    say(brain.ask(text))
                except anthropic.APIError as e:
                    print(f"[erro API] {e}")
                    say("Perdi a conexão com o meu núcleo de raciocínio. Tente novamente em instantes.")
                    break
                timeout = FOLLOW_UP_S


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDesligando.")
