"""Rotacao coordenada da frase do dono e do cofre criptografado."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from condor.security.approval import OwnerAuth
from condor.security.vault import CondorVault, VaultError


class PassphraseRotationError(RuntimeError):
    pass


def _restore(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.rollback")
    try:
        with temporary.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        temporary.unlink(missing_ok=True)


def rotate_passphrase(
    vault: CondorVault,
    owner: OwnerAuth,
    current: str,
    replacement: str,
) -> None:
    """Atualiza os dois registros ou restaura ambos ao estado anterior."""
    if current == replacement:
        raise PassphraseRotationError("Escolha uma palavra de acesso diferente da atual.")
    if not owner.verify(current):
        raise PassphraseRotationError("Palavra de acesso atual incorreta.")
    try:
        vault.unlock(current)
    except VaultError as exc:
        raise PassphraseRotationError("Palavra de acesso atual incorreta.") from exc

    owner_snapshot = owner.path.read_bytes()
    vault_snapshot = vault.path.read_bytes()
    try:
        owner.rotate(current, replacement)
        vault.rotate(current, replacement)
        vault.lock()
        vault.unlock(replacement)
        if not owner.verify(replacement):
            raise PassphraseRotationError("A nova identidade nao pôde ser verificada.")
    except Exception as exc:
        _restore(owner.path, owner_snapshot)
        _restore(vault.path, vault_snapshot)
        vault.lock()
        try:
            vault.unlock(current)
        except VaultError as rollback_exc:
            raise PassphraseRotationError(
                "A troca falhou e o cofre precisa de verificacao manual."
            ) from rollback_exc
        if isinstance(exc, PassphraseRotationError):
            raise
        raise PassphraseRotationError("A troca foi cancelada sem alterar o cofre.") from exc
