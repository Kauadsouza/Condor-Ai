"""Auditoria JSONL encadeada por hash para revelar alteracoes no historico."""

from __future__ import annotations

import hashlib
import json
import os
import time
import threading
from pathlib import Path
from typing import Any


class IntegrityAudit:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def append(self, event: dict[str, Any]) -> str:
        with self._lock:
            previous = self._last_hash()
            body = {
                "version": 1,
                "timestamp": time.time(),
                "previous": previous,
                "event": event,
            }
            encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            record = {**body, "hash": digest}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
            return digest

    def verify(self) -> tuple[bool, int]:
        with self._lock:
            if not self.path.exists():
                return True, 0
            previous = "0" * 64
            count = 0
            try:
                lines = self.path.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    record = json.loads(line)
                    expected = record.pop("hash")
                    encoded = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                    actual = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                    if not hmac_compare(expected, actual) or record.get("previous") != previous:
                        return False, count
                    previous = expected
                    count += 1
            except (OSError, KeyError, TypeError, json.JSONDecodeError):
                return False, count
            return True, count

    def _last_hash(self) -> str:
        if not self.path.exists():
            return "0" * 64
        lines = self.path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return "0" * 64
        return str(json.loads(lines[-1]).get("hash") or "0" * 64)


def hmac_compare(left: str, right: str) -> bool:
    import hmac
    return hmac.compare_digest(left, right)
