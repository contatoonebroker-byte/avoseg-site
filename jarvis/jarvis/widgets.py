"""Widgets da tela HUD: threads que buscam dados e publicam no Hud."""
from __future__ import annotations

import threading
import time


def system_snapshot(prev_net: tuple[float, int, int] | None = None):
    """Monitor do computador. Devolve (dados, leitura_de_rede_atual)."""
    import psutil

    now, net = time.time(), psutil.net_io_counters()
    cur_net = (now, net.bytes_recv, net.bytes_sent)
    down = up = 0.0
    if prev_net and now > prev_net[0]:
        dt = now - prev_net[0]
        down, up = (cur_net[1] - prev_net[1]) / dt / 1024, (cur_net[2] - prev_net[2]) / dt / 1024
    batt = psutil.sensors_battery()
    data = {
        "cpu": psutil.cpu_percent(), "mem": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage("/").percent,
        "battery": {"pct": round(batt.percent), "plugged": bool(batt.power_plugged)} if batt else None,
        "down": round(down), "up": round(up),
    }
    return data, cur_net


class Widgets:
    def __init__(self, hud, city: str, spotify=None) -> None:
        self.hud, self.city, self.spotify = hud, city, spotify

    def _loop(self, name: str, fn, interval: float) -> None:
        warned = False
        while True:
            try:
                fn()
                warned = False
            except Exception as e:  # sem internet, chave, etc.: tenta de novo depois
                if not warned:
                    print(f"[hud] widget {name}: {e}")
                    warned = True
            time.sleep(interval)

    def _system(self) -> None:
        state = {"net": None}

        def tick() -> None:
            data, state["net"] = system_snapshot(state["net"])
            self.hud.publish("sys", data)
            self.hud.publish("session", {"commands": self.hud.commands,
                                         "uptime": int(time.time() - self.hud.started)})
        return tick

    def _weather(self):
        from .tools.weather import fetch_weather

        def tick() -> None:
            w = fetch_weather(self.city)
            if w:
                self.hud.publish("weather", w)
        return tick

    def _spotify(self):
        return lambda: self.hud.publish("spotify", self.spotify.now_playing_info())

    def start(self) -> None:
        jobs = [("weather", self._weather(), 900)]
        try:
            import psutil  # noqa: F401
            jobs.append(("system", self._system(), 2))
        except ImportError:
            print("[hud] psutil não instalado: monitor do sistema desligado.")
        if self.spotify is not None:
            jobs.append(("spotify", self._spotify(), 4))
        for name, fn, interval in jobs:
            threading.Thread(target=self._loop, args=(name, fn, interval), daemon=True).start()
