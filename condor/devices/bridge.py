"""Base do Condor Device Bridge; não inventa dispositivos conectados."""

from __future__ import annotations

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
        ports = [asdict(item) for item in _serial_ports()]
        await self.events.publish(
            "DEVICE_SCAN_COMPLETED", {"serial_ports": len(ports)}, source="device_bridge"
        )
        return {"serial_ports": ports, "count": len(ports), "executed_commands": 0}

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
