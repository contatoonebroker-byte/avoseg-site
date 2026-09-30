"""Skill de marketing: o Jarvis age como estrategista e copywriter sênior das suas empresas.

Usa o perfil de marca guardado no Second Brain (20-Avoseg/marca.md, 30-Avogroup/marca.md) e salva
cada post como nota (20-Avoseg/marketing/...), para o cérebro lembrar do que já foi publicado.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..secondbrain.store import AREAS, Brain, norm
from ..tools import Tool
from . import arte, imagem

ESPECIALISTA = """Você é estrategista de marketing e copywriter sênior, especialista em marketing de conteúdo \
para corretoras de seguros e serviços financeiros no Brasil (Instagram, Facebook, LinkedIn, WhatsApp, Reels/TikTok e e-mail).

Como você trabalha:
- Pensa em funil (atrair, educar, converter, reter), em prova social e em uma ideia central por peça.
- Abre com um gancho forte nas 2 primeiras linhas (é o que aparece antes do "ver mais").
- Escreve em português do Brasil, natural e humano, sem clichês ("você sabia que"), sem jargão de seguro sem explicar.
- Uma chamada para ação clara e única (WhatsApp, link na bio, cotação, indicar um amigo).
- Hashtags relevantes e específicas (5 a 10), sem exagero. Pensa em acessibilidade (texto alternativo, legendas).
- Adapta o formato: carrossel (capa forte, 1 ideia por slide, fechamento com CTA), Reels (roteiro por cena com tempo),
  Stories (sequência curta com enquete ou caixinha), LinkedIn (mais argumento e dados), WhatsApp (curto e direto).
- Usa SOMENTE fatos presentes no perfil de marca e no pedido. Se faltar um dado importante (preço, prazo, condição),
  não invente: escreva "[CONFIRMAR: ...]" no ponto exato.

Texto da ARTE (campo 'slides'): são os textos curtos que vão escritos na imagem, então precisam funcionar sozinhos.
- Carrossel: 1 capa + 3 a 6 slides de conteúdo + 1 slide final de chamada para ação. Post único ou stories: 1 a 3 slides.
- Título com até 9 palavras (forte e claro); 'texto' com até 25 palavras; 'kicker' é um rótulo curto (2 a 4 palavras).
- No slide final (tipo cta), 'titulo' é a pergunta ou convite e 'texto' é o botão (ex.: "Chame no WhatsApp").
- Nunca coloque "[CONFIRMAR]" nos slides: se faltar um dado, simplesmente não o use na arte.

Conformidade (seguros no Brasil), sempre:
- Não prometa ganho, economia garantida, "menor preço do mercado", aprovação ou indenização garantida.
- Não use medo de forma abusiva nem exponha dados pessoais, sinistros ou nomes de clientes.
- Não cite seguradoras, concorrentes ou marcas de terceiros sem autorização do usuário.
- Toda oferta ou condição comercial deve ficar sujeita a análise e às condições da apólice, e a peça deve ser
  revisada quanto às regras de publicidade da SUSEP e da seguradora antes de publicar. Resuma isso em
  'observacoes_de_conformidade'.
"""

POST_SCHEMA = {
    "type": "object",
    "properties": {
        "titulo_interno": {"type": "string"}, "plataforma": {"type": "string"}, "formato": {"type": "string"},
        "gancho": {"type": "string"}, "legenda": {"type": "string"}, "cta": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "roteiro": {"type": "array", "items": {"type": "string"},
                    "description": "Slides do carrossel ou cenas do vídeo/stories, na ordem. Vazio se for post único."},
        "briefing_visual": {"type": "string", "description": "Instruções para a arte ou o vídeo (para designer/Canva)."},
        "melhor_horario": {"type": "string"},
        "alternativas_de_gancho": {"type": "array", "items": {"type": "string"}},
        "observacoes_de_conformidade": {"type": "string"},
        "slides": {"type": "array", "items": {
            "type": "object",
            "properties": {"tipo": {"type": "string", "enum": ["capa", "conteudo", "cta"]}, "kicker": {"type": "string"},
                           "titulo": {"type": "string"}, "texto": {"type": "string"}},
            "required": ["tipo", "kicker", "titulo", "texto"], "additionalProperties": False}},
    },
    "required": ["titulo_interno", "plataforma", "formato", "gancho", "legenda", "cta", "hashtags", "roteiro",
                 "briefing_visual", "melhor_horario", "alternativas_de_gancho", "observacoes_de_conformidade", "slides"],
    "additionalProperties": False,
}
IDEIAS_SCHEMA = {
    "type": "object",
    "properties": {"ideias": {"type": "array", "items": {
        "type": "object",
        "properties": {"titulo": {"type": "string"}, "formato": {"type": "string"}, "gancho": {"type": "string"},
                       "por_que_funciona": {"type": "string"}},
        "required": ["titulo", "formato", "gancho", "por_que_funciona"], "additionalProperties": False}}},
    "required": ["ideias"], "additionalProperties": False,
}
CALENDARIO_SCHEMA = {
    "type": "object",
    "properties": {
        "estrategia": {"type": "string"},
        "itens": {"type": "array", "items": {
            "type": "object",
            "properties": {"dia": {"type": "string"}, "plataforma": {"type": "string"}, "formato": {"type": "string"},
                           "tema": {"type": "string"}, "objetivo": {"type": "string"}, "gancho": {"type": "string"}},
            "required": ["dia", "plataforma", "formato", "tema", "objetivo", "gancho"],
            "additionalProperties": False}},
    },
    "required": ["estrategia", "itens"], "additionalProperties": False,
}


def _area(empresa: str) -> str:
    return "avogroup" if "group" in norm(empresa) else "avoseg"


def _post_markdown(d: dict) -> str:
    roteiro = "\n".join(f"{i}. {s}" for i, s in enumerate(d["roteiro"], 1)) or "(post único)"
    alt = "\n".join(f"- {g}" for g in d["alternativas_de_gancho"])
    return (f"**{d['plataforma']} · {d['formato']}**\n\n**Gancho:** {d['gancho']}\n\n## Legenda\n{d['legenda']}\n\n"
            f"**CTA:** {d['cta']}\n\n**Hashtags:** {' '.join(d['hashtags'])}\n\n## Roteiro\n{roteiro}\n\n"
            f"## Briefing visual\n{d['briefing_visual']}\n\n**Melhor horário:** {d['melhor_horario']}\n\n"
            f"## Ganchos alternativos\n{alt}\n\n## Conformidade\n{d['observacoes_de_conformidade']}\n")


def make_tools(brain: Brain, client, model: str, on_change=None, on_post=None, on_art=None,
               image_cfg: tuple = ("none", "", "gpt-image-1", "medium"), renderer=None, image_fn=None) -> list[Tool]:
    def especialista(empresa: str, pedido: str, schema: dict, max_tokens: int = 4000) -> dict:
        marca, _ = brain.brand(empresa)
        recentes = [n.title for n in brain.recent(8, None, _area(empresa), "post")]
        historico = ("\nPosts recentes (evite repetir ângulos): " + "; ".join(recentes)) if recentes else ""
        system = (ESPECIALISTA + f"\n# Perfil de marca ({empresa})\n{marca[:6000]}\n{historico}\n"
                  f"Hoje é {datetime.now():%A, %d/%m/%Y}.")
        cfg = {"format": {"type": "json_schema", "schema": schema}}
        if not model.startswith("claude-haiku"):
            cfg["effort"] = "medium"
        resp = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                      messages=[{"role": "user", "content": pedido}], output_config=cfg)
        if resp.stop_reason == "refusal":
            raise RuntimeError("o modelo recusou este pedido")
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("a resposta ficou longa demais")
        return json.loads(next(b.text for b in resp.content if b.type == "text"))

    def _precisa_marca(empresa: str) -> str | None:
        _, ok = brain.brand(empresa)
        if ok:
            return None
        return (f"O perfil de marca de {empresa} ainda está vazio. Antes de criar, pergunte ao usuário, em uma "
                "conversa rápida: o que a empresa vende, quem é o público, o tom de voz, os diferenciais e o que evitar. "
                "Depois salve as respostas com a ferramenta definir_marca.")

    state: dict = {"last": None}
    image_fn = image_fn or imagem.generate_image

    def _logo(empresa: str) -> Path | None:
        d = brain.root / AREAS[_area(empresa)] / "marca"
        return next((p for ext in ("png", "jpg", "jpeg") for p in [d / f"logo.{ext}"] if p.exists()), None)

    def _fazer_arte(empresa: str, post: dict, note, formato: str = "", estilo: str = "misto", com_ia: bool = False) -> str:
        """Gera os PNGs da arte e avisa a tela. Com IA: a OpenAI desenha cada slide com o texto do Claude (sem texto
        nosso por cima). Sem IA: layout da marca. Devolve um texto de resultado."""
        text, _ = brain.brand(empresa)
        brand = arte.brand_from_text(empresa.strip().title() or "Avoseg", text, _logo(empresa))
        out_dir = note.path.parent / "arte" / note.path.stem
        fmt = formato or post.get("formato", "")
        avisos: list[str] = []
        try:
            if com_ia:
                provider, key, modelo, *rest = image_cfg
                quality = rest[0] if rest else "medium"
                files, avisos = arte.make_art_ia(
                    post, brand, out_dir, fmt,
                    lambda prompt, api_size: image_fn(prompt, provider, key, modelo, api_size, quality),
                    renderer, estilo)
            else:
                files = arte.make_art(post, brand, out_dir, fmt, estilo, None, renderer)
        except Exception as e:
            return f"A arte não saiu: {e}"
        if on_art:
            on_art({"titulo": post.get("titulo_interno", ""), "pasta": str(out_dir), "pasta_rel": str(out_dir.relative_to(brain.root)).replace("\\", "/"),
                    "images": [str(f.relative_to(brain.root)).replace("\\", "/") for f in files]})
        aviso = (" Atenção: " + "; ".join(avisos) + ".") if avisos else ""
        modo = "desenhada pela IA com o texto do post" if com_ia else "no layout da marca"
        sem_logo = "" if brand.logo else " Dica: coloque o logo em " + f"{AREAS[_area(empresa)]}/marca/logo.png para aparecer na arte."
        return f"Arte criada ({modo}): {len(files)} imagem(ns) em {out_dir}.{aviso}{sem_logo}"

    def criar_arte(estilo: str = "misto", formato: str = "", com_ia: bool | None = None, referencia: str = "",
                   abrir_pasta: bool = False) -> str:
        """Cria (ou refaz) a arte do último post, ou de outro post salvo (pelo título)."""
        last = state["last"]
        if referencia:
            note = brain.get(referencia)
            sidecar = note.path.with_suffix(".json") if note else None
            if not note or not sidecar or not sidecar.exists():
                return "Não achei esse post com dados para gerar a arte."
            last = {"post": json.loads(sidecar.read_text(encoding="utf-8")), "note": note,
                    "empresa": "Avogroup" if "30-Avogroup" in str(note.path) else "Avoseg"}
        if not last:
            return "Ainda não criei nenhum post nesta conversa. Peça primeiro um post, ou diga o título de um post salvo."
        aviso = ""
        if com_ia is None:                       # padrão: usa a foto por IA sempre que estiver configurada
            com_ia = image_cfg[0] != "none"
        elif com_ia and image_cfg[0] == "none":
            com_ia = False
            aviso = " A arte por IA não está configurada (falta a OPENAI_API_KEY no .env); fiz a arte só com o layout da marca."
        res = _fazer_arte(last["empresa"], last["post"], last["note"], formato, estilo, com_ia) + aviso
        if abrir_pasta:
            import subprocess, sys
            if sys.platform == "darwin":
                subprocess.run(["open", str(last["note"].path.parent / "arte" / last["note"].path.stem)], check=False)
        return res

    def definir_marca(empresa: str, informacoes: str) -> str:
        brain.save_brand(empresa, informacoes)
        return f"Perfil de marca de {empresa} atualizado."

    def criar_post(empresa: str, tema: str, plataforma: str = "instagram", formato: str = "post",
                   objetivo: str = "", observacoes: str = "", com_arte: bool = True, com_ia: bool | None = None) -> str:
        if (msg := _precisa_marca(empresa)):
            return msg
        pedido = (f"Crie {formato} para {plataforma} da empresa {empresa}.\nTema: {tema}\n"
                  f"Objetivo: {objetivo or 'engajar e gerar contatos qualificados'}\n"
                  f"Observações do usuário: {observacoes or 'nenhuma'}")
        try:
            d = especialista(empresa, pedido, POST_SCHEMA)
        except Exception as e:
            return f"Não consegui criar o post agora: {e}"
        note = brain.add_note(f"Post: {d['titulo_interno']}", _post_markdown(d), _area(empresa), "post",
                              ["marketing", plataforma, formato], subdir="marketing")
        note.path.with_suffix(".json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        state["last"] = {"post": d, "note": note, "empresa": empresa}
        if on_change:
            on_change(note)
        if on_post:
            on_post({"empresa": empresa, "titulo": d["titulo_interno"], "plataforma": d["plataforma"],
                     "formato": d["formato"], "gancho": d["gancho"], "legenda": d["legenda"], "cta": d["cta"],
                     "hashtags": d["hashtags"], "roteiro": d["roteiro"], "visual": d["briefing_visual"],
                     "horario": d["melhor_horario"], "conformidade": d["observacoes_de_conformidade"]})
        resultado_arte = ""
        if com_arte:
            if com_ia is None or image_cfg[0] == "none":
                com_ia = image_cfg[0] != "none" if com_ia is None else False
            resultado_arte = " " + _fazer_arte(empresa, d, note, formato, "misto", com_ia)
        return (f"Post '{d['titulo_interno']}' criado e salvo no Second Brain; está aberto na tela.{resultado_arte} "
                f"Gancho: {d['gancho']} CTA: {d['cta']} Melhor horário: {d['melhor_horario']}. "
                f"Conformidade: {d['observacoes_de_conformidade'][:200]} "
                "Diga ao usuário o gancho e ofereça ler a legenda; não leia tudo em voz alta.")

    def ideias_de_conteudo(empresa: str, quantidade: int = 5, foco: str = "") -> str:
        if (msg := _precisa_marca(empresa)):
            return msg
        try:
            d = especialista(empresa, f"Dê {max(1, min(quantidade, 10))} ideias de conteúdo para {empresa}. "
                                      f"Foco: {foco or 'variado, cobrindo educar, converter e reter'}.", IDEIAS_SCHEMA, 2500)
        except Exception as e:
            return f"Não consegui gerar ideias agora: {e}"
        corpo = "\n".join(f"{i}. **{x['titulo']}** ({x['formato']}): {x['gancho']}  \n   _{x['por_que_funciona']}_"
                          for i, x in enumerate(d["ideias"], 1))
        note = brain.add_note(f"Ideias de conteúdo {empresa} {datetime.now():%d/%m}", corpo, _area(empresa), "ideia",
                              ["marketing", "ideias"], subdir="marketing")
        if on_change:
            on_change(note)
        return "Ideias salvas. Resumo: " + "; ".join(f"{x['titulo']} ({x['formato']})" for x in d["ideias"])

    def planejar_calendario(empresa: str, dias: int = 7, posts_por_semana: int = 3, foco: str = "") -> str:
        if (msg := _precisa_marca(empresa)):
            return msg
        try:
            d = especialista(empresa, f"Monte um calendário editorial de {max(1, min(dias, 31))} dias a partir de hoje, "
                                      f"com cerca de {posts_por_semana} posts por semana. Foco: {foco or 'variado'}.",
                             CALENDARIO_SCHEMA, 3500)
        except Exception as e:
            return f"Não consegui montar o calendário agora: {e}"
        linhas = "\n".join(f"- **{i['dia']}** · {i['plataforma']} · {i['formato']} · {i['tema']} "
                           f"({i['objetivo']}) — gancho: {i['gancho']}" for i in d["itens"])
        note = brain.add_note(f"Calendário editorial {empresa} {datetime.now():%d/%m}",
                              f"## Estratégia\n{d['estrategia']}\n\n## Plano\n{linhas}", _area(empresa), "nota",
                              ["marketing", "calendario"], subdir="marketing")
        if on_change:
            on_change(note)
        return f"Calendário salvo. Estratégia: {d['estrategia'][:250]} Itens: {len(d['itens'])}."

    empresas = {"type": "string", "description": "Avoseg ou Avogroup."}
    return [
        Tool("criar_post",
             "Age como especialista de marketing: cria um post completo (legenda, CTA, hashtags, roteiro, briefing "
             "visual, horário e conformidade) para uma empresa do usuário e salva no Second Brain.",
             {"empresa": empresas,
              "tema": {"type": "string", "description": "Assunto do post."},
              "plataforma": {"type": "string", "description": "instagram, facebook, linkedin, whatsapp, tiktok..."},
              "formato": {"type": "string", "description": "post, carrossel, reels, stories, artigo, mensagem..."},
              "objetivo": {"type": "string"}, "observacoes": {"type": "string"},
              "com_arte": {"type": "boolean", "description": "Gerar também a arte (padrão: sim)."},
              "com_ia": {"type": "boolean", "description": "A IA (OpenAI) desenha a arte inteira com o texto do post. Omita: usa "
                                                          "sozinho quando configurada. Envie false só se o usuário pedir 'sem IA' ou 'só o layout'."}},
             ["empresa", "tema"], criar_post),
        Tool("criar_arte",
             "Cria ou refaz a ARTE (imagens PNG com a identidade da marca) do último post, ou de um post salvo "
             "pelo título. Use quando o usuário pedir a arte, o design, as imagens do post, outro estilo ou a pasta.",
             {"estilo": {"type": "string", "enum": ["misto", "escuro", "claro"]},
              "formato": {"type": "string", "description": "feed (4:5), quadrado, story (vertical)."},
              "com_ia": {"type": "boolean", "description": "A IA (OpenAI) desenha a arte inteira com o texto do post. Omita: usa "
                                                            "sozinho quando configurada. Envie false só se o usuário pedir 'sem IA' ou 'só o layout'."},
              "referencia": {"type": "string", "description": "Título ou id de um post salvo (vazio = o último)."},
              "abrir_pasta": {"type": "boolean", "description": "Abrir a pasta no Finder."}}, [], criar_arte),
        Tool("ideias_de_conteudo", "Gera ideias de conteúdo de marketing para uma empresa e salva no Second Brain.",
             {"empresa": empresas, "quantidade": {"type": "integer"}, "foco": {"type": "string"}},
             ["empresa"], ideias_de_conteudo),
        Tool("planejar_calendario", "Monta um calendário editorial de posts para uma empresa e salva no Second Brain.",
             {"empresa": empresas, "dias": {"type": "integer"}, "posts_por_semana": {"type": "integer"},
              "foco": {"type": "string"}}, ["empresa"], planejar_calendario),
        Tool("definir_marca",
             "Salva no perfil de marca de uma empresa o que o usuário contou. Escreva como itens de lista no formato "
             "'- Campo: valor' (Público, Tom, Diferenciais, Evitar, Cores, Instagram, WhatsApp, Site, Rodapé legal).",
             {"empresa": empresas, "informacoes": {"type": "string"}}, ["empresa", "informacoes"], definir_marca),
    ]
