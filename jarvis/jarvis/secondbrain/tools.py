"""Ferramentas de voz do Second Brain (o Claude chama sozinho conforme o que você pede)."""
from __future__ import annotations

from ..tools import Tool
from .store import AREAS, Brain

_AREA_ENUM = list(AREAS)
_TIPOS_ANOTAR = ["nota", "ideia", "decisao", "tarefa", "pessoa", "reuniao"]


def _fmt(note, snippet: str | None = None) -> str:
    quando = note.created[:10]
    resto = snippet or note.excerpt(160)
    return f"- [{note.id}] {note.title} ({note.area}/{note.tipo}, {quando}): {resto}"


def make_tools(brain: Brain, on_change=None, on_show=None, on_list=None) -> list[Tool]:
    """on_change(nota): chamado depois de gravar uma nota (atualiza a tela do cérebro).
    on_show(): mostra o cérebro na tela. on_list(notas): abre a lista de notas na tela."""

    def anotar(texto: str, titulo: str, area: str = "inbox", tipo: str = "nota", tags: list | None = None) -> str:
        note = brain.add_note(titulo, texto, area, tipo, [str(t) for t in (tags or [])][:6])
        if on_change:
            on_change(note)
        rel = [n.title for n in brain.related(note, 3)]
        extra = f" Conectei com: {'; '.join(rel)}." if rel else ""
        return f"Anotado em {note.area} como {note.tipo}: '{note.title}'.{extra}"

    def buscar_notas(consulta: str, area: str | None = None, limite: int = 5) -> str:
        hits = brain.search(consulta, max(1, min(limite, 10)), area if area in AREAS else None)
        if not hits:
            return "Não encontrei nada nas notas sobre isso."
        return "\n".join(_fmt(n, s.replace("\n", " ")) for n, s in hits)

    def ler_nota(referencia: str) -> str:
        note = brain.get(referencia)
        if not note:
            return "Não achei essa nota."
        body = note.body if len(note.body) <= 4000 else note.body[:4000] + "\n[...cortado]"
        return f"# {note.title}\n({note.area}/{note.tipo}, {note.created[:10]}, tags: {', '.join(note.tags) or '-'})\n\n{body}"

    def notas_recentes(dias: int = 7, area: str | None = None, tipo: str | None = None, limite: int = 15) -> str:
        notes = brain.recent(max(1, min(limite, 40)), dias, area if area in AREAS else None, tipo)
        return "\n".join(_fmt(n) for n in notes) or "Nenhuma nota nesse período."

    def diario(texto: str) -> str:
        brain.append_daily(texto)
        return "Registrado no diário de hoje."

    def lembrar_sobre_mim(fato: str) -> str:
        brain.add_profile_fact(fato)
        return "Guardei no seu perfil. Vou levar isso em conta daqui para frente."

    def mostrar_notas(consulta: str = "", area: str | None = None, limite: int = 10) -> str:
        area = area if area in AREAS else None
        limite = max(1, min(limite, 20))
        if consulta.strip():
            notes = [n for n, _ in brain.search(consulta, limite, area)]
        else:
            notes = brain.recent(limite, None, area)
        if not notes:
            return "Não encontrei notas para mostrar."
        if on_list:
            on_list(brain.notes_payload(notes=notes), consulta or ("recentes" + (f" em {area}" if area else "")))
        return "Abri a lista na tela: " + "; ".join(f"{n.title} ({n.area})" for n in notes[:6])

    def mostrar_cerebro() -> str:
        if on_show:
            on_show()
        return f"Mostrando o cérebro na tela: {brain.count()} notas."

    return [
        Tool("anotar",
             "Guarda uma nota no Second Brain (a memória permanente do usuário). Use sempre que ele pedir para "
             "anotar, lembrar, registrar uma ideia, decisão, tarefa, reunião ou informação sobre pessoas. "
             "Escolha você mesmo um título curto, a área e as tags.",
             {"texto": {"type": "string", "description": "Conteúdo completo da nota, claro e autossuficiente."},
              "titulo": {"type": "string", "description": "Título curto (3 a 8 palavras)."},
              "area": {"type": "string", "enum": _AREA_ENUM,
                       "description": "pessoal, avoseg, avogroup, projetos, pessoas, decisoes ou inbox (se incerto)."},
              "tipo": {"type": "string", "enum": _TIPOS_ANOTAR},
              "tags": {"type": "array", "items": {"type": "string"}, "description": "Até 5 palavras-chave."}},
             ["texto", "titulo"], anotar),
        Tool("buscar_notas", "Procura nas notas do Second Brain (palavras-chave, sem precisar ser exato).",
             {"consulta": {"type": "string"},
              "area": {"type": "string", "enum": _AREA_ENUM},
              "limite": {"type": "integer"}}, ["consulta"], buscar_notas),
        Tool("ler_nota", "Lê uma nota inteira pelo id ou por parte do título.",
             {"referencia": {"type": "string"}}, ["referencia"], ler_nota),
        Tool("notas_recentes", "Lista as notas mais recentes (para resumos do dia ou da semana).",
             {"dias": {"type": "integer"}, "area": {"type": "string", "enum": _AREA_ENUM},
              "tipo": {"type": "string"}, "limite": {"type": "integer"}}, [], notas_recentes),
        Tool("diario", "Acrescenta uma linha com a hora ao diário de hoje.",
             {"texto": {"type": "string"}}, ["texto"], diario),
        Tool("lembrar_sobre_mim",
             "Guarda no perfil do usuário uma preferência ou fato duradouro sobre ele (gostos, rotina, regras).",
             {"fato": {"type": "string"}}, ["fato"], lembrar_sobre_mim),
        Tool("mostrar_notas",
             "Abre na tela a lista das notas (as mais recentes, de uma área ou de uma busca). Use quando o usuário "
             "pedir para ver, mostrar ou abrir suas notas.",
             {"consulta": {"type": "string", "description": "Opcional: palavras para filtrar."},
              "area": {"type": "string", "enum": _AREA_ENUM}, "limite": {"type": "integer"}}, [], mostrar_notas),
        Tool("mostrar_cerebro", "Mostra na tela o cérebro animado com todas as notas e conexões.",
             func=mostrar_cerebro),
    ]
