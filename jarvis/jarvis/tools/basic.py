from __future__ import annotations

import threading
from datetime import datetime
from typing import Callable

from . import Tool

_DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
         "sexta-feira", "sábado", "domingo"]
_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]


def now_text(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return (f"{_DIAS[now.weekday()]}, {now.day} de {_MESES[now.month - 1]} de {now.year}, "
            f"{now:%H:%M}")


def make_tools(notify: Callable[[str], None]) -> list[Tool]:
    def get_datetime() -> str:
        return now_text()

    def set_timer(seconds: int, label: str = "") -> str:
        if seconds <= 0:
            return "Duração inválida."
        msg = f"O temporizador{' de ' + label if label else ''} terminou."
        t = threading.Timer(seconds, notify, args=(msg,))
        t.daemon = True
        t.start()
        return f"Temporizador de {seconds} segundos iniciado."

    return [
        Tool("get_datetime", "Retorna a data e hora atuais.", func=get_datetime),
        Tool(
            "set_timer",
            "Inicia um temporizador; o assistente avisa por voz quando terminar.",
            properties={
                "seconds": {"type": "integer", "description": "Duração em segundos."},
                "label": {"type": "string", "description": "Rótulo opcional, ex.: 'macarrão'."},
            },
            required=["seconds"],
            func=set_timer,
        ),
    ]
