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


def icon(code: int) -> str:
    if code == 0: return "☀️"
    if code in (1, 2): return "🌤️"
    if code == 3: return "☁️"
    if code in (45, 48): return "🌫️"
    if 51 <= code <= 57: return "🌦️"
    if 61 <= code <= 67 or 80 <= code <= 82: return "🌧️"
    if 71 <= code <= 77: return "❄️"
    if code >= 95: return "⛈️"
    return "🌡️"


def fetch_weather(city: str, fetch=_get) -> dict | None:
    """Clima atual, previsão do dia e próximas horas. None se a cidade não existir."""
    geo = fetch(GEO, {"name": city, "count": 1, "language": "pt"}).get("results")
    if not geo:
        return None
    place = geo[0]
    data = fetch(FORECAST, {
        "latitude": place["latitude"], "longitude": place["longitude"],
        "current": "temperature_2m,apparent_temperature,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "hourly": "temperature_2m,precipitation_probability", "forecast_hours": 8,
        "timezone": "auto", "forecast_days": 1,
    })
    cur, day, hr = data["current"], data["daily"], data.get("hourly") or {}
    hours = [
        {"h": t[11:13] + "h", "t": round(temp), "p": (hr.get("precipitation_probability") or [0] * 99)[i] or 0}
        for i, (t, temp) in enumerate(zip(hr.get("time", []), hr.get("temperature_2m", [])))
    ]
    return {
        "city": place["name"], "temp": round(cur["temperature_2m"]),
        "feels": round(cur["apparent_temperature"]), "code": cur["weather_code"],
        "desc": WMO.get(cur["weather_code"], "tempo variável"), "icon": icon(cur["weather_code"]),
        "min": round(day["temperature_2m_min"][0]), "max": round(day["temperature_2m_max"][0]),
        "rain": day["precipitation_probability_max"][0] or 0, "hours": hours,
    }


def weather_text(city: str, fetch=_get) -> str:
    w = fetch_weather(city, fetch)
    if w is None:
        return f"Não encontrei a cidade {city}."
    return (
        f"Em {w['city']}: agora {w['temp']} graus, sensação de {w['feels']}, {w['desc']}. "
        f"Hoje mínima de {w['min']} e máxima de {w['max']} graus, "
        f"chance de chuva de {w['rain']} por cento."
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
