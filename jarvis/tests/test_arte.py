import base64
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.secondbrain import Brain  # noqa: E402
from jarvis.skills import arte, imagem, marketing  # noqa: E402
from test_secondbrain import POST, FakeMarketingClient  # noqa: E402


class FakeRenderer:
    """Não abre navegador: só registra o pedido e grava arquivos de mentira."""

    def __init__(self):
        self.calls = []

    def render(self, jobs, size):
        self.calls.append((size, [h for h, _ in jobs]))
        for _, out in jobs:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"\x89PNG fake")


POST_COM_SLIDES = {**POST, "slides": [
    {"tipo": "capa", "kicker": "Seguro de frota", "titulo": "Sua frota parada custa mais", "texto": "Entenda como proteger"},
    {"tipo": "conteudo", "kicker": "O problema", "titulo": "Sinistro sem cobertura", "texto": "O prejuízo vai além do conserto"},
    {"tipo": "cta", "kicker": "", "titulo": "Vamos analisar sua frota?", "texto": "Chame no WhatsApp"}]}


def test_brand_is_read_from_marca_md_and_ignores_unfilled_fields():
    text = ("# Marca\n## Identidade visual\n- Cores: #112233 #445566 #778899\n- Instagram: @avoseg\n"
            "- WhatsApp: PREENCHA\n- Site: avoseg.com.br\n- Rodapé legal: Consulte as condições.\n")
    b = arte.brand_from_text("Avoseg", text)
    assert (b.navy, b.blue, b.gold) == ("#112233", "#445566", "#778899")
    assert b.instagram == "@avoseg" and b.whatsapp == "" and b.site == "avoseg.com.br" and b.rodape == "Consulte as condições."
    assert arte.brand_from_text("X", "sem nada").navy == "#0F2744"      # padrão: cores do site


def test_slide_html_escapes_text_and_uses_brand_colors_and_size():
    b = arte.Brand(instagram="@avoseg")
    slide = {"tipo": "conteudo", "kicker": "<b>x</b>", "titulo": '"><img src=x onerror=alert(1)>', "texto": "a & b"}
    h = arte.slide_html(slide, 1, 4, b, (1080, 1350))
    assert "<img src=x" not in h and "&lt;img src=x" in h and "a &amp; b" in h
    assert "width:1080px;height:1350px" in h and "#2563EB" in h and ">02<" in h and "@avoseg" in h


def test_cta_slide_carries_legal_footer_and_button():
    h = arte.slide_html({"tipo": "cta", "kicker": "", "titulo": "Vamos?", "texto": "Chame no WhatsApp"}, 3, 4,
                        arte.Brand(), (1080, 1350))
    assert "Chame no WhatsApp" in h and arte.RODAPE_PADRAO in h


def test_make_art_picks_size_by_format_and_one_image_per_slide(tmp_path):
    r = FakeRenderer()
    files = arte.make_art(POST_COM_SLIDES, arte.Brand(), tmp_path / "a", "carrossel", renderer=r)
    assert [f.name for f in files] == ["slide-01.png", "slide-02.png", "slide-03.png"] and r.calls[0][0] == (1080, 1350)
    arte.make_art(POST_COM_SLIDES, arte.Brand(), tmp_path / "b", "stories", renderer=r)
    arte.make_art(POST_COM_SLIDES, arte.Brand(), tmp_path / "c", "quadrado", renderer=r)
    assert [c[0] for c in r.calls] == [(1080, 1350), (1080, 1920), (1080, 1080)]


def test_plan_slides_falls_back_to_hook_and_cta_when_model_sent_no_slides():
    s = arte.plan_slides({"gancho": "Gancho forte", "legenda": "Texto longo " * 30, "cta": "Chame", "plataforma": "instagram"})
    assert [x["tipo"] for x in s] == ["capa", "cta"] and s[0]["titulo"] == "Gancho forte" and s[0]["texto"].endswith("…")


CHROMIUM = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium")


@pytest.mark.skipif(not Path(CHROMIUM).exists(), reason="sem Chromium para renderizar de verdade")
def test_real_render_produces_png_with_expected_dimensions(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")

    class Real(arte.Renderer):
        def render(self, jobs, size):
            with pw.sync_playwright() as p:
                b = p.chromium.launch(executable_path=CHROMIUM)
                pg = b.new_page(viewport={"width": size[0], "height": size[1]})
                for h, out in jobs:
                    pg.set_content(h, wait_until="domcontentloaded")
                    pg.screenshot(path=str(out))
                b.close()

    files = arte.make_art(POST_COM_SLIDES, arte.Brand(), tmp_path, "feed", renderer=Real())
    from struct import unpack
    w, h = unpack(">II", files[0].read_bytes()[16:24])
    assert (w, h) == (1080, 1350) and len(files) == 3


@pytest.fixture
def sb(tmp_path):
    return Brain(tmp_path / "brain")


def _tools(sb, payload, **kw):
    client = FakeMarketingClient(payload)
    return {t.name: t for t in marketing.make_tools(sb, client, "claude-opus-5-5", **kw)}, client


def test_criar_post_generates_art_saves_sidecar_and_notifies_screen(sb):
    r, shown = FakeRenderer(), []
    tools, _ = _tools(sb, POST_COM_SLIDES | {"titulo_interno": "Frota sem susto"}, renderer=r, on_art=shown.append)
    out = tools["criar_post"].func(empresa="Avoseg", tema="frota", formato="carrossel")
    assert "Arte criada: 3 imagem" in out and r.calls and "logo.png" in out         # avisa que falta o logo
    assert shown[0]["images"][0].startswith("20-Avoseg/marketing/arte/") and len(shown[0]["images"]) == 3
    assert all((sb.root / i).exists() for i in shown[0]["images"])
    assert list((sb.root / "20-Avoseg" / "marketing").glob("*.json"))


def test_criar_post_without_art_and_criar_arte_later_with_other_style(sb):
    r = FakeRenderer()
    tools, _ = _tools(sb, POST_COM_SLIDES, renderer=r)
    assert "Arte criada" not in tools["criar_post"].func(empresa="Avoseg", tema="x", com_arte=False) and not r.calls
    assert "Arte criada" in tools["criar_arte"].func(estilo="escuro")
    assert "#0F2744" in r.calls[0][1][1]                                             # slide de conteúdo no estilo escuro


def test_criar_arte_can_redo_a_saved_post_by_title_and_fails_clearly_without_post(sb):
    tools, _ = _tools(sb, POST_COM_SLIDES, renderer=FakeRenderer())
    assert "Ainda não criei nenhum post" in tools["criar_arte"].func()
    tools["criar_post"].func(empresa="Avoseg", tema="x", com_arte=False)
    novo, _ = _tools(sb, POST_COM_SLIDES, renderer=FakeRenderer())                   # "nova conversa": sem memória do último
    assert "Arte criada" in novo["criar_arte"].func(referencia="Post: Frota sem susto")
    assert "Não achei" in novo["criar_arte"].func(referencia="não existe")


def test_ai_background_only_when_configured_and_requested(sb):
    used = []
    r = FakeRenderer()
    # sem provedor configurado: avisa e faz a arte só com o layout
    tools, _ = _tools(sb, POST_COM_SLIDES, renderer=r, image_fn=lambda *a: used.append(a) or b"x")
    tools["criar_post"].func(empresa="Avoseg", tema="x", com_arte=False)
    assert "não está configurada" in tools["criar_arte"].func(com_ia=True) and not used
    # com provedor: gera o fundo e usa na capa
    tools2, _ = _tools(sb, POST_COM_SLIDES, renderer=r, image_cfg=("openai", "k", "gpt-image-1"),
                       image_fn=lambda prompt, prov, key, model: used.append((prompt, prov, model)) or b"\x89PNGfundo")
    tools2["criar_post"].func(empresa="Avoseg", tema="x", com_arte=False)
    out = tools2["criar_arte"].func(com_ia=True)
    assert "Arte criada" in out and used and used[0][1] == "openai" and "NÃO inclua texto" in used[0][0]
    assert "data:image/png;base64" in r.calls[-1][1][0]                              # o fundo entrou na capa
    # falha do gerador não derruba a arte
    def boom(*a):
        raise RuntimeError("cota esgotada")
    tools3, _ = _tools(sb, POST_COM_SLIDES, renderer=r, image_cfg=("openai", "k", "m"), image_fn=boom)
    tools3["criar_post"].func(empresa="Avoseg", tema="x", com_arte=False)
    out = tools3["criar_arte"].func(com_ia=True)
    assert "Arte criada" in out and "cota esgotada" in out


def test_openai_image_call_shape_and_error_handling(monkeypatch):
    seen = {}

    class Resp:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(self.payload).encode()

    def fake_urlopen(req, timeout=0):
        seen["url"], seen["body"], seen["auth"] = req.full_url, json.loads(req.data), req.headers["Authorization"]
        return Resp({"data": [{"b64_json": base64.b64encode(b"PNGDATA").decode()}]})

    monkeypatch.setattr(imagem.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(imagem.json, "load", lambda r: json.loads(r.read()))
    assert imagem.generate_background("p", "openai", "KEY", "gpt-image-1") == b"PNGDATA"
    assert seen["url"].endswith("/v1/images/generations") and seen["body"]["model"] == "gpt-image-1"
    assert seen["auth"] == "Bearer KEY"
    with pytest.raises(RuntimeError, match="não configurado"):
        imagem.generate_background("p", "none", "", "m")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        imagem.generate_background("p", "openai", "", "m")


def test_hud_serves_only_art_images_and_blocks_traversal(tmp_path):
    import http.client

    from jarvis.hud import Hud

    art = tmp_path / "20-Avoseg" / "marketing" / "arte" / "post1"
    art.mkdir(parents=True)
    (art / "slide-01.png").write_bytes(b"\x89PNG-ok")
    (tmp_path / "20-Avoseg" / "marketing" / "segredo.png").write_bytes(b"nao")
    (tmp_path / "perfil.md").write_text("privado")
    hud = Hud(port=0)
    hud.art_root = tmp_path
    hud.start()

    def get(path):
        c = http.client.HTTPConnection("127.0.0.1", hud.port, timeout=3)
        c.request("GET", path)
        r = c.getresponse()
        return r.status, r.read(), r.getheader("Content-Type")

    assert get("/arte/20-Avoseg/marketing/arte/post1/slide-01.png") == (200, b"\x89PNG-ok", "image/png")
    assert get("/arte/20-Avoseg/marketing/arte/../segredo.png")[0] == 404
    assert get("/arte/perfil.md")[0] == 404
    assert get("/arte/20-Avoseg/marketing/arte/post1/%2e%2e/%2e%2e/segredo.png")[0] == 404
    assert get("/arte/20-Avoseg/marketing/arte/post1/nao-existe.png")[0] == 404
