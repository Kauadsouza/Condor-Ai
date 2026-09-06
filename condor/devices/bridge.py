"""Base do Condor Device Bridge; não inventa dispositivos conectados."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import time
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


def _windows_pnp_devices() -> list[dict[str, Any]]:
    """Inventário somente leitura dos dispositivos presentes no Windows."""
    if os.name != "nt":
        return []
    script = (
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object {$_.Status -eq 'OK'} | "
        "Select-Object -First 240 Class,FriendlyName,InstanceId,Status | "
        "ConvertTo-Json -Compress"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=8, check=False, shell=False, creationflags=creationflags,
        )
        if process.returncode != 0 or not process.stdout.strip():
            return []
        payload = json.loads(process.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    entries = payload if isinstance(payload, list) else [payload]
    result: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        instance_id = str(entry.get("InstanceId") or "")[:300]
        name = str(entry.get("FriendlyName") or entry.get("Class") or "Dispositivo")[:160]
        device_class = str(entry.get("Class") or "Other")[:80]
        if not instance_id or not name:
            continue
        normalized = device_class.lower()
        instance_upper = instance_id.upper()
        physical_markers = ("USB\\", "HID\\", "BTH", "FTDIBUS\\", "SWD\\MMDEVAPI")
        if not instance_upper.startswith(physical_markers):
            continue
        capabilities = ["presence"]
        kind = "device"
        if normalized in {"ports", "modem"}:
            capabilities.append("serial")
            kind = "serial"
        elif normalized in {"hidclass", "keyboard", "mouse"}:
            capabilities.append("input")
            kind = "input"
        elif normalized in {"camera", "image"}:
            capabilities.append("video")
            kind = "camera"
        elif normalized in {"diskdrive", "volume", "wceusbs"}:
            capabilities.append("storage")
            kind = "storage"
        elif normalized in {"audioendpoint", "media", "sound"}:
            capabilities.append("audio")
            kind = "audio"
        elif normalized in {"net", "network"}:
            capabilities.append("network")
            kind = "network"
        elif normalized in {"bluetooth"}:
            capabilities.append("bluetooth")
            kind = "bluetooth"
        elif "usb" in normalized or instance_id.upper().startswith("USB"):
            capabilities.append("usb")
            kind = "usb"
        digest = hashlib.sha256(instance_id.encode("utf-8")).hexdigest()[:16]
        result.append({
            "device_id": f"pnp_{digest}", "name": name, "kind": kind,
            "connection": "pnp", "hardware_id": instance_id,
            "capabilities": capabilities, "commandable": False, "status": "present",
        })
    return result


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
        self._scan_cache: dict[str, Any] | None = None
        self._scan_cache_at = 0.0

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
        if self._scan_cache and time.monotonic() - self._scan_cache_at < 2.0:
            return self._scan_cache
        serial_items, pnp_items = await asyncio.gather(
            asyncio.to_thread(_serial_ports), asyncio.to_thread(_windows_pnp_devices)
        )
        ports = []
        devices: list[dict[str, Any]] = []
        serial_hardware = set()
        for item in serial_items:
            data = asdict(item)
            data["device_id"] = self._device_id(item.port, item.hardware_id)
            data["connectable"] = True
            data["baud_rates"] = [9600, 57600, 115200]
            ports.append(data)
            serial_hardware.add(item.hardware_id.lower())
            devices.append({
                "device_id": data["device_id"], "name": item.description,
                "kind": "serial", "family": item.family,
                "connection": f"serial:{item.port}", "port": item.port,
                "hardware_id": item.hardware_id, "capabilities": ["presence", "serial_text"],
                "commandable": True, "status": "present",
            })
        for item in pnp_items:
            hardware_id = str(item.get("hardware_id") or "").lower()
            if hardware_id and any(token and token in hardware_id for token in serial_hardware):
                continue
            devices.append(item)
        devices = list({item["device_id"]: item for item in devices}.values())
        await self.events.publish(
            "DEVICE_SCAN_COMPLETED", {"serial_ports": len(ports), "devices": len(devices)}, source="device_bridge"
        )
        result = {
            "serial_ports": ports, "devices": devices, "count": len(devices),
            "commandable_count": sum(1 for item in devices if item.get("commandable")),
            "executed_commands": 0,
        }
        self._scan_cache = result
        self._scan_cache_at = time.monotonic()
        return result

    @staticmethod
    def _device_id(port: str, hardware_id: str) -> str:
        digest = hashlib.sha256(f"{port}|{hardware_id}".encode("utf-8")).hexdigest()[:16]
        return f"device_{digest}"

    async def connect(self, port: str, baud_rate: int, project_id: str | None) -> dict[str, Any]:
        if not self.memory.permission_available("serial"):
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

    async def send_text(
        self, device_id: str, text: str, project_id: str | None, *, confirmed: bool = False,
    ) -> dict[str, Any]:
        """Envia texto somente a um adaptador serial inequivocamente identificado."""
        if not self.memory.permission_allowed("serial"):
            raise PermissionError("permissao serial bloqueada no painel Sistema")
        payload = str(text or "").strip()
        if not payload:
            raise ValueError("comando vazio")
        if "\x00" in payload or len(payload.encode("utf-8")) > 4096:
            raise ValueError("comando serial inválido ou maior que 4 KB")
        scan = await self.scan()
        candidates = [item for item in scan["devices"] if item.get("commandable")]
        if device_id:
            candidates = [item for item in candidates if item["device_id"] == device_id]
        if not candidates:
            raise ValueError("nenhum dispositivo com adaptador serial de comandos foi encontrado")
        if len(candidates) != 1:
            raise ValueError("mais de um dispositivo aceita comandos; escolha o dispositivo pelo nome")
        target = candidates[0]
        command = {"command": payload, "adapter": "serial_text", "risk_level": 2}
        decision = self.safety.evaluate(command)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        if decision.requires_confirmation and not confirmed:
            return {
                "executed": False, "requires_confirmation": True,
                "device": target, "safety": asdict(decision),
            }
        connection = self._connections.get(target["device_id"])
        if connection is None:
            await self.connect(str(target["port"]), 115200, project_id)
            connection = self._connections.get(target["device_id"])
        elif not self.memory.permission_allowed("serial"):
            raise PermissionError("permissao serial bloqueada no painel Sistema")
        if connection is None:
            raise RuntimeError("a conexão serial não foi estabelecida")
        encoded = (payload + "\n").encode("utf-8")
        written = await asyncio.to_thread(connection.write, encoded)
        await asyncio.to_thread(connection.flush)
        await self.events.publish(
            "DEVICE_COMMAND_SENT",
            {"device_id": target["device_id"], "adapter": "serial_text", "bytes": int(written)},
            source="device_bridge", project_id=project_id,
        )
        return {
            "executed": True, "requires_confirmation": False, "device": target,
            "bytes": int(written), "adapter": "serial_text",
        }

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
