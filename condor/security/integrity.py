"""Manifesto assinado para detectar alteracoes no codigo do Condor."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from condor.paths import CODE_ROOT


class CodeIntegrity:
    EXTENSIONS = {".py", ".pyw", ".html", ".js", ".css", ".toml"}

    def __init__(self, manifest_path: Path, identity, root: Path = CODE_ROOT) -> None:
        self.path = manifest_path
        self.identity = identity
        self.root = root.resolve()

    def _files(self) -> list[Path]:
        candidates: list[Path] = []
        package = self.root / "condor"
        if package.exists():
            candidates.extend(package.rglob("*"))
        for name in ("condor_app.pyw", "condor_launcher.pyw", "condor_window.pyw", "pyproject.toml"):
            candidate = self.root / name
            if candidate.exists():
                candidates.append(candidate)
        return sorted({
            path.resolve() for path in candidates
            if path.is_file()
            and path.suffix.lower() in self.EXTENSIONS
            and "__pycache__" not in path.parts
        })

    def snapshot(self) -> dict[str, str]:
        return {
            path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self._files()
        }

    @staticmethod
    def _canonical(files: dict[str, str]) -> bytes:
        return json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def refresh(self) -> int:
        files = self.snapshot()
        payload = {
            "version": 1,
            "device_id": self.identity.device_id,
            "files": files,
            "signature": self.identity.sign(self._canonical(files)),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)
        try:
            self.path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        return len(files)

    def verify(self) -> tuple[bool, str, int]:
        if not self.path.exists():
            return False, "manifesto de integridade ausente", 0
        try:
            payload = json.loads(self.path.read_text("utf-8"))
            expected = payload["files"]
            signature_ok = self.identity.verify(self._canonical(expected), payload["signature"])
            if not signature_ok or payload.get("device_id") != self.identity.device_id:
                return False, "assinatura do manifesto invalida", len(expected)
            current = self.snapshot()
            if current != expected:
                changed = sorted(set(current) ^ set(expected))
                changed.extend(
                    name for name in set(current) & set(expected)
                    if current[name] != expected[name]
                )
                return False, "codigo alterado: " + ", ".join(sorted(set(changed))[:8]), len(expected)
            return True, "codigo confere com o manifesto assinado", len(expected)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return False, f"manifesto invalido: {type(exc).__name__}", 0
