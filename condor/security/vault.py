"""Cofre criptografado e independente do sistema operacional.

Formato simples, versionado e portavel: Scrypt deriva uma chave da frase
secreta do dono e AES-256-GCM autentica e cifra o conteudo inteiro.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


class VaultError(RuntimeError):
    pass


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _derive(passphrase: str, salt: bytes) -> bytes:
    if len(passphrase) < 12:
        raise VaultError("A frase secreta precisa ter pelo menos 12 caracteres.")
    if len(passphrase) > 512:
        raise VaultError("A frase secreta excede o limite seguro.")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(
        passphrase.encode("utf-8")
    )


class CondorVault:
    VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path
        self._key: bytearray | None = None
        self._salt: bytes | None = None
        self._data: dict[str, Any] = {}

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    @property
    def unlocked(self) -> bool:
        return self._key is not None

    def initialize(self, passphrase: str, initial: dict[str, Any] | None = None) -> None:
        if self.exists:
            raise VaultError("O cofre do Condor ja existe.")
        salt = os.urandom(16)
        self._key = bytearray(_derive(passphrase, salt))
        self._salt = salt
        self._data = dict(initial or {})
        self._write(salt)

    def unlock(self, passphrase: str) -> None:
        if not self.exists:
            raise VaultError("O cofre do Condor ainda nao foi criado.")
        envelope = json.loads(self.path.read_text(encoding="utf-8"))
        if envelope.get("version") != self.VERSION:
            raise VaultError("Versao de cofre desconhecida.")
        salt = _unb64(envelope["salt"])
        key = _derive(passphrase, salt)
        try:
            plaintext = AESGCM(key).decrypt(
                _unb64(envelope["nonce"]),
                _unb64(envelope["ciphertext"]),
                f"condor-vault:{self.VERSION}".encode(),
            )
        except (InvalidTag, ValueError) as exc:
            raise VaultError("Frase secreta incorreta ou cofre alterado.") from exc
        self._key = bytearray(key)
        self._salt = salt
        self._data = json.loads(plaintext.decode("utf-8"))

    def lock(self) -> None:
        if self._key is not None:
            for index in range(len(self._key)):
                self._key[index] = 0
        self._key = None
        self._salt = None
        self._data = {}

    def get(self, name: str, default: Any = None) -> Any:
        self._require_unlocked()
        return self._data.get(name, default)

    # O salt vive na memoria junto com a chave. Reler do disco a cada gravacao
    # deixava o cofre regravar com um salt vindo de arquivo possivelmente
    # adulterado: a chave em memoria continuava certa, mas o proximo unlock
    # derivava outra coisa e o cofre ficava inacessivel pra sempre.
    def set(self, name: str, value: Any) -> None:
        self._require_unlocked()
        self._data[name] = value
        self._write(self._salt)

    def delete(self, name: str) -> bool:
        self._require_unlocked()
        existed = name in self._data
        self._data.pop(name, None)
        if existed:
            self._write(self._salt)
        return existed

    def rotate(self, current: str, replacement: str) -> None:
        self.unlock(current)
        salt = os.urandom(16)
        self._key = bytearray(_derive(replacement, salt))
        self._salt = salt
        self._write(salt)

    def _require_unlocked(self) -> None:
        if self._key is None:
            raise VaultError("O cofre do Condor esta bloqueado.")

    def _write(self, salt: bytes | None) -> None:
        self._require_unlocked()
        if not salt:
            raise VaultError("Cofre sem salt em memoria; desbloqueie de novo.")
        nonce = os.urandom(12)
        plaintext = json.dumps(
            self._data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        ciphertext = AESGCM(bytes(self._key)).encrypt(
            nonce, plaintext, f"condor-vault:{self.VERSION}".encode()
        )
        envelope = {
            "version": self.VERSION,
            "kdf": "scrypt-n32768-r8-p1",
            "cipher": "aes-256-gcm",
            "salt": _b64(salt),
            "nonce": _b64(nonce),
            "ciphertext": _b64(ciphertext),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".vault-", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(envelope, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
