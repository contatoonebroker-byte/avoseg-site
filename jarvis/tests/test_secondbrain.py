import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.brain import Brain as Voice  # noqa: E402
from jarvis.secondbrain import Brain  # noqa: E402
from jarvis.secondbrain.tools import make_tools  # noqa: E402
from jarvis.skills import marketing  # noqa: E402


@pytest.fixture
def sb(tmp_path):
    return Brain(tmp_path / "brain")


def test_structure_and_starter_files_are_created(sb):
    for folder in ("00-Inbox", "20-Avoseg", "30-Avogroup", "70-Diario"):
        assert (sb.root / folder).is_dir()
    assert (sb.root / "perfil.md").exists() and (sb.root / "20-Avoseg" / "marca.md").exists()


def test_add_note_writes_markdown_with_frontmatter_and_is_searchable(sb):
    n = sb.add_note("Post sobre frota", "Carrossel para transportadoras sobre custo de sinistros",
                    "avoseg", "ideia", ["Marketing", "frota"])
    text = n.path.read_text(encoding="utf-8")
    assert text.startswith("---\nid: ") and 'title: "Post sobre frota"' in text and "tags: [frota, marketing]" in text
    assert n.path.parent.name == "20-Avoseg"
    hits = sb.search("transportadora sinistro")          # sem acento, singular/plural
    assert hits and hits[0][0].id == n.id and "[" in hits[0][1]


def test_search_is_accent_insensitive_and_scoped_by_area(sb):
    sb.add_note("Reunião", "Discutimos a campanha de indicação", "avoseg")
    sb.add_note("Reuniao", "Indicação de amigos na família", "pessoal")
    assert len(sb.search("reuniao indicacao")) == 2
    assert [n.area for n, _ in sb.search("indicacao", area="pessoal")] == ["pessoal"]


def test_manual_edits_and_deletions_are_picked_up_by_reindex(sb):
    n = sb.add_note("Ideia solta", "conteudo original", "projetos")
    n.path.write_text(n.path.read_text(encoding="utf-8") + "\nacrescentei pitaya", encoding="utf-8")
    import os, time
    os.utime(n.path, (time.time() + 5, time.time() + 5))
    assert sb.reindex() >= 1 and sb.search("pitaya")
    n.path.unlink()
    sb.reindex()
    assert not sb.search("pitaya")


def test_hand_written_note_without_frontmatter_is_indexed(sb):
    p = sb.root / "40-Projetos" / "meu-plano.md"
    p.write_text("# Plano de lançamento\n\nLançar o portal de parceiros em novembro.", encoding="utf-8")
    sb.reindex()
    n = sb.get("Plano de lançamento")
    assert n and n.area == "projetos" and sb.search("portal parceiros novembro")


def test_recall_needs_real_overlap_and_ignores_noise(sb):
    sb.add_note("Reunião com Maria", "Combinamos a campanha de frota para outubro", "avoseg", tags=["frota"])
    assert [n.title for n, _ in sb.recall("o que combinei com a Maria sobre a campanha de frota?")] == ["Reunião com Maria"]
    assert sb.recall("que horas são agora?") == []
    assert sb.recall("toca uma música") == []


def test_graph_connects_related_notes_and_not_unrelated_ones(sb):
    a = sb.add_note("Frota campanha", "campanha de seguro de frota para transportadoras", "avoseg", tags=["frota"])
    b = sb.add_note("Frota arte", "arte do carrossel de seguro de frota", "avoseg", tags=["frota"])
    c = sb.add_note("Receita de bolo", "farinha ovos açúcar forno", "pessoal")
    g = sb.graph()
    ids = [n["id"] for n in g["nodes"]]
    pairs = {frozenset((ids[i], ids[j])) for i, j, _ in g["edges"]}
    assert frozenset((a.id, b.id)) in pairs
    assert not any(c.id in p for p in pairs)
    assert g["total"] >= 3 and {"id", "title", "area", "deg"} <= set(g["nodes"][0])


def test_daily_diary_appends_lines_and_profile_facts_feed_profile(sb):
    sb.append_daily("Liguei para o contador")
    sb.append_daily("Fechei a apólice da frota")
    diary = next(sb.root.joinpath("70-Diario").glob("*.md")).read_text(encoding="utf-8")
    assert diary.count("\n- ") == 2 and "apólice da frota" in diary
    sb.add_profile_fact("Prefere respostas curtas")
    assert "Prefere respostas curtas" in sb.read_profile() and "PREENCHA" not in sb.read_profile()


def test_voice_tools_anotar_buscar_ler(sb):
    changed = []
    tools = {t.name: t for t in make_tools(sb, on_change=changed.append)}
    out = tools["anotar"].func(texto="Ligar para a seguradora sobre o endosso da frota", titulo="Ligar seguradora endosso",
                               area="avoseg", tipo="tarefa", tags=["frota", "endosso"])
    assert "Anotado em avoseg" in out and changed and changed[0].tipo == "tarefa"
    assert "endosso" in tools["buscar_notas"].func(consulta="endosso frota")
    nid = changed[0].id
    assert "Ligar para a seguradora" in tools["ler_nota"].func(referencia=nid)
    assert tools["buscar_notas"].func(consulta="zzzinexistente") .startswith("Não encontrei")
    assert "Anotado" in tools["anotar"].func(texto="x", titulo="Sem área informada")        # área padrão: inbox


def test_voice_brain_injects_relevant_notes_and_profile(sb):
    sb.add_note("Decisão sobre frota", "Decidi focar a campanha de frota em transportadoras de Sorocaba", "decisoes")
    sb.add_profile_fact("Gosta de respostas objetivas")
    seen = {}

    class Client:
        def __init__(self):
            self.messages = self

        def create(self, **kw):
            seen.update(kw)
            return NS(stop_reason="end_turn", content=[NS(type="text", text="ok")])

    tools = make_tools(sb)
    v = Voice(Client(), "claude-opus-5-5", tools, "senhor", "Sorocaba", profile_provider=sb.read_profile,
              context_provider=lambda t: "\n".join(f"- {n.title}: {n.excerpt()}" for n, _ in sb.recall(t)))
    v.ask("o que eu decidi sobre a campanha de frota?")
    user_msg = seen["messages"][0]["content"]
    assert "[Notas relevantes do Second Brain]" in user_msg and "Decisão sobre frota" in user_msg
    assert "Gosta de respostas objetivas" in seen["system"] and "Second Brain" in seen["system"]


class _NoRender:
    def render(self, jobs, size):
        for _, out in jobs:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"png")


class FakeMarketingClient:
    def __init__(self, payload, stop="end_turn"):
        self.messages, self.payload, self.stop, self.calls = self, payload, stop, []

    def create(self, **kw):
        self.calls.append(kw)
        return NS(stop_reason=self.stop, content=[NS(type="text", text=json.dumps(self.payload))])


POST = {
    "titulo_interno": "Frota sem susto", "plataforma": "instagram", "formato": "carrossel",
    "gancho": "Sua frota parada custa mais que o seguro.", "legenda": "Texto da legenda...", "cta": "Chame no WhatsApp",
    "hashtags": ["#seguro", "#frota"], "roteiro": ["Capa", "Problema", "Solução", "CTA"],
    "briefing_visual": "Fundo azul, caminhões", "melhor_horario": "terça, 11h",
    "alternativas_de_gancho": ["Outro gancho"], "observacoes_de_conformidade": "Revisar regras da SUSEP antes de publicar",
}


def test_marketing_blocks_when_brand_profile_is_empty(sb):
    client = FakeMarketingClient(POST)
    tools = {t.name: t for t in marketing.make_tools(sb, client, "claude-opus-5-5")}
    out = tools["criar_post"].func(empresa="Avogroup", tema="institucional")
    assert "perfil de marca" in out.lower() and "definir_marca" in out and client.calls == []


def test_marketing_creates_saves_and_shows_post(sb):
    client = FakeMarketingClient(POST)
    changed, shown = [], []
    tools = {t.name: t for t in marketing.make_tools(sb, client, "claude-opus-5-5", changed.append, shown.append, renderer=_NoRender())}
    out = tools["criar_post"].func(empresa="Avoseg", tema="seguro de frota", plataforma="instagram", formato="carrossel")
    assert "Frota sem susto" in out and "Gancho" in out
    note = changed[0]
    assert note.tipo == "post" and note.area == "avoseg" and note.path.parent.name == "marketing"
    assert "Legenda" in note.body and "Revisar regras da SUSEP" in note.body
    assert shown[0]["hashtags"] == ["#seguro", "#frota"] and shown[0]["roteiro"][0] == "Capa"
    call = client.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema" and call["output_config"]["effort"] == "medium"
    assert "SUSEP" in call["system"] and "Corretora de seguros" in call["system"]      # perfil de marca entrou no contexto
    assert "seguro de frota" in call["messages"][0]["content"]


def test_marketing_avoids_repeating_recent_posts_and_handles_failure(sb):
    client = FakeMarketingClient(POST)
    tools = {t.name: t for t in marketing.make_tools(sb, client, "claude-haiku-4-5", renderer=_NoRender())}
    tools["criar_post"].func(empresa="Avoseg", tema="frota")
    tools["criar_post"].func(empresa="Avoseg", tema="frota de novo")
    assert "Frota sem susto" in client.calls[1]["system"]          # lembra do que já foi criado
    assert "effort" not in client.calls[0]["output_config"]       # Haiku não recebe o parâmetro
    bad = {t.name: t for t in marketing.make_tools(sb, FakeMarketingClient(POST, stop="refusal"), "claude-opus-5-5")}
    assert "Não consegui criar o post" in bad["criar_post"].func(empresa="Avoseg", tema="x")


def test_define_brand_makes_empty_company_ready(sb):
    client = FakeMarketingClient(POST)
    tools = {t.name: t for t in marketing.make_tools(sb, client, "claude-opus-5-5")}
    assert sb.brand("avogroup")[1] is False
    tools["definir_marca"].func(empresa="Avogroup", informacoes=(
        "- Holding que reúne corretora, consultoria e tecnologia.\n- Público: empresas médias de Sorocaba e região.\n"
        "- Tom: profissional, próximo e direto.\n- Diferencial: atendimento humano com tecnologia.\n"))
    assert sb.brand("avogroup")[1] is True


def test_mostrar_notas_lists_recent_or_searched_notes_for_the_screen(sb):
    sb.add_note("Ideia de post de frota", "carrossel de seguro de frota", "avoseg", "ideia")
    sb.add_note("Comprar café", "café em grãos", "pessoal")
    shown = []
    tools = {t.name: t for t in make_tools(sb, on_list=lambda items, titulo: shown.append((items, titulo)))}
    out = tools["mostrar_notas"].func()
    assert "Abri a lista na tela" in out and len(shown[0][0]) >= 2 and shown[0][1] == "recentes"
    tools["mostrar_notas"].func(consulta="carrossel")
    assert [n["title"] for n in shown[1][0]] == ["Ideia de post de frota"] and "body" in shown[1][0][0]
    assert tools["mostrar_notas"].func(consulta="zzz").startswith("Não encontrei")


def test_hud_cards_are_ephemeral_and_not_replayed():
    import http.client
    from jarvis.hud import Hud

    hud = Hud(port=0)
    hud.start()
    hud.card("notes", {"items": [], "titulo": "x"})          # ninguém conectado: descartado
    ev = http.client.HTTPConnection("127.0.0.1", hud.port, timeout=3)
    ev.request("GET", "/events")
    resp = ev.getresponse()
    resp.fp.readline(); resp.fp.readline()                   # estado inicial
    hud.card("notes", {"items": [], "titulo": "y"})
    assert b'"type": "card"' in resp.fp.readline()


def test_starter_files_do_not_count_as_user_notes(sb):
    assert sb.count() == 0 and sb.recent(10) == [] and sb.graph()["nodes"] == []
    sb.add_note("Minha primeira nota", "olá", "pessoal")
    assert sb.count() == 1 and [n.title for n in sb.recent(10)] == ["Minha primeira nota"]
    assert sb.search("avoseg corretora")          # mas o perfil de marca continua pesquisável
