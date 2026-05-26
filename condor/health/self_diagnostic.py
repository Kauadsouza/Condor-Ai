"""
Auto-diagnóstico do CONDOR.
Detecta APENAS problemas reais. IDs estáveis por tipo de erro.
Distingue entre modelo ausente (crítico) e modelo carregando (info).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from condor.health.monitor import SystemMonitor

log = logging.getLogger("condor.health.diagnostic")


@dataclass
class CondorError:
    id: str
    severity: str     # critical, warning, info
    category: str     # CORE, INFERÊNCIA, RECURSOS, VOZ
    title: str
    description: str
    detail: str = ""
    ts: float = 0.0

    def __post_init__(self):
        if not self.ts:
            self.ts = time.time()

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "severity":    self.severity,
            "category":    self.category,
            "title":       self.title,
            "description": self.description,
            "detail":      self.detail,
            "ts":          self.ts,
        }


class SelfDiagnostic:
    def __init__(self, monitor: SystemMonitor) -> None:
        self._monitor    = monitor
        self._engine     = None   # referência viva ao engine
        self._stt_ok     = True
        self._tts_ok     = True
        self._first_seen: dict[str, float] = {}

    def set_engine(self, engine) -> None:
        """Guarda referência viva — health consultado dinamicamente a cada check."""
        self._engine = engine

    # Mantém compatibilidade com código antigo
    def set_engine_health(self, health) -> None:
        pass

    def set_voice_status(self, stt_ok: bool, tts_ok: bool) -> None:
        self._stt_ok = stt_ok
        self._tts_ok = tts_ok

    def run_checks(self) -> list[CondorError]:
        errors: list[CondorError] = []
        snap = self._monitor.snapshot()

        # ── Engine / LLM ────────────────────────────────────────────────────
        if self._engine is not None:
            health = self._engine.get_health()

            # Verifica se é LlamaServer ainda carregando (não é erro)
            is_loading = getattr(self._engine, "is_loading", False)
            is_ready   = getattr(self._engine, "is_ready",   False)

            if is_loading:
                # Apenas informativo — não conta como erro crítico
                errors.append(CondorError(
                    id="ERR-MODEL-LOADING",
                    severity="info",
                    category="INFERÊNCIA",
                    title="Modelo carregando...",
                    description="O modelo LLM está sendo carregado em background. Aguarde alguns segundos.",
                    detail=f"Modelo: {health.model_name}",
                ))
            elif not health.model_loaded:
                # Modelo realmente não carregado e não está tentando
                errors.append(CondorError(
                    id="ERR-MODEL",
                    severity="critical",
                    category="INFERÊNCIA",
                    title="Modelo LLM não carregado",
                    description=(
                        "Nenhum arquivo GGUF encontrado ou falha ao iniciar. "
                        "O Condor não consegue responder."
                    ),
                    detail=(
                        f"Caminho esperado: {health.model_name}\n"
                        "1. Baixe o modelo GGUF em: huggingface.co/Qwen\n"
                        "2. Coloque em: data/models/\n"
                        "3. Reinicie o Condor"
                    ),
                ))
            # Se is_ready=True → sem erro de modelo

        # ── RAM ─────────────────────────────────────────────────────────────
        # Thresholds mais altos porque o modelo LLM ocupa RAM intencionalmente
        if snap["ram_pct"] > 97:
            errors.append(CondorError(
                id="ERR-RAM-CRIT",
                severity="critical",
                category="RECURSOS",
                title="Memória RAM crítica",
                description=(
                    f"Uso em {snap['ram_pct']:.0f}%. "
                    "Feche outros programas para liberar memória."
                ),
                detail=(
                    f"Usado: {snap['ram_used'] / 1e9:.1f} GB / "
                    f"{snap['ram_total'] / 1e9:.1f} GB\n"
                    "Dica: feche o navegador, Discord ou outros apps pesados."
                ),
            ))
        elif snap["ram_pct"] > 92:
            errors.append(CondorError(
                id="ERR-RAM-WARN",
                severity="warning",
                category="RECURSOS",
                title="Memória RAM elevada",
                description=(
                    f"Uso em {snap['ram_pct']:.0f}%. "
                    "Normal com o modelo carregado, mas monitore."
                ),
            ))
        # Entre 80-92%: sem aviso (esperado com modelo de 4-5 GB rodando)

        # ── CPU muito alta ───────────────────────────────────────────────────
        if snap["cpu_pct"] > 95:
            errors.append(CondorError(
                id="ERR-CPU",
                severity="warning",
                category="RECURSOS",
                title="CPU sobrecarregada",
                description=f"CPU em {snap['cpu_pct']:.0f}%. Respostas podem demorar.",
            ))

        # ── Voz ─────────────────────────────────────────────────────────────
        if not self._stt_ok:
            errors.append(CondorError(
                id="ERR-STT",
                severity="warning",
                category="VOZ",
                title="Speech-to-Text indisponível",
                description="Whisper não carregou. Entrada por voz desativada.",
                detail="Reinstale: pip install faster-whisper",
            ))

        if not self._tts_ok:
            errors.append(CondorError(
                id="ERR-TTS",
                severity="info",
                category="VOZ",
                title="Text-to-Speech não configurado",
                description="O Condor responde só em texto por enquanto.",
                detail=(
                    "Opção 1: Baixe Piper em github.com/rhasspy/piper\n"
                    "Opção 2: pip install pyttsx3 (voz do sistema)"
                ),
            ))

        # Preserva timestamp da primeira aparição
        now = time.time()
        for err in errors:
            if err.id not in self._first_seen:
                self._first_seen[err.id] = now
            err.ts = self._first_seen[err.id]

        # Remove erros que sumiram
        active_ids = {e.id for e in errors}
        for eid in list(self._first_seen):
            if eid not in active_ids:
                del self._first_seen[eid]

        return errors

    def get_health(self) -> dict:
        errors     = self.run_checks()
        n_critical = sum(1 for e in errors if e.severity == "critical")
        n_warning  = sum(1 for e in errors if e.severity == "warning")

        score = max(0, 100 - n_critical * 30 - n_warning * 10)
        if n_critical >= 2:
            status = "CRITICO"
        elif n_critical == 1:
            status = "ATENCAO"
        elif n_warning >= 1:
            status = "ATENCAO"
        else:
            status = "OPERACIONAL"

        return {
            "score":    score,
            "status":   status,
            "critical": n_critical,
            "warning":  n_warning,
            "errors":   [e.to_dict() for e in errors],
        }
