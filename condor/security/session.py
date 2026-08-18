"""Sessao local contra acesso cruzado de sites ao servidor do Condor."""

from __future__ import annotations

import hmac
import os
import secrets
import stat
import threading
import time
from collections import deque
from urllib.parse import urlsplit

from condor.paths import state_path


class LocalSessionSecurity:
    COOKIE = "condor_session"
    CLIENT_HEADER = "x-condor-token"
    SESSION_TTL_SECONDS = 4 * 60 * 60

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.token = secrets.token_urlsafe(48)
        # Segredo de boot entregue pelo sistema de arquivos, nao pela rede.
        # Antes bastava mandar dois cabecalhos fixos ('Origin' e
        # 'X-Condor-Client') pra ganhar uma sessao completa da API — qualquer
        # programa rodando na maquina conseguia ler a memoria do Condor. Agora o
        # cliente precisa provar que consegue LER um arquivo do perfil do dono.
        self.boot_token = secrets.token_urlsafe(32)
        self._publish_boot_token()
        self._expires_at = time.monotonic() + self.SESSION_TTL_SECONDS
        self._rate_windows: dict[str, deque[float]] = {}
        self._auth_failures: dict[str, tuple[int, float, float]] = {}
        self._lock = threading.Lock()
        self.allowed_origins = {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
            f"http://[::1]:{port}",
        }

    # ── Segredo de boot ────────────────────────────────────────────────────

    @staticmethod
    def boot_token_path():
        return state_path("security", "ui-token")

    def _publish_boot_token(self) -> None:
        """Grava o segredo do boot so pro dono, substituindo o da execucao antiga."""
        path = self.boot_token_path()
        try:
            descriptor = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(self.boot_token)
                stream.flush()
                os.fsync(stream.fileno())
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            # Sem o arquivo a janela nao consegue abrir sessao; melhor falhar
            # ruidosamente no boot do que servir a API sem essa prova.
            raise

    def discard_boot_token(self) -> None:
        try:
            self.boot_token_path().unlink(missing_ok=True)
        except OSError:
            pass

    def boot_token_valid(self, supplied: str | None) -> bool:
        return bool(supplied and hmac.compare_digest(supplied, self.boot_token))

    # ── Origem e sessao ────────────────────────────────────────────────────

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
