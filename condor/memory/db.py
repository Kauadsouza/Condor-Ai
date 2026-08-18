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
import re
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

CREATE TABLE IF NOT EXISTS condor_x_region_items (
    id       TEXT PRIMARY KEY,
    regiao   TEXT NOT NULL,
    tipo     TEXT NOT NULL,
    titulo   TEXT NOT NULL,
    detalhes TEXT NOT NULL DEFAULT '',
    status   TEXT NOT NULL DEFAULT 'rascunho',
    criado   REAL NOT NULL,
    atualizado REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_condor_x_region_items
ON condor_x_region_items(regiao, atualizado DESC);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    active_version_id TEXT,
    created REAL NOT NULL,
    updated REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS project_versions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL,
    UNIQUE(project_id, number)
);

CREATE TABLE IF NOT EXISTS assemblies (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    parent_id TEXT REFERENCES assemblies(id) ON DELETE CASCADE,
    region TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created REAL NOT NULL,
    updated REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS parts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    assembly_id TEXT REFERENCES assemblies(id) ON DELETE SET NULL,
    region TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'component',
    status TEXT NOT NULL DEFAULT 'draft',
    current_version_id TEXT,
    material TEXT,
    weight_g REAL,
    dimensions_json TEXT NOT NULL DEFAULT '{}',
    thickness_mm REAL,
    position_json TEXT NOT NULL DEFAULT '{}',
    rotation_json TEXT NOT NULL DEFAULT '{}',
    integrated INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_parts_project_region ON parts(project_id, region, updated DESC);

CREATE TABLE IF NOT EXISTS part_versions (
    id TEXT PRIMARY KEY,
    part_id TEXT NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    label TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL,
    UNIQUE(part_id, number)
);

CREATE TABLE IF NOT EXISTS anchor_points (
    id TEXT PRIMARY KEY,
    part_id TEXT NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'mechanical',
    position_json TEXT NOT NULL DEFAULT '{}',
    rotation_json TEXT NOT NULL DEFAULT '{}',
    created REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS part_dependencies (
    part_id TEXT NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    depends_on_part_id TEXT NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    created REAL NOT NULL,
    PRIMARY KEY(part_id, depends_on_part_id)
);

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    connection TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    permissions_json TEXT NOT NULL DEFAULT '[]',
    last_seen REAL,
    created REAL NOT NULL,
    updated REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS device_sessions (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    started REAL NOT NULL,
    ended REAL,
    status TEXT NOT NULL DEFAULT 'connected'
);

CREATE TABLE IF NOT EXISTS permissions (
    capability TEXT PRIMARY KEY,
    allowed INTEGER NOT NULL DEFAULT 0,
    scope TEXT NOT NULL DEFAULT 'local',
    updated REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS core_events (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    source TEXT NOT NULL,
    project_id TEXT,
    correlation_id TEXT,
    payload_json TEXT NOT NULL,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_core_events_time ON core_events(timestamp DESC);

CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    part_id TEXT REFERENCES parts(id) ON DELETE SET NULL,
    path TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'document',
    checksum TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS code_buffers (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    language TEXT NOT NULL,
    content TEXT NOT NULL,
    checksum TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    updated REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS code_buffer_versions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    name TEXT NOT NULL,
    language TEXT NOT NULL,
    content TEXT NOT NULL,
    checksum TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'owner',
    created REAL NOT NULL,
    UNIQUE(project_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_code_versions_project
ON code_buffer_versions(project_id, revision DESC);

CREATE TABLE IF NOT EXISTS lab_experiments (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    objective TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'proposed',
    origin TEXT NOT NULL DEFAULT 'owner',
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lab_experiments_updated ON lab_experiments(updated DESC);

CREATE TABLE IF NOT EXISTS biometric_readings (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    recorded REAL NOT NULL,
    consent_ref TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS camera_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    protocol TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    zone TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'configured',
    enabled INTEGER NOT NULL DEFAULT 1,
    created REAL NOT NULL,
    updated REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS security_alerts (
    id TEXT PRIMARY KEY,
    camera_id TEXT REFERENCES camera_sources(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    confidence REAL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_alerts_time ON security_alerts(created DESC);

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

DEFAULT_PERMISSIONS = (
    ("microphone", 0, "local"),
    ("camera", 0, "local"),
    ("serial", 0, "device"),
    ("arduino_upload", 1, "physical"),
    ("bluetooth", 0, "device"),
    ("health_data", 0, "private"),
    ("robot_control", 0, "physical"),
    ("ai_projects", 1, "condor"),
    ("ai_programming", 1, "condor"),
    ("ai_laboratory", 1, "condor"),
    ("ai_memory", 1, "private"),
    ("ai_devices", 0, "device"),
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
        """Abre o banco em RAM. So regrava o snapshot cifrado se algo mudou.

        Antes toda saida deste bloco chamava ``_persist()`` — inclusive consulta
        pura. Cada ``estatisticas()`` ou ``custo_hoje()`` serializava o banco
        inteiro, cifrava em AES-GCM e dava fsync; com a interface consultando em
        laco, eram centenas de KB reescritos por segundo sem nada ter mudado.

        ``total_changes`` decide sozinho, em vez de cada metodo se declarar
        leitura ou escrita: assim um metodo novo nao pode esquecer de persistir.
        """
        with self._lock:
            marca = self._database.total_changes
            try:
                yield self._database
                if self._database.total_changes != marca:
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
                conn.execute(
                    """INSERT OR IGNORE INTO projects
                       (id,name,description,status,created,updated)
                       VALUES('condor-x','Condor X · Modelo 01',
                       'Ambiente técnico central para desenvolvimento digital e físico.',
                       'active',?,?)""",
                    (agora, agora),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO project_versions
                       (id,project_id,number,label,status,notes,created)
                       VALUES('project_version_condor_x_1','condor-x',1,'V1','active',
                       'Base arquitetural inicial do Condor X.',?)""",
                    (agora,),
                )
                conn.execute(
                    """UPDATE projects SET active_version_id=COALESCE(active_version_id,
                       'project_version_condor_x_1') WHERE id='condor-x'"""
                )
                conn.executemany(
                    """INSERT OR IGNORE INTO permissions
                       (capability,allowed,scope,updated) VALUES(?,?,?,?)""",
                    [(*item, agora) for item in DEFAULT_PERMISSIONS],
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
        stop = {
            "para", "como", "isso", "essa", "esse", "aqui", "quero", "condor",
            "sobre", "uma", "que", "com", "por", "das", "dos", "mais", "muito",
        }
        termos = []
        for term in re.findall(r"[\wÀ-ÿ]{3,}", str(consulta).lower()):
            if term not in stop and term not in termos:
                termos.append(term)
        termos = termos[:8]
        if not termos:
            return []
        with self._conn() as conn:
            where = " OR ".join("LOWER(conteudo) LIKE ?" for _ in termos)
            rows = conn.execute(
                f"SELECT papel, conteudo, ts FROM conversas WHERE {where} "
                "ORDER BY ts DESC LIMIT ?",
                (*[f"%{term}%" for term in termos], max(limite * 8, 24)),
            ).fetchall()
        pontuados = []
        for row in rows:
            item = dict(row)
            content = item["conteudo"].lower()
            score = sum(1 for term in termos if term in content)
            pontuados.append((score, item["ts"], item))
        pontuados.sort(key=lambda value: (-value[0], -value[1]))
        return [item for _, _, item in pontuados[:limite]]

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

    def condor_x_region_items(self, regiao: str | None = None) -> list[dict]:
        with self._conn() as conn:
            if regiao:
                rows = conn.execute(
                    "SELECT * FROM condor_x_region_items WHERE regiao=? ORDER BY atualizado DESC",
                    (regiao,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM condor_x_region_items ORDER BY atualizado DESC"
                ).fetchall()
            return [dict(row) for row in rows]

    def condor_x_create_region_item(
        self, regiao: str, tipo: str, titulo: str, detalhes: str
    ) -> dict:
        agora = time.time()
        item_id = self._id("cx")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO condor_x_region_items
                   (id,regiao,tipo,titulo,detalhes,status,criado,atualizado)
                   VALUES(?,?,?,?,?,'rascunho',?,?)""",
                (item_id, regiao, tipo, titulo, detalhes, agora, agora),
            )
            row = conn.execute(
                "SELECT * FROM condor_x_region_items WHERE id=?", (item_id,)
            ).fetchone()
            return dict(row)

    def condor_x_update_region_item(
        self, item_id: str, titulo: str, detalhes: str, status: str
    ) -> bool:
        with self._conn() as conn:
            result = conn.execute(
                """UPDATE condor_x_region_items
                   SET titulo=?, detalhes=?, status=?, atualizado=? WHERE id=?""",
                (titulo, detalhes, status, time.time(), item_id),
            )
            return result.rowcount > 0

    def condor_x_delete_region_item(self, item_id: str) -> bool:
        with self._conn() as conn:
            return conn.execute(
                "DELETE FROM condor_x_region_items WHERE id=?", (item_id,)
            ).rowcount > 0

    # ── Condor Core: projetos, peças, versões e eventos ──────────────────

    @staticmethod
    def _json_object(value) -> str:
        return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _safe_json_dict(value, label: str, max_bytes: int = 220_000) -> dict:
        """Normaliza snapshots do editor e impede payloads ilimitados/NaN."""
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"{label} precisa ser um objeto")
        try:
            encoded = json.dumps(
                value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{label} contém dados inválidos") from exc
        if len(encoded) > max_bytes:
            raise ValueError(f"{label} excede o limite de {max_bytes // 1000} KB")
        return json.loads(encoded.decode("utf-8"))

    @classmethod
    def _safe_geometry(cls, value) -> dict:
        geometry = cls._safe_json_dict(value, "geometry", 180_000)
        if not geometry:
            return {}
        if geometry.get("schema") != "condor-parametric-surface-v1":
            raise ValueError("schema de geometry inválido")
        parameters = geometry.get("parameters", {})
        if not isinstance(parameters, dict) or len(parameters) > 32:
            raise ValueError("parameters de geometry inválido")
        if any(not isinstance(item, (int, float)) or isinstance(item, bool) for item in parameters.values()):
            raise ValueError("parameters aceita somente valores numéricos")
        points = geometry.get("technicalPoints", [])
        if not isinstance(points, list) or len(points) > 128 or any(not isinstance(item, dict) for item in points):
            raise ValueError("technicalPoints excede o limite seguro")
        layers = geometry.get("layers", {})
        if not isinstance(layers, dict) or len(layers) > 16:
            raise ValueError("layers de geometry inválido")
        return geometry

    @staticmethod
    def _decode_json(value: str, fallback):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback

    def get_project(self, project_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT p.*, v.label AS active_version_label
                   FROM projects p LEFT JOIN project_versions v ON v.id=p.active_version_id
                   WHERE p.id=?""", (project_id,),
            ).fetchone()
            return dict(row) if row else None

    def project_snapshot(self, project_id: str) -> dict:
        if not self.unlocked:
            return {"locked": True, "project": None, "parts": [], "versions": []}
        with self._conn() as conn:
            project = self.get_project(project_id)
            if project is None:
                return {"locked": False, "project": None, "parts": [], "versions": []}
            parts = [dict(row) for row in conn.execute(
                "SELECT * FROM parts WHERE project_id=? ORDER BY updated DESC", (project_id,)
            ).fetchall()]
            for part in parts:
                part["dimensions"] = self._decode_json(part.pop("dimensions_json"), {})
                part["position"] = self._decode_json(part.pop("position_json"), {})
                part["rotation"] = self._decode_json(part.pop("rotation_json"), {})
                part["integrated"] = bool(part["integrated"])
                version = conn.execute(
                    "SELECT snapshot_json,label FROM part_versions WHERE id=?",
                    (part.get("current_version_id"),),
                ).fetchone()
                part["current_snapshot"] = (
                    self._decode_json(version["snapshot_json"], {}) if version else {}
                )
                part["current_version_label"] = version["label"] if version else None
            versions = [dict(row) for row in conn.execute(
                "SELECT * FROM project_versions WHERE project_id=? ORDER BY number DESC", (project_id,)
            ).fetchall()]
            return {"locked": False, "project": project, "parts": parts, "versions": versions}

    def create_part_draft(self, project_id: str, region: str, payload: dict) -> dict:
        if self.get_project(project_id) is None:
            raise KeyError("projeto não encontrado")
        agora = time.time()
        part_id = self._id("part")
        version_id = self._id("partv")
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("name obrigatório")
        part_type = str(payload.get("type") or "component").strip()[:50]
        material = str(payload.get("material") or "").strip()[:120] or None
        geometry = self._safe_geometry(payload.get("geometry"))
        snapshot = self._safe_json_dict({
            "name": name[:180], "type": part_type, "region": region,
            "material": material, "weight_g": payload.get("weight_g"),
            "dimensions": payload.get("dimensions") if isinstance(payload.get("dimensions"), dict) else {},
            "thickness_mm": payload.get("thickness_mm"),
            "position": payload.get("position") if isinstance(payload.get("position"), dict) else {},
            "rotation": payload.get("rotation") if isinstance(payload.get("rotation"), dict) else {},
            "geometry": geometry,
        }, "snapshot")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO parts
                   (id,project_id,region,name,type,status,current_version_id,material,weight_g,
                    dimensions_json,thickness_mm,position_json,rotation_json,integrated,created,updated)
                   VALUES(?,?,?,?,?,'draft',?,?,?,?,?,?,?,0,?,?)""",
                (part_id, project_id, region[:80], name[:180], part_type, version_id, material,
                 payload.get("weight_g"), self._json_object(snapshot["dimensions"]),
                 payload.get("thickness_mm"), self._json_object(snapshot["position"]),
                 self._json_object(snapshot["rotation"]), agora, agora),
            )
            conn.execute(
                """INSERT INTO part_versions
                   (id,part_id,project_id,number,label,snapshot_json,notes,created)
                   VALUES(?,?,?,1,'V1',?,?,?)""",
                (version_id, part_id, project_id, json.dumps(snapshot, ensure_ascii=False),
                 str(payload.get("notes") or "")[:4000], agora),
            )
        return next(
            part for part in self.project_snapshot(project_id)["parts"]
            if part["id"] == part_id
        )

    def create_part_version(self, part_id: str, payload: dict) -> dict:
        agora = time.time()
        with self._conn() as conn:
            part = conn.execute("SELECT * FROM parts WHERE id=?", (part_id,)).fetchone()
            if not part:
                raise KeyError("peça não encontrada")
            number = int(conn.execute(
                "SELECT COALESCE(MAX(number),0)+1 FROM part_versions WHERE part_id=?", (part_id,)
            ).fetchone()[0])
            version_id = self._id("partv")
            snapshot = self._safe_json_dict(payload.get("snapshot"), "snapshot")
            if not snapshot:
                snapshot = {"name": part["name"], "type": part["type"], "region": part["region"]}
            elif "geometry" in snapshot:
                snapshot["geometry"] = self._safe_geometry(snapshot["geometry"])
            conn.execute(
                """INSERT INTO part_versions
                   (id,part_id,project_id,number,label,snapshot_json,notes,created)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (version_id, part_id, part["project_id"], number, f"V{number}",
                 json.dumps(snapshot, ensure_ascii=False), str(payload.get("notes") or "")[:4000], agora),
            )
            geometry = snapshot.get("geometry") if isinstance(snapshot.get("geometry"), dict) else {}
            parameters = geometry.get("parameters") if isinstance(geometry.get("parameters"), dict) else None
            dimensions = parameters or self._decode_json(part["dimensions_json"], {})
            thickness = dimensions.get("thickness", part["thickness_mm"]) if isinstance(dimensions, dict) else part["thickness_mm"]
            name = str(snapshot.get("name") or part["name"]).strip()[:180] or part["name"]
            conn.execute(
                """UPDATE parts SET current_version_id=?,name=?,dimensions_json=?,
                   thickness_mm=?,updated=? WHERE id=?""",
                (version_id, name, self._json_object(dimensions), thickness, agora, part_id),
            )
            row = conn.execute("SELECT * FROM part_versions WHERE id=?", (version_id,)).fetchone()
            result = dict(row)
            result["snapshot"] = self._decode_json(result.pop("snapshot_json"), {})
            return result

    def integrate_part(self, part_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT project_id,region,type FROM parts WHERE id=?", (part_id,)).fetchone()
            if not row:
                return None
            agora = time.time()
            if row["type"] == "parametric_3d_model":
                conn.execute(
                    """UPDATE parts
                       SET status=CASE WHEN status='integrated' THEN 'draft' ELSE status END,
                           integrated=0,updated=?
                       WHERE project_id=? AND region=? AND type='parametric_3d_model' AND id<>?""",
                    (agora, row["project_id"], row["region"], part_id),
                )
            conn.execute(
                "UPDATE parts SET status='integrated', integrated=1, updated=? WHERE id=?",
                (agora, part_id),
            )
            return next((part for part in self.project_snapshot(row["project_id"])["parts"] if part["id"] == part_id), None)

    def part_versions(self, part_id: str) -> list[dict]:
        with self._conn() as conn:
            result = []
            for row in conn.execute(
                "SELECT * FROM part_versions WHERE part_id=? ORDER BY number DESC", (part_id,)
            ).fetchall():
                item = dict(row)
                item["snapshot"] = self._decode_json(item.pop("snapshot_json"), {})
                result.append(item)
            return result

    def registrar_evento(self, event: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO core_events
                   (id,type,source,project_id,correlation_id,payload_json,timestamp)
                   VALUES(?,?,?,?,?,?,?)""",
                (event["id"], event["type"], event["source"], event.get("project_id"),
                 event.get("correlation_id"), json.dumps(event.get("payload", {}), ensure_ascii=False),
                 event["timestamp"]),
            )

    def eventos_recentes(self, limite: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM core_events ORDER BY timestamp DESC LIMIT ?", (max(1, min(limite, 250)),)
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["payload"] = self._decode_json(item.pop("payload_json"), {})
                result.append(item)
            return result

    def devices(self) -> list[dict]:
        with self._conn() as conn:
            result = []
            for row in conn.execute("SELECT * FROM devices ORDER BY updated DESC").fetchall():
                item = dict(row)
                item["capabilities"] = self._decode_json(item.pop("capabilities_json"), [])
                item["permissions"] = self._decode_json(item.pop("permissions_json"), [])
                result.append(item)
            return result

    def upsert_device(self, device: dict) -> dict:
        agora = time.time()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO devices
                   (id,name,type,connection,status,capabilities_json,permissions_json,last_seen,created,updated)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name,type=excluded.type,
                   connection=excluded.connection,status=excluded.status,
                   capabilities_json=excluded.capabilities_json,last_seen=excluded.last_seen,
                   updated=excluded.updated""",
                (device["id"], device["name"], device["type"], device["connection"],
                 device.get("status", "available"), json.dumps(device.get("capabilities", []), ensure_ascii=False),
                 json.dumps(device.get("permissions", []), ensure_ascii=False), agora, agora, agora),
            )
        return next(item for item in self.devices() if item["id"] == device["id"])

    def start_device_session(self, device_id: str, project_id: str | None) -> str:
        session_id = self._id("device_session")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO device_sessions(id,device_id,project_id,started,status) VALUES(?,?,?,?, 'connected')",
                (session_id, device_id, project_id, time.time()),
            )
        return session_id

    def disconnect_device(self, device_id: str) -> None:
        agora = time.time()
        with self._conn() as conn:
            conn.execute("UPDATE devices SET status='disconnected',updated=? WHERE id=?", (agora, device_id))
            conn.execute(
                "UPDATE device_sessions SET status='disconnected',ended=? WHERE device_id=? AND ended IS NULL",
                (agora, device_id),
            )

    def code_buffer(self, project_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM code_buffers WHERE project_id=?", (project_id,)).fetchone()
            return dict(row) if row else None

    def save_code_buffer(
        self, project_id: str, name: str, language: str, content: str,
        checksum: str, source: str = "owner",
    ) -> dict:
        existing = self.code_buffer(project_id)
        if existing and existing["checksum"] == checksum and existing["name"] == name and existing["language"] == language:
            return existing
        agora = time.time()
        next_revision = int(existing["revision"]) + 1 if existing else 1
        with self._conn() as conn:
            if existing:
                conn.execute(
                    """INSERT OR IGNORE INTO code_buffer_versions
                       (id,project_id,revision,name,language,content,checksum,source,created)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (self._id("codev"), project_id, int(existing["revision"]), existing["name"],
                     existing["language"], existing["content"], existing["checksum"],
                     "migration", float(existing["updated"])),
                )
            conn.execute(
                """INSERT INTO code_buffers(project_id,name,language,content,checksum,revision,updated)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(project_id) DO UPDATE SET name=excluded.name,language=excluded.language,
                   content=excluded.content,checksum=excluded.checksum,
                   revision=excluded.revision,updated=excluded.updated""",
                (project_id, name, language, content, checksum, next_revision, agora),
            )
            conn.execute(
                """INSERT OR REPLACE INTO code_buffer_versions
                   (id,project_id,revision,name,language,content,checksum,source,created)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (self._id("codev"), project_id, next_revision, name, language, content,
                 checksum, str(source or "owner")[:40], agora),
            )
        return self.code_buffer(project_id) or {}

    def code_versions(self, project_id: str, limit: int = 30) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT revision,name,language,checksum,source,created
                   FROM code_buffer_versions WHERE project_id=?
                   ORDER BY revision DESC LIMIT ?""",
                (project_id, max(1, min(int(limit), 100))),
            ).fetchall()
            return [dict(row) for row in rows]

    def restore_code_version(self, project_id: str, revision: int, source: str = "owner-restore") -> dict:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT name,language,content,checksum FROM code_buffer_versions
                   WHERE project_id=? AND revision=?""",
                (project_id, int(revision)),
            ).fetchone()
        if row is None:
            raise KeyError("versao de codigo nao encontrada")
        return self.save_code_buffer(
            project_id, row["name"], row["language"], row["content"], row["checksum"], source
        )

    def lab_experiments(self, project_id: str | None = None) -> list[dict]:
        with self._conn() as conn:
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM lab_experiments WHERE project_id=? ORDER BY updated DESC", (project_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM lab_experiments ORDER BY updated DESC").fetchall()
            return [dict(row) for row in rows]

    def create_lab_experiment(self, project_id: str | None, title: str, objective: str, origin: str) -> dict:
        experiment_id = self._id("experiment"); agora = time.time()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO lab_experiments(id,project_id,title,objective,status,origin,created,updated)
                   VALUES(?,?,?,?, 'proposed',?,?,?)""",
                (experiment_id, project_id, title, objective, origin, agora, agora),
            )
        return next(item for item in self.lab_experiments(project_id) if item["id"] == experiment_id)

    def update_lab_experiment(self, experiment_id: str, status: str) -> dict | None:
        if status not in {"proposed", "testing", "done"}:
            raise ValueError("status de experimento invalido")
        with self._conn() as conn:
            result = conn.execute(
                "UPDATE lab_experiments SET status=?,updated=? WHERE id=?",
                (status, time.time(), experiment_id),
            )
            if result.rowcount == 0:
                return None
            row = conn.execute("SELECT * FROM lab_experiments WHERE id=?", (experiment_id,)).fetchone()
            return dict(row) if row else None

    def permissions(self) -> list[dict]:
        with self._conn() as conn:
            return [
                {**dict(row), "allowed": bool(row["allowed"])}
                for row in conn.execute("SELECT * FROM permissions ORDER BY capability").fetchall()
            ]

    def set_permission(self, capability: str, allowed: bool) -> bool:
        with self._conn() as conn:
            result = conn.execute(
                "UPDATE permissions SET allowed=?, updated=? WHERE capability=?",
                (int(allowed), time.time(), capability),
            )
            return result.rowcount > 0

    def permission_allowed(self, capability: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT allowed FROM permissions WHERE capability=?", (capability,)
            ).fetchone()
            return bool(row and row["allowed"])

    # ── Camera Bridge e alertas locais ───────────────────────────────────

    def create_camera_source(self, name: str, protocol: str, endpoint: str, zone: str) -> dict:
        agora = time.time()
        camera_id = self._id("camera")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO camera_sources
                   (id,name,protocol,endpoint,zone,status,enabled,created,updated)
                   VALUES(?,?,?,?,?,'configured',1,?,?)""",
                (camera_id, name, protocol, endpoint, zone, agora, agora),
            )
        return next(item for item in self.camera_sources() if item["id"] == camera_id)

    def camera_sources(self) -> list[dict]:
        with self._conn() as conn:
            result = []
            for row in conn.execute(
                "SELECT id,name,protocol,zone,status,enabled,created,updated FROM camera_sources ORDER BY updated DESC"
            ).fetchall():
                item = dict(row)
                item["enabled"] = bool(item["enabled"])
                result.append(item)
            return result

    def camera_source_private(self, camera_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM camera_sources WHERE id=?", (camera_id,)).fetchone()
            return dict(row) if row else None

    def update_camera_status(self, camera_id: str, status: str) -> bool:
        with self._conn() as conn:
            return conn.execute(
                "UPDATE camera_sources SET status=?, updated=? WHERE id=?",
                (status, time.time(), camera_id),
            ).rowcount > 0

    def create_security_alert(
        self, camera_id: str | None, event_type: str, summary: str, confidence: float | None
    ) -> dict:
        alert_id = self._id("alert")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO security_alerts
                   (id,camera_id,event_type,summary,confidence,acknowledged,created)
                   VALUES(?,?,?,?,?,0,?)""",
                (alert_id, camera_id, event_type, summary, confidence, time.time()),
            )
            row = conn.execute("SELECT * FROM security_alerts WHERE id=?", (alert_id,)).fetchone()
            item = dict(row)
            item["acknowledged"] = bool(item["acknowledged"])
            return item

    def security_alerts(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            return [
                {**dict(row), "acknowledged": bool(row["acknowledged"])}
                for row in conn.execute(
                    "SELECT * FROM security_alerts ORDER BY created DESC LIMIT ?",
                    (max(1, min(limit, 200)),),
                ).fetchall()
            ]

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
