"""
Registry central de skills.
Skills são registradas com @skill() e ficam disponíveis para o ActionRouter.
Cada skill declara quais recursos ela toca (filesystem, process, network…).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("condor.actions")


@dataclass
class SkillDef:
    name: str
    description: str
    handler: Callable
    params_schema: dict        # JSON Schema simplificado dos parâmetros
    resources: list[str]       # filesystem, process, network, display
    requires_confirm: bool = False


class SkillRegistry:
    def __init__(self, config) -> None:
        self._config = config
        self._skills: dict[str, SkillDef] = {}

    def register(self, skill: SkillDef) -> None:
        self._skills[skill.name] = skill
        log.debug("Skill registrada: %s", skill.name)

    def get(self, name: str) -> SkillDef | None:
        return self._skills.get(name)

    def list_skills(self) -> list[dict]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "resources": s.resources,
                "requires_confirm": s.requires_confirm,
            }
            for s in self._skills.values()
        ]

    def skill_names_for_prompt(self) -> str:
        lines = []
        for s in self._skills.values():
            lines.append(f'- "{s.name}": {s.description}')
        return "\n".join(lines)


def make_skill(
    name: str,
    description: str,
    handler: Callable,
    params_schema: dict | None = None,
    resources: list[str] | None = None,
    requires_confirm: bool = False,
) -> SkillDef:
    return SkillDef(
        name=name,
        description=description,
        handler=handler,
        params_schema=params_schema or {},
        resources=resources or [],
        requires_confirm=requires_confirm,
    )
