"""Second Brain: notas em Markdown numa pasta sua + índice de busca local (SQLite FTS5).

As notas são arquivos .md comuns (abrem em qualquer editor, inclusive Obsidian) e podem ser
editadas à mão: o índice se atualiza sozinho. Nada sai do seu computador.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

AREAS = {
    "inbox": "00-Inbox", "pessoal": "10-Pessoal", "avoseg": "20-Avoseg", "avogroup": "30-Avogroup",
    "projetos": "40-Projetos", "pessoas": "50-Pessoas", "diario": "70-Diario", "decisoes": "80-Decisoes",
}
FOLDER_TO_AREA = {v: k for k, v in AREAS.items()}
TIPOS = ["nota", "ideia", "decisao", "tarefa", "pessoa", "reuniao", "post", "marca", "diario", "perfil"]

STOPWORDS = set("""
a o as os um uma uns umas de do da dos das em no na nos nas por para com sem sob sobre entre ate
e ou mas que se como quando onde qual quais quem porque pois ja nao sim mais menos muito muita muitos
ser estar ter haver fazer ir vir poder dever eu tu ele ela nos vos eles elas me te lhe meu minha meus
minhas seu sua seus suas nosso nossa isso isto aquilo esse essa este esta aquele aquela aqui ali la
foi era sao esta estao tem tinha tenho vou vai fui hoje ontem amanha agora depois antes ainda tambem
so soh tudo nada algo alguem ninguem cada todo toda todos todas qualquer outro outra outros outras
anote anota anotar nota lembra lembre lembrar jarvis favor pode poderia quero preciso
""".split())

TEMPLATE_PERFIL = """# Perfil

> Quem eu sou, como penso e como quero que o Jarvis me ajude. O Jarvis lê este arquivo sempre.
> Edite à vontade ou peça por voz: "Jarvis, lembre que eu prefiro...".

## Sobre mim
- PREENCHA: nome, cidade, o que faz, empresas

## Como gosto de ser atendido
- PREENCHA: tom de voz, nível de detalhe, horários

## Prioridades do momento
- PREENCHA

## Fatos que o Jarvis aprendeu
"""

TEMPLATE_MARCA_AVOSEG = """# Marca Avoseg

> Perfil de marca usado pelo especialista de marketing. Quanto mais completo, melhores os posts.
> Itens com PREENCHA ainda precisam da sua resposta.

## O que é
- Corretora de seguros.
- Produtos que aparecem no site: seguro auto, seguro de vida, convênio (saúde), seguro empresarial.
- Atende também frotas e empresas (portal de clientes com apólices e sinistros).

## Programa Indique e Ganhe
- Cliente da Avoseg indica um amigo; quando o amigo fecha o seguro, recebe R$ 100 no PIX.
- Sem limite de indicações (5 indicações = R$ 500, 10 = R$ 1.000).
- Exclusivo para clientes; parceiros comerciais têm condições próprias no portal de parceiros.

## Público
- PREENCHA: quem são os clientes ideais (pessoa física, empresas, frotistas, regiões)

## Tom de voz
- PREENCHA: ex.: acolhedor, próximo e profissional; trata o cliente por "você"

## Diferenciais
- PREENCHA: o que a Avoseg faz melhor que os concorrentes (sem prometer "menor preço")

## Evitar
- PREENCHA: palavras, temas e promessas proibidas

## Identidade visual
- PREENCHA: cores, fontes, estilo das artes
"""

TEMPLATE_MARCA_AVOGROUP = """# Marca Avogroup

> Perfil de marca do grupo, usado pelo especialista de marketing.
> Itens com PREENCHA ainda precisam da sua resposta.

## O que é
- PREENCHA: o que é o Avogroup, quais empresas e serviços reúne

## Público
- PREENCHA

## Tom de voz
- PREENCHA

## Diferenciais
- PREENCHA

## Evitar
- PREENCHA

## Identidade visual
- PREENCHA
"""


def norm(text: str) -> str:
    """minúsculas e sem acentos: 'Transportadôras' -> 'transportadoras'."""
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def tokens(text: str, min_len: int = 3) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", norm(text)) if len(w) >= min_len and w not in STOPWORDS]


def slugify(text: str, limit: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", norm(text)).strip("-")
    return (s[:limit].strip("-")) or "nota"


@dataclass
class Note:
    id: str
    title: str
    body: str
    area: str = "inbox"
    tipo: str = "nota"
    tags: list[str] = field(default_factory=list)
    created: str = ""
    path: Path | None = None

    def excerpt(self, n: int = 220) -> str:
        flat = re.sub(r"\s+", " ", self.body).strip()
        return flat if len(flat) <= n else flat[: n - 1].rstrip() + "…"


def _parse(text: str) -> tuple[dict, str]:
    """Separa o frontmatter ('---' ... '---') do corpo. Sem frontmatter -> ({}, texto)."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    meta: dict = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val.startswith("["):
            meta[key] = [t.strip().strip("\"'") for t in val.strip("[]").split(",") if t.strip()]
        elif val.startswith('"'):
            try:
                meta[key] = json.loads(val)
            except ValueError:
                meta[key] = val.strip('"')
        else:
            meta[key] = val
    body = text[end + 4:].lstrip("\n")
    return meta, body


def _dump(note: Note) -> str:
    tags = ", ".join(note.tags)
    return (f"---\nid: {note.id}\ntitle: {json.dumps(note.title, ensure_ascii=False)}\narea: {note.area}\n"
            f"tipo: {note.tipo}\ntags: [{tags}]\ncriada: {note.created}\n---\n\n{note.body.strip()}\n")


class Brain:
    """A pasta de notas + o índice de busca."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser()
        self.ensure_structure()
        self._db = sqlite3.connect(self.root / ".jarvis-index.db", check_same_thread=False)
        self._db.executescript("""
            create table if not exists notes(id text primary key, path text unique, mtime real, title text,
                area text, tipo text, tags text, created text, body text);
            create virtual table if not exists fts using fts5(title, body, tags, id unindexed,
                tokenize='unicode61 remove_diacritics 2');
        """)
        self._graph_cache: tuple | None = None
        self.reindex()

    # ---------- estrutura ----------
    def ensure_structure(self) -> None:
        for folder in AREAS.values():
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        (self.root / AREAS["avoseg"] / "marketing").mkdir(exist_ok=True)
        for rel, content in (("perfil.md", TEMPLATE_PERFIL),
                             (f"{AREAS['avoseg']}/marca.md", TEMPLATE_MARCA_AVOSEG),
                             (f"{AREAS['avogroup']}/marca.md", TEMPLATE_MARCA_AVOGROUP)):
            p = self.root / rel
            if not p.exists():
                p.write_text(content, encoding="utf-8")

    # ---------- índice ----------
    def _load(self, path: Path) -> Note:
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse(text)
        rel = path.relative_to(self.root)
        folder = rel.parts[0] if len(rel.parts) > 1 else ""
        nid = meta.get("id") or "p-" + hashlib.sha1(str(rel).encode()).hexdigest()[:10]
        h1 = re.search(r"^#\s+(.+)$", body, re.M)
        title = meta.get("title") or (h1.group(1).strip() if h1 else path.stem)
        area = meta.get("area") or FOLDER_TO_AREA.get(folder, "pessoal" if not folder else "inbox")
        tipo = meta.get("tipo") or ("perfil" if rel.name == "perfil.md" else "marca" if rel.name == "marca.md" else "nota")
        created = meta.get("criada") or datetime.fromtimestamp(path.stat().st_ctime).isoformat(timespec="seconds")
        tags = meta.get("tags") or []
        return Note(nid, title, body, area, tipo, tags if isinstance(tags, list) else [], created, path)

    def _index(self, note: Note, mtime: float) -> None:
        rel = str(note.path.relative_to(self.root))
        self._db.execute("delete from fts where id = ?", (note.id,))
        self._db.execute("delete from notes where id = ? or path = ?", (note.id, rel))
        self._db.execute("insert into notes values (?,?,?,?,?,?,?,?,?)",
                         (note.id, rel, mtime, note.title, note.area, note.tipo, ",".join(note.tags),
                          note.created, note.body))
        self._db.execute("insert into fts(title, body, tags, id) values (?,?,?,?)",
                         (note.title, note.body, " ".join(note.tags), note.id))

    def reindex(self) -> int:
        """Atualiza o índice com o que mudou nos arquivos (inclusive edições feitas à mão)."""
        known = {r[0]: r[1] for r in self._db.execute("select path, mtime from notes")}
        seen, changed = set(), 0
        for p in self.root.rglob("*.md"):
            if any(part.startswith(".") for part in p.relative_to(self.root).parts):
                continue
            rel = str(p.relative_to(self.root))
            seen.add(rel)
            mtime = p.stat().st_mtime
            if known.get(rel) != mtime:
                self._index(self._load(p), mtime)
                changed += 1
        for rel in set(known) - seen:
            row = self._db.execute("select id from notes where path = ?", (rel,)).fetchone()
            if row:
                self._db.execute("delete from fts where id = ?", (row[0],))
            self._db.execute("delete from notes where path = ?", (rel,))
            changed += 1
        if changed:
            self._db.commit()
            self._graph_cache = None
        return changed

    def _row_to_note(self, row) -> Note:
        nid, rel, title, area, tipo, tags, created, body = row
        return Note(nid, title, body, area, tipo, [t for t in tags.split(",") if t], created, self.root / rel)

    _COLS = "id, path, title, area, tipo, tags, created, body"

    # ---------- escrita ----------
    def add_note(self, title: str, body: str, area: str = "inbox", tipo: str = "nota",
                 tags: list[str] | None = None, subdir: str | None = None) -> Note:
        area = area if area in AREAS else "inbox"
        tipo = tipo if tipo in TIPOS else "nota"
        now = datetime.now()
        nid = now.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
        folder = self.root / AREAS[area] / (subdir or "")
        folder.mkdir(parents=True, exist_ok=True)
        clean_tags = sorted({slugify(t, 24) for t in (tags or []) if t.strip()})
        note = Note(nid, title.strip() or "Sem título", body.strip(), area, tipo, clean_tags,
                    now.isoformat(timespec="seconds"), folder / f"{nid[:13]}-{slugify(title)}.md")
        tmp = note.path.with_suffix(".tmp")
        tmp.write_text(_dump(note), encoding="utf-8")
        tmp.replace(note.path)
        self._index(note, note.path.stat().st_mtime)
        self._db.commit()
        self._graph_cache = None
        return note

    def append_daily(self, text: str) -> Note:
        """Acrescenta uma linha com hora ao diário de hoje (cria o arquivo se preciso)."""
        now = datetime.now()
        path = self.root / AREAS["diario"] / f"{now:%Y-%m-%d}.md"
        line = f"- {now:%H:%M} {text.strip()}\n"
        if path.exists():
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
        else:
            note = Note(f"d-{now:%Y%m%d}", f"Diário {now:%d/%m/%Y}", "", "diario", "diario", ["diario"],
                        now.isoformat(timespec="seconds"), path)
            path.write_text(_dump(note) + line, encoding="utf-8")
        self.reindex()
        return self._load(path)

    def add_profile_fact(self, fact: str) -> None:
        p = self.root / "perfil.md"
        with p.open("a", encoding="utf-8") as f:
            f.write(f"- {fact.strip()}  _(em {datetime.now():%d/%m/%Y})_\n")
        self.reindex()

    # ---------- leitura ----------
    def read_profile(self, max_chars: int = 3000) -> str:
        text = (self.root / "perfil.md").read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if "PREENCHA" not in ln and not ln.startswith(">")]
        return "\n".join(lines).strip()[:max_chars]

    def get(self, ref: str) -> Note | None:
        """Busca por id exato ou por parte do título."""
        row = self._db.execute(f"select {self._COLS} from notes where id = ?", (ref,)).fetchone()
        if row:
            return self._row_to_note(row)
        want = norm(ref)
        best = None
        for r in self._db.execute(f"select {self._COLS} from notes"):
            t = norm(r[2])
            if want == t:
                return self._row_to_note(r)
            if want in t and best is None:
                best = r
        return self._row_to_note(best) if best else None

    def recent(self, limit: int = 10, days: int | None = None, area: str | None = None,
               tipo: str | None = None) -> list[Note]:
        sql, args = f"select {self._COLS} from notes where tipo != 'perfil'", []
        if days:
            sql += " and created >= ?"
            args.append((datetime.now() - timedelta(days=days)).isoformat(timespec="seconds"))
        if area:
            sql += " and area = ?"
            args.append(area)
        if tipo:
            sql += " and tipo = ?"
            args.append(tipo)
        sql += " order by created desc limit ?"
        args.append(limit)
        return [self._row_to_note(r) for r in self._db.execute(sql, args)]

    def count(self) -> int:
        return self._db.execute("select count(*) from notes").fetchone()[0]

    def search(self, query: str, limit: int = 5, area: str | None = None) -> list[tuple[Note, str]]:
        """Busca por palavras (sem acento, com variações: 'transportadora' acha 'transportadoras').
        Devolve (nota, trecho_destacado)."""
        words = tokens(query, 2)[:10]
        if not words:
            return []
        match = " OR ".join(f'"{w}"*' for w in words)
        sql = (f"select n.{self._COLS.replace(', ', ', n.')}, snippet(fts, 1, '[', ']', '…', 14) "
               "from fts join notes n on n.id = fts.id where fts match ?")
        args: list = [match]
        if area:
            sql += " and n.area = ?"
            args.append(area)
        sql += " order by bm25(fts, 6.0, 1.0, 3.0) limit ?"
        args.append(limit)
        try:
            rows = self._db.execute(sql, args).fetchall()
        except sqlite3.OperationalError:
            return []
        return [(self._row_to_note(r[:8]), r[8]) for r in rows]

    def recall(self, text: str, limit: int = 3) -> list[tuple[Note, str]]:
        """Notas realmente relevantes para o que foi dito (evita ruído: exige várias palavras em comum)."""
        words = list(dict.fromkeys(tokens(text, 4)))[:8]
        if not words:
            return []
        need = 1 if len(words) == 1 else 2
        out = []
        for note, snip in self.search(" ".join(words), limit=limit * 3):
            hay = norm(note.title + " " + note.body + " " + " ".join(note.tags))
            hits = sum(1 for w in words if w[:5] in hay)
            if hits >= need and note.tipo != "perfil":
                out.append((note, snip))
        return out[:limit]

    # ---------- conexões e grafo ----------
    def _vectors(self, notes: list[Note]) -> list[dict[str, float]]:
        docs = [tokens(n.title + " " + n.title + " " + n.body + " " + " ".join(n.tags)) for n in notes]
        df: dict[str, int] = {}
        for d in docs:
            for w in set(d):
                df[w] = df.get(w, 0) + 1
        n = max(1, len(docs))
        vecs = []
        for d in docs:
            tf: dict[str, float] = {}
            for w in d:
                tf[w] = tf.get(w, 0) + 1
            v = {w: (1 + math.log(c)) * math.log(1 + n / df[w]) for w, c in tf.items()}
            norm_ = math.sqrt(sum(x * x for x in v.values())) or 1.0
            vecs.append({w: x / norm_ for w, x in v.items()})
        return vecs

    def _edges(self, notes: list[Note]) -> list[tuple[int, int, float]]:
        vecs = self._vectors(notes)
        titles = [norm(n.title) for n in notes]
        weights: dict[tuple[int, int], float] = {}

        def bump(i: int, j: int, w: float) -> None:
            key = (i, j) if i < j else (j, i)
            weights[key] = max(weights.get(key, 0.0), w)

        for i, a in enumerate(notes):
            sims = []
            for j, b in enumerate(notes):
                if i == j:
                    continue
                shared = len(set(a.tags) & set(b.tags) - {"diario"})
                if shared:
                    bump(i, j, min(1.0, 0.45 + 0.2 * shared))
                cos = sum(x * vecs[j].get(w, 0.0) for w, x in vecs[i].items())
                sims.append((cos, j))
                if len(titles[j]) > 3 and f"[[{titles[j]}]]" in norm(a.body):
                    bump(i, j, 1.0)
            for cos, j in sorted(sims, reverse=True)[:3]:
                if cos >= 0.2:
                    bump(i, j, min(0.9, cos + 0.15))
        return [(i, j, round(w, 2)) for (i, j), w in weights.items()]

    def related(self, note: Note, limit: int = 3) -> list[Note]:
        notes = [n for n in self.recent(500) if True]
        if note.id not in {n.id for n in notes}:
            notes.append(note)
        idx = next(i for i, n in enumerate(notes) if n.id == note.id)
        scored = [(w, (j if i == idx else i)) for i, j, w in self._edges(notes) if idx in (i, j)]
        return [notes[j] for w, j in sorted(scored, reverse=True)[:limit]]

    def graph(self, limit: int = 300) -> dict:
        """Dados para a tela: nós (notas) e conexões. Cacheado até alguma nota mudar."""
        key = (self.count(), limit)
        if self._graph_cache and self._graph_cache[0] == key:
            return self._graph_cache[1]
        notes = list(reversed(self.recent(limit)))
        edges = self._edges(notes)
        deg = [0] * len(notes)
        for i, j, _ in edges:
            deg[i] += 1
            deg[j] += 1
        data = {
            "nodes": [{"id": n.id, "title": n.title[:60], "area": n.area, "tipo": n.tipo, "deg": deg[k]}
                      for k, n in enumerate(notes)],
            "edges": [[i, j, w] for i, j, w in edges],
            "total": self.count(),
        }
        self._graph_cache = (key, data)
        return data

    # ---------- marca (para o especialista de marketing) ----------
    def brand(self, empresa: str) -> tuple[str, bool]:
        """Perfil de marca da empresa e se está suficientemente preenchido."""
        area = "avogroup" if "group" in norm(empresa) else "avoseg"
        p = self.root / AREAS[area] / "marca.md"
        if not p.exists():
            return "", False
        text = p.read_text(encoding="utf-8")
        real = [ln for ln in text.splitlines()
                if ln.strip().startswith("-") and "PREENCHA" not in ln and len(ln.strip()) > 12]
        return text, len(real) >= 4

    def save_brand(self, empresa: str, conteudo: str) -> Path:
        area = "avogroup" if "group" in norm(empresa) else "avoseg"
        p = self.root / AREAS[area] / "marca.md"
        with p.open("a", encoding="utf-8") as f:
            f.write(f"\n## Atualização de {datetime.now():%d/%m/%Y}\n{conteudo.strip()}\n")
        self.reindex()
        return p
