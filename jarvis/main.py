"""JARVIS: hotword -> escuta -> Whisper -> Claude -> voz."""
from __future__ import annotations

import threading
import time
import webbrowser

import anthropic

from jarvis import audio
from jarvis.brain import Brain
from jarvis.config import STATE_FILE, Config
from jarvis.conversation import Conversation
from jarvis.hud import Hud
from jarvis.secondbrain import Brain as SecondBrain
from jarvis.secondbrain.tools import make_tools as second_brain_tools
from jarvis.skills.marketing import make_tools as marketing_tools
from jarvis.intro import DailyIntro
from jarvis.stt import Transcriber
from jarvis.tools import build_tools
from jarvis.tts import Speaker, SpeechQueue
from jarvis.wakeword import WakeWord
from jarvis.widgets import Widgets


def main() -> None:
    cfg = Config.load()
    speak_lock = threading.Lock()
    hud = Hud(cfg.hud_host, cfg.hud_port)
    lat: dict[str, float] = {}  # marcas de tempo do comando atual (para medir a latência)

    def say(text: str) -> None:  # saudação, timers...
        with speak_lock:
            hud.emit("speaking", text=text)
            speaker.say(text)

    def on_speech_start(text: str) -> None:
        hud.emit("speaking", text=text)
        if "audio" not in lat and {"end", "stt", "first"} <= lat.keys():
            lat["audio"] = time.monotonic()
            e = lat["end"]
            print(f"[latência] transcrição {lat['stt'] - e:.1f}s · 1ª frase {lat['first'] - e:.1f}s"
                  f" · voz começou {lat['audio'] - e:.1f}s (contando do fim da sua fala)")

    def on_sentence(text: str) -> None:
        lat.setdefault("first", time.monotonic())
        speech.put(text)

    speaker = Speaker(cfg.eleven_key, cfg.eleven_voice, cfg.eleven_model)
    speech = SpeechQueue(speaker, on_start=on_speech_start, lock=speak_lock)
    spotify = None
    if cfg.spotify_enabled:
        from jarvis.tools.spotify import Spotify

        spotify = Spotify()
    # --- Second Brain (memória) + skills ---
    sb = SecondBrain(cfg.brain_dir)
    client = anthropic.Anthropic()
    print(f"Second Brain: {sb.count()} notas em {sb.root}")

    def show_brain() -> None:
        hud.publish("brain", sb.graph())
        hud.emit("brain")

    def on_note(note) -> None:          # nota nova: o cérebro na tela ganha um neurônio e se ilumina
        print(f"[cérebro] nota salva: {note.title!r} -> {note.path}")
        hud.publish("brain", sb.graph())
        hud.publish("notes", sb.notes_payload(6))
        hud.emit("note", title=note.title, area=note.area)

    def recall(text: str) -> str:       # memória automática: notas relevantes para o que você acabou de dizer
        return "\n".join(f"- {n.title} ({n.area}, {n.created[:10]}): {n.excerpt(200)}" for n, _ in sb.recall(text, 3))

    tools = build_tools(cfg, notify=say, publish=lambda t: hud.publish("timers", t), spotify=spotify)
    tools += second_brain_tools(sb, on_change=on_note, on_show=show_brain,
                                on_list=lambda items, titulo: hud.card("notes", {"items": items, "titulo": titulo}))
    hud.art_root = sb.root
    tools += marketing_tools(
        sb, client, cfg.marketing_model, on_change=on_note, on_post=lambda d: hud.publish("post", d),
        on_art=lambda d: hud.card("arte", {**d, "images": ["/arte/" + i for i in d["images"]]}),
        image_cfg=(cfg.image_provider, cfg.openai_key, cfg.openai_image_model, cfg.image_quality))
    brain = Brain(client, cfg.model, tools, cfg.user_name, cfg.city,
                  profile_provider=sb.read_profile, context_provider=recall)

    intro = DailyIntro(
        STATE_FILE, cfg.intro_audio_file, cfg.intro_spotify_uri, cfg.intro_seconds, cfg.user_name,
        spotify if cfg.intro_spotify_uri else None, cfg.intro_lead, cfg.intro_tail, cfg.intro_duck,
        bed=cfg.intro_bed, after=cfg.intro_after, on_level=hud.level,
    )

    if cfg.hud_enabled:
        print(f"HUD em {hud.start()}")
        if hud.lan_url():
            print(f"No tablet, abra: {hud.lan_url()}")
        Widgets(hud, cfg.city, spotify).start()
        hud.publish("brain", sb.graph())
        hud.publish("notes", sb.notes_payload(6))
        if cfg.hud_auto_open:
            webbrowser.open(hud.url)

    if cfg.image_off:
        print("Arte por IA: DESLIGADA porque o .env tem IMAGE_PROVIDER=off. Apague essa linha para ligar.")
    elif cfg.image_provider == "none":
        print("Arte por IA: DESLIGADA (não achei OPENAI_API_KEY no .env; confira com: python scripts/check_env.py)")
    else:
        print(f"Arte por IA: ligada ({cfg.image_provider}, modelo {cfg.openai_image_model}, qualidade {cfg.image_quality})")
    print("Carregando modelos...")
    stt = Transcriber(cfg.whisper_model, cfg.whisper_language, cfg.whisper_backend, cfg.whisper_prompt)
    wake = WakeWord(cfg.wakeword_model, cfg.wakeword_threshold)
    ambient = audio.NoiseTracker()

    def build_conversation(mic) -> Conversation:
        def record(direct: bool, timeout: float):
            clip = audio.record_utterance(
                mic, start_timeout=timeout, noise=ambient.value,
                silence_s=cfg.silence_s, min_threshold=450 if intro.bed_active else 300,
                on_speech=intro.speech_started,   # música quase some enquanto você fala
                on_quiet=ambient.update,
            )
            intro.speech_ended()
            if clip is not None:
                lat.clear()
                lat["end"] = time.monotonic()
                print(f"[fala] {len(clip) / audio.SAMPLE_RATE:.1f}s captados")
            return clip

        def transcribe(clip) -> str:
            text = stt.transcribe(clip)
            lat["stt"] = time.monotonic()
            return text

        def ask(text: str) -> None:
            print(f"VOCÊ: {text}")
            hud.commands += 1
            hud.emit("thinking", user=text)
            try:
                brain.ask(text, on_sentence=on_sentence)  # fala frase a frase, enquanto o Claude escreve
            except anthropic.APIError as e:
                print(f"[erro API] {e}")
                speech.put("Perdi a conexão com o meu núcleo de raciocínio. Tente novamente em instantes.")
            speech.wait()

        return Conversation(record=record, transcribe=transcribe, ask=ask, chime=audio.chime,
                            flush=mic.flush, emit=hud.emit, minutes=cfg.conversation_minutes,
                            on_heard=lambda t, note: print(f"[ouvi] {t!r} -> {note}"),
                            follow_up_s=cfg.follow_up_s)

    print(f"Pronto. Diga a hotword ({cfg.wakeword_model}). Ctrl+C para sair.")
    with audio.MicStream() as mic:
        while True:
            hud.emit("idle")
            wake.wait(mic, on_block=ambient.update)
            chimed = False
            if intro.should_play():
                hud.emit("boot")
                # 1ª vez do dia: música + saudação; o bipe soa logo depois e a música segue baixinho
                intro.run(say, on_ending=audio.chime)
                chimed = True
            else:
                hud.emit("wake")
            build_conversation(mic).run(chimed)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDesligando.")
