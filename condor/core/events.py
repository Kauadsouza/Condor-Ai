"""Barramento de eventos do Condor Core."""

from __future__ import annotations

import asyncio
import inspect
import re
import time
import uuid
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable

EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]
_EVENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


@dataclass(frozen=True, slots=True)
class CoreEvent:
    id: str
    type: str
    source: str
    payload: dict[str, Any]
    timestamp: float
    project_id: str | None = None
    correlation_id: str | None = None


class EventBus:
    """Distribui eventos sem acoplar os módulos e conserva um histórico curto."""

    def __init__(self, memory=None, history_limit: int = 250) -> None:
        self._memory = memory
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._history: deque[dict[str, Any]] = deque(maxlen=history_limit)
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: str, handler: EventHandler) -> Callable[[], None]:
        key = event_type.upper()
        self._handlers[key].append(handler)

        def unsubscribe() -> None:
            if handler in self._handlers[key]:
                self._handlers[key].remove(handler)

        return unsubscribe

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        source: str = "core",
        project_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        name = event_type.upper().strip()
        if not _EVENT_NAME.fullmatch(name):
            raise ValueError("tipo de evento inválido")
        event = asdict(CoreEvent(
            id=f"evt_{uuid.uuid4().hex[:20]}",
            type=name,
            source=source[:64],
            payload=dict(payload or {}),
            timestamp=time.time(),
            project_id=project_id,
            correlation_id=correlation_id,
        ))
        async with self._lock:
            self._history.appendleft(event)
            if self._memory is not None and getattr(self._memory, "unlocked", False):
                self._memory.registrar_evento(event)
        handlers = [*self._handlers.get(name, ()), *self._handlers.get("*", ())]
        for handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                # Um consumidor não pode derrubar o núcleo nem impedir os demais.
                continue
        return event

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._history)[: max(1, min(limit, 250))]
