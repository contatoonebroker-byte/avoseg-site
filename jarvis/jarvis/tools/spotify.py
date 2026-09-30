from __future__ import annotations

from . import Tool

SCOPE = "user-modify-playback-state user-read-playback-state"
_KINDS = {"track": "tracks", "artist": "artists", "album": "albums", "playlist": "playlists"}


class Spotify:
    def __init__(self) -> None:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth

        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE))

    def _device(self) -> str | None:
        devices = self.sp.devices().get("devices", [])
        active = [d for d in devices if d.get("is_active")]
        pick = (active or devices or [None])[0]
        return pick["id"] if pick else None

    def play_uri(self, uri: str) -> None:
        kwargs = {"device_id": self._device()}
        if ":track:" in uri:
            kwargs["uris"] = [uri]
        else:
            kwargs["context_uri"] = uri
        self.sp.start_playback(**kwargs)

    def pause(self) -> None:
        self.sp.pause_playback()

    def get_volume(self) -> int:
        cur = self.sp.current_playback() or {}
        return (cur.get("device") or {}).get("volume_percent") or 80

    def set_volume(self, percent: int) -> None:
        self.sp.volume(max(0, min(100, percent)))


def make_tools() -> list[Tool]:
    sp = Spotify()

    def guard(fn):
        def run(**kw) -> str:
            try:
                return fn(**kw)
            except Exception as e:  # spotipy levanta SpotifyException, sem dispositivo etc.
                return f"Falha no Spotify: {e}"
        return run

    @guard
    def play(query: str, kind: str = "track") -> str:
        kind = kind if kind in _KINDS else "track"
        items = sp.sp.search(q=query, type=kind, limit=1)[_KINDS[kind]]["items"]
        if not items:
            return f"Nada encontrado para '{query}'."
        item = items[0]
        sp.play_uri(item["uri"])
        who = item.get("artists", [{}])[0].get("name", "")
        return f"Tocando {item['name']}{' de ' + who if who else ''}."

    @guard
    def control(action: str) -> str:
        actions = {"pause": sp.sp.pause_playback, "resume": sp.sp.start_playback,
                   "next": sp.sp.next_track, "previous": sp.sp.previous_track}
        if action not in actions:
            return "Ação desconhecida."
        actions[action]()
        return "Feito."

    @guard
    def volume(percent: int) -> str:
        sp.sp.volume(max(0, min(100, percent)))
        return f"Volume em {max(0, min(100, percent))}%."

    @guard
    def now_playing() -> str:
        cur = sp.sp.current_playback()
        if not cur or not cur.get("item"):
            return "Nada está tocando."
        item = cur["item"]
        return f"{item['name']} de {item['artists'][0]['name']}."

    return [
        Tool("spotify_play", "Toca música no Spotify buscando por nome.",
             {"query": {"type": "string"},
              "kind": {"type": "string", "enum": list(_KINDS), "description": "Padrão: track."}},
             ["query"], play),
        Tool("spotify_control", "Pausa, retoma, avança ou volta a faixa no Spotify.",
             {"action": {"type": "string", "enum": ["pause", "resume", "next", "previous"]}},
             ["action"], control),
        Tool("spotify_volume", "Ajusta o volume do Spotify (0 a 100).",
             {"percent": {"type": "integer"}}, ["percent"], volume),
        Tool("spotify_now_playing", "Diz qual música está tocando.", func=now_playing),
    ]
