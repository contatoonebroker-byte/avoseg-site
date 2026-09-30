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
    assert "Arte criada (no layout da marca): 3 imagem" in out and r.calls and "logo.png" in out         # avisa que falta o logo
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


PNG = b"\x89PNG fake ai image"


def test_slide_prompt_carries_the_exact_claude_text_and_forbids_extra_text():
    brand = arte.Brand()
    slide = POST_COM_SLIDES["slides"][0]
    p = imagem.build_slide_prompt(slide, POST_COM_SLIDES, brand, 0, 3)
    assert '"Sua frota parada custa mais"' in p and '"Entenda como proteger"' in p and '"Seguro de frota"' in p
    assert "EXATAMENTE" in p and "NENHUM outro texto" in p and "#0F2744" in p and "slide 1 de 3" in p
    cta = imagem.build_slide_prompt(POST_COM_SLIDES["slides"][2], POST_COM_SLIDES, brand, 2, 3)
    assert "BOTÃO" in cta and '"Chame no WhatsApp"' in cta


def test_ai_art_draws_each_slide_with_claude_text_and_writes_nothing_on_top(tmp_path):
    r, calls = FakeRenderer(), []
    brand = arte.Brand(instagram="@avoseg", rodape="Sujeito à análise.")
    files, avisos = arte.make_art_ia(POST_COM_SLIDES, brand, tmp_path, "carrossel",
                                     lambda prompt, size: calls.append((prompt, size)) or PNG, r, progress=lambda m: None)
    assert len(calls) == 3 and {c[1] for c in calls} == {"1024x1536"} and avisos == []
    assert [f.name for f in files] == ["slide-01.png", "slide-02.png", "slide-03.png"]
    size, htmls = r.calls[0]
    assert size == (1080, 1350)
    assert all('<img src="data:image/png;base64' in h and "<h1" not in h for h in htmls)      # nenhum texto nosso sobre a imagem
    assert "Sujeito à análise." not in htmls[0] and "Sujeito à análise." in htmls[2]         # rodapé legal só na faixa do slide final
    assert (tmp_path / "slide-01-ia.png").read_bytes() == PNG


def test_ai_art_overlays_only_the_real_logo_and_uses_square_size_for_square_posts(tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG-logo")
    r, sizes = FakeRenderer(), []
    arte.make_art_ia(POST_COM_SLIDES, arte.Brand(logo=logo), tmp_path / "o", "quadrado",
                     lambda p, size: sizes.append(size) or PNG, r, progress=lambda m: None)
    assert set(sizes) == {"1024x1024"} and r.calls[0][0] == (1080, 1080)
    assert "data:image/png;base64,iVBOR" in r.calls[0][1][0] and r.calls[0][1][0].count("<img") == 2   # imagem + logo


def test_ai_art_falls_back_to_layout_per_failed_slide_and_caps_cost(tmp_path):
    r = FakeRenderer()

    def gen(prompt, size):
        if "slide 2 de 3" in prompt:
            raise RuntimeError("limite de uso")
        return PNG

    files, avisos = arte.make_art_ia(POST_COM_SLIDES, arte.Brand(), tmp_path, "feed", gen, r, progress=lambda m: None)
    htmls = r.calls[0][1]
    assert "<h1" not in htmls[0] and "<h1" in htmls[1] and "<h1" not in htmls[2]          # só o 2º caiu para o layout
    assert len(avisos) == 1 and "slide 2" in avisos[0] and "limite de uso" in avisos[0]
    many = {**POST, "slides": [{"tipo": "conteudo", "kicker": "", "titulo": f"t{i}", "texto": ""} for i in range(20)]}
    calls = []
    arte.make_art_ia(many, arte.Brand(), tmp_path / "m", "feed", lambda p, s: calls.append(1) or PNG, FakeRenderer(),
                     progress=lambda m: None)
    assert len(calls) == imagem.MAX_SLIDES_IA


def test_marketing_uses_ai_art_automatically_when_configured_and_layout_when_asked(sb):
    r, calls = FakeRenderer(), []
    fake = lambda prompt, prov, key, model, size, quality: calls.append((prov, model, size, quality)) or PNG

    sem_chave, _ = _tools(sb, POST_COM_SLIDES, renderer=r, image_fn=fake)             # sem chave: layout, em silêncio
    out = sem_chave["criar_post"].func(empresa="Avoseg", tema="x")
    assert "no layout da marca" in out and not calls and "<h1" in r.calls[-1][1][0]
    assert "não está configurada" in sem_chave["criar_arte"].func(com_ia=True)

    cfg = ("openai", "k", "gpt-image-1", "low")
    com_chave, _ = _tools(sb, POST_COM_SLIDES, renderer=r, image_cfg=cfg, image_fn=fake)
    out = com_chave["criar_post"].func(empresa="Avoseg", tema="y")
    assert "desenhada pela IA" in out and len(calls) == 3 and calls[0] == ("openai", "gpt-image-1", "1024x1536", "low")
    assert "<h1" not in r.calls[-1][1][0]                                              # texto só dentro da imagem da IA
    com_chave["criar_arte"].func(com_ia=False)                                          # "só o layout": grátis
    assert len(calls) == 3 and "<h1" in r.calls[-1][1][0]
    com_chave["criar_arte"].func(estilo="escuro")                                       # refazer usa IA por padrão
    assert len(calls) == 6


def test_image_provider_turns_on_with_the_key_and_off_with_off():
    from jarvis.config import _image_provider

    assert _image_provider("", "sk-abc") == "openai"
    assert _image_provider("none", "sk-abc") == "openai"        # "none" do .env.example antigo não trava
    assert _image_provider("", "") == "none"
    assert _image_provider("off", "sk-abc") == "none"


def test_openai_image_call_shape_quality_retry_and_errors(monkeypatch):
    import io
    import urllib.error

    seen = []

    class Resp:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(self.payload).encode()

    def fake_urlopen(req, timeout=0):
        body = json.loads(req.data)
        seen.append((req.full_url, body, req.headers["Authorization"]))
        return Resp({"data": [{"b64_json": base64.b64encode(b"PNGDATA").decode()}]})

    monkeypatch.setattr(imagem.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(imagem.json, "load", lambda r: json.loads(r.read()))
    assert imagem.generate_image("p", "openai", "KEY", "gpt-image-1", "1024x1536", "medium") == b"PNGDATA"
    url, body, auth = seen[0]
    assert url.endswith("/v1/images/generations") and body["quality"] == "medium" and body["size"] == "1024x1536"
    assert auth == "Bearer KEY"

    tentativas = []

    def picky(req, timeout=0):
        body = json.loads(req.data)
        tentativas.append("quality" in body)
        if "quality" in body:
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b'{"error":{"message":"Unknown parameter: quality"}}'))
        return Resp({"data": [{"b64_json": base64.b64encode(b"OK").decode()}]})

    monkeypatch.setattr(imagem.urllib.request, "urlopen", picky)
    monkeypatch.setattr(imagem.json, "load", lambda r: json.loads(r.read()))
    assert imagem.generate_image("p", "openai", "K") == b"OK" and tentativas == [True, False]     # tenta de novo sem quality

    def denied(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 403, "no", {}, io.BytesIO(b'{"error":{"message":"organization must be verified"}}'))

    monkeypatch.setattr(imagem.urllib.request, "urlopen", denied)
    with pytest.raises(RuntimeError, match="HTTP 403.*verified"):
        imagem.generate_image("p", "openai", "K")
    with pytest.raises(RuntimeError, match="não configurado"):
        imagem.generate_image("p", "none", "", "m")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        imagem.generate_image("p", "openai", "", "m")


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
