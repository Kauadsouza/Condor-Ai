"""Base do Condor Device Bridge; não inventa dispositivos conectados."""

from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SerialPort:
    port: str
    description: str
    hardware_id: str
    family: str


def _family(description: str, hardware_id: str) -> str:
    value = f"{description} {hardware_id}".lower()
    if "arduino" in value:
        return "Arduino"
    if any(term in value for term in ("cp210", "ch340", "ch341", "usb serial", "usb-serial")):
        return "Microcontrolador serial"
    if "bluetooth" in value or "bthenum" in value:
        return "Serial Bluetooth"
    return "Serial genérico"


def _serial_ports() -> list[SerialPort]:
    ports: list[SerialPort] = []
    try:
        from serial.tools import list_ports

        for item in list_ports.comports():
            ports.append(SerialPort(
                port=str(item.device),
                description=str(item.description or "Porta serial"),
                hardware_id=str(item.hwid or ""),
                family=_family(str(item.description or ""), str(item.hwid or "")),
            ))
    except ImportError:
        if os.name == "nt":
            try:
                import winreg

                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as key:
                    index = 0
                    while True:
                        try:
                            name, port, _ = winreg.EnumValue(key, index)
                        except OSError:
                            break
                        ports.append(SerialPort(str(port), name, name, _family(name, name)))
                        index += 1
            except OSError:
                pass
    return sorted({item.port: item for item in ports}.values(), key=lambda item: item.port)


class DeviceBridge:
    SUPPORTED_FAMILIES = (
        "Arduino Uno", "Arduino Nano", "Arduino Mega", "Arduino Leonardo",
        "ESP32", "ESP8266", "Raspberry Pi", "Raspberry Pi Pico", "STM32",
    )

    def __init__(self, memory, events, safety) -> None:
        self.memory = memory
        self.events = events
        self.safety = safety
        self._connections: dict[str, Any] = {}

    def status(self) -> dict[str, Any]:
        devices = self.memory.devices() if self.memory.unlocked else []
        return {
            "bridge": "online",
            "transport": {"serial": "ready", "bluetooth": "discovery_only", "wifi": "ready"},
            "supported_families": list(self.SUPPORTED_FAMILIES),
            "connected": [device for device in devices if device["status"] == "connected"],
            "known": devices,
        }

    async def scan(self) -> dict[str, Any]:
        ports = []
        for item in _serial_ports():
            data = asdict(item)
            data["device_id"] = self._device_id(item.port, item.hardware_id)
            data["connectable"] = True
            data["baud_rates"] = [9600, 57600, 115200]
            ports.append(data)
        await self.events.publish(
            "DEVICE_SCAN_COMPLETED", {"serial_ports": len(ports)}, source="device_bridge"
        )
        return {"serial_ports": ports, "count": len(ports), "executed_commands": 0}

    @staticmethod
    def _device_id(port: str, hardware_id: str) -> str:
        digest = hashlib.sha256(f"{port}|{hardware_id}".encode("utf-8")).hexdigest()[:16]
        return f"device_{digest}"

    async def connect(self, port: str, baud_rate: int, project_id: str | None) -> dict[str, Any]:
        if not self.memory.permission_allowed("serial"):
            raise PermissionError("permissao serial bloqueada no painel Sistema")
        selected = next((item for item in _serial_ports() if item.port == port), None)
        if selected is None:
            raise ValueError("porta serial não encontrada; faça uma nova busca")
        if baud_rate not in {9600, 19200, 38400, 57600, 115200, 230400}:
            raise ValueError("velocidade serial não permitida")
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("pyserial não está instalado") from exc
        device_id = self._device_id(selected.port, selected.hardware_id)
        previous = self._connections.pop(device_id, None)
        if previous is not None:
            await asyncio.to_thread(previous.close)
        try:
            connection = await asyncio.to_thread(
                serial.Serial, selected.port, baud_rate, timeout=0.25, write_timeout=0.25
            )
        except Exception as exc:
            raise RuntimeError(f"não foi possível abrir {selected.port}: {exc}") from exc
        self._connections[device_id] = connection
        device = self.memory.upsert_device({
            "id": device_id,
            "name": f"{selected.family} · {selected.port}",
            "type": selected.family,
            "connection": f"serial:{selected.port}@{baud_rate}",
            "status": "connected",
            "capabilities": ["serial"],
            "permissions": [],
        })
        session_id = self.memory.start_device_session(device_id, project_id)
        await self.events.publish(
            "DEVICE_CONNECTED",
            {"device_id": device_id, "name": device["name"], "port": selected.port,
             "baud_rate": baud_rate, "session_id": session_id},
            source="device_bridge", project_id=project_id,
        )
        return {"device": device, "session_id": session_id, "executed_commands": 0}

    async def disconnect(self, device_id: str, project_id: str | None) -> dict[str, Any]:
        connection = self._connections.pop(device_id, None)
        if connection is not None:
            await asyncio.to_thread(connection.close)
        self.memory.disconnect_device(device_id)
        await self.events.publish(
            "DEVICE_DISCONNECTED", {"device_id": device_id},
            source="device_bridge", project_id=project_id,
        )
        return {"device_id": device_id, "status": "disconnected"}

    def available_ports(self) -> set[str]:
        """Snapshot das portas físicas que existem neste exato momento."""
        return {item.port for item in _serial_ports()}

    async def release_port(self, port: str, project_id: str | None) -> bool:
        """Fecha uma sessão serial do Condor antes do bootloader usar a porta."""
        released = False
        for device_id, connection in list(self._connections.items()):
            if str(getattr(connection, "port", "")) != port:
                continue
            await self.disconnect(device_id, project_id)
            released = True
        return released

    async def close_all(self) -> None:
        for device_id in list(self._connections):
            try:
                await self.disconnect(device_id, None)
            except Exception:
                continue

    async def plan_command(self, device_id: str, command: dict[str, Any]) -> dict[str, Any]:
        decision = self.safety.evaluate(command)
        result = {
            "device_id": device_id,
            "command": command,
            "safety": {
                "allowed": decision.allowed,
                "level": decision.level,
                "requires_simulation": decision.requires_simulation,
                "requires_confirmation": decision.requires_confirmation,
                "reason": decision.reason,
            },
            "executed": False,
        }
        await self.events.publish("DEVICE_COMMAND_PLANNED", result, source="device_bridge")
        return result
