"""
Banco de dados SQLite — memória persistente do CONDOR.
Schema: entities, relations, events, preferences, conversations.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger("condor.memory.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    type      TEXT NOT NULL,          -- person, project, place, concept, habit
    cluster   TEXT NOT NULL DEFAULT 'GERAL',  -- TRABALHO, PESSOAL, ESTUDOS, HÁBITOS
    data      TEXT NOT NULL DEFAULT '{}',     -- JSON com atributos extras
    created   REAL NOT NULL,
    updated   REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

CREATE TABLE IF NOT EXISTS relations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id    INTEGER NOT NULL REFERENCES entities(id),
    to_id      INTEGER NOT NULL REFERENCES entities(id),
    rel_type   TEXT NOT NULL,
    strength   REAL NOT NULL DEFAULT 1.0,
    created    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    title    TEXT NOT NULL,
    detail   TEXT,
    entities TEXT NOT NULL DEFAULT '[]',  -- JSON list de entity ids
    ts       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS preferences (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL,
    updated REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    role    TEXT NOT NULL,   -- user, assistant
    content TEXT NOT NULL,
    ts      REAL NOT NULL
);
"""


class MemoryDB:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)
        log.info("Banco de memória pronto: %s", self._path)

    # ── Entidades ──────────────────────────────────────────────────────────

    def upsert_entity(self, name: str, type: str, cluster: str = "GERAL", data: dict | None = None) -> int:
        now = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO entities(name, type, cluster, data, created, updated)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(name) DO UPDATE
                   SET type=excluded.type, cluster=excluded.cluster,
                       data=excluded.data, updated=excluded.updated""",
                (name, type, cluster, json.dumps(data or {}), now, now),
            )
            return cur.lastrowid or conn.execute(
                "SELECT id FROM entities WHERE name=?", (name,)
            ).fetchone()["id"]

    def get_entities(self, cluster: str | None = None) -> list[dict]:
        with self._conn() as conn:
            if cluster:
                rows = conn.execute(
                    "SELECT * FROM entities WHERE cluster=? ORDER BY updated DESC", (cluster,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM entities ORDER BY updated DESC LIMIT 200"
                ).fetchall()
            return [dict(r) for r in rows]

    def get_entity_by_name(self, name: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM entities WHERE name=?", (name,)).fetchone()
            return dict(row) if row else None

    # ── Relações ───────────────────────────────────────────────────────────

    def add_relation(self, from_name: str, to_name: str, rel_type: str) -> None:
        from_ent = self.get_entity_by_name(from_name)
        to_ent   = self.get_entity_by_name(to_name)
        if not from_ent or not to_ent:
            return
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO relations(from_id, to_id, rel_type, created)
                   VALUES(?,?,?,?)""",
                (from_ent["id"], to_ent["id"], rel_type, time.time()),
            )

    def get_relations(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT e1.name AS from_name, e2.name AS to_name, r.rel_type, r.strength
                FROM relations r
                JOIN entities e1 ON r.from_id = e1.id
                JOIN entities e2 ON r.to_id   = e2.id
            """).fetchall()
            return [dict(r) for r in rows]

    # ── Eventos ────────────────────────────────────────────────────────────

    def add_event(self, title: str, detail: str = "", entity_names: list[str] | None = None) -> None:
        ids = []
        for name in (entity_names or []):
            ent = self.get_entity_by_name(name)
            if ent:
                ids.append(ent["id"])
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO events(title, detail, entities, ts) VALUES(?,?,?,?)",
                (title, detail, json.dumps(ids), time.time()),
            )

    # ── Preferências ───────────────────────────────────────────────────────

    def set_preference(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO preferences(key, value, updated) VALUES(?,?,?)",
                (key, value, time.time()),
            )

    def get_preference(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def get_all_preferences(self) -> dict[str, str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT key, value FROM preferences").fetchall()
            return {r["key"]: r["value"] for r in rows}

    # ── Conversas ──────────────────────────────────────────────────────────

    def save_turn(self, role: str, content: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations(role, content, ts) VALUES(?,?,?)",
                (role, content, time.time()),
            )

    def get_recent_conversations(self, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    # ── Stats ──────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._conn() as conn:
            nodes = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            edges = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
            turns = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            return {"nodes": nodes, "edges": edges, "turns": turns}
