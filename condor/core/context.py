"""Estado contextual estruturado compartilhado por todas as interfaces."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class ContextState:
    project_id: str | None = None
    project_name: str | None = None
    project_version: str | None = None
    assembly_id: str | None = None
    region_id: str | None = None
    part_id: str | None = None
    selected_object: str | None = None
    device_id: str | None = None
    mode: str = "chat"
    current_file: str | None = None
    recent_intent: str | None = None
    updated_at: float = 0.0


class ContextEngine:
    FIELDS = frozenset(ContextState.__dataclass_fields__)

    def __init__(self) -> None:
        self._state = ContextState(updated_at=time.time())
        self._lock = threading.RLock()

    def update(self, **changes: Any) -> dict[str, Any]:
        invalid = set(changes) - self.FIELDS
        if invalid:
            raise ValueError(f"campos de contexto inválidos: {', '.join(sorted(invalid))}")
        with self._lock:
            for field, value in changes.items():
                if isinstance(value, str):
                    value = value.strip()[:500] or None
                setattr(self._state, field, value)
            self._state.updated_at = time.time()
            return asdict(self._state)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._state)

    def clear_selection(self) -> dict[str, Any]:
        return self.update(region_id=None, part_id=None, selected_object=None)

    def for_ai(self) -> dict[str, Any]:
        """Contrato estável enviado à IA; nunca inclui segredo ou biometria."""
        state = self.snapshot()
        return {key: value for key, value in state.items() if value is not None}
