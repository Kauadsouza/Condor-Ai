"""Núcleo compartilhado do Condor.

Todas as interfaces entram por esta camada antes de alcançar IA, projetos,
dispositivos ou memória. Isso mantém o Condor como um único cérebro, em vez de
uma coleção de funcionalidades independentes.
"""

from .ai_gateway import AIGateway, MockAIProvider
from .context import ContextEngine
from .events import EventBus
from .projects import ProjectEngine

__all__ = ["AIGateway", "ContextEngine", "EventBus", "MockAIProvider", "ProjectEngine"]
