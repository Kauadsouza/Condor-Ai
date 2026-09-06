"""Tarefas duráveis que sobrevivem a reinícios do Condor."""

from __future__ import annotations

from typing import Any


class DurableTaskEngine:
    STATUS = {"pending", "running", "waiting", "completed", "failed", "cancelled"}
    CHECKPOINT_STATUS = {"pending", "running", "completed", "failed", "blocked"}

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

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        priority = int(payload.get("priority", 50))
        if not 0 <= priority <= 100:
            raise ValueError("priority precisa estar entre 0 e 100")
        task = self.memory.create_durable_task(
            self._text(payload.get("title"), "title", 240),
            self._text(payload.get("objective"), "objective", 4000),
            project_id=str(payload.get("project_id") or "")[:80] or None,
            priority=priority,
            source=self._text(payload.get("source", "owner"), "source", 120),
            due_at=float(payload["due_at"]) if payload.get("due_at") else None,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )
        await self.events.publish(
            "DURABLE_TASK_CREATED", {"task_id": task["id"], "title": task["title"]},
            source="task_engine", project_id=task.get("project_id"),
        )
        return task

    async def transition(self, task_id: str, status: str) -> dict[str, Any]:
        state = status.strip().lower()
        if state not in self.STATUS:
            raise ValueError("status de tarefa inválido")
        task = self.memory.update_durable_task(task_id, state)
        if task is None:
            raise KeyError("tarefa não encontrada")
        await self.events.publish(
            "DURABLE_TASK_UPDATED", {"task_id": task_id, "status": state},
            source="task_engine", project_id=task.get("project_id"),
        )
        return task

    async def checkpoint(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        status = str(payload.get("status") or "completed").strip().lower()
        if status not in self.CHECKPOINT_STATUS:
            raise ValueError("status de checkpoint inválido")
        evidence = payload.get("evidence")
        if evidence is not None and not isinstance(evidence, list):
            raise ValueError("evidence precisa ser uma lista")
        checkpoint = self.memory.add_task_checkpoint(
            task_id,
            self._text(payload.get("step"), "step", 240),
            status,
            str(payload.get("summary") or "")[:4000],
            evidence or [],
        )
        await self.events.publish(
            "TASK_CHECKPOINT_RECORDED",
            {"task_id": task_id, "checkpoint_id": checkpoint["id"], "status": status},
            source="task_engine",
        )
        return checkpoint

    def resumable(self) -> list[dict[str, Any]]:
        return [
            *self.memory.list_durable_tasks(100, "running"),
            *self.memory.list_durable_tasks(100, "waiting"),
            *self.memory.list_durable_tasks(100, "pending"),
        ]
