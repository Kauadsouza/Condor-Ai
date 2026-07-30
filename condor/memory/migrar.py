"""
Traz o que presta do banco antigo (data/memory.db) pro novo (data/condor.db).

Do banco velho só as CONVERSAS são suas de verdade — o resto (139 entidades,
177 preferências) era seed genérico e regex ruim ('lang:italiano',
'objetivo_q_vc_me_fale'), que só poluiria a memória nova.

Roda uma vez só, no primeiro boot. O memory.db antigo não é tocado.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

from condor.memory.db import Memoria

log = logging.getLogger("condor.memoria.migrar")


def migrar_se_preciso(memoria: Memoria, banco_antigo: Path) -> int:
    """Copia as conversas do banco antigo. Devolve quantas trouxe."""
    if not banco_antigo.exists():
        return 0

    with memoria._conn() as conn:
        ja_veio = conn.execute(
            "SELECT COUNT(*) FROM conversas WHERE sessao = -1").fetchone()[0]
    if ja_veio:
        return 0

    try:
        antigo = sqlite3.connect(str(banco_antigo))
        antigo.row_factory = sqlite3.Row
        linhas = antigo.execute(
            "SELECT role, content, ts FROM conversations ORDER BY ts").fetchall()
        antigo.close()
    except Exception as exc:
        log.warning("Não consegui ler o banco antigo: %s", exc)
        return 0

    if not linhas:
        return 0

    with memoria._conn() as conn:
        conn.executemany(
            "INSERT INTO conversas(sessao, papel, conteudo, ts) VALUES(-1,?,?,?)",
            [(r["role"], r["content"], r["ts"] or time.time()) for r in linhas])

    log.info("Migradas %d conversas do banco antigo.", len(linhas))
    return len(linhas)
