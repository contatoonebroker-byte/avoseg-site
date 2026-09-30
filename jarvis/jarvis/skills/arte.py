"""Arte dos posts: layouts da marca em HTML/CSS renderizados para PNG (texto sempre correto).

O Claude escreve os textos dos slides; aqui eles viram imagens 1080x1350 (feed), 1080x1080 ou 1080x1920
(stories) com as cores, a fonte e o logo da empresa. Um gerador de imagem (opcional) só entra para o fundo.
"""
from __future__ import annotations

import base64
import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from . import imagem

SIZES = {"feed": (1080, 1350), "quadrado": (1080, 1080), "story": (1080, 1920)}
ESTILOS = ("misto", "escuro", "claro")
RODAPE_PADRAO = "Sujeito à análise de risco e às condições da apólice."


@dataclass
class Brand:
    nome: str = "Avoseg"
    navy: str = "#0F2744"
    navy_mid: str = "#1B3A6B"
    blue: str = "#2563EB"
    gold: str = "#F59E0B"
    sky: str = "#EFF6FF"
    instagram: str = ""
    whatsapp: str = ""
    site: str = ""
    rodape: str = RODAPE_PADRAO
    logo: Path | None = None


def brand_from_text(nome: str, text: str, logo: Path | None = None) -> Brand:
    """Lê do arquivo marca.md: linhas como "- Cores: #0F2744 #2563EB #F59E0B", "- Instagram: @avoseg",
    "- WhatsApp: (15) 99999-9999", "- Site: avoseg.com.br", "- Rodapé legal: ..."."""
    b = Brand(nome=nome, logo=logo if logo and logo.exists() else None)

    def field(label: str) -> str:
        m = re.search(rf"^\s*-\s*{label}\s*:\s*(.+)$", text, re.I | re.M)
        v = m.group(1).strip() if m else ""
        return "" if "PREENCHA" in v.upper() else v

    cores = re.findall(r"#[0-9a-fA-F]{6}\b", field("Cores"))
    for attr, val in zip(("navy", "blue", "gold", "navy_mid", "sky"), cores):
        setattr(b, attr, val)
    b.instagram, b.whatsapp, b.site = field("Instagram"), field("WhatsApp"), field("Site")
    b.rodape = field(r"Rodap[eé] legal") or RODAPE_PADRAO
    return b


def plan_slides(post: dict, formato: str = "") -> list[dict]:
    """Slides da arte: usa 'slides' do post; se não houver, monta capa + CTA a partir do gancho e da legenda."""
    slides = [s for s in post.get("slides") or [] if s.get("titulo")]
    if slides:
        return slides
    legenda = re.sub(r"\s+", " ", post.get("legenda", "")).strip()
    return [
        {"tipo": "capa", "kicker": post.get("plataforma", "").upper(), "titulo": post.get("gancho", ""),
         "texto": legenda[:120] + ("…" if len(legenda) > 120 else "")},
        {"tipo": "cta", "kicker": "", "titulo": post.get("cta", ""), "texto": ""},
    ]


def _size_for(formato: str) -> tuple[str, tuple[int, int]]:
    f = (formato or "").lower()
    key = "story" if any(k in f for k in ("stor", "reel", "tiktok", "vertical")) else \
          "quadrado" if "quadrad" in f else "feed"
    return key, SIZES[key]


def _title_px(text: str, base: int) -> int:
    n = len(text)
    return base if n <= 28 else int(base * .86) if n <= 48 else int(base * .72) if n <= 72 else int(base * .6)


def _data_uri(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def slide_html(slide: dict, idx: int, total: int, brand: Brand, size: tuple[int, int],
               estilo: str = "misto", bg_image: Path | None = None) -> str:
    w, h = size
    tipo = slide.get("tipo", "conteudo")
    esc = html.escape
    escuro = estilo == "escuro" or (estilo == "misto" and tipo == "capa")
    cta = tipo == "cta" and estilo != "claro"
    if cta:
        bg, fg, acc = f"linear-gradient(150deg,{brand.blue},{brand.navy_mid} 70%)", "#fff", brand.gold
    elif escuro:
        bg, fg, acc = f"linear-gradient(160deg,{brand.navy},{brand.navy_mid})", "#fff", brand.gold
    else:
        bg, fg, acc = f"linear-gradient(180deg,#fff,{brand.sky})", brand.navy, brand.blue
    bgimg = _data_uri(bg_image) if tipo == "capa" else ""
    overlay = (f"background:linear-gradient(180deg,rgba(15,39,68,.55),rgba(15,39,68,.88)),url({bgimg}) center/cover;"
               if bgimg else f"background:{bg};")
    logo = _data_uri(brand.logo)
    logo_html = (f'<img src="{logo}" style="height:64px;max-width:320px;object-fit:contain">' if logo else
                 f'<div class="mark"><i></i>{esc(brand.nome)}</div>')
    titulo = slide.get("titulo", "")
    big = 100 if tipo == "capa" else 84 if tipo == "cta" else 76
    tpx = _title_px(titulo, int(big * w / 1080))
    handle = " · ".join(x for x in (brand.instagram, brand.whatsapp, brand.site) if x)
    dots = "".join(f'<b class="{"on" if i == idx else ""}"></b>' for i in range(total)) if total > 1 else ""
    kicker = f'<div class="kicker">{esc(slide["kicker"])}</div>' if slide.get("kicker") else ""
    texto = f'<p class="txt">{esc(slide["texto"])}</p>' if slide.get("texto") else ""
    swipe = '<div class="swipe">Arraste para o lado <span>→</span></div>' if tipo == "capa" and total > 1 else ""
    pill = f'<div class="pill">{esc(slide["texto"])}</div>' if cta and slide.get("texto") else ""
    if cta:
        texto = ""
    num = f'<div class="num">{idx + 1:02d}</div>' if tipo == "conteudo" else ""
    left = swipe or (f'<div class="foot">{esc(handle)}</div>' if handle else "<div></div>")
    right = f'<div class="legal">{esc(brand.rodape)}</div>' if cta and brand.rodape else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;overflow:hidden}}
body{{font-family:'Sora','Helvetica Neue',Arial,sans-serif;color:{fg};{overlay}position:relative}}
.deco{{position:absolute;right:-{int(w*.22)}px;top:-{int(w*.22)}px;width:{int(w*.7)}px;height:{int(w*.7)}px;border-radius:50%;
  background:radial-gradient(circle,{acc}33,transparent 68%)}}
.deco2{{position:absolute;left:-{int(w*.3)}px;bottom:-{int(w*.36)}px;width:{int(w*.62)}px;height:{int(w*.62)}px;border-radius:50%;
  border:2px solid {acc}40}}
.wrap{{position:absolute;inset:0;padding:{int(w*.08)}px;display:flex;flex-direction:column}}
.top{{display:flex;justify-content:space-between;align-items:center;min-height:64px}}
.mark{{font-weight:800;font-size:44px;letter-spacing:-.02em;display:flex;align-items:center;gap:14px}}
.mark i{{width:16px;height:44px;border-radius:5px;background:{acc};transform:skewX(-14deg);display:block}}
.dots{{display:flex;gap:10px}} .dots b{{width:14px;height:14px;border-radius:50%;background:{fg};opacity:.25}}
.dots b.on{{opacity:1;background:{acc};width:34px;border-radius:8px}}
.main{{flex:1;display:flex;flex-direction:column;justify-content:center;gap:{int(h*.025)}px}}
.kicker{{font-size:30px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:{acc}}}
h1{{font-size:{tpx}px;line-height:1.08;font-weight:800;letter-spacing:-.025em}}
.txt{{font-size:{int(42*w/1080)}px;line-height:1.4;font-weight:400;opacity:.88;max-width:92%}}
.bar{{width:120px;height:10px;border-radius:5px;background:{acc}}}
.num{{font-size:{int(150*w/1080)}px;font-weight:800;line-height:1;color:{acc};opacity:.35;letter-spacing:-.04em}}
.pill{{align-self:flex-start;background:{acc};color:{brand.navy};font-weight:800;font-size:{int(46*w/1080)}px;
  padding:26px 48px;border-radius:999px;margin-top:10px}}
.swipe{{font-size:32px;font-weight:600;letter-spacing:.04em;opacity:.85;display:flex;gap:12px;align-items:center}}
.swipe span{{color:{acc};font-size:44px}}
.bottom{{display:flex;justify-content:space-between;align-items:flex-end;gap:30px;min-height:56px}}
.foot{{font-size:28px;font-weight:600;opacity:.8}}
.legal{{font-size:22px;opacity:.6;max-width:55%;text-align:right;line-height:1.3}}
</style></head><body>
<div class="deco"></div><div class="deco2"></div>
<div class="wrap">
  <div class="top">{logo_html}<div class="dots">{dots}</div></div>
  <div class="main">{num}{kicker}<div class="bar"></div><h1>{esc(titulo)}</h1>{texto}{pill}</div>
  <div class="bottom">{left}{right}</div>
</div></body></html>"""


class Renderer:
    """Renderiza HTML para PNG com o Chrome (do Mac, via Playwright) sem precisar baixar navegador."""

    def render(self, jobs: list[tuple[str, Path]], size: tuple[int, int]) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Falta instalar o Playwright: pip install playwright") from e
        w, h = size
        with sync_playwright() as p:
            browser = None
            for kwargs in ({"channel": "chrome"}, {}):
                try:
                    browser = p.chromium.launch(**kwargs)
                    break
                except Exception:
                    continue
            if browser is None:
                raise RuntimeError("Não achei o Google Chrome nem o Chromium do Playwright "
                                   "(rode: playwright install chromium)")
            try:
                page = browser.new_page(viewport={"width": w, "height": h})
                for html_text, out in jobs:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    page.set_content(html_text, wait_until="load", timeout=20000)
                    try:
                        page.evaluate("document.fonts.ready.then(() => true)")
                    except Exception:
                        pass
                    page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": w, "height": h})
            finally:
                browser.close()


def make_art(post: dict, brand: Brand, out_dir: Path, formato: str = "", estilo: str = "misto",
             bg_image: Path | None = None, renderer: Renderer | None = None) -> list[Path]:
    """Gera os PNGs (um por slide) em out_dir e devolve os caminhos, na ordem."""
    estilo = estilo if estilo in ESTILOS else "misto"
    _, size = _size_for(formato or post.get("formato", ""))
    slides = plan_slides(post, formato)
    jobs = [(slide_html(s, i, len(slides), brand, size, estilo, bg_image),
             out_dir / f"slide-{i + 1:02d}.png") for i, s in enumerate(slides)]
    (renderer or Renderer()).render(jobs, size)
    return [out for _, out in jobs]


def ia_compose_html(png: bytes, size: tuple[int, int], brand: Brand, tipo: str) -> str:
    """Imagem criada pela IA (com o texto do Claude dentro), ajustada ao formato. Nada de texto por cima, só:
    o logo num cantinho e, no slide final, uma faixa opaca no rodapé com contatos e aviso legal."""
    w, h = size
    src = "data:image/png;base64," + base64.b64encode(png).decode()
    logo = _data_uri(brand.logo)
    logo_html = (f'<div style="position:absolute;left:{int(w*.05)}px;top:{int(w*.05)}px;background:rgba(255,255,255,.94);'
                 f'padding:12px 18px;border-radius:14px"><img src="{logo}" style="height:{int(w*.055)}px;display:block"></div>'
                 if logo else "")
    handle = " · ".join(x for x in (brand.instagram, brand.whatsapp, brand.site) if x)
    band = ""
    if tipo == "cta" and (handle or brand.rodape):
        esc = html.escape
        band = (f'<div style="position:absolute;left:0;right:0;bottom:0;height:{int(h*.085)}px;background:{brand.navy};'
                f'color:#fff;display:flex;justify-content:space-between;align-items:center;padding:0 {int(w*.05)}px;'
                f'font-family:Helvetica,Arial,sans-serif;gap:24px"><span style="font-size:{int(w*.026)}px;font-weight:700">'
                f'{esc(handle)}</span><span style="font-size:{int(w*.02)}px;opacity:.75;text-align:right">{esc(brand.rodape)}</span></div>')
    return (f'<!doctype html><html><body style="margin:0;width:{w}px;height:{h}px;position:relative;overflow:hidden">'
            f'<img src="{src}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover">'
            f'{logo_html}{band}</body></html>')


def make_art_ia(post: dict, brand: Brand, out_dir: Path, formato: str, gen, renderer: Renderer | None = None,
                estilo: str = "misto", progress=print, workers: int = 3) -> tuple[list[Path], list[str]]:
    """A IA desenha cada slide com o texto do Claude. `gen(prompt, api_size) -> bytes`.
    Se um slide falhar, ele cai para o layout da marca (sem texto duplicado). Devolve (arquivos, avisos)."""
    estilo = estilo if estilo in ESTILOS else "misto"
    key, size = _size_for(formato or post.get("formato", ""))
    slides = plan_slides(post, formato)[:imagem.MAX_SLIDES_IA]
    api_size = "1024x1024" if key == "quadrado" else "1024x1536"
    prompts = [imagem.build_slide_prompt(s, post, brand, i, len(slides)) for i, s in enumerate(slides)]
    results: dict[int, bytes | Exception] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(slides)))) as ex:
        futures = {ex.submit(gen, p, api_size): i for i, p in enumerate(prompts)}
        for f in as_completed(futures):
            i = futures[f]
            try:
                results[i] = f.result()
            except Exception as e:  # noqa: BLE001
                results[i] = e
            progress(f"[arte] slide {i + 1}/{len(slides)} {'pronto' if isinstance(results[i], bytes) else 'falhou'}")
    jobs, avisos = [], []
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(slides):
        out = out_dir / f"slide-{i + 1:02d}.png"
        if isinstance(results[i], bytes):
            (out_dir / f"slide-{i + 1:02d}-ia.png").write_bytes(results[i])
            jobs.append((ia_compose_html(results[i], size, brand, s.get("tipo", "")), out))
        else:
            avisos.append(f"slide {i + 1} caiu para o layout da marca ({results[i]})")
            jobs.append((slide_html(s, i, len(slides), brand, size, estilo), out))
    (renderer or Renderer()).render(jobs, size)
    return [out for _, out in jobs], avisos
