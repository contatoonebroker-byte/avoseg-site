import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.audio import BLOCK, Endpointer  # noqa: E402
from jarvis.brain import Brain  # noqa: E402
from jarvis.intro import DailyIntro  # noqa: E402
from jarvis.tools import Tool  # noqa: E402
from jarvis.tools.basic import now_text  # noqa: E402


def test_intro_only_once_per_day(tmp_path):
    intro = DailyIntro(tmp_path / "s.json")
    d = date(2026, 9, 30)
    assert intro.should_play(d)
    intro.mark_played(d)
    assert not intro.should_play(d)
    assert intro.should_play(date(2026, 10, 1))


def test_intro_run_speaks_and_marks(tmp_path):
    intro = DailyIntro(tmp_path / "s.json", audio_file="nao-existe.mp3")
    said = []
    intro.run(said.append)
    assert said and "Todos os sistemas" in said[0]
    assert not intro.should_play()


def test_greeting_periods(tmp_path):
    intro = DailyIntro(tmp_path / "s.json", user_name="Marcos")
    assert intro.greeting(datetime(2026, 1, 1, 8)).startswith("Bom dia, Marcos")
    assert intro.greeting(datetime(2026, 1, 1, 15)).startswith("Boa tarde")
    assert intro.greeting(datetime(2026, 1, 1, 21)).startswith("Boa noite")


def test_endpointer_detects_end_of_speech():
    rng = np.random.default_rng(0)
    quiet = lambda: (rng.normal(0, 20, BLOCK)).astype(np.int16)
    loud = lambda: (rng.normal(0, 3000, BLOCK)).astype(np.int16)
    ep = Endpointer(silence_s=0.4)
    for _ in range(6):
        assert not ep.feed(quiet())
    assert not ep.speaking
    for _ in range(10):
        assert not ep.feed(loud())
    assert ep.speaking
    results = [ep.feed(quiet()) for _ in range(10)]
    assert any(results)


def test_now_text():
    assert now_text(datetime(2026, 9, 30, 9, 5)) == "quarta-feira, 30 de setembro de 2026, 09:05"


class FakeClient:
    """Primeiro pede a ferramenta, depois responde com texto."""

    def __init__(self):
        self.calls = 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        if self.calls == 1:
            block = NS(type="tool_use", id="t1", name="ola", input={"nome": "Ana"})
            return NS(stop_reason="tool_use", content=[block])
        return NS(stop_reason="end_turn", content=[NS(type="text", text="Feito, senhor.")])


def test_brain_tool_loop():
    tool = Tool("ola", "diz olá", {"nome": {"type": "string"}}, ["nome"],
                func=lambda nome: f"Olá, {nome}")
    client = FakeClient()
    brain = Brain(client, "m", [tool])
    assert brain.ask("diga olá para Ana") == "Feito, senhor."
    result = brain.messages[2]["content"][0]
    assert result["tool_use_id"] == "t1" and result["content"] == "Olá, Ana"
    assert not result["is_error"]


def test_brain_tool_error_is_reported_not_raised():
    def boom(**_):
        raise RuntimeError("falhou")

    client = FakeClient()
    brain = Brain(client, "m", [Tool("ola", "x", func=boom)])
    brain.ask("oi")
    assert brain.messages[2]["content"][0]["is_error"] is True


def test_history_trim_keeps_turn_boundaries():
    brain = Brain(NS(), "m", [])
    for i in range(20):
        brain.messages += [{"role": "user", "content": f"q{i}"},
                           {"role": "assistant", "content": []}]
    brain._trim()
    assert brain._is_user_text(brain.messages[0])


def test_mlx_model_mapping():
    from jarvis.stt import mlx_repo

    assert mlx_repo("small") == "mlx-community/whisper-small-mlx"
    assert mlx_repo("large-v3") == "mlx-community/whisper-large-v3-mlx"
    assert mlx_repo("org/custom") == "org/custom"


def test_speaker_falls_back_when_elevenlabs_fails():
    from jarvis.tts import Speaker

    class Boom(Exception):
        status_code = 402
        body = {"detail": {"message": "plano pago necessário"}}

    class FakeTTS:
        def convert(self, **kw):
            raise Boom()

    sp = Speaker("", "", "m")
    sp._client = NS(text_to_speech=FakeTTS())
    spoken = []
    sp._fallback = spoken.append
    sp.say("olá")
    sp.say("de novo")
    assert spoken == ["olá", "de novo"]
    assert "plano pago" in sp._reason(Boom())


def test_weather_text_formats_open_meteo_data():
    from jarvis.tools.weather import weather_text

    def fake(url, params):
        if "geocoding" in url:
            return {"results": [{"name": "Sorocaba", "latitude": -23.5, "longitude": -47.4}]}
        return {"current": {"temperature_2m": 27.4, "apparent_temperature": 29.1, "weather_code": 2},
                "daily": {"temperature_2m_max": [31.2], "temperature_2m_min": [18.6],
                          "precipitation_probability_max": [40]}}

    out = weather_text("Sorocaba", fetch=fake)
    assert "27 graus" in out and "parcialmente nublado" in out and "máxima de 31" in out


def test_weather_city_not_found():
    from jarvis.tools.weather import weather_text

    assert "Não encontrei" in weather_text("xyz", fetch=lambda u, p: {})


def test_music_player_ducks_and_fades():
    from jarvis.intro import MusicPlayer

    rate = 1000
    p = MusicPlayer(np.ones((10 * rate, 2), dtype=np.float32), rate, volume=0.9)
    p.fill(rate)
    assert abs(p.gain - 0.9) < 1e-6
    p.set_volume(0.25, seconds=1.0)
    out = p.fill(rate)  # 1 s de rampa
    assert abs(p.gain - 0.25) < 1e-3
    assert out[0, 0] > out[-1, 0] and abs(out[-1, 0] - 0.25) < 1e-2
    p.set_volume(0.0, seconds=1.0)
    p.fill(rate)
    assert p.gain < 1e-3


def test_intro_sequence_music_ducks_then_stays_as_background(tmp_path):
    from jarvis.intro import DailyIntro

    events = []

    class FakePlayer:
        def set_volume(self, level, seconds=1.0):
            events.append(("vol", level))

        def fade_out(self, seconds=2.5, block=True):
            events.append(("fade", block))

    intro = DailyIntro(tmp_path / "s.json", lead=7, tail=1, duck=0.3, bed=0.1, after=999,
                       sleep=lambda s: events.append(("sleep", s)))
    intro._start_music = lambda: (events.append("start"), FakePlayer())[1]
    intro.run(lambda t: events.append("speak"), on_ending=lambda: events.append("chime"))
    # voz entra com a música abaixada; bipe soa e a música fica de fundo (não some ainda)
    assert events == ["start", ("sleep", 7), ("vol", 0.3), "speak", ("sleep", 1), ("vol", 0.1), "chime"]
    assert intro.bed_active

    events.clear()
    intro.speech_started()   # você fala: música quase some
    intro.speech_ended()     # terminou: volta ao fundo
    intro.end_music()        # depois de `after` segundos: fade-out
    assert events == [("vol", 0.03), ("vol", 0.1), ("fade", False)]
    assert not intro.bed_active


def test_hud_serves_page_and_streams_events():
    import http.client
    import json

    from jarvis.hud import Hud

    hud = Hud(port=0)
    hud.start()
    conn = http.client.HTTPConnection("127.0.0.1", hud.port, timeout=5)
    conn.request("GET", "/")
    page = conn.getresponse()
    assert page.status == 200 and b"J.A.R.V.I.S." in page.read()

    ev = http.client.HTTPConnection("127.0.0.1", hud.port, timeout=5)
    ev.request("GET", "/events")
    resp = ev.getresponse()
    first = json.loads(resp.fp.readline().decode().removeprefix("data: "))
    assert first["state"] == "idle"          # estado inicial ao conectar
    resp.fp.readline()
    hud.emit("speaking", text="olá")
    second = json.loads(resp.fp.readline().decode().removeprefix("data: "))
    assert second["state"] == "speaking" and second["text"] == "olá"


def test_hud_replays_widgets_to_new_clients():
    import http.client
    import json

    from jarvis.hud import Hud

    hud = Hud(port=0)
    hud.start()
    hud.publish("weather", {"city": "Sorocaba", "temp": 27})
    ev = http.client.HTTPConnection("127.0.0.1", hud.port, timeout=5)
    ev.request("GET", "/events")
    resp = ev.getresponse()
    json.loads(resp.fp.readline().decode().removeprefix("data: "))  # estado
    resp.fp.readline()
    w = json.loads(resp.fp.readline().decode().removeprefix("data: "))
    assert w == {"type": "widget", "name": "weather", "data": {"city": "Sorocaba", "temp": 27}}


def test_fetch_weather_includes_hourly_forecast():
    from jarvis.tools.weather import fetch_weather

    def fake(url, params):
        if "geocoding" in url:
            return {"results": [{"name": "Sorocaba", "latitude": 1, "longitude": 2}]}
        return {"current": {"temperature_2m": 27.4, "apparent_temperature": 29.1, "weather_code": 61},
                "daily": {"temperature_2m_max": [31], "temperature_2m_min": [18],
                          "precipitation_probability_max": [None]},
                "hourly": {"time": ["2026-09-30T15:00", "2026-09-30T16:00"],
                           "temperature_2m": [27.2, 28.4], "precipitation_probability": [10, None]}}

    w = fetch_weather("Sorocaba", fake)
    assert w["hours"] == [{"h": "15h", "t": 27, "p": 10}, {"h": "16h", "t": 28, "p": 0}]
    assert w["rain"] == 0 and w["icon"] == "🌧️"


def test_timer_tool_publishes_remaining_time():
    from jarvis.tools import basic

    published = []
    tools = {t.name: t for t in basic.make_tools(lambda m: None, published.append)}
    assert "iniciado" in tools["set_timer"].func(seconds=60, label="macarrão")
    assert published[-1][0]["label"] == "macarrão" and 58 <= published[-1][0]["remaining"] <= 60


def test_system_snapshot_shape():
    from jarvis.widgets import system_snapshot

    data, net = system_snapshot()
    assert 0 <= data["cpu"] <= 100 and 0 <= data["mem"] <= 100 and "down" in data
    data2, _ = system_snapshot(net)
    assert data2["down"] >= 0


def test_endpointer_with_known_noise_detects_speech_from_first_block():
    rng = np.random.default_rng(1)
    loud = lambda: (rng.normal(0, 3000, BLOCK)).astype(np.int16)
    quiet = lambda: (rng.normal(0, 20, BLOCK)).astype(np.int16)
    ep = Endpointer(silence_s=0.3, noise=60)
    ep.feed(loud())                       # falou logo após o bipe
    assert ep.speaking                    # sem calibrar em cima da própria voz
    assert any(ep.feed(quiet()) for _ in range(10))


def test_noise_tracker_ignores_speech_peaks():
    from jarvis.audio import NoiseTracker

    rng = np.random.default_rng(2)
    t = NoiseTracker(initial=100)
    for _ in range(200):
        t.update((rng.normal(0, 40, BLOCK)).astype(np.int16))
    settled = t.value
    for _ in range(20):
        t.update((rng.normal(0, 4000, BLOCK)).astype(np.int16))
    assert settled < 80 and abs(t.value - settled) < 1


def test_beat_analyzer_finds_bass_and_beats():
    from jarvis.beat import BeatAnalyzer

    rate, n = 44100, 1024
    t = np.arange(n) / rate
    bass = np.sin(2 * np.pi * 60 * t).astype(np.float32)
    high = np.sin(2 * np.pi * 5000 * t).astype(np.float32)
    an = BeatAnalyzer(rate)
    out = None
    for i in range(8):                     # silêncio de graves: só agudos
        out = an.process(high * 0.5, now=i * 0.05)
    assert out["bands"][-8:] != [0] * 8 and out["bass"] < 0.2 and not out["beat"]
    hit = an.process(bass, now=1.0)        # entra um bumbo
    assert hit["beat"] and hit["bass"] > 0.8 and hit["bands"][0] + hit["bands"][1] > 0.5
    assert len(hit["bands"]) == 32


def test_music_player_reports_levels_from_original_audio():
    from jarvis.intro import MusicPlayer

    rate = 44100
    tone = np.tile(np.sin(2 * np.pi * 80 * np.arange(rate) / rate).astype(np.float32)[:, None], (1, 2))
    levels = []
    p = MusicPlayer(tone, rate, volume=0.02, on_level=levels.append)  # volume quase zero
    for _ in range(4):
        p.fill(1024)
        p._last_level = 0.0
    assert levels and levels[-1]["bass"] > 0.5      # o holograma reage mesmo com a música baixa


def test_sentence_splitter_streams_complete_sentences():
    from jarvis.brain import SentenceSplitter

    out = []
    sp = SentenceSplitter(out.append, min_len=10)
    for chunk in ["Boa tarde, senhor. Hoje faz ", "27 graus em Sorocaba. Sim", ". Levo um guarda-chuva?"]:
        sp.feed(chunk)
    sp.flush()
    assert out == ["Boa tarde, senhor.", "Hoje faz 27 graus em Sorocaba.", "Sim. Levo um guarda-chuva?"]


class FakeStreamClient:
    def __init__(self):
        self.messages = self

    def stream(self, **kw):
        outer = self

        class Ctx:
            text_stream = iter(["Claro, senhor. ", "São três da tarde."])

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get_final_message(self):
                return NS(stop_reason="end_turn",
                          content=[NS(type="text", text="Claro, senhor. São três da tarde.")])
        return Ctx()


def test_brain_streams_sentences_as_they_arrive():
    said = []
    brain = Brain(FakeStreamClient(), "m", [])
    reply = brain.ask("que horas são?", on_sentence=said.append)
    assert said == ["Claro, senhor. São três da tarde."] or said == ["Claro, senhor.", "São três da tarde."]
    assert reply == "Claro, senhor. São três da tarde."


def test_speech_queue_prefetches_and_speaks_in_order():
    from jarvis.tts import SpeechQueue

    events, started = [], []

    class FakeSpeaker:
        def prepare(self, text):
            events.append(("prepare", text))      # o áudio começa a baixar ao chegar a frase
            return NS(text=text)

        def play(self, clip):
            events.append(("play", clip.text))

    q = SpeechQueue(FakeSpeaker(), on_start=started.append)
    for t in ["um", "dois", "três"]:
        q.put(t)
    q.wait()
    assert [e for e in events if e[0] == "play"] == [("play", "um"), ("play", "dois"), ("play", "três")]
    assert started == ["um", "dois", "três"]


def test_hud_level_events_are_not_replayed():
    import http.client

    from jarvis.hud import Hud

    hud = Hud(port=0)
    hud.start()
    hud.level({"bands": [0.1], "bass": 0.5, "beat": True})   # sem ninguém conectado: descartado
    ev = http.client.HTTPConnection("127.0.0.1", hud.port, timeout=3)
    ev.request("GET", "/events")
    resp = ev.getresponse()
    resp.fp.readline()                                        # estado inicial
    resp.fp.readline()
    hud.level({"bands": [0.2], "bass": 0.9, "beat": False})
    assert b'"type": "level"' in resp.fp.readline()


def test_find_name_variants_and_command_extraction():
    from jarvis.wakename import find_name

    assert find_name("Jarvis") == ""
    assert find_name("Jarvis, que horas são?") == "que horas são"
    assert find_name("Hey Jarvis, toca uma música") == "toca uma música"
    assert find_name("que horas são, Jarvis?") == "que horas são"
    assert find_name("Jarbas, qual o clima hoje") == "qual o clima hoje"
    assert find_name("Garvis abre a agenda") == "abre a agenda"
    assert find_name("Jarvís!") == ""
    assert find_name("vou ao mercado comprar pão") is None
    assert find_name("Travis chegou ontem") is None


def test_speaker_streams_chunks_into_clip_and_signals_end():
    from jarvis.tts import Speaker

    class FakeTTS:
        def convert(self, **kw):
            assert kw["output_format"] == "pcm_24000"
            yield b"\x01\x00"
            yield b""
            yield b"\x02\x00"

    sp = Speaker("", "", "m")
    sp._client = NS(text_to_speech=FakeTTS())
    clip = sp.prepare("olá")
    got = []
    while (c := clip.q.get(timeout=2)) is not None:
        got.append(c)
    assert got == [b"\x01\x00", b"\x02\x00"] and clip.error is None


def test_first_sentence_is_released_early():
    from jarvis.brain import SentenceSplitter

    out = []
    sp = SentenceSplitter(out.append)             # padrões: 1ª frase com 12+ caracteres
    sp.feed("Claro, senhor. Vou ver isso")
    assert out == ["Claro, senhor."]              # 1ª sai cedo, para começar a falar logo
    sp.feed(" agora mesmo. Um instante. Pronto.")
    sp.flush()
    assert out[1:] == ["Vou ver isso agora mesmo.", "Um instante. Pronto."]   # curtas grudam


def test_haiku_gets_no_effort_parameter():
    seen = []

    class Client:
        def __init__(self):
            self.messages = self

        def create(self, **kw):
            seen.append(kw)
            return NS(stop_reason="end_turn", content=[NS(type="text", text="ok")])

    Brain(Client(), "claude-haiku-4-5", []).ask("oi")
    Brain(Client(), "claude-opus-5-5", []).ask("oi")
    assert "output_config" not in seen[0] and seen[1]["output_config"] == {"effort": "low"}


def test_record_utterance_with_known_noise_starts_immediately_and_reports():
    from jarvis.audio import record_utterance

    rng = np.random.default_rng(3)
    loud = lambda: (rng.normal(0, 3000, BLOCK)).astype(np.int16)
    quiet = lambda: (rng.normal(0, 20, BLOCK)).astype(np.int16)
    blocks = [quiet(), quiet()] + [loud() for _ in range(6)] + [quiet() for _ in range(12)]

    class FakeMic:
        def read(self, timeout=1.0):
            return blocks.pop(0) if blocks else None

    calls = {"speech": 0, "quiet": 0}
    clip = record_utterance(FakeMic(), noise=50, silence_s=0.4, max_seconds=5,
                            on_speech=lambda: calls.__setitem__("speech", calls["speech"] + 1),
                            on_quiet=lambda b: calls.__setitem__("quiet", calls["quiet"] + 1))
    assert calls["speech"] == 1 and calls["quiet"] >= 2
    assert clip is not None and len(clip) >= 6 * BLOCK      # pegou a fala inteira (+ pré-rolagem)


class ConvHarness:
    """Simula relógio, microfone e Jarvis para testar o modo conversa sem hardware."""

    def __init__(self, script, minutes=5.0, follow_up_s=8.0):
        from jarvis.conversation import Conversation

        self.t = 1000.0
        self.script = list(script)       # [(segundos_até_a_fala, texto)] ; texto None = silêncio
        self.log, self.commands = [], []
        self.conv = Conversation(
            record=self.record, transcribe=lambda clip: clip[1], ask=self.commands.append,
            chime=lambda: self.log.append("bipe"), flush=lambda: None,
            emit=lambda s: self.log.append(s), minutes=minutes, follow_up_s=follow_up_s,
            clock=lambda: self.t)

    def record(self, direct, timeout):
        if not self.script:              # nada mais será dito: deixa o tempo correr até o fim
            self.t += timeout
            return None
        wait, text = self.script[0]
        if wait > timeout:               # ninguém falou dentro do prazo
            self.script[0] = (wait - timeout, text)
            self.t += timeout
            return None
        self.script.pop(0)
        self.t += wait
        return (np.zeros(16000, dtype=np.int16), text)


class _Clip(tuple):
    def __len__(self):                   # o clip simulado tem 1 s de áudio
        return 16000


def _fix(h):
    orig = h.record
    h.record = lambda d, t: (lambda r: _Clip(r) if r else None)(orig(d, t))
    h.conv.record = h.record
    return h


def test_conversation_follow_up_needs_no_name_then_name_is_required():
    h = _fix(ConvHarness([(2, "que horas são"),          # 1º comando após a hotword
                          (3, "e a data de hoje"),       # logo depois: sem nome
                          (60, "quero café"),            # 1 min depois: sem nome -> ignora
                          (5, "Jarvis, toca uma música"),  # com o nome -> executa
                          ]))
    h.conv.run()
    assert h.commands == ["que horas são", "e a data de hoje", "toca uma música"]
    assert h.log[0] == "bipe" and "standby" in h.log


def test_conversation_just_calling_the_name_opens_a_new_listening_window():
    h = _fix(ConvHarness([(2, "oi"), (30, "Jarvis"), (4, "abre a agenda")]))
    h.conv.run()
    assert h.commands == ["oi", "abre a agenda"]      # "Jarvis" sozinho -> bipe -> comando sem nome
    assert h.log.count("bipe") == 2


def test_conversation_ends_after_configured_minutes_of_inactivity():
    h = _fix(ConvHarness([(2, "oi")], minutes=2))
    h.conv.run()                                       # termina sozinha (não trava)
    assert h.commands == ["oi"] and h.t - 1000 >= 2 * 60


def test_conversation_disabled_when_minutes_zero():
    h = _fix(ConvHarness([(2, "oi"), (30, "Jarvis, e agora?")], minutes=0))
    h.conv.run()
    assert h.commands == ["oi"]                        # passada a janela direta, volta ao "Hey Jarvis"


def test_conversation_gives_up_on_repeated_empty_transcripts():
    h = _fix(ConvHarness([(1, ""), (1, ""), (1, "algo sem nome")], minutes=0.1))
    h.conv.run()
    assert h.commands == []                            # sem fala reconhecida e sem nome: nada executado


def test_whisper_prompt_echo_is_discarded_but_real_speech_is_kept():
    from jarvis.stt import Transcriber

    t = object.__new__(Transcriber)
    t.prompt = "Conversa com o assistente Jarvis. Comandos: Jarvis, anota esta ideia; registra no diário."
    assert t._clean("Jarvis, anota esta ideia") == ""              # eco do vocabulário (alucinação com ruído)
    assert t._clean("Jarvis, anota que preciso ligar para o contador") != ""
    assert t._clean("  ") == ""


def test_elevenlabs_unknown_model_falls_back_to_flash_and_still_speaks():
    from jarvis.tts import Speaker

    seen = []

    class FakeTTS:
        def convert(self, **kw):
            seen.append(kw["model_id"])
            if kw["model_id"] == "eleven_multilingual_v2_5":
                raise Exception("400 A model with model ID eleven_multilingual_v2_5 does not exist")
            yield b"\x01\x00"

    sp = Speaker("", "", "eleven_multilingual_v2_5")
    sp._client = NS(text_to_speech=FakeTTS())
    clip = sp.prepare("olá")
    got = []
    while (c := clip.q.get(timeout=2)) is not None:
        got.append(c)
    assert seen == ["eleven_multilingual_v2_5", "eleven_flash_v2_5"] and got == [b"\x01\x00"] and clip.error is None
    assert sp.model_id == "eleven_flash_v2_5"


def test_looks_incomplete_flags_cut_sentences_but_not_complete_commands():
    from jarvis.incomplete import looks_incomplete as inc

    for cortada in ["anota", "Jarvis, anota que", "crie um post sobre", "preciso ligar para o", "anota a ideia:",
                    "me manda", "fale com a Maria e", "registra..."]:
        assert inc(cortada), cortada
    for completa in ["que horas são", "qual a temperatura em Sorocaba", "anota que preciso ligar para o contador",
                     "mostre minhas notas", "crie um post sobre seguro de frota", "toca uma música", ""]:
        assert not inc(completa), completa


def test_endpointer_hysteresis_keeps_weak_word_endings_inside_the_sentence():
    rng = np.random.default_rng(5)
    at = lambda rms_: (rng.normal(0, rms_, BLOCK)).astype(np.int16)
    ep = Endpointer(silence_s=0.4, noise=60)            # limiar de início = 300*? (mínimo 300)
    assert ep.threshold == 300 and ep.off_threshold == 180
    assert not ep.feed(at(2500)) and ep.speaking
    weak = [ep.feed(at(230)) for _ in range(12)]        # fim de palavra fraco: abaixo do início, acima do fim
    assert not any(weak) and ep._quiet == 0
    assert any(ep.feed(at(20)) for _ in range(12))      # silêncio de verdade encerra


def _conv(texts_by_seconds, first_clip_s=1, more_clips=()):
    """Harness: cada 'clip' é um array de N segundos; a transcrição depende da duração total."""
    from jarvis.conversation import Conversation

    more = list(more_clips)
    log = {"asked": [], "records": 0}

    def record(direct, timeout):
        log["records"] += 1
        if log["records"] == 1:
            return np.zeros(16000 * first_clip_s, dtype=np.int16)
        return np.zeros(16000 * more.pop(0), dtype=np.int16) if more else None

    conv = Conversation(record=record, transcribe=lambda clip: texts_by_seconds[len(clip) // 16000],
                        ask=log["asked"].append, chime=lambda: None, flush=lambda: None, emit=lambda s: None,
                        minutes=0, follow_up_s=0.0, continue_wait_s=0.1)
    return conv, log


def test_conversation_joins_the_continuation_of_a_cut_sentence():
    conv, log = _conv({1: "Jarvis, anota que", 3: "Jarvis, anota que preciso ligar para o contador"}, 1, [2])
    conv.run(chimed=True)
    assert log["asked"] == ["anota que preciso ligar para o contador"]


def test_conversation_does_not_wait_when_sentence_is_complete_and_gives_up_when_nothing_follows():
    conv, log = _conv({1: "que horas são"})
    conv.run(chimed=True)
    assert log["asked"] == ["que horas são"] and log["records"] >= 1
    conv2, log2 = _conv({1: "Jarvis, anota"})                      # incompleta, mas ninguém continua
    conv2.run(chimed=True)
    assert log2["asked"] == ["anota"]                              # segue com o que tem (o Claude pergunta o resto)


def test_env_check_finds_common_mistakes_without_leaking_keys(tmp_path):
    from jarvis.envcheck import check

    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=sk-ant-SEGREDO123456\n# OPENAI_API_KEY=sk-naoaparece\nOPEN_AI_API_KEY=sk-xyz\n"
                   "openai_image_model = gpt-image-1\nELEVENLABS_API_KEY=\"abc\"\n")
    report = "\n".join(check(env))
    assert "SEGREDO" not in report and "sk-xyz" not in report and "naoaparece" not in report
    assert "✓ ANTHROPIC_API_KEY: 20 caracteres, começa com 'sk-'" in report
    assert "COMENTADA" in report and "OPENAI_API_KEY NÃO está no .env" in report
    assert "MAIÚSCULAS" in report and "entre aspas" in report
    env.write_text("OPENAI_API_KEY=\nANTHROPIC_API_KEY=x\n")
    assert "VAZIA" in "\n".join(check(env))
    assert "Não achei o arquivo" in check(tmp_path / "nao-existe")[0]


def test_config_cleans_quotes_spaces_and_dotenv_overrides_empty_shell_variable(tmp_path, monkeypatch):
    import jarvis.config as cfgmod

    (tmp_path / ".env").write_text('OPENAI_API_KEY = "  sk-abc  "\nJARVIS_CITY=Sorocaba\n')
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "")            # variável vazia herdada do Terminal
    cfg = cfgmod.Config.load()
    assert cfg.openai_key == "sk-abc" and cfg.image_provider == "openai"
