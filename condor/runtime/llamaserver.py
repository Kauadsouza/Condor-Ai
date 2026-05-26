"""
Engine usando llama-server.exe (binário oficial do llama.cpp).
Inicia em background para não bloquear o boot do FastAPI.
A UI recebe 'engine.ready' quando o modelo terminar de carregar.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import AsyncIterator

import aiohttp

from condor.config import ModelConfig
from condor.runtime.base import EngineHealth

log = logging.getLogger("condor.runtime.llamaserver")

LLAMA_PORT = 8081
LLAMA_URL  = f"http://127.0.0.1:{LLAMA_PORT}"


class LlamaServerEngine:
    """
    Inicia llama-server.exe como subprocesso em background.
    O FastAPI sobe imediatamente; o modelo carrega em paralelo.
    """

    def __init__(self, config: ModelConfig, bin_dir: Path) -> None:
        self._config  = config
        self._bin_dir = bin_dir
        self._model   = Path(config.path)
        self._proc:   subprocess.Popen | None = None
        self._ready   = False
        self._loading = False
        self._session: aiohttp.ClientSession | None = None
        # Callback chamado quando o modelo terminar de carregar
        self.on_ready: "asyncio.Task | None" = None

    def start_background(self) -> None:
        """Inicia o processo do servidor. Não bloqueia."""
        exe = self._bin_dir / "llama-server.exe"
        if not exe.exists() or not self._model.exists():
            log.error("llama-server.exe ou modelo não encontrado.")
            return

        self._loading = True
        log.info("Iniciando llama-server.exe em background...")
        self._proc = subprocess.Popen(
            [
                str(exe),
                "--model",      str(self._model),
                "--port",       str(LLAMA_PORT),
                "--host",       "127.0.0.1",
                "--ctx-size",   str(self._config.n_ctx),
                "--temp",       str(self._config.temperature),
                "--top-p",      str(self._config.top_p),
                "--top-k",      str(self._config.top_k),
                "-ngl",         str(self._config.n_gpu_layers),
                "--threads",    "6",       # threads CPU para inferência mais rápida
                "--batch-size", "512",     # processa 512 tokens por batch
                "--ubatch-size","256",     # microbatch — reduz latência dos primeiros tokens
                "--cont-batching",         # reutiliza slots sem parar o servidor
                "--log-disable",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,  # sem janela visível no Windows
        )

    async def wait_ready_async(self, on_ready_cb=None, timeout: int = 120) -> bool:
        """
        Aguarda o servidor ficar pronto em background.
        Chama on_ready_cb() quando pronto (para notificar a UI via WebSocket).
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            # Processo morreu?
            if self._proc and self._proc.poll() is not None:
                log.error("llama-server.exe encerrou inesperadamente (exit %d).", self._proc.returncode)
                self._loading = False
                return False

            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        f"{LLAMA_URL}/health",
                        timeout=aiohttp.ClientTimeout(total=2),
                    ) as r:
                        if r.status == 200:
                            self._ready   = True
                            self._loading = False
                            self._session = aiohttp.ClientSession()
                            log.info("llama-server pronto.")
                            if on_ready_cb:
                                await on_ready_cb()
                            return True
            except Exception:
                pass
            await asyncio.sleep(1)

        self._loading = False
        log.error("llama-server não ficou pronto em %ds.", timeout)
        return False

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def is_loading(self) -> bool:
        return self._loading

    async def generate(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        if not self._ready:
            yield "⏳ Modelo ainda carregando... aguarde alguns segundos e tente de novo."
            return

        full_msgs: list[dict] = []
        if system_prompt:
            full_msgs.append({"role": "system", "content": system_prompt})
        for m in messages:
            if m.get("role") != "system":
                full_msgs.append(m)

        payload = {
            "model":       "local",
            "messages":    full_msgs,
            "max_tokens":  self._config.max_tokens,
            "temperature": self._config.temperature,
            "stream":      True,
        }

        try:
            async with self._session.post(
                f"{LLAMA_URL}/v1/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        token = chunk["choices"][0]["delta"].get("content", "")
                        if token:
                            yield token
                    except (json.JSONDecodeError, KeyError):
                        pass
        except Exception as exc:
            log.error("Erro na geração: %s", exc)
            yield f"Erro: {exc}"

    async def embed(self, text: str) -> list[float]:
        return [0.0] * 384

    def get_health(self) -> EngineHealth:
        alive = self._proc is not None and self._proc.poll() is None
        if self._loading:
            status = "Carregando modelo..."
        elif self._ready and alive:
            status = None
        else:
            status = "Processo encerrado" if not alive else "Não iniciado"

        return EngineHealth(
            available=True,
            model_loaded=self._ready and alive,
            model_name=self._model.name,
            backend="llama-server.exe",
            error=status,
        )

    def shutdown(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            log.info("llama-server encerrado.")
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())
