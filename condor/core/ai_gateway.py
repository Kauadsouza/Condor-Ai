"""Ponto único de entrada para qualquer provedor de IA do Condor."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from condor.brain.identity import contrato_runtime


class MockAIProvider:
    """Fallback explícito: nunca finge que uma IA externa está conectada."""

    name = "mock"

    @property
    def pronto(self) -> bool:
        return True

    async def stream(self, prompt: str, context: dict[str, Any]) -> AsyncIterator[str]:
        del prompt, context
        yield "O AI Gateway está pronto, mas nenhum provedor de IA foi conectado."


class AIGateway:
    """Fachada compatível com o cérebro existente e observável pelo Core."""

    def __init__(self, provider, context, events) -> None:
        self._provider = provider
        self._context = context
        self._events = events

    def __getattr__(self, name: str):
        return getattr(self._provider, name)

    @property
    def provider_name(self) -> str:
        return str(getattr(self._provider, "provedor", "mock"))

    def status(self) -> dict[str, Any]:
        ready = getattr(self._provider, "pronto", False)
        if callable(ready):
            ready = ready()
        result = {
            "provider": self.provider_name,
            "model": str(getattr(self._provider, "modelo_ativo", "não configurado")),
            "ready": bool(ready),
            "gateway": "online",
            "context_contract": "v1",
            "identity_contract": contrato_runtime(),
            "streaming": "transport_ready",
            "orchestrator": (
                "ready" if getattr(self._provider, "_orchestrator", None) is not None
                else "not_connected"
            ),
        }
        connector_state = getattr(self._provider, "connector_state", None)
        if isinstance(connector_state, dict):
            result["connector"] = connector_state
            if connector_state.get("verified") is False:
                result["ready"] = False
        return result

    async def responder(self, *args, **kwargs):
        history = args[0] if args else kwargs.get("historico", [])
        if history and isinstance(history[-1], dict) and history[-1].get("role") == "user":
            self._context.update(recent_intent=str(history[-1].get("content") or "")[:500])
        structured_context = json.dumps(self._context.for_ai(), ensure_ascii=False, separators=(",", ":"))
        existing_reference = str(kwargs.get("memoria_relevante") or "").strip()
        kwargs["memoria_relevante"] = (
            f"{existing_reference}\n\n" if existing_reference else ""
        ) + "ESTADO ATUAL DA INTERFACE (JSON ESTRUTURADO):\n" + structured_context
        await self._events.publish(
            "AI_REQUEST", {"context": self._context.for_ai()}, source="ai_gateway",
            project_id=self._context.snapshot().get("project_id"),
        )
        try:
            result = await self._provider.responder(*args, **kwargs)
        except Exception as exc:
            await self._events.publish(
                "AI_ERROR", {"error": type(exc).__name__}, source="ai_gateway",
                project_id=self._context.snapshot().get("project_id"),
            )
            raise
        await self._events.publish(
            "AI_RESPONSE", {"completed": True}, source="ai_gateway",
            project_id=self._context.snapshot().get("project_id"),
        )
        return result

    async def completar(self, *args, **kwargs):
        return await self._provider.completar(*args, **kwargs)

    async def embedding(self, *args, **kwargs):
        return await self._provider.embedding(*args, **kwargs)
