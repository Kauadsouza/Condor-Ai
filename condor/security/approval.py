"""Autenticacao propria do dono e aprovacoes exatas, curtas e de uso unico."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import stat
import time
from dataclasses import dataclass
from pathlib import Path


def _hash(passphrase: str, salt: bytes) -> bytes:
    if len(passphrase) < 12:
        raise ValueError("Use uma palavra de acesso com pelo menos 12 caracteres.")
    if len(passphrase) > 512:
        raise ValueError("A palavra de acesso excede o limite seguro.")
    return hashlib.scrypt(
        passphrase.encode("utf-8"), salt=salt, n=2**15, r=8, p=1,
        dklen=32, maxmem=64 * 1024 * 1024,
    )


@dataclass(frozen=True)
class ApprovalChallenge:
    id: str
    action_digest: str
    description: str
    expires_at: float


class OwnerAuth:
    """Nao usa conta Microsoft, Apple, Google nem recurso exclusivo de um SO."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._challenges: dict[str, ApprovalChallenge] = {}
        self._approved: dict[str, tuple[str, float]] = {}

    @property
    def configured(self) -> bool:
        return self.path.is_file()

    def setup(self, passphrase: str) -> None:
        if self.configured:
            raise RuntimeError("A identidade do dono ja esta configurada.")
        self._write_verifier(passphrase)

    def rotate(self, current: str, replacement: str) -> None:
        """Troca o verificador somente depois de validar a frase atual."""
        if not self.verify(current):
            raise ValueError("Palavra de acesso atual incorreta.")
        self._write_verifier(replacement)

    def _write_verifier(self, passphrase: str) -> None:
        salt = os.urandom(16)
        record = {
            "version": 1,
            "kdf": "scrypt-n32768-r8-p1",
            "salt": base64.b64encode(salt).decode(),
            "verifier": base64.b64encode(_hash(passphrase, salt)).decode(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{secrets.token_hex(8)}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(record, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        try:
            self.path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def verify(self, passphrase: str) -> bool:
        if not self.configured:
            return False
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            salt = base64.b64decode(record["salt"])
            expected = base64.b64decode(record["verifier"])
            actual = _hash(passphrase, salt)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        return hmac.compare_digest(actual, expected)

    def challenge(self, action_digest: str, description: str, ttl: int = 90) -> ApprovalChallenge:
        self._prune()
        challenge = ApprovalChallenge(
            id=secrets.token_urlsafe(24),
            action_digest=action_digest,
            description=description,
            expires_at=time.time() + max(15, min(ttl, 180)),
        )
        self._challenges[challenge.id] = challenge
        return challenge

    def approve(self, challenge_id: str, passphrase: str) -> str | None:
        self._prune()
        challenge = self._challenges.pop(challenge_id, None)
        if challenge is None or not self.verify(passphrase):
            return None
        token = secrets.token_urlsafe(32)
        self._approved[token] = (challenge.action_digest, time.time() + 45)
        return token

    def consume(self, token: str, action_digest: str) -> bool:
        self._prune()
        approved = self._approved.pop(token, None)
        return bool(approved and hmac.compare_digest(approved[0], action_digest))

    def _prune(self) -> None:
        now = time.time()
        self._challenges = {
            key: value for key, value in self._challenges.items() if value.expires_at > now
        }
        self._approved = {
            key: value for key, value in self._approved.items() if value[1] > now
        }
