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
