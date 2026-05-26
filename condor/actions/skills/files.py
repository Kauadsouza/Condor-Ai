"""
Skills de operações em arquivos.
Todas as operações de escrita/deleção exigem confirmação se fora da whitelist.
"""

from __future__ import annotations

import logging
from pathlib import Path

from condor.actions.base import SkillRegistry, make_skill
from condor.config import ActionsConfig

log = logging.getLogger("condor.actions.skills.files")


def _safe_path(path_str: str, whitelist: list[str]) -> Path:
    p = Path(path_str).resolve()
    for allowed in whitelist:
        if str(p).startswith(str(Path(allowed).resolve())):
            return p
    raise PermissionError(
        f"Caminho '{p}' fora da whitelist. Adicione em config.actions.whitelist_paths."
    )


def register(registry: SkillRegistry, config: ActionsConfig) -> None:
    wl = config.whitelist_paths

    def file_read(path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"Arquivo não encontrado: {path}"
        content = p.read_text(encoding="utf-8", errors="replace")
        return content[:4000]  # limite para não explodir o contexto

    def file_create(path: str, content: str = "") -> str:
        p = _safe_path(path, wl)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Arquivo criado: {p}"

    def file_delete(path: str) -> str:
        p = _safe_path(path, wl)
        if not p.exists():
            return f"Arquivo não encontrado: {path}"
        p.unlink()
        return f"Arquivo removido: {p}"

    def file_list(path: str = ".") -> str:
        p = Path(path)
        if not p.is_dir():
            return f"Não é um diretório: {path}"
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        lines = [f"{'DIR ' if i.is_dir() else 'FILE'} {i.name}" for i in items[:50]]
        return "\n".join(lines)

    registry.register(make_skill(
        name="file_read",
        description="Lê conteúdo de um arquivo de texto",
        handler=file_read,
        params_schema={"path": "string"},
        resources=["filesystem"],
    ))
    registry.register(make_skill(
        name="file_create",
        description="Cria ou sobrescreve um arquivo com conteúdo",
        handler=file_create,
        params_schema={"path": "string", "content": "string"},
        resources=["filesystem"],
    ))
    registry.register(make_skill(
        name="file_delete",
        description="Remove um arquivo do sistema",
        handler=file_delete,
        params_schema={"path": "string"},
        resources=["filesystem"],
        requires_confirm=True,
    ))
    registry.register(make_skill(
        name="file_list",
        description="Lista arquivos de um diretório",
        handler=file_list,
        params_schema={"path": "string"},
        resources=["filesystem"],
    ))
