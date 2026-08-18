"""Manifesto assinado para detectar alteracoes no codigo do Condor."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from pathlib import Path

from condor.paths import CODE_ROOT


class CodeIntegrity:
    EXTENSIONS = {".py", ".pyw", ".html", ".js", ".css", ".toml"}
    # Mesmo com a assinatura conferindo, refaz o hash completo de tempos em
    # tempos: pega adulteracao que tenha restaurado mtime e tamanho.
    REVALIDACAO_SEGUNDOS = 60.0

    def __init__(self, manifest_path: Path, identity, root: Path = CODE_ROOT) -> None:
        self.path = manifest_path
        self.identity = identity
        self.root = root.resolve()
        self._cache: tuple[bool, str, int] | None = None
        self._cache_marca: tuple | None = None
        self._cache_ate = 0.0

    def _marca_dos_arquivos(self) -> tuple:
        """Impressao barata do estado do codigo: caminho, mtime e tamanho.

        Custa um stat por arquivo (~1 ms) contra ~40 ms de SHA-256 em tudo. A
        interface consulta /api/seguranca/estado em laco, e sem isto cada
        consulta relia e re-hasheava o codigo inteiro.
        """
        marcas = []
        for caminho in self._files():
            try:
                info = caminho.stat()
                marcas.append((caminho.as_posix(), info.st_mtime_ns, info.st_size))
            except OSError:
                marcas.append((caminho.as_posix(), -1, -1))
        try:
            manifesto = self.path.stat()
            marcas.append(("::manifesto", manifesto.st_mtime_ns, manifesto.st_size))
        except OSError:
            marcas.append(("::manifesto", -1, -1))
        return tuple(marcas)

    def _files(self) -> list[Path]:
        candidates: list[Path] = []
        package = self.root / "condor"
        if package.exists():
            candidates.extend(package.rglob("*"))
        for name in ("condor_app.pyw", "condor_launcher.pyw", "condor_window.pyw", "pyproject.toml"):
            candidate = self.root / name
            if candidate.exists():
                candidates.append(candidate)
        # Sem resolve() por arquivo: rglob a partir de uma raiz ja resolvida ja
        # devolve caminho absoluto, e um resolve() por item custava um acesso ao
        # sistema de arquivos cada — 20 ms dos 32 ms desta funcao no Windows.
        return sorted({
            path for path in candidates
            if path.suffix.lower() in self.EXTENSIONS
            and "__pycache__" not in path.parts
            and path.is_file()
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
        self._cache = None
        self._cache_marca = None
        self._cache_ate = 0.0
        return len(files)

    def verify(self, usar_cache: bool = True) -> tuple[bool, str, int]:
        agora = time.monotonic()
        marca = self._marca_dos_arquivos() if usar_cache else None
        if (
            usar_cache
            and self._cache is not None
            and marca == self._cache_marca
            and agora < self._cache_ate
        ):
            return self._cache
        resultado = self._verificar()
        self._cache = resultado
        self._cache_marca = marca
        self._cache_ate = agora + self.REVALIDACAO_SEGUNDOS
        return resultado

    def _verificar(self) -> tuple[bool, str, int]:
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
