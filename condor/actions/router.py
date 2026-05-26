"""
Router de ações: extrai intent do texto do LLM e executa a skill certa.
O LLM pode retornar um bloco JSON como:
    {"action": "open_application", "params": {"name": "Brave"}}
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from condor.actions.base import SkillRegistry
from condor.config import ActionsConfig

log = logging.getLogger("condor.actions.router")

_JSON_PATTERN = re.compile(r'\{[^{}]*"action"\s*:[^{}]*\}', re.DOTALL)


class ActionRouter:
    def __init__(self, registry: SkillRegistry, config: ActionsConfig) -> None:
        self._registry = registry
        self._config   = config

    def extract_and_route(self, llm_response: str) -> dict | None:
        """Extrai bloco de ação do texto do LLM. Retorna None se não houver ação."""
        match = _JSON_PATTERN.search(llm_response)
        if not match:
            return None

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return None

        action = data.get("action")
        if not action:
            return None

        skill = self._registry.get(action)
        if not skill:
            log.warning("Skill desconhecida: %s", action)
            return None

        return {
            "skill": action,
            "params": data.get("params", {}),
            "requires_confirm": skill.requires_confirm
                                or action in self._config.require_confirmation,
        }

    async def execute(self, action_data: dict) -> dict:
        """Executa a skill. Retorna resultado como dict."""
        skill_name = action_data.get("skill")
        params     = action_data.get("params", {})

        skill = self._registry.get(skill_name)
        if not skill:
            return {"success": False, "error": f"Skill '{skill_name}' não encontrada."}

        log.info("Executando skill '%s' com params %s", skill_name, params)
        try:
            if asyncio.iscoroutinefunction(skill.handler):
                result = await skill.handler(**params)
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: skill.handler(**params)
                )
            return {"success": True, "skill": skill_name, "result": result}
        except Exception as exc:
            log.error("Erro na skill '%s': %s", skill_name, exc)
            return {"success": False, "skill": skill_name, "error": str(exc)}
