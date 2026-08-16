"""Sessao local contra acesso cruzado de sites ao servidor do Condor."""

from __future__ import annotations

import hmac
import secrets
from urllib.parse import urlsplit


class LocalSessionSecurity:
    COOKIE = "condor_session"

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.token = secrets.token_urlsafe(48)
        self.allowed_origins = {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
            f"http://[::1]:{port}",
        }

    def origin_allowed(self, origin: str | None) -> bool:
        return bool(origin and origin.rstrip("/") in self.allowed_origins)

    def host_allowed(self, host_header: str | None) -> bool:
        if not host_header:
            return False
        hostname = urlsplit("//" + host_header).hostname
        return hostname in {"127.0.0.1", "localhost", "::1"}

    def token_valid(self, supplied: str | None) -> bool:
        return bool(supplied and hmac.compare_digest(supplied, self.token))
