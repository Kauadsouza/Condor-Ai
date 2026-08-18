"""Ponte privada entre câmeras domésticas e a visão local do Condor."""

from __future__ import annotations

import ipaddress
import json
import re
from typing import Any
from urllib.parse import urlsplit


class CameraBridge:
    PROTOCOLS = ("rtsp", "onvif", "http", "mjpeg")
    EVENTS = frozenset({"motion", "person_detected", "online", "offline"})

    def __init__(self, memory, events, vision) -> None:
        self.memory = memory
        self.events = events
        self.vision = vision

    @staticmethod
    def _validate_endpoint(endpoint: str) -> str:
        value = endpoint.strip()
        if len(value) > 1200 or any(char in value for char in "\r\n\x00"):
            raise ValueError("endereço da câmera inválido")
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"rtsp", "http", "https"} or not parsed.hostname:
            raise ValueError("use um endereço RTSP, HTTP ou HTTPS válido")
        host = parsed.hostname.lower()
        try:
            address = ipaddress.ip_address(host)
            private = address.is_private or address.is_loopback or address.is_link_local
        except ValueError:
            private = host == "localhost" or host.endswith(".local") or "." not in host
        if not private:
            raise ValueError("a Camera Bridge aceita somente câmeras da rede privada")
        return value

    def status(self) -> dict[str, Any]:
        sources = self.memory.camera_sources() if self.memory.unlocked else []
        alerts = self.memory.security_alerts(20) if self.memory.unlocked else []
        return {
            "bridge": "online",
            "processing": "local_only",
            "frame_storage": "disabled",
            "supported_protocols": list(self.PROTOCOLS),
            "sources": sources,
            "alerts": alerts,
            "vision_ready": False,
        }

    async def add_source(self, name: str, protocol: str, endpoint: str, zone: str) -> dict:
        if protocol not in self.PROTOCOLS:
            raise ValueError("protocolo de câmera não suportado")
        source = self.memory.create_camera_source(
            name.strip()[:120], protocol, self._validate_endpoint(endpoint), zone.strip()[:120]
        )
        await self.events.publish(
            "CAMERA_CONFIGURED", {"camera": source}, source="camera_bridge"
        )
        return source

    async def record_event(
        self, camera_id: str, event_type: str, confidence: float | None = None
    ) -> dict[str, Any]:
        camera = self.memory.camera_source_private(camera_id)
        if camera is None:
            raise KeyError("câmera não encontrada")
        if event_type not in self.EVENTS:
            raise ValueError("evento de câmera inválido")
        self.memory.update_camera_status(camera_id, "offline" if event_type == "offline" else "online")
        if event_type != "person_detected":
            await self.events.publish(
                f"CAMERA_{event_type.upper()}", {"camera_id": camera_id}, source="camera_bridge"
            )
            return {"alert": None, "event": event_type}
        zone = camera.get("zone") or camera["name"]
        summary = f"Possível pessoa detectada em {zone}. Confirme a imagem antes de agir."
        alert = self.memory.create_security_alert(camera_id, event_type, summary, confidence)
        await self.events.publish(
            "SECURITY_ALERT", {"alert": alert, "camera": camera["name"], "zone": zone},
            source="camera_bridge",
        )
        return {"alert": alert, "event": event_type}

    async def analyze_frame(self, camera_id: str, image_b64: str) -> dict[str, Any]:
        if not self.memory.camera_source_private(camera_id):
            raise KeyError("câmera não encontrada")
        if not image_b64 or len(image_b64) > 8_000_000:
            raise ValueError("quadro de câmera ausente ou grande demais")
        response = await self.vision.analisar(
            image_b64,
            "Analise apenas este quadro de segurança doméstica. Responda JSON puro no formato "
            '{"person_present":true|false,"confidence":0.0,"summary":"curto"}. '
            "Não identifique pessoas, não use reconhecimento facial e não invente detalhes.",
        )
        match = re.search(r"\{.*\}", response, flags=re.DOTALL)
        if not match:
            raise RuntimeError("a visão local não devolveu resultado estruturado")
        data = json.loads(match.group(0))
        present = data.get("person_present") is True
        confidence = max(0.0, min(1.0, float(data.get("confidence") or 0.0)))
        result = {"person_present": present, "confidence": confidence, "stored_frame": False}
        if present:
            result.update(await self.record_event(camera_id, "person_detected", confidence))
        return result
