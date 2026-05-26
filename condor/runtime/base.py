"""
Interface base para engines de inferência.
Qualquer backend (llama-cpp, nativo, remoto) implementa este protocolo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Protocol, runtime_checkable

log = logging.getLogger("condor.runtime")


@dataclass
class EngineHealth:
    available: bool
    model_loaded: bool
    model_name: str
    backend: str
    error: str | None = None


@runtime_checkable
class InferenceEngine(Protocol):
    async def generate(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Gera tokens em streaming dado histórico de mensagens."""
        ...

    async def embed(self, text: str) -> list[float]:
        """Retorna embedding do texto (para busca semântica)."""
        ...

    def get_health(self) -> EngineHealth:
        """Retorna status atual do engine."""
        ...


class StubEngine:
    """
    Engine substituto quando o modelo GGUF não está disponível.
    Responde com mensagem de erro amigável ao invés de travar.
    """

    def __init__(self, model_path: Path) -> None:
        self._path = model_path

    async def generate(self, messages, system_prompt=None, **kwargs) -> AsyncIterator[str]:
        msg = (
            f"⚠️  Modelo não encontrado em '{self._path}'.\n"
            "Baixe um arquivo GGUF e coloque na pasta data/models/.\n"
            "Sugestão: qwen2.5-coder-7b-instruct-q4_k_m.gguf (~4 GB)\n"
            "Fonte: https://huggingface.co/Qwen"
        )
        for token in msg.split(" "):
            yield token + " "

    async def embed(self, text: str) -> list[float]:
        return [0.0] * 384

    def get_health(self) -> EngineHealth:
        return EngineHealth(
            available=False,
            model_loaded=False,
            model_name=str(self._path.name),
            backend="stub",
            error=f"Modelo não encontrado: {self._path}",
        )
