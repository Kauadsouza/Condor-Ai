"""Ferramentas internas que transformam a IA no operador do Condor Core.

O modelo nunca recebe objetos Python, banco ou conexoes diretamente. Ele chama
operacoes pequenas e tipadas; esta camada valida, persiste, atualiza o contexto
e publica eventos reais antes de devolver qualquer resultado.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Awaitable, Callable

from condor.development import detect_language


class CondorOrchestrator:
    """Une projetos, programacao, laboratorio, memoria e dispositivos."""

    MEMORY_CATEGORIES = {"pessoal", "trabalho", "preferencia", "rotina", "projeto", "tecnico"}
    EXPERIMENT_STATUSES = {"proposed", "testing", "done"}
    TOOL_CAPABILITIES = {
        "condor_abrir_projeto": "ai_projects",
        "condor_selecionar_regiao": "ai_projects",
        "condor_criar_rascunho": "ai_projects",
        "condor_salvar_codigo": "ai_programming",
        "condor_historico_codigo": "ai_programming",
        "condor_restaurar_codigo": "ai_programming",
        "condor_criar_experimento": "ai_laboratory",
        "condor_atualizar_experimento": "ai_laboratory",
        "condor_registrar_memoria": "ai_memory",
        "condor_buscar_dispositivos": "ai_devices",
        "condor_conectar_dispositivo": "ai_devices",
        "condor_desconectar_dispositivo": "ai_devices",
    }

    def __init__(self, memory, context, events, projects, devices) -> None:
        self.memory = memory
        self.context = context
        self.events = events
        self.projects = projects
        self.devices = devices
        self._handlers: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {
            "condor_estado": self._state,
            "condor_abrir_projeto": self._open_project,
            "condor_selecionar_regiao": self._select_region,
            "condor_criar_rascunho": self._create_draft,
            "condor_salvar_codigo": self._save_code,
            "condor_historico_codigo": self._code_history,
            "condor_restaurar_codigo": self._restore_code,
            "condor_criar_experimento": self._create_experiment,
            "condor_atualizar_experimento": self._update_experiment,
            "condor_registrar_memoria": self._remember,
            "condor_buscar_dispositivos": self._scan_devices,
            "condor_conectar_dispositivo": self._connect_device,
            "condor_desconectar_dispositivo": self._disconnect_device,
        }

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.memory.unlocked:
            return {"ok": False, "saida": "O cofre do Condor esta bloqueado."}
        handler = self._handlers.get(name)
        if handler is None:
            return {"ok": False, "saida": f"Operacao interna desconhecida: {name}"}
        capability = self.TOOL_CAPABILITIES.get(name)
        if capability and not self.memory.permission_allowed(capability):
            return {
                "ok": False,
                "saida": f"Permissao {capability} bloqueada no painel Sistema.",
            }
        try:
            data = await handler(arguments)
            return {"ok": True, "saida": json.dumps(data, ensure_ascii=False, separators=(",", ":"))[:8000]}
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            return {"ok": False, "saida": str(exc)}

    @staticmethod
    def _text(arguments: dict[str, Any], key: str, limit: int, required: bool = True) -> str:
        value = str(arguments.get(key) or "").strip()
        if required and not value:
            raise ValueError(f"{key} obrigatorio")
        if len(value) > limit:
            raise ValueError(f"{key} excede {limit} caracteres")
        return value

    def _project(self, project_id: str) -> dict[str, Any]:
        project = self.memory.get_project(project_id)
        if project is None:
            raise KeyError("projeto nao encontrado")
        return project

    async def _state(self, _: dict[str, Any]) -> dict[str, Any]:
        context = self.context.snapshot()
        project_id = context.get("project_id") or "condor-x"
        project = self.memory.get_project(project_id)
        code = self.memory.code_buffer(project_id)
        experiments = self.memory.lab_experiments(project_id)
        return {
            "context": context,
            "project": ({"id": project["id"], "name": project["name"]} if project else None),
            "code": ({key: code.get(key) for key in ("name", "language", "revision", "updated")} if code else None),
            "experiments": {
                status: sum(1 for item in experiments if item["status"] == status)
                for status in sorted(self.EXPERIMENT_STATUSES)
            },
            "devices": self.devices.status(),
            "permissions": self.memory.permissions(),
        }

    async def _open_project(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.projects.open(self._text(arguments, "project_id", 80))

    async def _select_region(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_id = self._text(arguments, "project_id", 80)
        region_id = self._text(arguments, "region_id", 80)
        self._project(project_id)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", region_id):
            raise ValueError("region_id invalido")
        return {"context": await self.projects.select_region(project_id, region_id)}

    async def _create_draft(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_id = self._text(arguments, "project_id", 80)
        region_id = self._text(arguments, "region_id", 80)
        payload = {
            "name": self._text(arguments, "name", 180),
            "type": self._text(arguments, "type", 50, False) or "component",
            "notes": self._text(arguments, "notes", 1200, False),
        }
        self._project(project_id)
        part = await self.projects.create_draft(project_id, region_id, payload)
        return {"part": {key: part.get(key) for key in ("id", "project_id", "region", "name", "type", "status")}}

    async def _save_code(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_id = self._text(arguments, "project_id", 80)
        project = self._project(project_id)
        content = str(arguments.get("content") or "")
        if len(content.encode("utf-8")) > 500_000:
            raise ValueError("codigo excede 500 KB")
        detected = detect_language(content)
        name = self._text(arguments, "name", 120, False) or f"programa{detected['extension']}"
        if not name.lower().endswith(detected["extension"]):
            stem = re.sub(r"\.[a-z0-9]+$", "", name, flags=re.IGNORECASE)[:100] or "programa"
            name = f"{stem}{detected['extension']}"
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        previous = self.memory.code_buffer(project_id)
        buffer = self.memory.save_code_buffer(
            project_id, name, detected["language"], content, checksum, source="condor-ai"
        )
        context = self.context.update(
            project_id=project_id,
            project_name=project["name"],
            mode="programming",
            current_file=name,
            code_language=detected["language"],
            code_revision=int(buffer.get("revision") or 1),
        )
        if not previous or previous.get("checksum") != checksum:
            await self.events.publish(
                "CODE_BUFFER_UPDATED",
                {"file": name, "language": detected["language"], "revision": buffer["revision"], "source": "condor-ai"},
                source="condor_orchestrator",
                project_id=project_id,
            )
        return {
            "buffer": {key: buffer.get(key) for key in ("name", "language", "revision", "checksum", "updated")},
            "detected": detected,
            "context": context,
        }

    async def _code_history(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_id = self._text(arguments, "project_id", 80)
        self._project(project_id)
        return {"project_id": project_id, "versions": self.memory.code_versions(project_id, 30)}

    async def _restore_code(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_id = self._text(arguments, "project_id", 80)
        revision = int(arguments.get("revision") or 0)
        if revision < 1:
            raise ValueError("revision invalida")
        self._project(project_id)
        buffer = self.memory.restore_code_version(project_id, revision, source="condor-ai-restore")
        self.context.update(
            project_id=project_id,
            mode="programming",
            current_file=buffer["name"],
            code_language=buffer["language"],
            code_revision=int(buffer["revision"]),
        )
        await self.events.publish(
            "CODE_BUFFER_RESTORED",
            {"from_revision": revision, "revision": buffer["revision"]},
            source="condor_orchestrator",
            project_id=project_id,
        )
        return {"buffer": {key: buffer.get(key) for key in ("name", "language", "revision", "checksum", "updated")}}

    async def _create_experiment(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_id = self._text(arguments, "project_id", 80)
        self._project(project_id)
        experiment = self.memory.create_lab_experiment(
            project_id,
            self._text(arguments, "title", 160),
            self._text(arguments, "objective", 1200, False),
            "condor",
        )
        context = self.context.update(project_id=project_id, experiment_id=experiment["id"], mode="laboratory")
        await self.events.publish(
            "EXPERIMENT_CREATED", {"experiment": experiment}, source="condor_orchestrator", project_id=project_id
        )
        return {"experiment": experiment, "context": context}

    async def _update_experiment(self, arguments: dict[str, Any]) -> dict[str, Any]:
        experiment_id = self._text(arguments, "experiment_id", 80)
        status = self._text(arguments, "status", 20).lower()
        if status not in self.EXPERIMENT_STATUSES:
            raise ValueError("status precisa ser proposed, testing ou done")
        experiment = self.memory.update_lab_experiment(experiment_id, status)
        if experiment is None:
            raise KeyError("experimento nao encontrado")
        self.context.update(project_id=experiment.get("project_id"), experiment_id=experiment_id, mode="laboratory")
        await self.events.publish(
            "EXPERIMENT_UPDATED", {"experiment": experiment}, source="condor_orchestrator", project_id=experiment.get("project_id")
        )
        return {"experiment": experiment}

    async def _remember(self, arguments: dict[str, Any]) -> dict[str, Any]:
        category = self._text(arguments, "category", 30).lower()
        if category not in self.MEMORY_CATEGORIES:
            raise ValueError("categoria de memoria invalida")
        key = self._text(arguments, "key", 80)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_]{1,79}", key):
            raise ValueError("key precisa estar em snake_case")
        value = self._text(arguments, "value", 500)
        if re.search(r"\b(password|senha|api[_ -]?key|token|segredo)\b", value, flags=re.IGNORECASE) or re.search(r"\bsk-[A-Za-z0-9_-]{12,}\b", value):
            raise ValueError("segredos pertencem ao cofre, nunca a memoria conversacional")
        confidence = float(arguments.get("confidence") or 0.8)
        fact_id = self.memory.salvar_fato(
            category, key, value, max(0.1, min(1.0, confidence)), "condor-ai"
        )
        await self.events.publish(
            "MEMORY_FACT_SAVED", {"fact_id": fact_id, "category": category, "key": key}, source="condor_orchestrator"
        )
        return {"fact_id": fact_id, "category": category, "key": key, "encrypted": True}

    async def _scan_devices(self, _: dict[str, Any]) -> dict[str, Any]:
        result = await self.devices.scan()
        return {
            "count": result["count"],
            "serial_ports": [
                {key: item.get(key) for key in ("port", "description", "family", "connectable", "baud_rates")}
                for item in result["serial_ports"]
            ],
            "executed_commands": result["executed_commands"],
        }

    async def _connect_device(self, arguments: dict[str, Any]) -> dict[str, Any]:
        port = self._text(arguments, "port", 80)
        baud_rate = int(arguments.get("baud_rate") or 115200)
        project_id = self._text(arguments, "project_id", 80, False) or self.context.snapshot().get("project_id") or "condor-x"
        self._project(project_id)
        result = await self.devices.connect(port, baud_rate, project_id)
        device = result["device"]
        context = self.context.update(
            project_id=project_id,
            device_id=device["id"],
            device_name=device["name"],
            connection_state="connected",
            mode="programming",
        )
        return {**result, "context": context}

    async def _disconnect_device(self, arguments: dict[str, Any]) -> dict[str, Any]:
        device_id = self._text(arguments, "device_id", 80)
        result = await self.devices.disconnect(device_id, self.context.snapshot().get("project_id"))
        current = self.context.snapshot()
        if current.get("device_id") == device_id:
            self.context.update(device_id=None, device_name=None, connection_state="disconnected")
        return {**result, "context": self.context.snapshot()}
