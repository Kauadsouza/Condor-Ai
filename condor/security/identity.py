"""Identidade criptografica do dispositivo, pertencente ao Condor."""

from __future__ import annotations

import base64
import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


class DeviceIdentity:
    SECRET_NAME = "DEVICE_ED25519_PRIVATE"

    def __init__(self, vault) -> None:
        self.vault = vault

    def ensure(self) -> str:
        encoded = self.vault.get(self.SECRET_NAME, "")
        if not encoded:
            private = Ed25519PrivateKey.generate()
            raw = private.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
            self.vault.set(self.SECRET_NAME, base64.b64encode(raw).decode())
        return self.device_id

    @property
    def private(self) -> Ed25519PrivateKey:
        raw = base64.b64decode(self.vault.get(self.SECRET_NAME))
        return Ed25519PrivateKey.from_private_bytes(raw)

    @property
    def public_bytes(self) -> bytes:
        return self.private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )

    @property
    def device_id(self) -> str:
        return "condor-" + hashlib.sha256(self.public_bytes).hexdigest()[:24]

    def sign(self, payload: bytes) -> str:
        return base64.b64encode(self.private.sign(payload)).decode()

    def verify(self, payload: bytes, signature: str) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(self.public_bytes).verify(
                base64.b64decode(signature), payload
            )
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False
