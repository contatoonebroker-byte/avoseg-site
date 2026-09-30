"""Uma sessão de conversa: hotword -> comandos -> (alguns minutos) basta chamar "Jarvis"."""
from __future__ import annotations

import time

from .audio import SAMPLE_RATE
from .wakename import find_name

FIRST_WAIT_S = 8.0   # depois da hotword (ou do nome), tempo para começar a falar
MIN_CLIP_S = 0.35    # ruídos mais curtos que isso são ignorados


class Conversation:
    """As ações reais (microfone, Whisper, Claude, voz) entram por parâmetro, para poder testar.

    record(direct, timeout) -> clip | None    ouve uma fala; `direct` = não precisa dizer o nome
    transcribe(clip) -> str                   fala -> texto
    ask(text)                                 executa o comando e fala a resposta (bloqueia até terminar)
    chime() / flush() / emit(state)           bipe, descartar áudio do mic, estado da tela
    """

    def __init__(self, *, record, transcribe, ask, chime, flush, emit,
                 minutes: float = 5.0, follow_up_s: float = 8.0, on_command=None,
                 clock=time.monotonic) -> None:
        self.record, self.transcribe, self.ask = record, transcribe, ask
        self.chime, self.flush, self.emit = chime, flush, emit
        self.minutes, self.follow_up_s = minutes, follow_up_s
        self.on_command = on_command
        self.clock = clock

    def run(self, chimed: bool = False) -> None:
        now = self.clock()
        session_end = now + self.minutes * 60
        direct_until = now + FIRST_WAIT_S   # janela em que não precisa dizer o nome
        empties = 0
        if not chimed:
            self.chime()  # só após a hotword; nos acompanhamentos fica em silêncio
        self.flush()
        while True:
            now = self.clock()
            direct = now < direct_until
            if not direct and (self.minutes <= 0 or now >= session_end):
                return  # conversa encerrada: volta a exigir "Hey Jarvis"
            self.emit("listening" if direct else "standby")
            clip = self.record(direct, (direct_until - now) if direct else 2.0)
            if clip is None or len(clip) < MIN_CLIP_S * SAMPLE_RATE:
                continue
            self.emit("thinking")
            text = self.transcribe(clip)
            if not text:
                empties += 1
                if direct and empties > 1:
                    direct_until = 0.0
                continue
            empties = 0

            rest = find_name(text)
            if rest is None and not direct:
                continue                       # não falaram comigo
            if rest == "":                     # só chamaram pelo nome: "Jarvis?"
                self.chime()
                self.flush()
                direct_until = self.clock() + FIRST_WAIT_S
                continue
            if rest:
                text = rest                    # "Jarvis, que horas são?" -> "que horas são?"

            if self.on_command:
                self.on_command(text)
            self.ask(text)
            self.flush()                       # descarta o que o microfone ouviu da própria voz
            direct_until = self.clock() + self.follow_up_s
            session_end = self.clock() + self.minutes * 60
