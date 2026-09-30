"""Servidor local da tela HUD: página estática + eventos em tempo real (SSE).

O Jarvis chama hud.emit(estado, ...) e todo navegador aberto em http://127.0.0.1:8765
(no Mac ou, se HUD_HOST=0.0.0.0, no tablet da mesma rede) atualiza na hora.
"""
from __future__ import annotations

import json
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = Path(__file__).parent / "hud" / "index.html"
ART_DIR = re.compile(r"(20-Avoseg|30-Avogroup)/marketing/arte/[\w.\-]+")
ART_PATH = re.compile(r"(20-Avoseg|30-Avogroup)/marketing/arte/[\w.\-]+/[\w.\-]+\.(png|jpg|jpeg)")
ART_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}


class Hud:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host, self.port = host, port
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._last: dict = {"state": "idle"}
        self._widgets: dict[str, dict] = {}
        self.started = time.time()
        self.art_root: Path | None = None   # pasta do Second Brain; só as imagens de arte dela são servidas
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

    def card(self, kind: str, data) -> None:
        """Abre um cartão na tela (ex.: lista de notas). Efêmero: não é reenviado a quem conectar depois."""
        event = {"type": "card", "kind": kind, "data": data}
        with self._lock:
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

    def open_art_dir(self, rel: str) -> bool:
        root = self.art_root
        if root is None or not ART_DIR.fullmatch(rel) or ".." in rel.split("/"):
            return False
        p = (root / rel).resolve()
        if root.resolve() not in p.parents or not p.is_dir():
            return False
        cmd = "open" if sys.platform == "darwin" else "xdg-open"
        try:
            subprocess.Popen([cmd, str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return False
        return True

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
                if self.path.startswith("/arte/"):
                    return self._art(urllib.parse.unquote(self.path[len("/arte/"):].split("?")[0]))
                if self.path == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                    return
                self.send_error(404)

            def do_POST(self) -> None:
                # Abre a pasta de uma arte no Finder. Só a própria máquina, só pastas de arte do Second Brain.
                if self.path != "/abrir" or self.client_address[0] not in ("127.0.0.1", "::1"):
                    return self.send_error(404)
                try:
                    n = min(int(self.headers.get("Content-Length") or 0), 2048)
                    rel = str(json.loads(self.rfile.read(n) or b"{}").get("pasta", ""))
                except Exception:
                    return self.send_error(400)
                ok = hud.open_art_dir(rel)
                self.send_response(200 if ok else 404)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def _art(self, rel: str) -> None:
                root = hud.art_root
                ok = root is not None and ART_PATH.fullmatch(rel) and ".." not in rel.split("/")
                p = (root / rel).resolve() if ok else None
                if not (p and root.resolve() in p.parents and p.is_file()):
                    return self.send_error(404)
                body = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ART_TYPES[p.suffix.lower().lstrip(".")])
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)

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
