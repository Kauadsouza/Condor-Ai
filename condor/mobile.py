"""Visualizacao movel local, sanitizada e estritamente somente leitura."""

from __future__ import annotations

import ipaddress
import secrets
import socket
import time
from collections import defaultdict, deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from condor.paths import CODE_ROOT

MOBILE_ROOT = CODE_ROOT / "condor" / "mobile"
UI_ROOT = CODE_ROOT / "condor" / "ui"
COOKIE = "condor_mobile_view"
SESSION_SECONDS = 8 * 60 * 60
PAIR_WINDOW_SECONDS = 10 * 60
PAIR_ATTEMPTS = 5
PRIVATE_IPV4 = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
PRIVATE_IPV6 = ipaddress.ip_network("fc00::/7")


def private_client(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if ip.is_loopback:
        return True
    if ip.version == 4:
        return any(ip in network for network in PRIVATE_IPV4)
    return ip in PRIVATE_IPV6


def private_host(host_header: str | None) -> bool:
    if not host_header:
        return False
    host = host_header.strip()
    if host.startswith("["):
        host = host[1:].split("]", 1)[0]
    elif ":" in host:
        host = host.rsplit(":", 1)[0]
    if host.lower() == "localhost":
        return True
    return private_client(host)


def lan_ipv4() -> str | None:
    candidates: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.add(info[4][0])
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("192.0.2.1", 9))
            candidates.add(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    for candidate in sorted(candidates):
        if candidate != "127.0.0.1" and private_client(candidate):
            return candidate
    return None


class MobileAccess:
    def __init__(self, port: int) -> None:
        self.port = port
        self.code = f"{secrets.randbelow(100_000_000):08d}"
        self._sessions: dict[str, float] = {}
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def details(self) -> dict[str, Any]:
        address = lan_ipv4()
        return {
            "enabled": True,
            "url": f"http://{address}:{self.port}" if address else None,
            "code": self.code,
            "mode": "somente leitura",
        }

    def pair(self, address: str, code: str) -> tuple[str | None, int]:
        now = time.monotonic()
        attempts = self._attempts[address]
        while attempts and now - attempts[0] > PAIR_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= PAIR_ATTEMPTS:
            return None, 429
        if not secrets.compare_digest(code, self.code):
            attempts.append(now)
            return None, 403
        attempts.clear()
        token = secrets.token_urlsafe(32)
        self._sessions[token] = now + SESSION_SECONDS
        return token, 200

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        expires = self._sessions.get(token)
        if expires is None:
            return False
        if expires <= time.monotonic():
            self._sessions.pop(token, None)
            return False
        return True


class MobileViewer:
    def __init__(self, port: int, snapshot: Callable[[], dict[str, Any]]) -> None:
        self.port = port
        self.access = MobileAccess(port)
        self.app = self._build(snapshot)

    def _build(self, snapshot: Callable[[], dict[str, Any]]) -> FastAPI:
        app = FastAPI(title="Condor Mobile View", docs_url=None, redoc_url=None)

        @app.middleware("http")
        async def private_lan_only(request: Request, call_next):
            address = request.client.host if request.client else ""
            if not private_client(address):
                return JSONResponse({"erro": "acesso fora da rede privada"}, status_code=403)
            if not private_host(request.headers.get("host")):
                return JSONResponse({"erro": "host privado invalido"}, status_code=400)
            try:
                content_length = int(request.headers.get("content-length") or 0)
            except ValueError:
                return JSONResponse({"erro": "requisicao invalida"}, status_code=400)
            if content_length < 0 or content_length > 4096:
                return JSONResponse({"erro": "requisicao excede o limite"}, status_code=413)

            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
                "media-src 'none'; object-src 'none'; base-uri 'none'; "
                "form-action 'self'; frame-ancestors 'none'"
            )
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
            response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = (
                "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
            )
            return response

        @app.post("/api/pair")
        async def pair(request: Request):
            try:
                payload = await request.json()
                code = str(payload.get("code") or "")
            except Exception:
                return JSONResponse({"erro": "codigo invalido"}, status_code=400)
            address = request.client.host if request.client else ""
            token, status = self.access.pair(address, code)
            if not token:
                message = "muitas tentativas" if status == 429 else "codigo incorreto"
                return JSONResponse({"erro": message}, status_code=status)
            response = JSONResponse({"ok": True, "mode": "somente leitura"})
            response.set_cookie(
                COOKIE,
                token,
                httponly=True,
                secure=False,
                samesite="strict",
                path="/",
                max_age=SESSION_SECONDS,
            )
            return response

        @app.get("/api/status")
        async def status(request: Request):
            if not self.access.valid(request.cookies.get(COOKIE)):
                return JSONResponse({"erro": "pareamento necessario"}, status_code=401)
            return snapshot()

        app.mount("/assets", StaticFiles(directory=str(UI_ROOT / "assets")), name="assets")
        app.mount("/vendor", StaticFiles(directory=str(UI_ROOT / "vendor")), name="vendor")
        app.mount("/scripts", StaticFiles(directory=str(UI_ROOT / "scripts")), name="scripts")
        app.mount("/", StaticFiles(directory=str(MOBILE_ROOT), html=True), name="mobile")
        return app
