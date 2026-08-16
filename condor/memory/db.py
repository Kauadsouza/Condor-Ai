"""
Banco de memoria do Condor — SQLite em RAM, cifrado em disco.

Tudo que ele aprende fica no snapshot ~/.condor/memory/condor.memory.enc:

  fatos      → o que ele sabe de você (gosto, hábito, projeto, decisão, pessoa)
  entidades  → coisas/pessoas/projetos que aparecem na sua vida
  relacoes   → como as entidades se ligam (o grafo da tela Memória)
  conversas  → histórico completo, por sessão
  sessoes    → cada vez que ele acordou e o resumo do que rolou
  acoes      → auditoria: todo comando que ele rodou no PC
  uso_api    → quanto de token/dinheiro cada chamada gastou

Busca em dois modos, combinados:
  - textual  (FTS5, casa palavra exata)
  - semantica (embedding, casa significado mesmo com outras palavras)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import struct
import time
import base64
import os
import tempfile
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

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

CREATE TABLE IF NOT EXISTS hub_projects (
    id       TEXT PRIMARY KEY,
    nome     TEXT NOT NULL,
    tipo     TEXT NOT NULL,
    status   TEXT NOT NULL,
    progresso INTEGER NOT NULL DEFAULT 0,
    resumo   TEXT NOT NULL DEFAULT '',
    rota     TEXT NOT NULL DEFAULT '',
    tom      TEXT NOT NULL DEFAULT 'cyan',
    atualizado REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS hub_tasks (
    id       TEXT PRIMARY KEY,
    titulo   TEXT NOT NULL,
    projeto  TEXT NOT NULL DEFAULT 'condor',
    status   TEXT NOT NULL DEFAULT 'pendente',
    prioridade TEXT NOT NULL DEFAULT 'media',
    criado   REAL NOT NULL,
    atualizado REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hub_tasks_updated ON hub_tasks(atualizado DESC);

CREATE TABLE IF NOT EXISTS hub_notes (
    id       TEXT PRIMARY KEY,
    titulo   TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    projeto  TEXT NOT NULL DEFAULT 'condor',
    criado   REAL NOT NULL,
    atualizado REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hub_notes_updated ON hub_notes(atualizado DESC);

CREATE TABLE IF NOT EXISTS condor_x_parts (
    id       TEXT PRIMARY KEY,
    nome     TEXT NOT NULL,
    zona     TEXT NOT NULL,
    status   TEXT NOT NULL,
    progresso INTEGER NOT NULL DEFAULT 0,
    risco    TEXT NOT NULL DEFAULT 'baixo',
    resumo   TEXT NOT NULL DEFAULT '',
    atualizado REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS creator_items (
    id       TEXT PRIMARY KEY,
    titulo   TEXT NOT NULL,
    etapa    TEXT NOT NULL,
    status   TEXT NOT NULL DEFAULT 'ideia',
    notas    TEXT NOT NULL DEFAULT '',
    criado   REAL NOT NULL,
    atualizado REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_creator_updated ON creator_items(atualizado DESC);

CREATE TABLE IF NOT EXISTS hub_missions (
    id       TEXT PRIMARY KEY,
    titulo   TEXT NOT NULL,
    estado   TEXT NOT NULL DEFAULT 'planejada',
    progresso INTEGER NOT NULL DEFAULT 0,
    detalhe  TEXT NOT NULL DEFAULT '',
    criado   REAL NOT NULL,
    atualizado REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_missions_updated ON hub_missions(atualizado DESC);
"""

DEFAULT_PROJECTS = (
    ("condor", "Condor", "IA local", "ativo", 82,
     "Nucleo privado, memoria cifrada e automacao supervisionada.", "/ui/index.html", "cyan"),
    ("condor-x", "Condor X", "Digital twin", "prototipo", 28,
     "Exoesqueleto conceitual modular, inerte e orientado por simulacao.", "", "amber"),
    ("kauaartx", "KauaArtx", "Canal", "foco", 42,
     "Operacao criativa do canal, do roteiro a publicacao.", "", "violet"),
    ("university", "University Path", "Oxford", "ativo", 64,
     "Documentos, prazos e preparacao universitaria.", "", "blue"),
    ("site", "Site", "Sistema independente", "independente", 100,
     "Marca pessoal publicada e mantida fora do nucleo do Condor.", "", "mint"),
    ("videos", "Videos", "Sistema independente", "independente", 100,
     "Pipeline de midia preservado como aplicacao independente.", "", "mint"),
    ("sat", "SAT", "Sistema independente", "independente", 100,
     "Sistema SAT preservado com codigo e dados proprios.", "", "mint"),
)

DEFAULT_CONDOR_X_PARTS = (
    ("helmet", "Capacete", "cabeca", "conceito", 20, "baixo", "HUD, audio e ventilacao; sem vedacao pressurizada."),
    ("chest", "Nucleo peitoral", "torso", "simulacao", 36, "baixo", "Computacao, telemetria e bateria de bancada protegida."),
    ("left-arm", "Braco esquerdo", "membro", "conceito", 18, "baixo", "Sensores e controle gestual, sem propulsao ou arma."),
    ("right-arm", "Braco direito", "membro", "conceito", 18, "baixo", "Sensores e controle gestual, sem propulsao ou arma."),
    ("legs", "Pernas", "mobilidade", "conceito", 12, "medio", "Estudo ergonomico passivo; nenhum atuador de alta forca."),
    ("power", "Energia", "infraestrutura", "bloqueado", 8, "alto", "Somente fonte certificada e teste de bancada com protecao."),
)

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
        self._path = Path(caminho)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fts = False
        self.sessao_atual = 0
        self._key: bytes | None = None
        self._lock = threading.RLock()
        self._database = sqlite3.connect(":memory:", check_same_thread=False)
        self._database.row_factory = sqlite3.Row

    @contextmanager
    def _conn(self):
        with self._lock:
            try:
                yield self._database
                self._database.commit()
                self._persist()
            except Exception:
                self._database.rollback()
                raise

    @property
    def unlocked(self) -> bool:
        return self._key is not None

    def unlock(self, key: bytes) -> None:
        """Carrega o snapshot cifrado inteiro apenas na memoria RAM."""
        if len(key) != 32:
            raise ValueError("A chave da memoria precisa ter 32 bytes.")
        with self._lock:
            if self._path.exists() and self._path.stat().st_size:
                envelope = json.loads(self._path.read_text(encoding="utf-8"))
                try:
                    plaintext = AESGCM(key).decrypt(
                        base64.b64decode(envelope["nonce"]),
                        base64.b64decode(envelope["ciphertext"]),
                        b"condor-memory:1",
                    )
                except (InvalidTag, ValueError) as exc:
                    raise RuntimeError("Memoria cifrada invalida ou adulterada.") from exc
                self._database.close()
                self._database = sqlite3.connect(":memory:", check_same_thread=False)
                self._database.row_factory = sqlite3.Row
                self._database.deserialize(plaintext)
            self._key = bytes(key)
            self.inicializar()

    def lock(self) -> None:
        with self._lock:
            self._persist()
            self._database.close()
            self._database = sqlite3.connect(":memory:", check_same_thread=False)
            self._database.row_factory = sqlite3.Row
            self._key = None
            self.sessao_atual = 0
            self.inicializar()

    def _persist(self) -> None:
        if self._key is None:
            return
        plaintext = self._database.serialize()
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, plaintext, b"condor-memory:1")
        envelope = {
            "version": 1,
            "cipher": "aes-256-gcm",
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        }
        fd, temporary = tempfile.mkstemp(prefix=".memory-", dir=str(self._path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(envelope, stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
            try:
                self._path.chmod(0o600)
            except OSError:
                pass
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def inicializar(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            try:
                conn.executescript(FTS)
                self._fts = True
            except sqlite3.OperationalError as exc:
                # SQLite sem FTS5 compilado: busca cai pra LIKE, tudo segue.
                log.warning("FTS5 indisponível (%s) — busca textual usará LIKE.", exc)
            if self.unlocked:
                agora = time.time()
                conn.executemany(
                    """INSERT OR IGNORE INTO hub_projects
                       (id,nome,tipo,status,progresso,resumo,rota,tom,atualizado)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    [(*item, agora) for item in DEFAULT_PROJECTS],
                )
                conn.executemany(
                    """INSERT OR IGNORE INTO condor_x_parts
                       (id,nome,zona,status,progresso,risco,resumo,atualizado)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    [(*item, agora) for item in DEFAULT_CONDOR_X_PARTS],
                )
        log.info("Memória pronta em RAM; snapshot cifrado: %s", self._path)

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

    # ── ARTX Hub local ────────────────────────────────────────────────────

    @staticmethod
    def _id(prefixo: str) -> str:
        return f"{prefixo}_{uuid.uuid4().hex[:16]}"

    def hub_snapshot(self) -> dict:
        """Estado operacional do Hub; quando bloqueado, nunca expõe dados privados."""
        if not self.unlocked:
            return {
                "locked": True,
                "projects": [],
                "tasks": [],
                "notes": [],
                "parts": [],
                "creator": [],
                "missions": [],
            }
        with self._conn() as conn:
            def rows(query: str, params: tuple = ()) -> list[dict]:
                return [dict(row) for row in conn.execute(query, params).fetchall()]

            return {
                "locked": False,
                "projects": rows("SELECT * FROM hub_projects ORDER BY atualizado DESC"),
                "tasks": rows("SELECT * FROM hub_tasks ORDER BY atualizado DESC LIMIT 100"),
                "notes": rows("SELECT * FROM hub_notes ORDER BY atualizado DESC LIMIT 100"),
                "parts": rows("SELECT * FROM condor_x_parts ORDER BY rowid"),
                "creator": rows("SELECT * FROM creator_items ORDER BY atualizado DESC LIMIT 100"),
                "missions": rows("SELECT * FROM hub_missions ORDER BY atualizado DESC LIMIT 100"),
            }

    def hub_create_task(self, titulo: str, projeto: str, prioridade: str) -> dict:
        agora = time.time()
        item_id = self._id("task")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO hub_tasks
                   (id,titulo,projeto,status,prioridade,criado,atualizado)
                   VALUES(?,?,?,'pendente',?,?,?)""",
                (item_id, titulo, projeto, prioridade, agora, agora),
            )
            row = conn.execute("SELECT * FROM hub_tasks WHERE id=?", (item_id,)).fetchone()
            return dict(row)

    def hub_update_task(self, item_id: str, status: str) -> bool:
        with self._conn() as conn:
            result = conn.execute(
                "UPDATE hub_tasks SET status=?, atualizado=? WHERE id=?",
                (status, time.time(), item_id),
            )
            return result.rowcount > 0

    def hub_delete_task(self, item_id: str) -> bool:
        with self._conn() as conn:
            return conn.execute("DELETE FROM hub_tasks WHERE id=?", (item_id,)).rowcount > 0

    def hub_create_note(self, titulo: str, conteudo: str, projeto: str) -> dict:
        agora = time.time()
        item_id = self._id("note")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO hub_notes
                   (id,titulo,conteudo,projeto,criado,atualizado) VALUES(?,?,?,?,?,?)""",
                (item_id, titulo, conteudo, projeto, agora, agora),
            )
            row = conn.execute("SELECT * FROM hub_notes WHERE id=?", (item_id,)).fetchone()
            return dict(row)

    def hub_update_note(self, item_id: str, titulo: str, conteudo: str) -> bool:
        with self._conn() as conn:
            result = conn.execute(
                "UPDATE hub_notes SET titulo=?, conteudo=?, atualizado=? WHERE id=?",
                (titulo, conteudo, time.time(), item_id),
            )
            return result.rowcount > 0

    def hub_delete_note(self, item_id: str) -> bool:
        with self._conn() as conn:
            return conn.execute("DELETE FROM hub_notes WHERE id=?", (item_id,)).rowcount > 0

    def hub_update_part(self, item_id: str, status: str, progresso: int) -> bool:
        with self._conn() as conn:
            result = conn.execute(
                """UPDATE condor_x_parts SET status=?, progresso=?, atualizado=?
                   WHERE id=?""",
                (status, progresso, time.time(), item_id),
            )
            return result.rowcount > 0

    def hub_create_creator_item(self, titulo: str, etapa: str, notas: str) -> dict:
        agora = time.time()
        item_id = self._id("creator")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO creator_items
                   (id,titulo,etapa,status,notas,criado,atualizado)
                   VALUES(?,?,?,'ideia',?,?,?)""",
                (item_id, titulo, etapa, notas, agora, agora),
            )
            row = conn.execute("SELECT * FROM creator_items WHERE id=?", (item_id,)).fetchone()
            return dict(row)

    def hub_update_creator_item(self, item_id: str, status: str) -> bool:
        with self._conn() as conn:
            result = conn.execute(
                "UPDATE creator_items SET status=?, atualizado=? WHERE id=?",
                (status, time.time(), item_id),
            )
            return result.rowcount > 0

    def hub_create_mission(self, titulo: str, detalhe: str) -> dict:
        agora = time.time()
        item_id = self._id("mission")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO hub_missions
                   (id,titulo,estado,progresso,detalhe,criado,atualizado)
                   VALUES(?,?,'planejada',0,?,?,?)""",
                (item_id, titulo, detalhe, agora, agora),
            )
            row = conn.execute("SELECT * FROM hub_missions WHERE id=?", (item_id,)).fetchone()
            return dict(row)

    def hub_update_mission(self, item_id: str, estado: str, progresso: int) -> bool:
        with self._conn() as conn:
            result = conn.execute(
                """UPDATE hub_missions SET estado=?, progresso=?, atualizado=? WHERE id=?""",
                (estado, progresso, time.time(), item_id),
            )
            return result.rowcount > 0
