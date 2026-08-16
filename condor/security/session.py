"""Sessao local contra acesso cruzado de sites ao servidor do Condor."""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections import deque
from urllib.parse import urlsplit


class LocalSessionSecurity:
    COOKIE = "condor_session"
    SESSION_TTL_SECONDS = 4 * 60 * 60

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.token = secrets.token_urlsafe(48)
        self._expires_at = time.monotonic() + self.SESSION_TTL_SECONDS
        self._rate_windows: dict[str, deque[float]] = {}
        self._auth_failures: dict[str, tuple[int, float, float]] = {}
        self._lock = threading.Lock()
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
        return bool(
            supplied
            and time.monotonic() < self._expires_at
            and hmac.compare_digest(supplied, self.token)
        )

    def issue(self) -> str:
        """Entrega a sessão atual e renova sua validade sem expor o token ao JS."""
        with self._lock:
            if time.monotonic() >= self._expires_at:
                self.token = secrets.token_urlsafe(48)
            self._expires_at = time.monotonic() + self.SESSION_TTL_SECONDS
            return self.token

    @staticmethod
    def client_allowed(value: str | None) -> bool:
        return value in {"desktop-ui", "hub-local"}

    def request_allowed(
        self,
        origin: str | None,
        referer: str | None,
        fetch_site: str | None,
        method: str,
    ) -> bool:
        """Bloqueia CSRF inclusive entre portas diferentes do loopback."""
        if origin:
            return self.origin_allowed(origin)
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            return False
        if referer:
            parsed = urlsplit(referer)
            candidate = f"{parsed.scheme}://{parsed.netloc}"
            return self.origin_allowed(candidate)
        return fetch_site == "same-origin"

    def rate_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            window = self._rate_windows.setdefault(key, deque())
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= limit:
                return False
            window.append(now)
            return True

    def auth_allowed(self, action: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            failures, blocked_until, last = self._auth_failures.get(action, (0, 0.0, 0.0))
            if last and now - last > 15 * 60:
                self._auth_failures.pop(action, None)
                return True, 0
            wait = max(0, int(blocked_until - now + 0.999))
            return wait == 0, wait

    def auth_failed(self, action: str) -> int:
        now = time.monotonic()
        with self._lock:
            failures, _, last = self._auth_failures.get(action, (0, 0.0, 0.0))
            if last and now - last > 15 * 60:
                failures = 0
            failures += 1
            delay = 0 if failures <= 3 else min(300, 2 ** (failures - 3))
            self._auth_failures[action] = (failures, now + delay, now)
            return delay

    def auth_succeeded(self, action: str) -> None:
        with self._lock:
            self._auth_failures.pop(action, None)
