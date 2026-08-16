"""Análise de imagens pelo modelo multimodal local servido pelo Ollama."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx


class VisaoLocal:
    def __init__(self, config) -> None:
        self._cfg = config

    @property
    def modelo(self) -> str:
        return self._cfg.cerebro.modelo_visao_local.strip()

    @property
    def endpoint(self) -> str:
        parsed = urlsplit(self._cfg.cerebro.endpoint_local)
        host = parsed.hostname or "127.0.0.1"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{host}{port}/api/chat"

    async def analisar(self, imagem_b64: str, pedido: str = "") -> str:
        if not self.modelo:
            raise RuntimeError("modelo de visão local não configurado")
        prompt = pedido.strip() or (
            "Descreva com precisão o que aparece nesta captura de tela. "
            "Priorize textos legíveis, botões, estado da interface e possíveis erros. "
            "Não invente elementos que não estejam visíveis. Responda em português."
        )
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                self.endpoint,
                json={
                    "model": self.modelo,
                    "messages": [{"role": "user", "content": prompt, "images": [imagem_b64]}],
                    "stream": False,
                    "keep_alive": "2m",
                    "options": {"temperature": 0.1, "num_predict": 700},
                },
            )
            response.raise_for_status()
            data = response.json()
        texto = str((data.get("message") or {}).get("content") or "").strip()
        if not texto:
            raise RuntimeError("o modelo de visão local não devolveu descrição")
        return texto

    async def pronto(self) -> bool:
        if not self.modelo:
            return False
        parsed = urlsplit(self.endpoint)
        url = f"{parsed.scheme}://{parsed.netloc}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                data = (await client.get(url)).json()
            return any(str(item.get("name", "")) == self.modelo for item in data.get("models", []))
        except Exception:
            return False
