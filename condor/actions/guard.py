"""Guarda deterministica do Condor.

Substitui a antiga lista de comandos proibidos. A IA nao consegue ampliar as
proprias permissoes: toda chamada passa por uma politica local, e aprovacoes
sao exatas, expiram rapido e nao podem ser reutilizadas por outra acao.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Awaitable, Callable

from condor.paths import CODE_ROOT, state_path
from condor.security.approval import OwnerAuth
from condor.security.audit import IntegrityAudit
from condor.security.policy import ActionDecision, AutonomyProfile, PolicyEngine

PedidoAprovacao = Callable[[str, str], Awaitable[str | None]]

# Ferramentas que continuam pedindo a palavra de acesso mesmo com a sessao do dono
# aberta. Sao as de efeito irreversivel ou de alcance grande demais pra confiar
# num planejador que le pagina da internet: uma instrucao escondida num site
# lido pelo `ler_site` nao pode virar arquivo gravado ou processo encerrado sem
# voce ver. As demais (screenshot, clicar, digitar, ler_clipboard) seguem
# liberadas durante a sessao — se quiser endurecer, e so acrescentar aqui.
SEMPRE_CONFIRMA = frozenset({
    "escrever_arquivo",
    "deletar",
    "mover",
    "baixar",
    "fechar_app",
})


class Guarda:
    def __init__(self, config, memoria=None, identity=None) -> None:
        self._cfg = config
        self._memoria = memoria
        roots = [Path(value) for value in config.seguranca.pastas_permitidas]
        if not roots:
            roots = [
                Path.home() / "Desktop",
                Path.home() / "Documents",
                Path.home() / "Downloads",
                CODE_ROOT,
            ]
        self._policy = PolicyEngine(
            profile=AutonomyProfile(config.seguranca.perfil),
            allowed_roots=roots,
            simulation=config.seguranca.simulacao,
        )
        self.owner = OwnerAuth(state_path("security", "owner.json"))
        # A identidade Ed25519 assina a ancora da auditoria: sem ela, o log
        # inteiro pode ser reconstruido do zero e ainda passar na verificacao.
        self._audit = IntegrityAudit(state_path("audit", "actions.jsonl"), identity)
        self._pedir: PedidoAprovacao | None = None
        self._emergency_stop = False
        self._owner_session_active = False

    @property
    def allowed_roots(self) -> list[str]:
        return [str(path) for path in self._policy.allowed_roots]

    @property
    def configurada(self) -> bool:
        return self.owner.configured

    def configurar_dono(self, passphrase: str) -> None:
        self.owner.setup(passphrase)

    def unlock_owner_session(self) -> None:
        """Uma autenticacao local valida abre a sessao operacional do dono.

        A sessao muda o runtime, nao o arquivo de configuracao. Antes daqui
        forcava perfil=admin e simulacao=False no proprio ``config.yaml``: quem
        escolhesse ``observer`` ou ligasse a simulacao via desbloqueio, perdia a
        escolha no primeiro desbloqueio e nunca entendia por que. A preferencia
        gravada e do dono; a sessao so a aplica.
        """
        self._owner_session_active = True
        self._policy.profile = AutonomyProfile(self._cfg.seguranca.perfil)
        self._policy.simulation = self._cfg.seguranca.simulacao

    def lock_owner_session(self) -> None:
        self._owner_session_active = False

    @property
    def owner_session_active(self) -> bool:
        return self._owner_session_active

    def registrar_pedido_senha(self, fn: PedidoAprovacao) -> None:
        """Mantem o nome da API antiga para compatibilidade com a sessao."""
        self._pedir = fn

    def avaliar(self, ferramenta: str, argumentos: dict) -> ActionDecision:
        if self._emergency_stop:
            decision = self._policy.decide(ferramenta, argumentos)
            return ActionDecision(
                allowed=False,
                requires_approval=False,
                simulated=False,
                risk=decision.risk,
                reason="Interruptor de emergencia do Condor esta ativo.",
                digest=decision.digest,
            )
        if not self._owner_session_active:
            decision = self._policy.decide(ferramenta, argumentos)
            return ActionDecision(
                allowed=False,
                requires_approval=False,
                simulated=False,
                risk=decision.risk,
                reason="Condor bloqueado. Entre com a palavra de acesso do dono.",
                digest=decision.digest,
            )
        return self._policy.decide(ferramenta, argumentos)

    def emergency_stop(self) -> None:
        self._emergency_stop = True
        self.auditar("emergency", "stop", "ATIVADO", True, False)

    def emergency_resume(self, passphrase: str) -> bool:
        if not self.owner.verify(passphrase):
            return False
        self._emergency_stop = False
        self.auditar("emergency", "resume", "DESATIVADO", True, True)
        return True

    @property
    def stopped(self) -> bool:
        return self._emergency_stop

    async def autorizar(
        self, decision: ActionDecision, descricao: str, ferramenta: str = ""
    ) -> bool:
        if not decision.allowed or decision.simulated:
            self.auditar(
                "policy", descricao,
                "SIMULADO" if decision.simulated else f"BLOQUEADO: {decision.reason}",
                False, decision.requires_approval,
            )
            return False
        if not decision.requires_approval:
            return True
        if self._owner_session_active and ferramenta not in SEMPRE_CONFIRMA:
            self.auditar("policy", descricao, "AUTORIZADO PELO DONO AUTENTICADO", True, True)
            return True
        if self._pedir is None or not self.owner.configured:
            self.auditar("policy", descricao, "BLOQUEADO: dono nao configurado", False, True)
            return False

        challenge = self.owner.challenge(
            decision.digest,
            descricao,
            ttl=self._cfg.seguranca.timeout_aprovacao,
        )
        motivo = (
            f"O Condor quer executar: {descricao}. Risco: {decision.risk.value}. "
            "Confirme localmente com sua palavra de acesso. Voz nao autoriza esta acao."
        )
        response = await self._pedir(motivo, challenge.id)
        if not response:
            self.auditar("policy", descricao, "BLOQUEADO: sem confirmacao", False, True)
            return False
        token = self.owner.approve(challenge.id, response)
        accepted = bool(token and self.owner.consume(token, decision.digest))
        self.auditar(
            "policy", descricao,
            "AUTORIZADO" if accepted else "BLOQUEADO: palavra de acesso incorreta",
            accepted, True,
        )
        return accepted

    def auditar(
        self,
        ferramenta: str,
        entrada: str,
        resultado: str,
        sucesso: bool = True,
        exigiu_senha: bool = False,
    ) -> None:
        if not self._cfg.seguranca.auditoria:
            return
        event = {
            "tool": ferramenta,
            "input": entrada[:1000],
            "result": resultado[:1000],
            "success": bool(sucesso),
            "approval_required": bool(exigiu_senha),
        }
        self._audit.append(event)
        if self._memoria is not None:
            try:
                self._memoria.registrar_acao(
                    ferramenta,
                    json.dumps(event, ensure_ascii=False),
                    resultado,
                    sucesso,
                    exigiu_senha,
                )
            except Exception:
                pass

    def verificar_auditoria(self) -> tuple[bool, int]:
        return self._audit.verify()
