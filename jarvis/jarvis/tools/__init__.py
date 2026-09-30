"""Registro das ferramentas que o Claude pode chamar."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    properties: dict = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    func: Callable[..., str] = lambda **_: ""

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.properties,
                "required": self.required,
                "additionalProperties": False,
            },
        }


def build_tools(cfg, notify: Callable[[str], None]) -> list[Tool]:
    from . import basic, weather

    tools = basic.make_tools(notify) + weather.make_tools()
    if cfg.spotify_enabled:
        from . import spotify

        tools += spotify.make_tools()
    return tools
