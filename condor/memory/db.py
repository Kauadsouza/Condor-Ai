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
import math
import re
import sqlite3
import struct
import time
import unicodedata
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

CREATE TABLE IF NOT EXISTS memory_meta (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

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

-- Diário do próprio CONDOR: o que ele fez, o que o dono disse sobre ele,
-- as opiniões que ele formou e os planos que o dono comentou. É a memória
-- dele sobre si mesmo — a de fatos (acima) é sobre o dono.
CREATE TABLE IF NOT EXISTS diario (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo   TEXT NOT NULL,
    texto  TEXT NOT NULL,
    ts     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_diario_tipo_ts ON diario(tipo, ts DESC);

-- Exemplos para treinar o modelo local com o jeito do dono. Cada resposta
-- real do cérebro vira um exemplo; o dono avalia (👍/👎) e pode corrigir.
CREATE TABLE IF NOT EXISTS treino_exemplos (
    id        TEXT PRIMARY KEY,
    pedido    TEXT NOT NULL,
    resposta  TEXT NOT NULL,
    correcao  TEXT NOT NULL DEFAULT '',
    contexto  TEXT NOT NULL DEFAULT '',
    anteriores TEXT NOT NULL DEFAULT '[]',
    provedor  TEXT NOT NULL DEFAULT '',
    modelo    TEXT NOT NULL DEFAULT '',
    por_voz   INTEGER NOT NULL DEFAULT 0,
    nota      INTEGER NOT NULL DEFAULT 0,
    criado    REAL NOT NULL,
    avaliado  REAL
);
CREATE INDEX IF NOT EXISTS idx_treino_criado ON treino_exemplos(criado DESC);

-- Galeria: metadados aqui, pixels cifrados em ~/.condor/memory/gallery.
CREATE TABLE IF NOT EXISTS imagens (
    id           TEXT PRIMARY KEY,
    pedido       TEXT NOT NULL,
    prompt_final TEXT NOT NULL DEFAULT '',
    modelo       TEXT NOT NULL DEFAULT '',
    seed         INTEGER NOT NULL DEFAULT -1,
    largura      INTEGER NOT NULL DEFAULT 0,
    altura       INTEGER NOT NULL DEFAULT 0,
    origem       TEXT NOT NULL DEFAULT 'chat',
    criado       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_imagens_criado ON imagens(criado DESC);

-- Trocas ainda nao analisadas pelo extrator. Ficam no snapshot cifrado para
-- sobreviver a reinicio e a cerebro fora do ar: nada dito se perde.
CREATE TABLE IF NOT EXISTS memoria_pendente (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fala_dono   TEXT NOT NULL,
    fala_condor TEXT NOT NULL DEFAULT '',
    assinatura  TEXT NOT NULL UNIQUE,
    tentativas  INTEGER NOT NULL DEFAULT 0,
    criado      REAL NOT NULL
);

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

CREATE TABLE IF NOT EXISTS condor_x_propulsion_layouts (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    data_json TEXT NOT NULL,
    criado    REAL NOT NULL,
    atualizado REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_condor_x_propulsion_layouts_updated
ON condor_x_propulsion_layouts(atualizado DESC);

CREATE TABLE IF NOT EXISTS condor_x_propulsion_runs (
    id          TEXT PRIMARY KEY,
    layout_id   TEXT NOT NULL REFERENCES condor_x_propulsion_layouts(id) ON DELETE CASCADE,
    input_json  TEXT NOT NULL,
    result_json TEXT NOT NULL,
    criado      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_condor_x_propulsion_runs_layout
ON condor_x_propulsion_runs(layout_id, criado DESC);

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
    decision TEXT NOT NULL DEFAULT 'ask',
    one_time_uses INTEGER NOT NULL DEFAULT 0,
    updated REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS permission_requests (
    id TEXT PRIMARY KEY,
    capability TEXT NOT NULL REFERENCES permissions(capability) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'condor',
    status TEXT NOT NULL DEFAULT 'pending',
    created REAL NOT NULL,
    resolved REAL
);
CREATE INDEX IF NOT EXISTS idx_permission_requests_pending
ON permission_requests(status, created DESC);

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

CREATE TABLE IF NOT EXISTS memory_episodes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    source TEXT NOT NULL,
    project_id TEXT,
    device_id TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    occurred_at REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_episodes_time
ON memory_episodes(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_episodes_project
ON memory_episodes(project_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS world_beliefs (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    confidence REAL NOT NULL DEFAULT 1.0,
    source TEXT NOT NULL,
    valid_from REAL NOT NULL,
    valid_until REAL,
    supersedes_id TEXT REFERENCES world_beliefs(id) ON DELETE SET NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_world_beliefs_active
ON world_beliefs(subject, predicate, status, updated DESC);

CREATE TABLE IF NOT EXISTS durable_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 50,
    source TEXT NOT NULL DEFAULT 'owner',
    due_at REAL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_durable_tasks_status
ON durable_tasks(status, priority DESC, updated DESC);

CREATE TABLE IF NOT EXISTS task_checkpoints (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES durable_tasks(id) ON DELETE CASCADE,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_checkpoints_task
ON task_checkpoints(task_id, created ASC);

CREATE TABLE IF NOT EXISTS device_identities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    public_key TEXT NOT NULL UNIQUE,
    trust_state TEXT NOT NULL DEFAULT 'pending',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    created REAL NOT NULL,
    last_seen REAL,
    updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_device_identities_trust
ON device_identities(trust_state, updated DESC);

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

CREATE TABLE IF NOT EXISTS face_identity_profile (
    owner_id TEXT PRIMARY KEY CHECK(owner_id = 'owner'),
    template_json TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    threshold REAL NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    model TEXT NOT NULL,
    created REAL NOT NULL,
    updated REAL NOT NULL
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

"""

DEFAULT_PERMISSIONS = (
    ("microphone", 0, "local"),
    ("camera", 0, "local"),
    ("chat_camera", 0, "local"),
    ("gesture_camera", 0, "local"),
    ("gesture_pc_control", 0, "local"),
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
    ("ai_media", 0, "local"),
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


_MEMORY_STOPWORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "ele", "ela", "eu", "me", "meu", "meus", "minha", "minhas",
    "na", "nas", "no", "nos", "o", "os", "ou", "para", "por", "que", "se",
    "seu", "seus", "sua", "suas", "tem", "ter", "uma", "um", "voce", "condor",
}


def _termos_memoria(texto: str) -> set[str]:
    """Termos estáveis para explicar associações, sem depender de um modelo."""
    normalizado = unicodedata.normalize("NFKD", str(texto).casefold())
    normalizado = "".join(c for c in normalizado if not unicodedata.combining(c))
    return {
        termo for termo in re.findall(r"[a-z0-9]{3,}", normalizado)
        if termo not in _MEMORY_STOPWORDS and not termo.isdigit()
    }


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
    def _conn(self, persistir: bool = True):
        """Abre o banco em RAM. So regrava o snapshot cifrado se algo mudou.

        Antes toda saida deste bloco chamava ``_persist()`` — inclusive consulta
        pura. Cada ``estatisticas()`` ou ``custo_hoje()`` serializava o banco
        inteiro, cifrava em AES-GCM e dava fsync; com a interface consultando em
        laco, eram centenas de KB reescritos por segundo sem nada ter mudado.

        ``total_changes`` decide sozinho, em vez de cada metodo se declarar
        leitura ou escrita: assim um metodo novo nao pode esquecer de persistir.
        ``persistir=False`` serve so para contadores descartaveis (acessos do
        recall): a mudanca fica na RAM e segue junto na proxima gravacao real.
        """
        with self._lock:
            marca = self._database.total_changes
            try:
                yield self._database
                if self._database.total_changes != marca:
                    self._database.commit()
                    if persistir:
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
            permission_columns = {
                str(row["name"]) for row in conn.execute("PRAGMA table_info(permissions)")
            }
            if "decision" not in permission_columns:
                conn.execute(
                    "ALTER TABLE permissions ADD COLUMN decision TEXT NOT NULL DEFAULT 'ask'"
                )
            if "one_time_uses" not in permission_columns:
                conn.execute(
                    "ALTER TABLE permissions ADD COLUMN one_time_uses INTEGER NOT NULL DEFAULT 0"
                )
            permission_migration = conn.execute(
                "SELECT valor FROM memory_meta WHERE chave='permission_decisions_v1'"
            ).fetchone()
            if permission_migration is None:
                conn.execute(
                    """UPDATE permissions
                       SET decision=CASE WHEN allowed=1 THEN 'always' ELSE 'ask' END,
                           one_time_uses=0"""
                )
                conn.execute(
                    "INSERT INTO memory_meta(chave,valor) VALUES('permission_decisions_v1','done')"
                )
            fato_columns = {
                str(row["name"]) for row in conn.execute("PRAGMA table_info(fatos)")
            }
            if "embedding_modelo" not in fato_columns:
                # Vetores de modelos diferentes nao sao comparaveis. Os antigos
                # (OpenAI) ficam marcados e o extrator os refaz localmente.
                conn.execute("ALTER TABLE fatos ADD COLUMN embedding_modelo TEXT NOT NULL DEFAULT ''")
                conn.execute(
                    "UPDATE fatos SET embedding_modelo='text-embedding-3-small' "
                    "WHERE embedding IS NOT NULL"
                )
            try:
                conn.executescript(FTS)
                self._fts = True
                migrado = conn.execute(
                    "SELECT valor FROM memory_meta WHERE chave='fts_rebuild_v1'"
                ).fetchone()
                if migrado is None:
                    # Snapshots criados antes do FTS já podem conter fatos. Os
                    # gatilhos cuidam apenas das próximas escritas, então a
                    # migração precisa indexar o conteúdo antigo uma vez.
                    conn.execute("INSERT INTO fatos_fts(fatos_fts) VALUES('rebuild')")
                    conn.execute(
                        "INSERT INTO memory_meta(chave,valor) VALUES('fts_rebuild_v1','done')"
                    )
            except sqlite3.OperationalError as exc:
                # SQLite sem FTS5 compilado: busca cai pra LIKE, tudo segue.
                log.warning("FTS5 indisponível (%s) — busca textual usará LIKE.", exc)
            if self.unlocked:
                agora = time.time()
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
                from condor.engine.contracts import blank_layout
                for layout_id, name in (("layout-a", "LAYOUT A"), ("layout-b", "LAYOUT B")):
                    layout = blank_layout(layout_id, name)
                    conn.execute(
                        """INSERT OR IGNORE INTO condor_x_propulsion_layouts
                           (id,name,data_json,criado,atualizado) VALUES(?,?,?,?,?)""",
                        (layout_id, name, json.dumps(layout, ensure_ascii=False, allow_nan=False), agora, agora),
                    )
                conn.executemany(
                    """INSERT OR IGNORE INTO permissions
                       (capability,allowed,scope,decision,one_time_uses,updated)
                       VALUES(?,?,?,?,?,?)""",
                    [
                        (capability, allowed, scope, "always" if allowed else "ask", 0, agora)
                        for capability, allowed, scope in DEFAULT_PERMISSIONS
                    ],
                )
                # A geração deixou de transmitir prompts para um conector.
                # Conserva a decisão do dono, mas corrige o escopo legado.
                conn.execute(
                    "UPDATE permissions SET scope='local', updated=? "
                    "WHERE capability='ai_media' AND scope!='local'",
                    (agora,),
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

    _UPSERT_FATO = """INSERT INTO fatos(categoria, chave, valor, confianca, origem,
                                   embedding, embedding_modelo, criado, atualizado)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(categoria, chave) DO UPDATE SET
                       valor=excluded.valor,
                       confianca=excluded.confianca,
                       origem=excluded.origem,
                       -- Texto novo sem vetor novo: o vetor antigo descreveria
                       -- outra coisa. Zera e deixa o extrator recalcular.
                       embedding=CASE
                           WHEN excluded.embedding IS NOT NULL THEN excluded.embedding
                           WHEN excluded.valor = fatos.valor THEN fatos.embedding
                           ELSE NULL END,
                       embedding_modelo=CASE
                           WHEN excluded.embedding IS NOT NULL THEN excluded.embedding_modelo
                           WHEN excluded.valor = fatos.valor THEN fatos.embedding_modelo
                           ELSE '' END,
                       atualizado=excluded.atualizado"""

    def salvar_fato(self, categoria: str, chave: str, valor: str,
                    confianca: float = 0.8, origem: str = "conversa",
                    embedding: list[float] | None = None,
                    embedding_modelo: str = "") -> int:
        """Grava (ou atualiza) um fato. Chave repetida na mesma categoria
        sobrescreve — é assim que ele corrige o que aprendeu errado."""
        agora = time.time()
        blob = _empacotar(embedding) if embedding else None
        with self._conn() as conn:
            conn.execute(
                self._UPSERT_FATO,
                (categoria, chave, valor, confianca, origem, blob,
                 embedding_modelo if blob else "", agora, agora),
            )
            # lastrowid nao e confiavel depois de ON CONFLICT DO UPDATE.
            row = conn.execute("SELECT id FROM fatos WHERE categoria=? AND chave=?",
                               (categoria, chave)).fetchone()
            return row["id"] if row else 0

    def salvar_fatos_lote(self, fatos: list[dict], origem: str = "conversa") -> list[dict]:
        """Insere/atualiza muitos fatos com uma unica persistencia cifrada.

        O snapshot inteiro da memoria e autenticado e recifrado a cada escrita.
        Fazer um ``salvar_fato`` por item tornava perfis longos proporcionalmente
        lentos. Este metodo preserva o mesmo upsert por ``(categoria, chave)``,
        mas confirma todos os itens dentro de uma transacao so.

        Cada item confirmado volta com ``status``: ``novo``, ``atualizado`` ou
        ``igual`` — so os dois primeiros sao aprendizado de verdade.
        """
        if not fatos:
            return []
        agora = time.time()
        confirmados: list[dict] = []
        with self._conn() as conn:
            for fato in fatos[:100]:
                categoria = str(fato.get("categoria") or "pessoal")[:40]
                chave = str(fato.get("chave") or "")[:80]
                valor = str(fato.get("valor") or "")[:2000]
                if not chave or not valor:
                    continue
                try:
                    confianca = max(0.0, min(1.0, float(fato.get("confianca", 0.8))))
                except (TypeError, ValueError):
                    confianca = 0.8
                fato_origem = str(fato.get("origem") or origem)[:80]
                embedding = fato.get("embedding")
                blob = _empacotar(embedding) if isinstance(embedding, list) and embedding else None
                modelo = str(fato.get("embedding_modelo") or "")[:80] if blob else ""
                anterior = conn.execute(
                    "SELECT valor FROM fatos WHERE categoria=? AND chave=?",
                    (categoria, chave),
                ).fetchone()
                if anterior is None:
                    status = "novo"
                elif anterior["valor"] != valor:
                    status = "atualizado"
                else:
                    status = "igual"
                if status == "igual" and blob is None:
                    # Nada a gravar: nao reescreve o snapshot nem finge novidade.
                    row = conn.execute(
                        "SELECT id,categoria,chave,valor,confianca,origem,atualizado "
                        "FROM fatos WHERE categoria=? AND chave=?",
                        (categoria, chave),
                    ).fetchone()
                    if row:
                        confirmados.append({**dict(row), "status": status})
                    continue
                conn.execute(
                    self._UPSERT_FATO,
                    (categoria, chave, valor, confianca, fato_origem, blob, modelo, agora, agora),
                )
                row = conn.execute(
                    "SELECT id,categoria,chave,valor,confianca,origem,atualizado "
                    "FROM fatos WHERE categoria=? AND chave=?",
                    (categoria, chave),
                ).fetchone()
                if row:
                    confirmados.append({**dict(row), "status": status})
        return confirmados

    def esquecer_fato(self, fato_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM fatos WHERE id=?", (fato_id,))
            return cur.rowcount > 0

    def fato_por_chave(self, categoria: str, chave: str) -> dict | None:
        """Consulta direta para confirmação/deduplicação do aprendizado local."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id,categoria,chave,valor,confianca,origem,atualizado "
                "FROM fatos WHERE categoria=? AND chave=?",
                (categoria, chave),
            ).fetchone()
            return dict(row) if row else None

    def buscar_fatos(self, consulta: str, limite: int = 8,
                     embedding: list[float] | None = None,
                     embedding_modelo: str = "") -> list[dict]:
        """Busca híbrida: texto exato (FTS5) + significado (embedding).
        Junta os dois, tira duplicado e devolve ordenado por relevância."""
        achados: dict[int, dict] = {}

        with self._conn() as conn:
            # 1. Textual
            if self._fts and consulta.strip():
                stop = {
                    "qual", "quais", "quem", "onde", "como", "meu", "minha",
                    "meus", "minhas", "sobre", "isso", "essa", "esse", "condor",
                    "voce", "você", "lembra", "sabe", "fale", "diga",
                }
                palavras = []
                for termo in re.findall(r"[\wÀ-ÿ]{3,}", consulta.casefold()):
                    if termo not in stop and termo not in palavras:
                        palavras.append(termo)
                termos = " OR ".join(
                    f'"{termo}"' for termo in palavras[:10]
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
                        # bm25 ja vem ordenado: o melhor casamento textual vale
                        # 1.0 e os seguintes decaem, em vez de empatar todos.
                        for posicao, r in enumerate(rows):
                            d = dict(r)
                            d["relevancia"] = 1.0 / (1.0 + 0.25 * posicao)
                            achados[d["id"]] = d
                    except sqlite3.OperationalError:
                        pass
            elif consulta.strip():
                termos = [
                    termo for termo in re.findall(r"[\wÀ-ÿ]{3,}", consulta.casefold())
                ][:6] or [consulta.strip()]
                filtro = " OR ".join("valor LIKE ? OR chave LIKE ?" for _ in termos)
                parametros = [p for termo in termos for p in (f"%{termo}%", f"%{termo}%")]
                rows = conn.execute(
                    f"SELECT * FROM fatos WHERE {filtro} LIMIT ?",
                    (*parametros, limite * 2),
                ).fetchall()
                for r in rows:
                    d = dict(r)
                    d["relevancia"] = 1.0
                    achados[d["id"]] = d

            # 2. Semântica
            if embedding:
                for sim, d in self._mais_parecidos(conn, embedding, embedding_modelo,
                                                   0.30, limite * 2):
                    if d["id"] in achados:
                        achados[d["id"]]["relevancia"] += sim
                    else:
                        d["relevancia"] = sim
                        achados[d["id"]] = d

        ordenados = sorted(achados.values(), key=lambda d: -d["relevancia"])[:limite]
        if ordenados:
            # Contador de uso nao justifica recifrar o banco inteiro a cada turno.
            with self._conn(persistir=False) as conn:
                conn.executemany("UPDATE fatos SET acessos=acessos+1 WHERE id=?",
                                 [(d["id"],) for d in ordenados])
        for d in ordenados:
            d.pop("embedding", None)
        return ordenados

    @staticmethod
    def _mais_parecidos(conn, embedding: list[float], modelo: str,
                        limiar: float, limite: int) -> list[tuple[float, dict]]:
        if modelo:
            rows = conn.execute(
                "SELECT * FROM fatos WHERE embedding IS NOT NULL AND embedding_modelo=?",
                (modelo,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM fatos WHERE embedding IS NOT NULL").fetchall()
        pontuados = []
        for r in rows:
            sim = _similaridade(embedding, _desempacotar(r["embedding"]))
            if sim > limiar:
                d = dict(r)
                d.pop("embedding", None)
                pontuados.append((sim, d))
        pontuados.sort(key=lambda x: x[0], reverse=True)
        return pontuados[:limite]

    def fatos_parecidos(self, embedding: list[float], embedding_modelo: str,
                        limiar: float = 0.80, limite: int = 3) -> list[tuple[float, dict]]:
        """Deduplicação por sentido: o mesmo fato dito com outras palavras."""
        if not embedding:
            return []
        with self._conn() as conn:
            return self._mais_parecidos(conn, embedding, embedding_modelo, limiar, limite)

    def fatos_sem_embedding(self, embedding_modelo: str, limite: int = 16) -> list[dict]:
        """Fatos salvos sem vetor (regex, ferramenta, nuvem) ou com vetor de outro modelo."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id,categoria,chave,valor FROM fatos "
                "WHERE embedding IS NULL OR embedding_modelo!=? "
                "ORDER BY atualizado DESC LIMIT ?",
                (embedding_modelo, limite),
            ).fetchall()
            return [dict(r) for r in rows]

    def definir_embeddings(self, vetores: list[tuple[int, str, list[float]]],
                           embedding_modelo: str) -> int:
        """Grava vetores calculados depois, só se o texto não mudou nesse meio tempo."""
        if not vetores:
            return 0
        with self._conn() as conn:
            total = 0
            for fato_id, valor, vetor in vetores:
                cur = conn.execute(
                    "UPDATE fatos SET embedding=?, embedding_modelo=? WHERE id=? AND valor=?",
                    (_empacotar(vetor), embedding_modelo, fato_id, valor),
                )
                total += cur.rowcount
            return total

    # ── Treino do modelo local ─────────────────────────────────────────────

    # Resposta de API (OpenAI/Claude) é de um modelo mais forte: serve de
    # "professor" mesmo sem avaliação. Resposta neutra do próprio modelo local
    # só ensinaria o que ele já faz, então precisa de 👍 ou correção.
    _TREINO_UTIL = (
        "(nota = 1 OR correcao != '' OR (nota = 0 AND provedor IN ('openai','claude')))"
    )

    def registrar_exemplo(self, pedido: str, resposta: str, *, contexto: str = "",
                          anteriores: list[dict] | None = None, provedor: str = "",
                          modelo: str = "", por_voz: bool = False) -> str:
        exemplo_id = f"ex_{uuid.uuid4().hex[:20]}"
        limpos = [
            {"role": m["role"], "content": str(m["content"])[:2000]}
            for m in (anteriores or [])[-6:]
            if m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str)
        ]
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO treino_exemplos(id,pedido,resposta,contexto,anteriores,provedor,"
                "modelo,por_voz,criado) VALUES(?,?,?,?,?,?,?,?,?)",
                (exemplo_id, pedido[:4000], resposta[:6000], contexto[:6000],
                 json.dumps(limpos, ensure_ascii=False), provedor[:20], modelo[:120],
                 1 if por_voz else 0, time.time()),
            )
            # Teto: os 5000 mais recentes; avaliados e corrigidos ficam sempre.
            conn.execute(
                "DELETE FROM treino_exemplos WHERE nota=0 AND correcao='' AND id NOT IN "
                "(SELECT id FROM treino_exemplos ORDER BY criado DESC LIMIT 5000)"
            )
        return exemplo_id

    def avaliar_exemplo(self, exemplo_id: str, nota: int, correcao: str = "") -> bool:
        if nota not in {-1, 0, 1}:
            raise ValueError("nota deve ser -1, 0 ou 1")
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE treino_exemplos SET nota=?, correcao=?, avaliado=? WHERE id=?",
                (nota, correcao.strip()[:6000], time.time(), exemplo_id),
            )
            return cur.rowcount > 0

    def resumo_treino(self) -> dict:
        with self._conn() as conn:
            def n(where: str = "1=1") -> int:
                return int(conn.execute(f"SELECT COUNT(*) FROM treino_exemplos WHERE {where}").fetchone()[0])
            return {
                "total": n(),
                "positivos": n("nota = 1"),
                "negativos": n("nota = -1"),
                "corrigidos": n("correcao != ''"),
                "professor_api": n("nota = 0 AND provedor IN ('openai','claude')"),
                "prontos": n(self._TREINO_UTIL),
            }

    def exemplos_para_treino(self, limite: int = 5000) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM treino_exemplos WHERE {self._TREINO_UTIL} "
                "ORDER BY criado LIMIT ?",
                (limite,),
            ).fetchall()
        exemplos = []
        for row in rows:
            item = dict(row)
            try:
                item["anteriores"] = json.loads(item.get("anteriores") or "[]")
            except (TypeError, ValueError):
                item["anteriores"] = []
            exemplos.append(item)
        return exemplos

    # ── Galeria de imagens ─────────────────────────────────────────────────

    def _pasta_galeria(self) -> Path:
        pasta = self._path.parent / "gallery"
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def _arquivo_imagem(self, imagem_id: str) -> Path:
        if not re.fullmatch(r"img_[a-f0-9]{20}", str(imagem_id or "")):
            raise ValueError("imagem invalida")
        return self._pasta_galeria() / f"{imagem_id}.enc"

    def salvar_imagem(self, png: bytes, meta: dict) -> dict:
        """Guarda a imagem cifrada com a mesma chave da memória (AES-256-GCM)."""
        if self._key is None:
            raise RuntimeError("cofre da memoria bloqueado")
        imagem_id = f"img_{os.urandom(10).hex()}"
        nonce = os.urandom(12)
        cifrado = AESGCM(self._key).encrypt(nonce, png, f"condor-image:1:{imagem_id}".encode())
        arquivo = self._arquivo_imagem(imagem_id)
        fd, temporario = tempfile.mkstemp(prefix=".img-", dir=str(arquivo.parent))
        with os.fdopen(fd, "wb") as stream:
            stream.write(nonce + cifrado)
        os.replace(temporario, arquivo)
        item = {
            "id": imagem_id,
            "pedido": str(meta.get("pedido") or "")[:4000],
            "prompt_final": str(meta.get("prompt_final") or "")[:4000],
            "modelo": str(meta.get("modelo") or "")[:120],
            "seed": int(meta.get("seed") if meta.get("seed") is not None else -1),
            "largura": int(meta.get("largura") or 0),
            "altura": int(meta.get("altura") or 0),
            "origem": str(meta.get("origem") or "chat")[:40],
            "criado": time.time(),
        }
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO imagens(id,pedido,prompt_final,modelo,seed,largura,altura,origem,criado) "
                "VALUES(:id,:pedido,:prompt_final,:modelo,:seed,:largura,:altura,:origem,:criado)",
                item,
            )
        return item

    def imagens(self, limite: int = 60, antes: float | None = None) -> list[dict]:
        with self._conn() as conn:
            if antes:
                rows = conn.execute(
                    "SELECT * FROM imagens WHERE criado<? ORDER BY criado DESC LIMIT ?",
                    (antes, limite),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM imagens ORDER BY criado DESC LIMIT ?", (limite,)
                ).fetchall()
            return [dict(r) for r in rows]

    def ler_imagem(self, imagem_id: str) -> bytes | None:
        if self._key is None:
            raise RuntimeError("cofre da memoria bloqueado")
        arquivo = self._arquivo_imagem(imagem_id)
        with self._conn() as conn:
            if conn.execute("SELECT 1 FROM imagens WHERE id=?", (imagem_id,)).fetchone() is None:
                return None
        dados = arquivo.read_bytes()
        try:
            return AESGCM(self._key).decrypt(
                dados[:12], dados[12:], f"condor-image:1:{imagem_id}".encode()
            )
        except (InvalidTag, ValueError) as exc:
            raise RuntimeError("imagem cifrada invalida ou adulterada") from exc

    def apagar_imagem(self, imagem_id: str) -> bool:
        arquivo = self._arquivo_imagem(imagem_id)
        with self._conn() as conn:
            removida = conn.execute("DELETE FROM imagens WHERE id=?", (imagem_id,)).rowcount > 0
        if removida:
            arquivo.unlink(missing_ok=True)
        return removida

    # ── Fila de aprendizado ────────────────────────────────────────────────

    def enfileirar_aprendizado(self, fala_dono: str, fala_condor: str, assinatura: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO memoria_pendente"
                "(fala_dono, fala_condor, assinatura, criado) VALUES(?,?,?,?)",
                (fala_dono[:4000], fala_condor[:1500], assinatura, time.time()),
            )
            # Nunca deixa a fila crescer sem limite se o cérebro ficar dias fora.
            conn.execute(
                "DELETE FROM memoria_pendente WHERE id NOT IN "
                "(SELECT id FROM memoria_pendente ORDER BY id DESC LIMIT 200)"
            )
            return cur.rowcount > 0

    def aprendizados_pendentes(self, limite: int = 4) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, fala_dono, fala_condor, tentativas FROM memoria_pendente "
                "ORDER BY id LIMIT ?",
                (limite,),
            ).fetchall()
            return [dict(r) for r in rows]

    def total_aprendizados_pendentes(self) -> int:
        with self._conn() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM memoria_pendente").fetchone()[0])

    def concluir_aprendizado(self, pendente_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM memoria_pendente WHERE id=?", (pendente_id,))

    def falhar_aprendizado(self, pendente_id: int, maximo: int = 3) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE memoria_pendente SET tentativas=tentativas+1 WHERE id=?",
                (pendente_id,),
            )
            conn.execute(
                "DELETE FROM memoria_pendente WHERE id=? AND tentativas>=?",
                (pendente_id, maximo),
            )

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

    def vocabulario(self, limite: int = 24) -> list[str]:
        """Nomes próprios da vida do dono, para o Whisper escrevê-los certo."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT nome FROM entidades ORDER BY mencoes DESC, atualizado DESC LIMIT ?",
                (limite,),
            ).fetchall()
            return [str(r["nome"]) for r in rows if str(r["nome"]).strip()]

    def salvar_entidade(self, nome: str, tipo: str, cluster: str = "GERAL",
                        resumo: str = "") -> int:
        agora = time.time()
        with self._conn() as conn:
            existente = conn.execute(
                "SELECT id FROM entidades WHERE nome=? COLLATE NOCASE", (nome,)
            ).fetchone()
            if existente:
                conn.execute(
                    """UPDATE entidades SET tipo=?,cluster=?,
                       resumo=CASE WHEN ? != '' THEN ? ELSE resumo END,
                       mencoes=mencoes+1,atualizado=? WHERE id=?""",
                    (tipo, cluster, resumo, resumo, agora, existente["id"]),
                )
                return existente["id"]
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

    def mapa_memoria(self) -> dict:
        """Visão completa e explicável do que está no cofre.

        Fatos e relações confirmadas vêm diretamente do banco. Associações entre
        fatos são calculadas para a tela usando evidência textual, entidades já
        conhecidas e embeddings que já existam; elas não alteram nem fundem o
        conteúdo cifrado.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id,categoria,chave,valor,confianca,origem,acessos,
                          criado,atualizado,embedding
                   FROM fatos ORDER BY atualizado DESC, id DESC"""
            ).fetchall()
            entidades = [dict(r) for r in conn.execute(
                """SELECT id,nome,tipo,cluster,resumo,mencoes,atualizado
                   FROM entidades ORDER BY mencoes DESC, atualizado DESC"""
            )]
            relacoes = [dict(r) for r in conn.execute(
                """SELECT r.id,r.de_id de,r.para_id para,r.tipo,r.forca,
                          origem.nome de_nome,destino.nome para_nome
                   FROM relacoes r
                   JOIN entidades origem ON origem.id=r.de_id
                   JOIN entidades destino ON destino.id=r.para_id
                   ORDER BY r.forca DESC,r.criado DESC"""
            )]

        fatos = []
        vetores: dict[int, list[float]] = {}
        termos: dict[int, set[str]] = {}
        for row in rows:
            item = dict(row)
            blob = item.pop("embedding", None)
            if blob:
                try:
                    vetores[item["id"]] = _desempacotar(blob)
                except (struct.error, TypeError, ValueError):
                    pass
            termos[item["id"]] = _termos_memoria(f'{item["chave"]} {item["valor"]}')
            fatos.append(item)

        por_id = {fato["id"]: fato for fato in fatos}
        associacoes: dict[tuple[int, int], dict] = {}

        def registrar(a: int, b: int, tipo: str, pontuacao: float,
                      evidencia: list[str], rotulo: str) -> None:
            if a == b:
                return
            chave = tuple(sorted((a, b)))
            atual = associacoes.get(chave)
            proposta = {
                "de": chave[0], "para": chave[1], "tipo": tipo,
                "pontuacao": round(max(0.0, min(1.0, pontuacao)), 3),
                "evidencia": evidencia[:5], "rotulo": rotulo,
                "confirmada": False,
            }
            if atual is None or proposta["pontuacao"] > atual["pontuacao"]:
                associacoes[chave] = proposta

        # Termos raros compartilhados dão uma associação auditável. Termos que
        # aparecem em muitos fatos são ignorados para não ligar tudo a tudo.
        indice: dict[str, list[int]] = {}
        for fato_id, itens in termos.items():
            for termo in itens:
                indice.setdefault(termo, []).append(fato_id)
        pares_textuais: dict[tuple[int, int], set[str]] = {}
        for termo, ids in indice.items():
            if len(ids) < 2 or len(ids) > max(12, len(fatos) // 2):
                continue
            for pos, primeiro in enumerate(ids):
                for segundo in ids[pos + 1:]:
                    pares_textuais.setdefault(tuple(sorted((primeiro, segundo))), set()).add(termo)
        for (a, b), compartilhados in pares_textuais.items():
            evidencias = sorted(compartilhados, key=lambda t: (-len(t), t))[:5]
            pontuacao = min(.88, .54 + .08 * (len(compartilhados) - 1))
            registrar(a, b, "termos_compartilhados", pontuacao, evidencias,
                      "termos em comum")

        # Uma entidade conhecida mencionada em dois fatos é uma associação mais
        # forte e continua totalmente explicável ao usuário.
        for entidade in entidades:
            nome = str(entidade.get("nome") or "").strip()
            termos_nome = _termos_memoria(nome)
            if not termos_nome:
                continue
            mencionados = [
                fato["id"] for fato in fatos
                if termos_nome.issubset(termos[fato["id"]])
            ]
            if len(mencionados) > max(8, len(fatos) // 3):
                continue
            for pos, primeiro in enumerate(mencionados[:40]):
                for segundo in mencionados[pos + 1:40]:
                    registrar(primeiro, segundo, "entidade_compartilhada", .94,
                              [nome], "mesma entidade")

        # Reaproveita embeddings já armazenados. Não chama IA nem cria fato novo.
        cobertura_semantica = len(vetores)
        ids_vetores = list(vetores)[:220]
        for pos, a in enumerate(ids_vetores):
            va = vetores[a]
            norma_a = math.sqrt(sum(valor * valor for valor in va)) or 1.0
            for b in ids_vetores[pos + 1:]:
                vb = vetores[b]
                if len(va) != len(vb):
                    continue
                norma_b = math.sqrt(sum(valor * valor for valor in vb)) or 1.0
                similaridade = sum(x * y for x, y in zip(va, vb)) / (norma_a * norma_b)
                if similaridade >= .78:
                    registrar(a, b, "similaridade_semantica", similaridade,
                              [], "significado semelhante")

        candidatas = sorted(
            associacoes.values(),
            key=lambda item: (-item["pontuacao"], item["de"], item["para"]),
        )
        # A tela precisa ser legível: somente evidência forte e no máximo quatro
        # associações por fato. O restante continua preservado nos fatos, apenas
        # não vira uma ligação visual fraca.
        graus = {fato["id"]: 0 for fato in fatos}
        ligacoes = []
        for ligacao in candidatas:
            a, b = ligacao["de"], ligacao["para"]
            if ligacao["pontuacao"] < .62 or graus[a] >= 4 or graus[b] >= 4:
                continue
            ligacoes.append(ligacao)
            graus[a] += 1
            graus[b] += 1

        # Componentes conectados viram cadeias. Fatos isolados continuam
        # presentes, individualmente, para a tela realmente mostrar tudo.
        pai = {fato["id"]: fato["id"] for fato in fatos}
        tamanho = {fato["id"]: 1 for fato in fatos}

        def raiz(item: int) -> int:
            while pai[item] != item:
                pai[item] = pai[pai[item]]
                item = pai[item]
            return item

        def unir(a: int, b: int) -> None:
            ra, rb = raiz(a), raiz(b)
            if ra != rb and tamanho[ra] + tamanho[rb] <= 8:
                pai[rb] = ra
                tamanho[ra] += tamanho[rb]

        for ligacao in ligacoes:
            if ligacao["pontuacao"] >= .62:
                unir(ligacao["de"], ligacao["para"])
        componentes: dict[int, list[int]] = {}
        for fato in fatos:
            componentes.setdefault(raiz(fato["id"]), []).append(fato["id"])

        cadeias = []
        for indice_cadeia, ids in enumerate(sorted(
            componentes.values(),
            key=lambda grupo: (-len(grupo), -max(por_id[item]["atualizado"] for item in grupo)),
        ), 1):
            categorias: dict[str, int] = {}
            for item in ids:
                categoria = por_id[item]["categoria"]
                categorias[categoria] = categorias.get(categoria, 0) + 1
            principal = max(categorias, key=categorias.get) if categorias else "geral"
            links = [l for l in ligacoes if l["de"] in ids and l["para"] in ids]
            cadeias.append({
                "id": f"cadeia-{indice_cadeia}",
                "titulo": principal.replace("_", " ").upper(),
                "fatos": ids,
                "ligacoes": links,
                "conectada": len(ids) > 1,
            })

        atualizado = max((fato["atualizado"] for fato in fatos), default=0.0)
        return {
            "fatos": fatos,
            "entidades": entidades,
            "relacoes_confirmadas": relacoes,
            "associacoes_sugeridas": ligacoes,
            "cadeias": cadeias,
            "inteligencia": {
                "fatos": len(fatos),
                "entidades": len(entidades),
                "relacoes_confirmadas": len(relacoes),
                "associacoes_sugeridas": len(ligacoes),
                "cadeias": sum(1 for cadeia in cadeias if cadeia["conectada"]),
                "isoladas": sum(1 for cadeia in cadeias if not cadeia["conectada"]),
                "categorias": len({fato["categoria"] for fato in fatos}),
                "cobertura_semantica": cobertura_semantica,
                "atualizado": atualizado,
                "modo": "deterministico_e_semantico_local",
            },
        }

    # ── Conversas ──────────────────────────────────────────────────────────

    def salvar_turno(self, papel: str, conteudo: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversas(sessao, papel, conteudo, ts) VALUES(?,?,?,?)",
                (self.sessao_atual, papel, conteudo, time.time()))

    def historico(self, limite: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT papel, conteudo FROM conversas
                   WHERE ts >= COALESCE((SELECT CAST(valor AS REAL) FROM memory_meta
                     WHERE chave='active_conversation_since'), 0)
                   ORDER BY ts DESC LIMIT ?""",
                (limite,)).fetchall()
            return [{"role": r["papel"], "content": r["conteudo"]} for r in reversed(rows)]

    def ultimo_turno_em(self) -> float:
        """Quando foi a última mensagem da conversa (0 se não houver)."""
        with self._conn() as conn:
            row = conn.execute("SELECT MAX(ts) FROM conversas").fetchone()
            return float(row[0] or 0.0)

    def arquivar_conversa(self) -> None:
        """Starts an empty chat while preserving encrypted past messages."""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO memory_meta(chave,valor) VALUES('active_conversation_since',?)
                   ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor""", (str(time.time()),))

    def arquivo_conversas(self, antes: int | None = None, limite: int = 50) -> list[dict]:
        """Read encrypted conversation history, including earlier archived chats."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id,papel,conteudo,ts FROM conversas WHERE (? IS NULL OR id < ?) ORDER BY id DESC LIMIT ?",
                (antes, antes, max(1, min(limite, 100))),
            ).fetchall()
            return [dict(row) for row in rows]

    def limpar_conversas(self) -> int:
        """Apaga somente mensagens; fatos, projetos e demais memórias ficam intactos."""
        with self._conn() as conn:
            removidas = int(conn.execute("SELECT COUNT(*) FROM conversas").fetchone()[0])
            conn.execute("DELETE FROM conversas")
        return removidas

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
                # Trocas esperando o extrator: a interface mostra "aprendendo".
                "aprendendo": n("SELECT COUNT(*) FROM memoria_pendente"),
            }

    # ── Diário do CONDOR (memória dele sobre si mesmo) ────────────────────

    TIPOS_DIARIO = ("acao", "sobre_mim", "opiniao", "plano")

    def registrar_diario(self, tipo: str, texto: str) -> bool:
        """Anota no diário. Repetição idêntica recente não vira linha nova."""
        texto = " ".join(str(texto or "").split())[:400]
        if tipo not in self.TIPOS_DIARIO or len(texto) < 3 or not self.unlocked:
            return False
        agora = time.time()
        with self._conn() as conn:
            if conn.execute(
                "SELECT 1 FROM diario WHERE tipo=? AND texto=? AND ts>?",
                (tipo, texto, agora - 6 * 3600),
            ).fetchone():
                return False
            conn.execute("INSERT INTO diario(tipo, texto, ts) VALUES(?,?,?)", (tipo, texto, agora))
            # O diário não cresce sem fim: fica o último ano de cada tipo, até 2.000.
            conn.execute(
                "DELETE FROM diario WHERE tipo=? AND id NOT IN "
                "(SELECT id FROM diario WHERE tipo=? ORDER BY ts DESC LIMIT 2000)",
                (tipo, tipo),
            )
        return True

    def diario(self, tipos: tuple[str, ...] = TIPOS_DIARIO, limite: int = 10,
               desde: float = 0.0) -> list[dict]:
        if not self.unlocked:
            return []
        tipos = tuple(t for t in tipos if t in self.TIPOS_DIARIO) or self.TIPOS_DIARIO
        marcas = ",".join("?" * len(tipos))
        with self._conn(persistir=False) as conn:
            rows = conn.execute(
                f"SELECT tipo, texto, ts FROM diario WHERE tipo IN ({marcas}) AND ts>=? "
                "ORDER BY ts DESC LIMIT ?",
                (*tipos, float(desde), max(1, min(int(limite), 200))),
            ).fetchall()
        return [dict(r) for r in rows]

    def autocontagem(self) -> dict:
        """Números reais do que o CONDOR guarda, para ele saber de si."""
        if not self.unlocked:
            return {}
        with self._conn(persistir=False) as conn:
            def n(q: str) -> int:
                return int(conn.execute(q).fetchone()[0])
            primeira = conn.execute("SELECT MIN(ts) FROM conversas").fetchone()[0]
            return {
                "fatos": n("SELECT COUNT(*) FROM fatos"),
                "turnos": n("SELECT COUNT(*) FROM conversas"),
                "imagens": n("SELECT COUNT(*) FROM imagens"),
                "diario": n("SELECT COUNT(*) FROM diario"),
                "desde": float(primeira or 0),
            }

    def fluxo_recente(self, limite: int = 10) -> list[dict]:
        """Alimenta o painel 'o que estou aprendendo' da tela Memória."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT categoria, chave, valor, atualizado FROM fatos "
                "ORDER BY atualizado DESC LIMIT ?", (limite,)).fetchall()
            return [{"categoria": r["categoria"], "texto": r["valor"][:90],
                     "ts": r["atualizado"]} for r in rows]

    # ── Cérebro temporal e operacional ───────────────────────────────────

    @staticmethod
    def _json_field(row: sqlite3.Row | dict, field: str, fallback):
        item = dict(row)
        try:
            item[field.removesuffix("_json")] = json.loads(item.pop(field))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            item[field.removesuffix("_json")] = fallback
        return item

    def record_episode(
        self, kind: str, summary: str, source: str, *,
        project_id: str | None = None, device_id: str | None = None,
        confidence: float = 1.0, occurred_at: float | None = None,
        metadata: dict | None = None,
    ) -> dict:
        now = time.time()
        item_id = self._id("episode")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO memory_episodes
                   (id,kind,summary,source,project_id,device_id,confidence,
                    occurred_at,metadata_json,created)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (item_id, kind, summary, source, project_id, device_id,
                 confidence, occurred_at or now,
                 json.dumps(metadata or {}, ensure_ascii=False), now),
            )
            row = conn.execute(
                "SELECT * FROM memory_episodes WHERE id=?", (item_id,)
            ).fetchone()
        return self._json_field(row, "metadata_json", {})

    def list_episodes(
        self, limit: int = 50, *, project_id: str | None = None,
        kind: str | None = None,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list = []
        if project_id:
            clauses.append("project_id=?")
            params.append(project_id)
        if kind:
            clauses.append("kind=?")
            params.append(kind)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 250)))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_episodes{where} "
                "ORDER BY occurred_at DESC LIMIT ?", tuple(params)
            ).fetchall()
        return [self._json_field(row, "metadata_json", {}) for row in rows]

    def save_belief(
        self, subject: str, predicate: str, value: str, *, source: str,
        status: str = "confirmed", confidence: float = 1.0,
        evidence: list | None = None, valid_from: float | None = None,
        valid_until: float | None = None,
    ) -> dict:
        """Registra uma versão; uma mudança nunca apaga a crença anterior."""
        now = time.time()
        evidence_json = json.dumps(evidence or [], ensure_ascii=False)
        with self._conn() as conn:
            previous = conn.execute(
                """SELECT * FROM world_beliefs
                   WHERE subject=? AND predicate=?
                     AND status IN ('confirmed','inferred','conflicted')
                   ORDER BY updated DESC LIMIT 1""",
                (subject, predicate),
            ).fetchone()
            if previous is not None and previous["value"] == value:
                conn.execute(
                    """UPDATE world_beliefs SET status=?, confidence=?, source=?,
                       valid_until=?, evidence_json=?, updated=? WHERE id=?""",
                    (status, confidence, source, valid_until, evidence_json,
                     now, previous["id"]),
                )
                item_id = previous["id"]
            else:
                previous_id = previous["id"] if previous is not None else None
                if previous is not None:
                    conn.execute(
                        """UPDATE world_beliefs SET status='outdated',
                           valid_until=COALESCE(valid_until,?), updated=? WHERE id=?""",
                        (now, now, previous_id),
                    )
                item_id = self._id("belief")
                conn.execute(
                    """INSERT INTO world_beliefs
                       (id,subject,predicate,value,status,confidence,source,
                        valid_from,valid_until,supersedes_id,evidence_json,created,updated)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (item_id, subject, predicate, value, status, confidence,
                     source, valid_from or now, valid_until, previous_id,
                     evidence_json, now, now),
                )
            row = conn.execute(
                "SELECT * FROM world_beliefs WHERE id=?", (item_id,)
            ).fetchone()
        return self._json_field(row, "evidence_json", [])

    def list_beliefs(
        self, limit: int = 100, *, subject: str | None = None,
        include_outdated: bool = False,
    ) -> list[dict]:
        clauses = [] if include_outdated else ["status != 'outdated'"]
        params: list = []
        if subject:
            clauses.append("subject=?")
            params.append(subject)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM world_beliefs{where} ORDER BY updated DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [self._json_field(row, "evidence_json", []) for row in rows]

    def create_durable_task(
        self, title: str, objective: str, *, project_id: str | None = None,
        priority: int = 50, source: str = "owner", due_at: float | None = None,
        metadata: dict | None = None,
    ) -> dict:
        now = time.time()
        item_id = self._id("work")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO durable_tasks
                   (id,project_id,title,objective,status,priority,source,due_at,
                    metadata_json,created,updated)
                   VALUES(?,?,?,?,'pending',?,?,?,?,?,?)""",
                (item_id, project_id, title, objective, priority, source,
                 due_at, json.dumps(metadata or {}, ensure_ascii=False), now, now),
            )
            row = conn.execute("SELECT * FROM durable_tasks WHERE id=?", (item_id,)).fetchone()
        return self._json_field(row, "metadata_json", {})

    def update_durable_task(self, task_id: str, status: str) -> dict | None:
        with self._conn() as conn:
            changed = conn.execute(
                "UPDATE durable_tasks SET status=?, updated=? WHERE id=?",
                (status, time.time(), task_id),
            )
            if not changed.rowcount:
                return None
            row = conn.execute("SELECT * FROM durable_tasks WHERE id=?", (task_id,)).fetchone()
        return self._json_field(row, "metadata_json", {})

    def add_task_checkpoint(
        self, task_id: str, step: str, status: str, summary: str = "",
        evidence: list | None = None,
    ) -> dict:
        now = time.time()
        item_id = self._id("checkpoint")
        with self._conn() as conn:
            if conn.execute("SELECT 1 FROM durable_tasks WHERE id=?", (task_id,)).fetchone() is None:
                raise KeyError("tarefa não encontrada")
            conn.execute(
                """INSERT INTO task_checkpoints
                   (id,task_id,step,status,summary,evidence_json,created)
                   VALUES(?,?,?,?,?,?,?)""",
                (item_id, task_id, step, status, summary,
                 json.dumps(evidence or [], ensure_ascii=False), now),
            )
            conn.execute("UPDATE durable_tasks SET updated=? WHERE id=?", (now, task_id))
            row = conn.execute("SELECT * FROM task_checkpoints WHERE id=?", (item_id,)).fetchone()
        return self._json_field(row, "evidence_json", [])

    def list_durable_tasks(self, limit: int = 100, status: str | None = None) -> list[dict]:
        params: list = []
        where = ""
        if status:
            where = " WHERE status=?"
            params.append(status)
        params.append(max(1, min(int(limit), 500)))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM durable_tasks{where} "
                "ORDER BY priority DESC, updated DESC LIMIT ?", tuple(params)
            ).fetchall()
        return [self._json_field(row, "metadata_json", {}) for row in rows]

    def durable_task(self, task_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM durable_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                return None
            checkpoints = conn.execute(
                "SELECT * FROM task_checkpoints WHERE task_id=? ORDER BY created ASC", (task_id,)
            ).fetchall()
        item = self._json_field(row, "metadata_json", {})
        item["checkpoints"] = [self._json_field(cp, "evidence_json", []) for cp in checkpoints]
        return item

    def register_device_identity(
        self, name: str, kind: str, public_key: str, capabilities: list[str]
    ) -> dict:
        now = time.time()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM device_identities WHERE public_key=?", (public_key,)
            ).fetchone()
            item_id = existing["id"] if existing else self._id("peer")
            conn.execute(
                """INSERT INTO device_identities
                   (id,name,kind,public_key,trust_state,capabilities_json,created,last_seen,updated)
                   VALUES(?,?,?,?,'pending',?,?,?,?)
                   ON CONFLICT(public_key) DO UPDATE SET name=excluded.name,
                     kind=excluded.kind, capabilities_json=excluded.capabilities_json,
                     last_seen=excluded.last_seen, updated=excluded.updated""",
                (item_id, name, kind, public_key,
                 json.dumps(capabilities, ensure_ascii=False), now, now, now),
            )
            row = conn.execute("SELECT * FROM device_identities WHERE public_key=?", (public_key,)).fetchone()
        return self._json_field(row, "capabilities_json", [])

    def set_device_trust(self, device_id: str, trust_state: str) -> dict | None:
        with self._conn() as conn:
            changed = conn.execute(
                "UPDATE device_identities SET trust_state=?, updated=? WHERE id=?",
                (trust_state, time.time(), device_id),
            )
            if not changed.rowcount:
                return None
            row = conn.execute("SELECT * FROM device_identities WHERE id=?", (device_id,)).fetchone()
        return self._json_field(row, "capabilities_json", [])

    def list_device_identities(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM device_identities ORDER BY updated DESC"
            ).fetchall()
        return [self._json_field(row, "capabilities_json", []) for row in rows]

    # ── Identificadores ───────────────────────────────────────────────────

    @staticmethod
    def _id(prefixo: str) -> str:
        return f"{prefixo}_{uuid.uuid4().hex[:16]}"

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

    # ── Condor X: Propulsion Placement Lab ────────────────────────────

    def condor_x_propulsion_layouts(self) -> list[dict]:
        if not self.unlocked:
            return []
        with self._conn() as conn:
            result = []
            rows = conn.execute(
                "SELECT id,name,data_json,criado,atualizado FROM condor_x_propulsion_layouts ORDER BY criado,id"
            ).fetchall()
            for row in rows:
                item = dict(row)
                data = self._decode_json(item.pop("data_json"), {})
                data["id"] = item["id"]
                data["name"] = item["name"]
                data["createdAt"] = item["criado"]
                data["updatedAt"] = item["atualizado"]
                result.append(data)
            return result

    def condor_x_propulsion_layout(self, layout_id: str) -> dict | None:
        if not self.unlocked:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id,name,data_json,criado,atualizado FROM condor_x_propulsion_layouts WHERE id=?",
                (layout_id,),
            ).fetchone()
            if not row:
                return None
            item = dict(row)
            data = self._decode_json(item.pop("data_json"), {})
            data["id"] = item["id"]
            data["name"] = item["name"]
            data["createdAt"] = item["criado"]
            data["updatedAt"] = item["atualizado"]
            return data

    def condor_x_save_propulsion_layout(self, layout: dict) -> dict:
        normalized = self._safe_json_dict(layout, "propulsion layout", 500_000)
        layout_id = str(normalized.get("id") or "")[:80]
        name = str(normalized.get("name") or layout_id).strip()[:120]
        if not layout_id or not name:
            raise ValueError("id e name do layout são obrigatórios")
        encoded = json.dumps(normalized, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        agora = time.time()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO condor_x_propulsion_layouts(id,name,data_json,criado,atualizado)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name,data_json=excluded.data_json,
                   atualizado=excluded.atualizado""",
                (layout_id, name, encoded, agora, agora),
            )
        return self.condor_x_propulsion_layout(layout_id) or normalized

    def condor_x_delete_propulsion_layout(self, layout_id: str) -> bool:
        with self._conn() as conn:
            return conn.execute(
                "DELETE FROM condor_x_propulsion_layouts WHERE id=?", (layout_id,)
            ).rowcount > 0

    def condor_x_record_propulsion_run(self, layout: dict, result: dict) -> dict:
        safe_layout = self._safe_json_dict(layout, "propulsion run input", 500_000)
        safe_result = self._safe_json_dict(result, "propulsion run result", 2_000_000)
        layout_id = str(safe_layout.get("id") or "")[:80]
        if self.condor_x_propulsion_layout(layout_id) is None:
            raise KeyError("layout não encontrado")
        run_id = self._id("cxprun")
        agora = time.time()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO condor_x_propulsion_runs
                   (id,layout_id,input_json,result_json,criado) VALUES(?,?,?,?,?)""",
                (run_id, layout_id,
                 json.dumps(safe_layout, ensure_ascii=False, allow_nan=False),
                 json.dumps(safe_result, ensure_ascii=False, allow_nan=False), agora),
            )
        return {"id": run_id, "layoutId": layout_id, "createdAt": agora}

    def condor_x_propulsion_runs(self, layout_id: str | None = None, limit: int = 25) -> list[dict]:
        if not self.unlocked:
            return []
        limit = max(1, min(100, int(limit)))
        with self._conn() as conn:
            if layout_id:
                rows = conn.execute(
                    """SELECT id,layout_id,result_json,criado FROM condor_x_propulsion_runs
                       WHERE layout_id=? ORDER BY criado DESC LIMIT ?""", (layout_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id,layout_id,result_json,criado FROM condor_x_propulsion_runs
                       ORDER BY criado DESC LIMIT ?""", (limit,)
                ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                analysis = self._decode_json(item.pop("result_json"), {})
                result.append({
                    "id": item["id"], "layoutId": item["layout_id"], "createdAt": item["criado"],
                    "decision": analysis.get("decision"), "dashboard": analysis.get("dashboard", {}),
                    "evidenceChain": analysis.get("evidenceChain", {}),
                })
            return result

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
        return self.set_permission_decision(capability, "always" if allowed else "block")

    def set_permission_decision(self, capability: str, decision: str) -> bool:
        normalized = str(decision or "").strip().lower()
        aliases = {
            "allow_always": "always", "always": "always",
            "allow_once": "once", "once": "once",
            "block": "block", "deny": "block",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in {"always", "once", "block"}:
            raise ValueError("decisao de permissao invalida")
        allowed = normalized != "block"
        stored_decision = normalized if allowed else "ask"
        uses = 1 if normalized == "once" else 0
        with self._conn() as conn:
            result = conn.execute(
                """UPDATE permissions
                   SET allowed=?,decision=?,one_time_uses=?,updated=?
                   WHERE capability=?""",
                (int(allowed), stored_decision, uses, time.time(), capability),
            )
            return result.rowcount > 0

    def permission_allowed(self, capability: str, consume_once: bool = True) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT allowed,decision,one_time_uses FROM permissions
                   WHERE capability=?""", (capability,)
            ).fetchone()
            if row is None or not bool(row["allowed"]):
                return False
            if row["decision"] != "once":
                return True
            remaining = int(row["one_time_uses"] or 0)
            if remaining <= 0:
                return False
            if consume_once:
                conn.execute(
                    """UPDATE permissions
                       SET allowed=0,decision='ask',one_time_uses=0,updated=?
                       WHERE capability=?""",
                    (time.time(), capability),
                )
            return True

    def permission_available(self, capability: str) -> bool:
        """Consulta a autoridade sem consumir uma concessao de uso unico."""
        return self.permission_allowed(capability, consume_once=False)

    def request_permission(
        self, capability: str, reason: str, source: str = "condor", force: bool = False
    ) -> dict | None:
        """Cria uma solicitacao visivel sem conceder autoridade por conta propria."""
        agora = time.time()
        with self._conn() as conn:
            permission = conn.execute(
                "SELECT capability,allowed,scope FROM permissions WHERE capability=?",
                (capability,),
            ).fetchone()
            if permission is None or (self.permission_available(capability) and not force):
                return None
            existing = conn.execute(
                """SELECT * FROM permission_requests
                   WHERE capability=? AND status='pending'
                   ORDER BY created DESC LIMIT 1""",
                (capability,),
            ).fetchone()
            if existing:
                return dict(existing)
            request_id = self._id("permission")
            conn.execute(
                """INSERT INTO permission_requests
                   (id,capability,reason,source,status,created)
                   VALUES(?,?,?,?, 'pending', ?)""",
                (request_id, capability, reason.strip()[:500], source.strip()[:80], agora),
            )
            row = conn.execute(
                "SELECT * FROM permission_requests WHERE id=?", (request_id,)
            ).fetchone()
            return dict(row) if row else None

    def pending_permission_requests(self) -> list[dict]:
        with self._conn() as conn:
            return [
                dict(row) for row in conn.execute(
                    """SELECT r.id,r.capability,r.reason,r.source,r.status,r.created,p.scope
                       FROM permission_requests r
                       JOIN permissions p ON p.capability=r.capability
                       WHERE r.status='pending' ORDER BY r.created DESC"""
                ).fetchall()
            ]

    def resolve_permission_request(self, request_id: str, decision: str | bool) -> dict | None:
        """Resolve o pedido e atualiza a permissao na mesma persistencia cifrada."""
        normalized = ("always" if decision else "block") if isinstance(decision, bool) else str(decision)
        aliases = {"allow_always": "always", "allow_once": "once"}
        normalized = aliases.get(normalized, normalized)
        if normalized not in {"always", "once", "block"}:
            raise ValueError("decisao de permissao invalida")
        allowed = normalized != "block"
        stored_decision = normalized if allowed else "ask"
        uses = 1 if normalized == "once" else 0
        agora = time.time()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM permission_requests WHERE id=? AND status='pending'",
                (request_id,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """UPDATE permissions
                   SET allowed=?,decision=?,one_time_uses=?,updated=?
                   WHERE capability=?""",
                (int(allowed), stored_decision, uses, agora, row["capability"]),
            )
            status = f"granted_{normalized}" if allowed else "blocked"
            conn.execute(
                "UPDATE permission_requests SET status=?,resolved=? WHERE id=?",
                (status, agora, request_id),
            )
            return {
                "id": request_id,
                "capability": row["capability"],
                "allowed": bool(allowed),
                "decision": normalized,
                "status": status,
            }

    # ── Identidade facial local ──────────────────────────────────────────

    def face_identity_profile(self) -> dict | None:
        """Retorna somente o vetor facial guardado no snapshot cifrado."""
        if not self.unlocked:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM face_identity_profile WHERE owner_id='owner'"
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["template"] = json.loads(item.pop("template_json"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        item["enabled"] = bool(item["enabled"])
        return item

    def save_face_identity_profile(
        self, template: list[float], sample_count: int, threshold: float, model: str
    ) -> dict:
        if not self.unlocked:
            raise RuntimeError("cofre bloqueado")
        if len(template) < 64 or len(template) > 4096:
            raise ValueError("vetor facial fora do formato esperado")
        if not all(isinstance(value, (int, float)) for value in template):
            raise ValueError("vetor facial invalido")
        agora = time.time()
        encoded = json.dumps(
            [round(float(value), 8) for value in template], separators=(",", ":")
        )
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO face_identity_profile
                   (owner_id,template_json,sample_count,threshold,enabled,model,created,updated)
                   VALUES ('owner',?,?,?,?,?,?,?)
                   ON CONFLICT(owner_id) DO UPDATE SET
                     template_json=excluded.template_json,
                     sample_count=excluded.sample_count,
                     threshold=excluded.threshold,
                     enabled=1,
                     model=excluded.model,
                     updated=excluded.updated""",
                (encoded, int(sample_count), float(threshold), 1, model[:120], agora, agora),
            )
        return self.face_identity_profile() or {}

    def set_face_identity_enabled(self, enabled: bool) -> bool:
        if not self.unlocked:
            raise RuntimeError("cofre bloqueado")
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE face_identity_profile SET enabled=?, updated=? WHERE owner_id='owner'",
                (int(bool(enabled)), time.time()),
            )
        return cursor.rowcount == 1

    def delete_face_identity_profile(self) -> bool:
        if not self.unlocked:
            raise RuntimeError("cofre bloqueado")
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM face_identity_profile WHERE owner_id='owner'")
        return cursor.rowcount == 1

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

