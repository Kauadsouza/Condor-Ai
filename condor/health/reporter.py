"""
Reporter de saúde — formata dados para logs estruturados.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("condor.health.reporter")

_LOG_FILE = Path("data/logs/health.jsonl")


class HealthReporter:
    def __init__(self) -> None:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def record(self, health: dict) -> None:
        entry = {"ts": time.time(), **health}
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
