"""Compilacao e gravacao Arduino reais, sempre por argumentos sem shell."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from condor.paths import state_path


COMMON_AVR_BOARDS = (
    {"name": "Arduino Uno", "fqbn": "arduino:avr:uno"},
    {"name": "Arduino Nano", "fqbn": "arduino:avr:nano"},
    {"name": "Arduino Mega 2560", "fqbn": "arduino:avr:mega"},
    {"name": "Arduino Leonardo", "fqbn": "arduino:avr:leonardo"},
    {"name": "Arduino Micro", "fqbn": "arduino:avr:micro"},
)

_FQBN = re.compile(
    r"^[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+"
    r"(?::[A-Za-z0-9_.=,-]+)?$"
)
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class ArduinoToolchain:
    """Fachada local do Arduino CLI; nunca considera upload como compilacao."""

    def __init__(self, executable: str | Path | None = None) -> None:
        self.executable = Path(executable).resolve() if executable else self._locate()
        self._lock = asyncio.Lock()

    @staticmethod
    def _locate() -> Path | None:
        configured = (os.getenv("CONDOR_ARDUINO_CLI") or "").strip()
        candidates = [
            Path(configured).expanduser() if configured else None,
            Path(found) if (found := shutil.which("arduino-cli")) else None,
            state_path("tools", "arduino-cli", "arduino-cli.exe" if os.name == "nt" else "arduino-cli"),
        ]
        return next((item.resolve() for item in candidates if item and item.is_file()), None)

    @property
    def installed(self) -> bool:
        return bool(self.executable and self.executable.is_file())

    @staticmethod
    def _clean_output(value: str, limit: int = 24_000) -> str:
        cleaned = _ANSI.sub("", str(value or "")).replace("\x00", "").strip()
        return cleaned[-limit:]

    def _invoke_sync(self, args: list[str], timeout: int) -> dict[str, Any]:
        if not self.installed:
            raise RuntimeError("Arduino CLI não está instalado")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            process = subprocess.run(
                [str(self.executable), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
                creationflags=creationflags,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Arduino CLI excedeu o limite de {timeout} segundos") from exc
        output = self._clean_output("\n".join(part for part in (process.stdout, process.stderr) if part))
        return {"ok": process.returncode == 0, "exit_code": process.returncode, "output": output}

    async def _invoke(self, args: list[str], timeout: int = 30) -> dict[str, Any]:
        return await asyncio.to_thread(self._invoke_sync, args, timeout)

    async def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "installed": self.installed,
            "version": "",
            "avr_ready": False,
            "common_boards": list(COMMON_AVR_BOARDS),
        }
        if not self.installed:
            return result
        version = await self._invoke(["version", "--format", "json"])
        if version["ok"]:
            try:
                payload = json.loads(version["output"])
                result["version"] = str(payload.get("VersionString") or payload.get("version") or "")
            except (json.JSONDecodeError, AttributeError):
                result["version"] = version["output"].splitlines()[0][:80]
        cores = await self._invoke(["core", "list", "--format", "json"])
        if cores["ok"]:
            try:
                payload = json.loads(cores["output"])
                installed = payload.get("platforms", payload) if isinstance(payload, dict) else payload
                result["avr_ready"] = any(
                    str(item.get("id") or item.get("ID") or "") == "arduino:avr"
                    for item in (installed or []) if isinstance(item, dict)
                )
            except (json.JSONDecodeError, AttributeError, TypeError):
                result["avr_ready"] = "arduino:avr" in cores["output"]
        return result

    async def detect_boards(self) -> dict[str, Any]:
        if not self.installed:
            return {"installed": False, "detected": [], "common_boards": list(COMMON_AVR_BOARDS)}
        response = await self._invoke(["board", "list", "--format", "json"])
        if not response["ok"]:
            return {
                "installed": True, "detected": [], "common_boards": list(COMMON_AVR_BOARDS),
                "error": response["output"] or "falha ao procurar placas",
            }
        try:
            payload = json.loads(response["output"])
        except json.JSONDecodeError as exc:
            raise RuntimeError("Arduino CLI retornou uma busca inválida") from exc
        detected: list[dict[str, Any]] = []
        for entry in payload.get("detected_ports", []) if isinstance(payload, dict) else []:
            port = entry.get("port") or {}
            boards = []
            for board in entry.get("matching_boards") or []:
                fqbn = str(board.get("fqbn") or "")
                if _FQBN.fullmatch(fqbn):
                    boards.append({"name": str(board.get("name") or fqbn)[:120], "fqbn": fqbn})
            detected.append({
                "port": str(port.get("address") or "")[:120],
                "protocol": str(port.get("protocol") or "")[:40],
                "label": str(port.get("label") or port.get("address") or "")[:120],
                "boards": boards,
            })
        return {"installed": True, "detected": detected, "common_boards": list(COMMON_AVR_BOARDS)}

    async def automatic_target(self) -> dict[str, str]:
        """Resolve um único alvo real; nunca escolhe por chute quando há ambiguidade."""
        detection = await self.detect_boards()
        candidates: list[dict[str, str]] = []
        for item in detection.get("detected") or []:
            port = str(item.get("port") or "")
            for board in item.get("boards") or []:
                if port and board.get("fqbn"):
                    candidates.append({
                        "port": port, "fqbn": str(board["fqbn"]),
                        "name": str(board.get("name") or board["fqbn"]),
                    })
        unique = {(item["port"], item["fqbn"]): item for item in candidates}
        candidates = list(unique.values())
        if not candidates:
            raise ValueError("nenhuma placa compatível foi identificada automaticamente")
        if len(candidates) != 1:
            names = ", ".join(f"{item['name']} em {item['port']}" for item in candidates[:4])
            raise ValueError(f"mais de um alvo de firmware foi detectado: {names}")
        return candidates[0]

    @staticmethod
    def _validate(content: str, port: str, fqbn: str, available_ports: set[str]) -> None:
        if not content.strip():
            raise ValueError("o editor está vazio")
        if len(content.encode("utf-8")) > 500_000:
            raise ValueError("código excede 500 KB")
        if not re.search(r"\bvoid\s+setup\s*\(", content) or not re.search(r"\bvoid\s+loop\s*\(", content):
            raise ValueError("o código Arduino precisa conter setup() e loop()")
        if port not in available_ports:
            raise ValueError("porta selecionada não está conectada; procure novamente")
        if not _FQBN.fullmatch(fqbn):
            raise ValueError("modelo de placa inválido")

    async def compile_and_upload(
        self, *, content: str, sketch_name: str, port: str, fqbn: str,
        available_ports: set[str],
    ) -> dict[str, Any]:
        if not self.installed:
            raise RuntimeError("Arduino CLI não está instalado")
        self._validate(content, port, fqbn, available_ports)
        safe_name = re.sub(r"[^A-Za-z0-9_]", "_", Path(sketch_name).stem)[:60].strip("_") or "condor_sketch"
        async with self._lock:
            with tempfile.TemporaryDirectory(prefix="condor-arduino-") as temporary:
                sketch_dir = Path(temporary) / safe_name
                build_dir = Path(temporary) / "build"
                sketch_dir.mkdir()
                build_dir.mkdir()
                (sketch_dir / f"{safe_name}.ino").write_text(content, encoding="utf-8", newline="\n")
                compile_result = await self._invoke([
                    "compile", "--fqbn", fqbn, "--build-path", str(build_dir),
                    "--no-color", str(sketch_dir),
                ], timeout=180)
                if not compile_result["ok"]:
                    return {"success": False, "phase": "compile", "compile": compile_result, "upload": None}
                upload_result = await self._invoke([
                    "upload", "--port", port, "--fqbn", fqbn, "--build-path", str(build_dir),
                    "--verify", "--no-color", str(sketch_dir),
                ], timeout=180)
                return {
                    "success": bool(upload_result["ok"]),
                    "phase": "complete" if upload_result["ok"] else "upload",
                    "compile": compile_result,
                    "upload": upload_result,
                }
