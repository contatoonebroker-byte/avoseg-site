"""Servidor local da tela HUD: página estática + eventos em tempo real (SSE).

O Jarvis chama hud.emit(estado, ...) e todo navegador aberto em http://127.0.0.1:8765
(no Mac ou, se HUD_HOST=0.0.0.0, no tablet da mesma rede) atualiza na hora.
"""
from __future__ import annotations

import json
import queue
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = Path(__file__).parent / "hud" / "index.html"


class Hud:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host, self.port = host, port
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._last: dict = {"state": "idle"}
        self._widgets: dict[str, dict] = {}
        self.started = time.time()
        self.commands = 0
        self._server: ThreadingHTTPServer | None = None

    # --- publicação ---
    def emit(self, state: str, **data) -> None:
        event = {"state": state, "t": time.time(), **data}
        with self._lock:
            self._last = event
            subs = list(self._subs)
        for q in subs:
            self._offer(q, event)

    def publish(self, name: str, data) -> None:
        """Atualiza um widget da tela (clima, monitor, spotify...)."""
        event = {"type": "widget", "name": name, "data": data}
        with self._lock:
            self._widgets[name] = event
            subs = list(self._subs)
        for q in subs:
            self._offer(q, event)

    @staticmethod
    def _offer(q: queue.Queue, event: dict) -> None:
        try:
            q.put_nowait(event)
        except queue.Full:
            pass

    def level(self, payload: dict) -> None:
        """Espectro/batida da música (efêmero: não é guardado nem reenviado a quem conecta depois)."""
        event = {"type": "level", **payload}
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            self._offer(q, event)  # cliente lento (ex.: tablet no Wi-Fi): descarta

    def _subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        with self._lock:
            self._subs.append(q)
        return q

    def _unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    # --- servidor ---
    def start(self) -> str:
        hud = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # silencioso
                pass

            def do_GET(self) -> None:
                if self.path.split("?")[0] == "/events":
                    return self._events()
                if self.path.split("?")[0] in ("/", "/index.html"):
                    body = PAGE.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                    return
                self.send_error(404)

            def _events(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                q = hud._subscribe()
                try:
                    self._send(hud._last)
                    for w in list(hud._widgets.values()):
                        self._send(w)
                    while True:
                        try:
                            self._send(q.get(timeout=15))
                        except queue.Empty:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    hud._unsubscribe(q)

            def _send(self, event: dict) -> None:
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                self.wfile.flush()

        ThreadingHTTPServer.daemon_threads = True
        for port in range(self.port, self.port + 10):  # porta ocupada: tenta a próxima
            try:
                self._server = ThreadingHTTPServer((self.host, port), Handler)
                self.port = self._server.server_address[1]
                break
            except OSError:
                continue
        else:
            raise OSError("Nenhuma porta livre para o HUD")
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self.url

    @property
    def url(self) -> str:
        return f"http://{'127.0.0.1' if self.host == '0.0.0.0' else self.host}:{self.port}"

    def lan_url(self) -> str | None:
        """Endereço para abrir no tablet (só quando HUD_HOST=0.0.0.0)."""
        if self.host != "0.0.0.0":
            return None
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return f"http://{s.getsockname()[0]}:{self.port}"
        except OSError:
            return None
