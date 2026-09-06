"""Memória temporal e estado do mundo do cérebro local."""

from __future__ import annotations

import math
from typing import Any


class WorldStateLedger:
    BELIEF_STATUS = {"confirmed", "inferred", "conflicted"}

    def __init__(self, memory, events) -> None:
        self.memory = memory
        self.events = events

    @staticmethod
    def _text(value: Any, field: str, limit: int) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field} obrigatório")
        if len(text) > limit:
            raise ValueError(f"{field} excede {limit} caracteres")
        return text

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("confidence inválida") from exc
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ValueError("confidence precisa estar entre 0 e 1")
        return number

    async def remember_episode(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = self.memory.record_episode(
            self._text(payload.get("kind", "observation"), "kind", 64),
            self._text(payload.get("summary"), "summary", 4000),
            self._text(payload.get("source", "owner"), "source", 120),
            project_id=str(payload.get("project_id") or "")[:80] or None,
            device_id=str(payload.get("device_id") or "")[:80] or None,
            confidence=self._confidence(payload.get("confidence", 1.0)),
            occurred_at=float(payload["occurred_at"]) if payload.get("occurred_at") else None,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )
        await self.events.publish(
            "MEMORY_EPISODE_RECORDED", {"episode_id": item["id"], "kind": item["kind"]},
            source="world_state", project_id=item.get("project_id"),
        )
        return item

    async def assert_belief(self, payload: dict[str, Any]) -> dict[str, Any]:
        status = str(payload.get("status") or "confirmed").strip().lower()
        if status not in self.BELIEF_STATUS:
            raise ValueError("status de crença inválido")
        evidence = payload.get("evidence")
        if evidence is not None and not isinstance(evidence, list):
            raise ValueError("evidence precisa ser uma lista")
        item = self.memory.save_belief(
            self._text(payload.get("subject"), "subject", 240),
            self._text(payload.get("predicate"), "predicate", 160),
            self._text(payload.get("value"), "value", 4000),
            source=self._text(payload.get("source", "owner"), "source", 120),
            status=status,
            confidence=self._confidence(payload.get("confidence", 1.0)),
            evidence=evidence or [],
        )
        await self.events.publish(
            "WORLD_BELIEF_UPDATED",
            {"belief_id": item["id"], "subject": item["subject"], "predicate": item["predicate"]},
            source="world_state",
        )
        return item

    def snapshot(self, *, limit: int = 100, include_outdated: bool = False) -> dict[str, Any]:
        beliefs = self.memory.list_beliefs(limit, include_outdated=include_outdated)
        return {
            "beliefs": beliefs,
            "episodes": self.memory.list_episodes(min(limit, 100)),
            "conflicts": [item for item in beliefs if item["status"] == "conflicted"],
        }
