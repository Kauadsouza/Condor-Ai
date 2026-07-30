"""
Banco de memória do CONDOR — SQLite local, na sua máquina.

Tudo que ele aprende sobre você fica aqui, em data/condor.db:

  fatos      → o que ele sabe de você (gosto, hábito, projeto, decisão, pessoa)
  entidades  → coisas/pessoas/projetos que aparecem na sua vida
  relacoes   → como as entidades se ligam (o grafo da tela Memória)
  conversas  → histórico completo, por sessão
  sessoes    → cada vez que ele acordou e o resumo do que rolou
  acoes      → auditoria: todo comando que ele rodou no PC
  uso_api    → quanto de token/dinheiro cada chamada gastou

Busca em dois modos, combinados:
  - textual  (FTS5, casa palavra exata)
  - semântica (embedding, casa significado mesmo com outras palavras)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import struct
import time
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger("condor.memoria")

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS fatos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria  TEXT NOT NULL,             -- pessoal, trabalho, preferencia, tecnico, rotina, projeto
    chave      TEXT NOT NULL,             -- identificador curto do fato
    valor      TEXT NOT NULL,             -- o fato escrito por extenso
    confianca  REAL NOT NULL DEFAULT 0.8,
    origem     TEXT NOT NULL DEFAULT 'conversa',
    embedding  BLOB,
    acessos    INTEGER NOT NULL DEFAULT 0,
    criado     REAL NOT NULL,
    atualizado REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fatos_chave ON fatos(categoria, chave);
CREATE INDEX IF NOT EXISTS idx_fatos_atualizado ON fatos(atualizado DESC);

CREATE TABLE IF NOT EXISTS entidades (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT NOT NULL UNIQUE,
    tipo       TEXT NOT NULL,             -- pessoa, projeto, lugar, empresa, ferramenta
    cluster    TEXT NOT NULL DEFAULT 'GERAL',
    resumo     TEXT NOT NULL DEFAULT '',
    mencoes    INTEGER NOT NULL DEFAULT 1,
    criado     REAL NOT NULL,
    atualizado REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS relacoes (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    de_id    INTEGER NOT NULL REFERENCES entidades(id) ON DELETE CASCADE,
    para_id  INTEGER NOT NULL REFERENCES entidades(id) ON DELETE CASCADE,
    tipo     TEXT NOT NULL,
    forca    REAL NOT NULL DEFAULT 1.0,
    criado   REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rel ON relacoes(de_id, para_id, tipo);

CREATE TABLE IF NOT EXISTS conversas (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao   INTEGER NOT NULL DEFAULT 0,
    papel    TEXT NOT NULL,               -- user, assistant
    conteudo TEXT NOT NULL,
    ts       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_ts ON conversas(ts DESC);

CREATE TABLE IF NOT EXISTS sessoes (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio REAL NOT NULL,
    fim    REAL,
    resumo TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS acoes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ferramenta TEXT NOT NULL,
    entrada    TEXT NOT NULL,
    saida      TEXT NOT NULL DEFAULT '',
    sucesso    INTEGER NOT NULL DEFAULT 1,
    exigiu_senha INTEGER NOT NULL DEFAULT 0,
    ts         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_acoes_ts ON acoes(ts DESC);

CREATE TABLE IF NOT EXISTS uso_api (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    modelo    TEXT NOT NULL,
    entrada   INTEGER NOT NULL DEFAULT 0,
    saida     INTEGER NOT NULL DEFAULT 0,
    custo_usd REAL NOT NULL DEFAULT 0,
    ts        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uso_ts ON uso_api(ts DESC);
"""

FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS fatos_fts USING fts5(
    chave, valor, content='fatos', content_rowid='id', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS fatos_ai AFTER INSERT ON fatos BEGIN
    INSERT INTO fatos_fts(rowid, chave, valor) VALUES (new.id, new.chave, new.valor);
END;
CREATE TRIGGER IF NOT EXISTS fatos_ad AFTER DELETE ON fatos BEGIN
    INSERT INTO fatos_fts(fatos_fts, rowid, chave, valor) VALUES('delete', old.id, old.chave, old.valor);
END;
CREATE TRIGGER IF NOT EXISTS fatos_au AFTER UPDATE ON fatos BEGIN
    INSERT INTO fatos_fts(fatos_fts, rowid, chave, valor) VALUES('delete', old.id, old.chave, old.valor);
    INSERT INTO fatos_fts(rowid, chave, valor) VALUES (new.id, new.chave, new.valor);
END;
"""


def _empacotar(vetor: list[float]) -> bytes:
    return struct.pack(f"{len(vetor)}f", *vetor)


def _desempacotar(blob: bytes) -> list[float]:
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def _similaridade(a: list[float], b: list[float]) -> float:
    """Cosseno. Embeddings da OpenAI já vêm normalizados, então é só o produto."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


class Memoria:
    def __init__(self, caminho: str | Path) -> None:
        self._path = str(caminho)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._fts = False
        self.sessao_atual = 0

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._path, check_same_thread=False, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def inicializar(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            try:
                conn.executescript(FTS)
                self._fts = True
            except sqlite3.OperationalError as exc:
                # SQLite sem FTS5 compilado: busca cai pra LIKE, tudo segue.
                log.warning("FTS5 indisponível (%s) — busca textual usará LIKE.", exc)
        log.info("Memória pronta: %s", self._path)

    # ── Sessões ────────────────────────────────────────────────────────────

    def abrir_sessao(self) -> int:
        with self._conn() as conn:
            cur = conn.execute("INSERT INTO sessoes(inicio) VALUES(?)", (time.time(),))
            self.sessao_atual = cur.lastrowid or 0
        return self.sessao_atual

    def fechar_sessao(self, resumo: str = "") -> None:
        if not self.sessao_atual:
            return
        with self._conn() as conn:
            conn.execute("UPDATE sessoes SET fim=?, resumo=? WHERE id=?",
                         (time.time(), resumo, self.sessao_atual))
        self.sessao_atual = 0

    # ── Fatos ──────────────────────────────────────────────────────────────

    def salvar_fato(self, categoria: str, chave: str, valor: str,
                    confianca: float = 0.8, origem: str = "conversa",
                    embedding: list[float] | None = None) -> int:
        """Grava (ou atualiza) um fato. Chave repetida na mesma categoria
        sobrescreve — é assim que ele corrige o que aprendeu errado."""
        agora = time.time()
        blob = _empacotar(embedding) if embedding else None
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO fatos(categoria, chave, valor, confianca, origem,
                                     embedding, criado, atualizado)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(categoria, chave) DO UPDATE SET
                       valor=excluded.valor,
                       confianca=excluded.confianca,
                       embedding=COALESCE(excluded.embedding, fatos.embedding),
                       atualizado=excluded.atualizado""",
                (categoria, chave, valor, confianca, origem, blob, agora, agora),
            )
            if cur.lastrowid:
                return cur.lastrowid
            row = conn.execute("SELECT id FROM fatos WHERE categoria=? AND chave=?",
                               (categoria, chave)).fetchone()
            return row["id"] if row else 0

    def esquecer_fato(self, fato_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM fatos WHERE id=?", (fato_id,))
            return cur.rowcount > 0

    def buscar_fatos(self, consulta: str, limite: int = 8,
                     embedding: list[float] | None = None) -> list[dict]:
        """Busca híbrida: texto exato (FTS5) + significado (embedding).
        Junta os dois, tira duplicado e devolve ordenado por relevância."""
        achados: dict[int, dict] = {}

        with self._conn() as conn:
            # 1. Textual
            if self._fts and consulta.strip():
                termos = " OR ".join(
                    f'"{t}"' for t in consulta.split() if len(t) > 2
                )
                if termos:
                    try:
                        rows = conn.execute(
                            """SELECT f.*, bm25(fatos_fts) AS score
                               FROM fatos_fts JOIN fatos f ON f.id = fatos_fts.rowid
                               WHERE fatos_fts MATCH ?
                               ORDER BY score LIMIT ?""",
                            (termos, limite * 2),
                        ).fetchall()
                        for r in rows:
                            d = dict(r)
                            d["relevancia"] = 1.0
                            achados[d["id"]] = d
                    except sqlite3.OperationalError:
                        pass
            elif consulta.strip():
                rows = conn.execute(
                    "SELECT * FROM fatos WHERE valor LIKE ? OR chave LIKE ? LIMIT ?",
                    (f"%{consulta}%", f"%{consulta}%", limite * 2),
                ).fetchall()
                for r in rows:
                    d = dict(r)
                    d["relevancia"] = 1.0
                    achados[d["id"]] = d

            # 2. Semântica
            if embedding:
                rows = conn.execute(
                    "SELECT * FROM fatos WHERE embedding IS NOT NULL"
                ).fetchall()
                pontuados = []
                for r in rows:
                    sim = _similaridade(embedding, _desempacotar(r["embedding"]))
                    if sim > 0.30:
                        pontuados.append((sim, dict(r)))
                pontuados.sort(key=lambda x: x[0], reverse=True)
                for sim, d in pontuados[:limite * 2]:
                    if d["id"] in achados:
                        achados[d["id"]]["relevancia"] += sim
                    else:
                        d["relevancia"] = sim
                        achados[d["id"]] = d

        ordenados = sorted(achados.values(), key=lambda d: -d["relevancia"])[:limite]
        if ordenados:
            with self._conn() as conn:
                conn.executemany("UPDATE fatos SET acessos=acessos+1 WHERE id=?",
                                 [(d["id"],) for d in ordenados])
        for d in ordenados:
            d.pop("embedding", None)
        return ordenados

    def fatos_recentes(self, limite: int = 20, categoria: str | None = None) -> list[dict]:
        with self._conn() as conn:
            if categoria:
                rows = conn.execute(
                    "SELECT id,categoria,chave,valor,confianca,atualizado FROM fatos "
                    "WHERE categoria=? ORDER BY atualizado DESC LIMIT ?",
                    (categoria, limite)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id,categoria,chave,valor,confianca,atualizado FROM fatos "
                    "ORDER BY atualizado DESC LIMIT ?", (limite,)).fetchall()
            return [dict(r) for r in rows]

    def fatos_essenciais(self, limite: int = 12) -> list[dict]:
        """Os fatos que entram no prompt sempre — mais confiáveis e mais usados."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id,categoria,chave,valor FROM fatos
                   ORDER BY confianca * (1 + acessos * 0.1) DESC, atualizado DESC
                   LIMIT ?""", (limite,)).fetchall()
            return [dict(r) for r in rows]

    # ── Entidades e relações ───────────────────────────────────────────────

    def salvar_entidade(self, nome: str, tipo: str, cluster: str = "GERAL",
                        resumo: str = "") -> int:
        agora = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO entidades(nome, tipo, cluster, resumo, criado, atualizado)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(nome) DO UPDATE SET
                       tipo=excluded.tipo,
                       cluster=excluded.cluster,
                       resumo=CASE WHEN excluded.resumo != '' THEN excluded.resumo
                                   ELSE entidades.resumo END,
                       mencoes=entidades.mencoes+1,
                       atualizado=excluded.atualizado""",
                (nome, tipo, cluster, resumo, agora, agora))
            if cur.lastrowid:
                return cur.lastrowid
            row = conn.execute("SELECT id FROM entidades WHERE nome=?", (nome,)).fetchone()
            return row["id"] if row else 0

    def salvar_relacao(self, de: str, para: str, tipo: str) -> None:
        with self._conn() as conn:
            a = conn.execute("SELECT id FROM entidades WHERE nome=?", (de,)).fetchone()
            b = conn.execute("SELECT id FROM entidades WHERE nome=?", (para,)).fetchone()
            if not a or not b or a["id"] == b["id"]:
                return
            conn.execute(
                """INSERT INTO relacoes(de_id, para_id, tipo, criado) VALUES(?,?,?,?)
                   ON CONFLICT(de_id, para_id, tipo) DO UPDATE SET forca=relacoes.forca+0.5""",
                (a["id"], b["id"], tipo, time.time()))

    def grafo(self, limite: int = 40) -> dict:
        """Dados do grafo pra tela Memória."""
        with self._conn() as conn:
            nos = [dict(r) for r in conn.execute(
                "SELECT id,nome,tipo,cluster,mencoes FROM entidades "
                "ORDER BY mencoes DESC, atualizado DESC LIMIT ?", (limite,))]
            ids = {n["id"] for n in nos}
            arestas = [
                {"de": r["de_id"], "para": r["para_id"], "tipo": r["tipo"]}
                for r in conn.execute("SELECT de_id,para_id,tipo FROM relacoes")
                if r["de_id"] in ids and r["para_id"] in ids
            ]
        return {"nos": nos, "arestas": arestas}

    # ── Conversas ──────────────────────────────────────────────────────────

    def salvar_turno(self, papel: str, conteudo: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversas(sessao, papel, conteudo, ts) VALUES(?,?,?,?)",
                (self.sessao_atual, papel, conteudo, time.time()))

    def historico(self, limite: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT papel, conteudo FROM conversas ORDER BY ts DESC LIMIT ?",
                (limite,)).fetchall()
            return [{"role": r["papel"], "content": r["conteudo"]} for r in reversed(rows)]

    def buscar_conversas(self, consulta: str, limite: int = 5) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT papel, conteudo, ts FROM conversas WHERE conteudo LIKE ? "
                "ORDER BY ts DESC LIMIT ?", (f"%{consulta}%", limite)).fetchall()
            return [dict(r) for r in rows]

    # ── Auditoria e custo ──────────────────────────────────────────────────

    def registrar_acao(self, ferramenta: str, entrada: str, saida: str,
                       sucesso: bool, exigiu_senha: bool = False) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO acoes(ferramenta, entrada, saida, sucesso, exigiu_senha, ts)
                   VALUES(?,?,?,?,?,?)""",
                (ferramenta, entrada[:2000], saida[:2000], int(sucesso),
                 int(exigiu_senha), time.time()))

    def acoes_recentes(self, limite: int = 30) -> list[dict]:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT id,ferramenta,substr(entrada,1,160) entrada,sucesso,exigiu_senha,ts "
                "FROM acoes ORDER BY ts DESC LIMIT ?", (limite,))]

    def registrar_uso(self, modelo: str, entrada: int, saida: int, custo: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO uso_api(modelo, entrada, saida, custo_usd, ts) VALUES(?,?,?,?,?)",
                (modelo, entrada, saida, custo, time.time()))

    def custo_hoje(self) -> dict:
        inicio_dia = time.time() - (time.time() % 86400)
        with self._conn() as conn:
            hoje = conn.execute(
                "SELECT COALESCE(SUM(custo_usd),0) c, COALESCE(SUM(entrada+saida),0) t "
                "FROM uso_api WHERE ts >= ?", (inicio_dia,)).fetchone()
            total = conn.execute(
                "SELECT COALESCE(SUM(custo_usd),0) c FROM uso_api").fetchone()
        return {"hoje_usd": round(hoje["c"], 4), "hoje_tokens": hoje["t"],
                "total_usd": round(total["c"], 4)}

    # ── Estatísticas ───────────────────────────────────────────────────────

    def estatisticas(self) -> dict:
        with self._conn() as conn:
            def n(q: str) -> int:
                return conn.execute(q).fetchone()[0]
            return {
                "fatos": n("SELECT COUNT(*) FROM fatos"),
                "nos": n("SELECT COUNT(*) FROM entidades"),
                "conexoes": n("SELECT COUNT(*) FROM relacoes"),
                "turnos": n("SELECT COUNT(*) FROM conversas"),
                "acoes": n("SELECT COUNT(*) FROM acoes"),
            }

    def fluxo_recente(self, limite: int = 10) -> list[dict]:
        """Alimenta o painel 'o que estou aprendendo' da tela Memória."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT categoria, chave, valor, atualizado FROM fatos "
                "ORDER BY atualizado DESC LIMIT ?", (limite,)).fetchall()
            return [{"categoria": r["categoria"], "texto": r["valor"][:90],
                     "ts": r["atualizado"]} for r in rows]

    def projetos(self, limite: int = 4) -> list[dict]:
        """Entidades do tipo projeto — os cards que orbitam na tela Projetos."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT nome, resumo, cluster FROM entidades WHERE tipo='projeto' "
                "ORDER BY mencoes DESC, atualizado DESC LIMIT ?", (limite,)).fetchall()
            return [dict(r) for r in rows]
