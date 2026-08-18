"""Politica declarativa de capacidades do Condor.

O modelo nunca decide a propria permissao. Ele pede uma ferramenta; este
modulo, que nao usa IA, decide se a chamada e permitida, simulada ou bloqueada.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from condor.paths import resolver_alvo


class RiskLevel(str, Enum):
    SAFE = "safe"
    REVIEW = "review"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


class AutonomyProfile(str, Enum):
    OBSERVER = "observer"
    ASSISTANT = "assistant"
    OPERATOR = "operator"
    ADMIN = "admin"


@dataclass(frozen=True)
class ActionDecision:
    allowed: bool
    requires_approval: bool
    simulated: bool
    risk: RiskLevel
    reason: str
    digest: str


TOOL_RISK: dict[str, RiskLevel] = {
    "condor_estado": RiskLevel.REVIEW,
    "condor_abrir_projeto": RiskLevel.REVIEW,
    "condor_selecionar_regiao": RiskLevel.REVIEW,
    "condor_criar_rascunho": RiskLevel.CONFIRM,
    "condor_salvar_codigo": RiskLevel.CONFIRM,
    "condor_historico_codigo": RiskLevel.REVIEW,
    "condor_restaurar_codigo": RiskLevel.CONFIRM,
    "condor_criar_experimento": RiskLevel.CONFIRM,
    "condor_atualizar_experimento": RiskLevel.CONFIRM,
    "condor_registrar_memoria": RiskLevel.REVIEW,
    "condor_buscar_dispositivos": RiskLevel.REVIEW,
    "condor_conectar_dispositivo": RiskLevel.CONFIRM,
    "condor_desconectar_dispositivo": RiskLevel.REVIEW,
    "info_sistema": RiskLevel.REVIEW,
    "listar_pasta": RiskLevel.REVIEW,
    "buscar_arquivos": RiskLevel.REVIEW,
    "buscar_web": RiskLevel.REVIEW,
    "ler_site": RiskLevel.REVIEW,
    "buscar_memoria": RiskLevel.CONFIRM,
    "ler_arquivo": RiskLevel.REVIEW,
    "ler_pdf": RiskLevel.REVIEW,
    "listar_janelas": RiskLevel.REVIEW,
    "abrir": RiskLevel.REVIEW,
    "focar_janela": RiskLevel.REVIEW,
    "copiar": RiskLevel.REVIEW,
    "escrever_clipboard": RiskLevel.REVIEW,
    "screenshot": RiskLevel.CONFIRM,
    "ler_clipboard": RiskLevel.CONFIRM,
    "escrever_arquivo": RiskLevel.CONFIRM,
    "mover": RiskLevel.CONFIRM,
    "deletar": RiskLevel.CONFIRM,
    "baixar": RiskLevel.CONFIRM,
    "fechar_app": RiskLevel.CONFIRM,
    "clicar": RiskLevel.CONFIRM,
    "digitar": RiskLevel.CONFIRM,
    "atalho": RiskLevel.CONFIRM,
    "instalar_pacote": RiskLevel.BLOCKED,
    "executar_powershell": RiskLevel.BLOCKED,
    "executar_python": RiskLevel.BLOCKED,
}


def action_digest(tool: str, arguments: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"tool": tool, "arguments": arguments},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class PolicyEngine:
    def __init__(
        self,
        profile: AutonomyProfile = AutonomyProfile.ASSISTANT,
        allowed_roots: list[Path] | None = None,
        simulation: bool = False,
    ) -> None:
        self.profile = profile
        self.allowed_roots = [path.expanduser().resolve() for path in (allowed_roots or [])]
        self.simulation = simulation

    def decide(self, tool: str, arguments: dict[str, Any]) -> ActionDecision:
        risk = TOOL_RISK.get(tool, RiskLevel.BLOCKED)
        digest = action_digest(tool, arguments)

        path_reason = self._validate_paths(tool, arguments)
        if path_reason:
            return ActionDecision(False, False, False, RiskLevel.BLOCKED, path_reason, digest)

        if risk is RiskLevel.BLOCKED:
            return ActionDecision(
                False, False, False, risk,
                "Capacidade irrestrita desativada. Use uma ferramenta especifica e isolada.",
                digest,
            )

        if self.profile is AutonomyProfile.OBSERVER and risk is not RiskLevel.SAFE:
            return ActionDecision(False, False, False, risk, "Perfil Observador nao altera o PC.", digest)

        approval = (
            risk is RiskLevel.CONFIRM
            or (risk is RiskLevel.REVIEW and self.profile is AutonomyProfile.ASSISTANT)
        )
        if self.simulation and risk is not RiskLevel.SAFE:
            return ActionDecision(False, approval, True, risk, "Modo simulacao: nada foi executado.", digest)
        return ActionDecision(True, approval, False, risk, "Permitido pela politica local.", digest)

    def _validate_paths(self, tool: str, arguments: dict[str, Any]) -> str | None:
        if not self.allowed_roots:
            return None
        keys = {
            "ler_arquivo": ("caminho",), "ler_pdf": ("caminho",),
            "listar_pasta": ("caminho",), "buscar_arquivos": ("raiz",),
            "escrever_arquivo": ("caminho",), "deletar": ("caminho",),
            "mover": ("origem", "destino"), "copiar": ("origem", "destino"),
            "baixar": ("destino",),
        }.get(tool, ())
        for key in keys:
            raw = str(arguments.get(key) or "").strip()
            if not raw:
                continue
            # resolver_alvo e a mesma normalizacao que o executor aplica, entao
            # os dois lados enxergam o mesmo destino. O .resolve() final segue
            # link simbolico e junction — e exatamente onde o sistema vai gravar,
            # que e o que precisa estar dentro das raizes. As raizes tambem sao
            # guardadas resolvidas, entao pasta redirecionada (OneDrive) casa.
            try:
                candidate = resolver_alvo(raw).resolve()
            except (OSError, ValueError):
                return f"Caminho invalido em {key}."
            if not any(
                candidate == root or root in candidate.parents
                for root in self.allowed_roots
            ):
                return f"{candidate} esta fora das pastas permitidas do Condor."
        return None
