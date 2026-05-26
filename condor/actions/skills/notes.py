"""
Skill de anotações rápidas — salva notas no banco do Condor.
"""

from __future__ import annotations

import time
from pathlib import Path

from condor.actions.base import SkillRegistry, make_skill


_NOTES_FILE = Path("data/notes.md")


def note_save(content: str, title: str = "") -> str:
    _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M")
    heading = f"## {title or ts}\n" if title else f"## {ts}\n"
    with open(_NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{heading}{content}\n")
    return f"Nota salva: {title or ts}"


def notes_list() -> str:
    if not _NOTES_FILE.exists():
        return "Nenhuma nota ainda."
    text = _NOTES_FILE.read_text(encoding="utf-8")
    return text[-3000:] if len(text) > 3000 else text


def register(registry: SkillRegistry) -> None:
    registry.register(make_skill(
        name="note_save",
        description="Salva uma nota ou lembrete rápido",
        handler=note_save,
        params_schema={"content": "string", "title": "string"},
        resources=["filesystem"],
    ))
    registry.register(make_skill(
        name="notes_list",
        description="Lista todas as notas salvas",
        handler=notes_list,
        params_schema={},
        resources=["filesystem"],
    ))
