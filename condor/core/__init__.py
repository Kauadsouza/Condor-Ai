"""Núcleo compartilhado do Condor.

Todas as interfaces entram por esta camada antes de alcançar IA, projetos,
dispositivos ou memória. Isso mantém o Condor como um único cérebro, em vez de
uma coleção de funcionalidades independentes.
"""

from .ai_gateway import AIGateway, MockAIProvider
from .context import ContextEngine
from .device_mesh import DeviceMesh
from .events import EventBus
from .orchestrator import CondorOrchestrator
from .projects import ProjectEngine
from .tasks import DurableTaskEngine
from .world import WorldStateLedger

__all__ = [
    "AIGateway", "CondorOrchestrator", "ContextEngine", "DeviceMesh",
    "DurableTaskEngine", "EventBus", "MockAIProvider", "ProjectEngine",
    "WorldStateLedger",
]
