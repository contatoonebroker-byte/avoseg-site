"""Clima atual e previsão do dia via Open-Meteo (grátis, sem chave)."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from . import Tool

GEO = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"

WMO = {
    0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina", 51: "garoa fraca", 53: "garoa", 55: "garoa forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte", 66: "chuva congelante",
    67: "chuva congelante forte", 71: "neve fraca", 73: "neve", 75: "neve forte",
    80: "pancadas de chuva fracas", 81: "pancadas de chuva", 82: "pancadas de chuva fortes",
    95: "trovoadas", 96: "trovoadas com granizo", 99: "trovoadas com granizo forte",
}


def _get(url: str, params: dict) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(full, timeout=10) as r:
        return json.load(r)


def weather_text(city: str, fetch=_get) -> str:
    geo = fetch(GEO, {"name": city, "count": 1, "language": "pt"}).get("results")
    if not geo:
        return f"Não encontrei a cidade {city}."
    place = geo[0]
    data = fetch(FORECAST, {
        "latitude": place["latitude"], "longitude": place["longitude"],
        "current": "temperature_2m,apparent_temperature,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto", "forecast_days": 1,
    })
    cur, day = data["current"], data["daily"]
    return (
        f"Em {place['name']}: agora {round(cur['temperature_2m'])} graus, "
        f"sensação de {round(cur['apparent_temperature'])}, "
        f"{WMO.get(cur['weather_code'], 'tempo variável')}. "
        f"Hoje mínima de {round(day['temperature_2m_min'][0])} e máxima de "
        f"{round(day['temperature_2m_max'][0])} graus, "
        f"chance de chuva de {day['precipitation_probability_max'][0]} por cento."
    )


def make_tools() -> list[Tool]:
    def get_weather(city: str) -> str:
        try:
            return weather_text(city)
        except Exception as e:
            return f"Não consegui consultar o clima: {e}"

    return [Tool(
        "get_weather",
        "Consulta a temperatura atual e a previsão de hoje de uma cidade.",
        {"city": {"type": "string", "description": "Nome da cidade, ex.: Sorocaba."}},
        ["city"], get_weather,
    )]
