"""
Engine de inferência usando llama-cpp-python.
Carrega modelo GGUF diretamente no processo — sem Ollama, sem servidor externo.

Instale com: pip install llama-cpp-python
Para GPU CUDA: pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator

from condor.config import ModelConfig
from condor.runtime.base import EngineHealth

log = logging.getLogger("condor.runtime.llamacpp")

try:
    from llama_cpp import Llama
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    log.warning("llama-cpp-python não instalado. Instale com: pip install llama-cpp-python")


class LlamaCppEngine:
    """
    Wrapper assíncrono para llama-cpp-python.
    O modelo fica carregado em memória entre chamadas (sem reload).
    """

    def __init__(self, config: ModelConfig) -> None:
        self._config = config
        self._llm: "Llama | None" = None
        self._model_path = Path(config.path)

    async def initialize(self) -> None:
        if not _AVAILABLE:
            raise RuntimeError("llama-cpp-python não está instalado.")
        if not self._model_path.exists():
            raise FileNotFoundError(f"Modelo não encontrado: {self._model_path}")

        log.info("Carregando modelo: %s", self._model_path.name)
        # Roda em thread para não bloquear o loop de eventos
        loop = asyncio.get_event_loop()
        self._llm = await loop.run_in_executor(None, self._load_model)
        log.info("Modelo carregado. n_gpu_layers=%s", self._config.n_gpu_layers)

    def _load_model(self) -> "Llama":
        return Llama(
            model_path=str(self._model_path),
            n_ctx=self._config.n_ctx,
            n_gpu_layers=self._config.n_gpu_layers,
            verbose=False,
            n_threads=None,     # auto detecta núcleos
            use_mlock=False,
        )

    async def generate(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        if self._llm is None:
            yield "Engine não inicializado. Chame initialize() primeiro."
            return

        prompt = self._build_prompt(messages, system_prompt)

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _stream() -> None:
            try:
                stream = self._llm.create_completion(
                    prompt=prompt,
                    max_tokens=self._config.max_tokens,
                    temperature=self._config.temperature,
                    top_p=self._config.top_p,
                    top_k=self._config.top_k,
                    repeat_penalty=self._config.repeat_penalty,
                    stream=True,
                    stop=["<|im_end|>", "<|endoftext|>", "\nUsuário:", "\nVocê:"],
                )
                for chunk in stream:
                    token = chunk["choices"][0]["text"]
                    if token:
                        loop.call_soon_threadsafe(queue.put_nowait, token)
            except Exception as exc:
                log.error("Erro durante geração: %s", exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(None, _stream)

        while True:
            token = await queue.get()
            if token is None:
                break
            yield token

    async def embed(self, text: str) -> list[float]:
        if self._llm is None:
            return [0.0] * 384
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._llm.create_embedding(text)["data"][0]["embedding"],
        )
        return result

    def get_health(self) -> EngineHealth:
        return EngineHealth(
            available=_AVAILABLE,
            model_loaded=self._llm is not None,
            model_name=self._model_path.name,
            backend="llama-cpp-python",
        )

    @staticmethod
    def _build_prompt(messages: list[dict], system_prompt: str | None) -> str:
        # Formato ChatML — padrão para Qwen e maioria dos instruct models
        parts: list[str] = []
        if system_prompt:
            parts.append(f"<|im_start|>system\n{system_prompt}<|im_end|>")
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                continue
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)
