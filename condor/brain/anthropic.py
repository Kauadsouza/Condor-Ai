"""Cliente mínimo da Messages API da Anthropic, sem expor a chave ao navegador."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any


class AnthropicAPIError(RuntimeError):
    def __init__(self, message: str, status: int = 0, request_id: str = "") -> None:
        super().__init__(message)
        self.status = int(status or 0)
        self.request_id = str(request_id or "")[:160]


class AnthropicMessagesClient:
    ENDPOINT = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"
    MAX_RESPONSE_BYTES = 10 * 1024 * 1024

    def __init__(self, api_key: str, timeout: float = 90.0) -> None:
        self._api_key = str(api_key or "").strip()
        self._timeout = float(timeout)

    async def create(self, **payload: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._create_sync, payload)

    def _create_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise AnthropicAPIError("Chave da Anthropic ausente", status=401)
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.ENDPOINT,
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": self.API_VERSION,
                "user-agent": "Condor-Local/2.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read(self.MAX_RESPONSE_BYTES + 1)
                if len(raw) > self.MAX_RESPONSE_BYTES:
                    raise AnthropicAPIError("Resposta da Anthropic excedeu 10 MB")
                request_id = response.headers.get("request-id", "")
        except urllib.error.HTTPError as exc:
            raw = exc.read(256_000)
            message = self._error_message(raw, f"Anthropic HTTP {exc.code}")
            raise AnthropicAPIError(
                message, status=exc.code, request_id=exc.headers.get("request-id", "")
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AnthropicAPIError(f"Falha de conexão com a Anthropic: {exc}") from exc
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AnthropicAPIError("Anthropic retornou JSON inválido", request_id=request_id) from exc
        if not isinstance(result, dict):
            raise AnthropicAPIError("Anthropic retornou resposta incompatível", request_id=request_id)
        result["_request_id"] = request_id
        return result

    @staticmethod
    def _error_message(raw: bytes, fallback: str) -> str:
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])[:500]
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
        return fallback
