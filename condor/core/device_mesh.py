"""Identidade e capacidades mínimas para futuros clientes de celular/relógio."""

from __future__ import annotations

import re
from typing import Any


class DeviceMesh:
    SAFE_CAPABILITIES = frozenset({"status", "chat", "capture", "projects", "notifications"})
    TRUST_STATES = {"pending", "trusted", "revoked"}
    _PUBLIC_KEY = re.compile(r"^[A-Za-z0-9_+/:=.\-]{32,2048}$")

    def __init__(self, memory, events) -> None:
        self.memory = memory
        self.events = events

    async def register(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()[:160]
        kind = str(payload.get("kind") or "").strip().lower()[:40]
        public_key = str(payload.get("public_key") or "").strip()
        requested = payload.get("capabilities") or []
        if not name or kind not in {"phone", "watch", "tablet", "desktop"}:
            raise ValueError("nome ou tipo de dispositivo inválido")
        if not self._PUBLIC_KEY.fullmatch(public_key):
            raise ValueError("chave pública de dispositivo inválida")
        if not isinstance(requested, list):
            raise ValueError("capabilities precisa ser uma lista")
        capabilities = sorted({str(item) for item in requested} & self.SAFE_CAPABILITIES)
        rejected = sorted({str(item) for item in requested} - self.SAFE_CAPABILITIES)
        if rejected:
            raise ValueError("capacidade insegura recusada: " + ", ".join(rejected))
        device = self.memory.register_device_identity(name, kind, public_key, capabilities)
        await self.events.publish(
            "DEVICE_IDENTITY_REGISTERED",
            {"device_id": device["id"], "kind": kind, "capabilities": capabilities},
            source="device_mesh",
        )
        return device

    async def set_trust(self, device_id: str, state: str) -> dict[str, Any]:
        trust = state.strip().lower()
        if trust not in self.TRUST_STATES:
            raise ValueError("estado de confiança inválido")
        device = self.memory.set_device_trust(device_id, trust)
        if device is None:
            raise KeyError("dispositivo não encontrado")
        await self.events.publish(
            "DEVICE_TRUST_CHANGED", {"device_id": device_id, "trust_state": trust},
            source="device_mesh",
        )
        return device

    def status(self) -> dict[str, Any]:
        devices = self.memory.list_device_identities()
        return {
            "local_core_only": True,
            "raw_pc_control_exposed": False,
            "devices": devices,
            "allowed_capabilities": sorted(self.SAFE_CAPABILITIES),
        }
