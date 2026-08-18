"""Política independente para ações físicas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class RiskLevel(IntEnum):
    READ_ONLY = 0
    SIMULATION = 1
    SOFTWARE_CHANGE = 2
    LOW_RISK_PHYSICAL = 3
    ACTUATOR = 4
    DANGEROUS = 5


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    allowed: bool
    level: int
    requires_simulation: bool
    requires_confirmation: bool
    reason: str


class ActionSafetyLayer:
    """Nenhuma IA pode contornar esta camada."""

    BLOCKED_TERMS = frozenset({"arma", "weapon", "chama", "flame", "propulsão", "propulsion", "explosivo", "explosive"})

    def evaluate(self, action: dict[str, Any]) -> SafetyDecision:
        text = " ".join(str(value).lower() for value in action.values())
        if any(term in text for term in self.BLOCKED_TERMS):
            return SafetyDecision(False, RiskLevel.DANGEROUS, True, True, "ação física proibida pela política permanente")
        requested = int(action.get("risk_level", RiskLevel.READ_ONLY))
        level = max(RiskLevel.READ_ONLY, min(RiskLevel.DANGEROUS, requested))
        if level >= RiskLevel.DANGEROUS:
            return SafetyDecision(False, int(level), True, True, "nível 5 não pode ser executado pelo Condor")
        if level >= RiskLevel.ACTUATOR:
            return SafetyDecision(False, int(level), True, True, "atuadores exigem validação externa e permanecem bloqueados nesta versão")
        return SafetyDecision(
            True,
            int(level),
            level >= RiskLevel.LOW_RISK_PHYSICAL,
            level >= RiskLevel.SOFTWARE_CHANGE,
            "leitura permitida" if level == 0 else "ação condicionada aos controles indicados",
        )
