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


def test_speech_queue_speaks_in_order():
    from jarvis.tts import SpeechQueue

    spoken = []
    q = SpeechQueue(spoken.append)
    for t in ["um", "dois", "três"]:
        q.put(t)
    q.wait()
    assert spoken == ["um", "dois", "três"]


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
