"""Motor de projetos, peças, rascunhos e versões do Condor Core."""

from __future__ import annotations

from typing import Any


class ProjectEngine:
    def __init__(self, memory, context, events) -> None:
        self.memory = memory
        self.context = context
        self.events = events

    def snapshot(self, project_id: str = "condor-x") -> dict[str, Any]:
        return self.memory.project_snapshot(project_id)

    async def open(self, project_id: str) -> dict[str, Any]:
        project = self.memory.get_project(project_id)
        if project is None:
            raise KeyError("projeto não encontrado")
        context = self.context.update(
            project_id=project_id,
            project_name=project["name"],
            project_version=project.get("active_version_label"),
            mode="development",
        )
        await self.events.publish("PROJECT_OPENED", {"project": project}, source="project_engine", project_id=project_id)
        return {"project": project, "context": context}

    async def select_region(self, project_id: str, region_id: str) -> dict[str, Any]:
        context = self.context.update(project_id=project_id, region_id=region_id, part_id=None, selected_object=region_id, mode="development")
        await self.events.publish("PART_SELECTED", {"region_id": region_id}, source="project_engine", project_id=project_id)
        return context

    async def create_draft(self, project_id: str, region_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        part = self.memory.create_part_draft(project_id, region_id, payload)
        self.context.update(project_id=project_id, region_id=region_id, part_id=part["id"], selected_object=part["id"], mode="development")
        await self.events.publish("PART_CREATED", {"part": part}, source="project_engine", project_id=project_id)
        return part

    async def create_version(self, part_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        version = self.memory.create_part_version(part_id, payload)
        project_id = version["project_id"]
        await self.events.publish("PART_UPDATED", {"part_id": part_id, "version": version}, source="project_engine", project_id=project_id)
        return version

    async def integrate(self, part_id: str) -> dict[str, Any]:
        part = self.memory.integrate_part(part_id)
        if part is None:
            raise KeyError("peça não encontrada")
        await self.events.publish("MODEL_UPDATED", {"part": part, "action": "integrated"}, source="project_engine", project_id=part["project_id"])
        return part
