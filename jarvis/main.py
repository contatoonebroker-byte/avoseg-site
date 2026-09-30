"""JARVIS: hotword -> escuta -> Whisper -> Claude -> voz."""
from __future__ import annotations

import threading
import webbrowser

import anthropic

from jarvis import audio
from jarvis.brain import Brain
from jarvis.config import STATE_FILE, Config
from jarvis.hud import Hud
from jarvis.intro import DailyIntro
from jarvis.stt import Transcriber
from jarvis.tools import build_tools
from jarvis.tts import Speaker
from jarvis.widgets import Widgets
from jarvis.wakeword import WakeWord

FOLLOW_UP_S = 6.0  # janela para continuar a conversa sem repetir a hotword


def main() -> None:
    cfg = Config.load()
    speak_lock = threading.Lock()

    hud = Hud(cfg.hud_host, cfg.hud_port)

    def say(text: str) -> None:
        with speak_lock:
            hud.emit("speaking", text=text)
            speaker.say(text)

    speaker = Speaker(cfg.eleven_key, cfg.eleven_voice, cfg.eleven_model)
    spotify = None
    if cfg.spotify_enabled:
        from jarvis.tools.spotify import Spotify

        spotify = Spotify()
    tools = build_tools(cfg, notify=say, publish=lambda t: hud.publish("timers", t), spotify=spotify)
    brain = Brain(anthropic.Anthropic(), cfg.model, tools, cfg.user_name, cfg.city)

    spotify_intro = spotify if cfg.intro_spotify_uri else None
    intro = DailyIntro(STATE_FILE, cfg.intro_audio_file, cfg.intro_spotify_uri,
                       cfg.intro_seconds, cfg.user_name, spotify_intro,
                       cfg.intro_lead, cfg.intro_tail, cfg.intro_duck)

    if cfg.hud_enabled:
        print(f"HUD em {hud.start()}")
        if hud.lan_url():
            print(f"No tablet, abra: {hud.lan_url()}")
        Widgets(hud, cfg.city, spotify).start()
        if cfg.hud_auto_open:
            webbrowser.open(hud.url)

    print("Carregando modelos...")
    stt = Transcriber(cfg.whisper_model, cfg.whisper_language, cfg.whisper_backend)
    wake = WakeWord(cfg.wakeword_model, cfg.wakeword_threshold)

    print(f"Pronto. Diga a hotword ({cfg.wakeword_model}). Ctrl+C para sair.")
    with audio.MicStream() as mic:
        while True:
            hud.emit("idle")
            wake.wait(mic)
            chimed = False
            if intro.should_play():
                hud.emit("boot")
                # primeira vez do dia: música + saudação; o bipe soa quando a música começa a sumir
                intro.run(say, on_ending=audio.chime)
                chimed = True
            else:
                hud.emit("wake")
            timeout = None  # primeira fala após a hotword: espera sem pressa
            while True:
                if timeout is None and not chimed:
                    audio.chime()  # só após a hotword; nos acompanhamentos fica em silêncio
                chimed = False
                mic.flush()
                hud.emit("listening")
                clip = audio.record_utterance(mic, start_timeout=timeout or 8.0)
                if clip is None:
                    break
                text = stt.transcribe(clip)
                if not text:
                    break
                print(f"VOCÊ: {text}")
                hud.commands += 1
                hud.emit("thinking", user=text)
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
