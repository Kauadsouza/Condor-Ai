"""
Servidor do Condor — FastAPI + WebSocket.

Monta todos os pedaços na ordem certa, serve a interface e mantém a janela
sincronizada com o que está acontecendo por voz.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import platform
import re
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from condor.actions.guard import Guarda
from condor.brain.client import Cerebro
from condor.config import Config, salvar_config
from condor.core import AIGateway, ContextEngine, EventBus, ProjectEngine
from condor.devices import ActionSafetyLayer, CameraBridge, DeviceBridge
from condor.development import human_model_contract
from condor.memory.db import Memoria
from condor.memory.extractor import Extrator
from condor.memory.recall import Recall
from condor.mobile import MobileViewer
from condor.paths import CODE_ROOT, state_path, state_root
from condor.security.integrity import CodeIntegrity
from condor.security.session import LocalSessionSecurity
from condor.security.vault import CondorVault, VaultError
from condor.security.identity import DeviceIdentity
from condor.session import Sessao
from condor.voice.stt import Ouvidos
from condor.voice.tts import Voz
from condor.voice.wake import Escuta

log = logging.getLogger("condor.servidor")

ROOT = CODE_ROOT
DATA = state_root()
HUB_OUT = Path(
    os.getenv("CONDOR_HUB_OUT")
    or (CODE_ROOT.parent.parent / "ARTX Hub" / "out")
).resolve()


_HUB_CSP_CACHE: dict[str, object] = {}

CONDOR_X_REGIONS = {
    "head-group", "head", "neck", "torso", "chest", "abdomen", "pelvis", "power",
    "left-arm", "left-shoulder", "left-upper-arm", "left-elbow", "left-forearm", "left-hand",
    "right-arm", "right-shoulder", "right-upper-arm", "right-elbow", "right-forearm", "right-hand",
    "legs", "left-thigh", "left-knee", "left-shin", "left-foot",
    "right-thigh", "right-knee", "right-shin", "right-foot",
}
CONDOR_X_ITEM_TYPES = {"componente", "requisito", "nota", "teste"}
CONDOR_X_ITEM_STATUSES = {"rascunho", "planejado", "em_desenvolvimento", "bloqueado", "validado"}


def _hub_inline_script_sources() -> str:
    """Retorna hashes CSP dos scripts inline exatos exportados pelo Next.js.

    Guardado em cache por mtime/tamanho: antes isto lia o index.html do disco e
    fazia SHA-256 de cada bloco a cada requisicao a /hub.
    """
    index = HUB_OUT / "index.html"
    if not index.is_file():
        return ""
    try:
        marca = index.stat()
        assinatura = (marca.st_mtime_ns, marca.st_size)
        if _HUB_CSP_CACHE.get("assinatura") == assinatura:
            return str(_HUB_CSP_CACHE.get("valor", ""))
        html = index.read_bytes()
    except OSError:
        return ""
    sources: list[str] = []
    for match in re.finditer(
        rb"<script\b([^>]*)>(.*?)</script\s*>", html, flags=re.IGNORECASE | re.DOTALL
    ):
        attributes, body = match.groups()
        if re.search(rb"\bsrc\s*=", attributes, flags=re.IGNORECASE):
            continue
        digest = base64.b64encode(hashlib.sha256(body).digest()).decode("ascii")
        sources.append(f"'sha256-{digest}'")
    valor = " ".join(sources)
    _HUB_CSP_CACHE.update({"assinatura": assinatura, "valor": valor})
    return valor


class Conexoes:
    """As janelas abertas agora (normalmente uma só)."""

    def __init__(self) -> None:
        self._sockets: list[WebSocket] = []

    async def entrar(self, ws: WebSocket) -> None:
        await ws.accept()
        self._sockets.append(ws)

    def sair(self, ws: WebSocket) -> None:
        if ws in self._sockets:
            self._sockets.remove(ws)

    @property
    def total(self) -> int:
        return len(self._sockets)

    async def transmitir(self, msg: dict) -> None:
        texto = json.dumps(msg, ensure_ascii=False)
        for ws in list(self._sockets):
            try:
                await ws.send_text(texto)
            except Exception:
                self.sair(ws)


def montar(config: Config) -> tuple[FastAPI, Sessao]:
    DATA.mkdir(parents=True, exist_ok=True)

    vault = CondorVault(state_path("security", "vault.json"))
    config.ligar_cofre(vault)
    local_security = LocalSessionSecurity(config.servidor.host, config.servidor.porta)
    identity = DeviceIdentity(vault)
    integrity = CodeIntegrity(state_path("security", "code-manifest.json"), identity)

    # ── Memória ────────────────────────────────────────────────────────────
    memoria = Memoria(DATA / "memory" / "condor.memory.enc")
    memoria.inicializar()

    # ── Condor Core ────────────────────────────────────────────────────────
    event_bus = EventBus(memoria)
    context_engine = ContextEngine()

    # Toda IA, inclusive a implementação local existente, passa pelo gateway.
    recall = Recall(memoria)
    guarda = Guarda(config, memoria, identity)
    provider = Cerebro(config, memoria, guarda, recall)
    cerebro = AIGateway(provider, context_engine, event_bus)
    recall.ligar_cerebro(cerebro)
    extrator = Extrator(memoria, cerebro, config)
    project_engine = ProjectEngine(memoria, context_engine, event_bus)
    safety_layer = ActionSafetyLayer()
    device_bridge = DeviceBridge(memoria, event_bus, safety_layer)
    camera_bridge = CameraBridge(memoria, event_bus, provider._visao)

    # ── Voz ────────────────────────────────────────────────────────────────
    ouvidos = Ouvidos(config, cerebro)
    voz = Voz(config, cerebro)
    sessao_ref: dict = {}
    escuta = Escuta(config, lambda wav: sessao_ref["s"].ao_ouvir(wav))

    sessao = Sessao(config, memoria, cerebro, recall, extrator,
                    guarda, escuta, ouvidos, voz)
    sessao_ref["s"] = sessao

    async def _ensure_voice() -> None:
        """Inicia ou recria a thread de voz somente com cofre e modelo prontos."""
        nonlocal escuta
        if not config.escuta.ativa or not vault.unlocked:
            return
        if not config.chave_picovoice:
            escuta.motivo_inativa = "chave local do detector de voz ausente no cofre"
            return
        wake_models = list((state_root() / "wake").glob("condor*.ppn"))
        if not wake_models:
            escuta.motivo_inativa = "modelo condor*.ppn ausente em ~/.condor/wake"
            return
        if escuta.is_alive() or escuta.ativa:
            return
        if escuta.ident is not None:
            escuta = Escuta(config, lambda wav: sessao_ref["s"].ao_ouvir(wav))
            sessao.escuta = escuta
        escuta.start()
        await asyncio.sleep(0.25)

    conexoes = Conexoes()
    sessao.ligar_avisos(conexoes.transmitir)
    event_bus.subscribe(
        "*", lambda event: conexoes.transmitir({"tipo": "core.event", "event": event})
    )

    # ── App ────────────────────────────────────────────────────────────────
    app = FastAPI(title="CONDOR", docs_url=None, redoc_url=None)
    app.state.event_bus = event_bus
    app.state.context_engine = context_engine
    app.state.ai_gateway = cerebro
    app.state.project_engine = project_engine
    app.state.device_bridge = device_bridge
    app.state.camera_bridge = camera_bridge

    def _mobile_snapshot() -> dict:
        state = sessao.snapshot()
        integrity_ok = integrity.verify()[0] if vault.unlocked else None
        return {
            "nome": "Condor",
            "estado": state["estado"],
            "acordado": state["acordado"],
            "cerebro_pronto": state["cerebro_pronto"],
            "modelo": state["modelo"],
            "provedor": state["provedor"],
            "voz_local_pronta": state["stt_local_pronto"] and state["tts_local_pronto"],
            "integridade_ok": integrity_ok,
            "modo": "somente leitura",
            "projetos": [{"id": "condor-x", "nome": "Condor X · Modelo 01", "versao": "V1"}],
        }

    mobile_viewer = MobileViewer(config.visualizacao_movel.porta, _mobile_snapshot)
    app.state.mobile_viewer = mobile_viewer

    def _texto(payload: dict, campo: str, limite: int, obrigatorio: bool = True) -> str:
        valor = str(payload.get(campo) or "").strip()
        if obrigatorio and not valor:
            raise ValueError(f"{campo} obrigatorio")
        if len(valor) > limite:
            raise ValueError(f"{campo} excede {limite} caracteres")
        return valor

    def _memoria_pronta() -> JSONResponse | None:
        if memoria.unlocked:
            return None
        return JSONResponse(
            {"erro": "cofre bloqueado; desbloqueie o Condor para gravar"},
            status_code=423,
        )

    def _passphrase(payload: dict, minimum: int = 1) -> str:
        value = str(payload.get("passphrase") or "")
        if len(value) < minimum or len(value) > 512:
            raise ValueError("frase secreta fora do limite seguro")
        return value

    def _auth_wait(action: str) -> JSONResponse | None:
        allowed, wait = local_security.auth_allowed(action)
        if allowed:
            return None
        return JSONResponse(
            {"erro": "autenticacao temporariamente bloqueada"},
            status_code=429,
            headers={"Retry-After": str(max(1, wait))},
        )

    def _auth_failed(action: str) -> JSONResponse:
        delay = local_security.auth_failed(action)
        guarda.auditar("security", action, "DENIED", False, True)
        return JSONResponse(
            {"erro": "frase secreta incorreta"},
            status_code=403,
            headers={"Retry-After": str(delay)} if delay else None,
        )

    def _verify_owner(action: str, payload: dict) -> JSONResponse | None:
        if response := _auth_wait(action):
            return response
        try:
            passphrase = _passphrase(payload)
        except ValueError:
            return _auth_failed(action)
        if not guarda.owner.verify(passphrase):
            return _auth_failed(action)
        local_security.auth_succeeded(action)
        return None

    @app.middleware("http")
    async def _sem_cache(request, call_next):
        if not local_security.host_allowed(request.headers.get("host")):
            return JSONResponse({"erro": "host local invalido"}, status_code=400)
        path = request.url.path
        try:
            content_length = int(request.headers.get("content-length") or 0)
        except ValueError:
            return JSONResponse({"erro": "tamanho de requisicao invalido"}, status_code=400)
        media_upload = path == "/api/voice/transcribe" or (
            path.startswith("/api/cameras/") and path.endswith("/frame")
        )
        body_limit = 20 * 1024 * 1024 if media_upload else 1024 * 1024
        if content_length < 0 or content_length > body_limit:
            return JSONResponse({"erro": "requisicao excede o limite seguro"}, status_code=413)
        if path.startswith("/api/"):
            if path == "/api/session":
                if not local_security.rate_allowed("session", 30, 60):
                    return JSONResponse(
                        {"erro": "muitas tentativas de sessao"},
                        status_code=429,
                        headers={"Retry-After": "60"},
                    )
            else:
                if not local_security.request_allowed(
                    request.headers.get("origin"),
                    request.headers.get("referer"),
                    request.headers.get("sec-fetch-site"),
                    request.method,
                ):
                    return JSONResponse({"erro": "origem local invalida"}, status_code=403)
                if not local_security.token_valid(request.cookies.get(local_security.COOKIE)):
                    return JSONResponse({"erro": "sessao local ausente ou expirada"}, status_code=401)
                bucket = "api-write" if request.method not in {"GET", "HEAD", "OPTIONS"} else "api-read"
                limit = 180 if bucket == "api-write" else 600
                if not local_security.rate_allowed(bucket, limit, 60):
                    return JSONResponse(
                        {"erro": "limite local temporariamente atingido"},
                        status_code=429,
                        headers={"Retry-After": "60"},
                    )
        resposta = await call_next(request)
        if path.startswith(("/api", "/ui", "/hub")):
            resposta.headers["Cache-Control"] = "no-store, must-revalidate"
            resposta.headers["Pragma"] = "no-cache"
        script_sources = "'self'"
        if request.url.path.startswith("/hub"):
            inline_sources = _hub_inline_script_sources()
            if inline_sources:
                script_sources += f" {inline_sources}"
        resposta.headers["Content-Security-Policy"] = (
            f"default-src 'self'; script-src {script_sources}; "
            "style-src 'self' 'unsafe-inline'; font-src 'self' data:; img-src 'self' data:; "
            "connect-src 'self' https://*.supabase.co wss://*.supabase.co "
            "ws://127.0.0.1:* ws://localhost:*; "
            "frame-src 'self' https://kauaartx.vercel.app https://sistema-videos.vercel.app "
            "https://sat-simulado.vercel.app https://university-path-six.vercel.app; "
            "media-src 'self' blob:; worker-src 'self' blob:; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; "
            "manifest-src 'self'; frame-ancestors 'self'"
        )
        resposta.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        resposta.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "SAMEORIGIN"
        resposta.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        resposta.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        resposta.headers["Referrer-Policy"] = "no-referrer"
        resposta.headers["Permissions-Policy"] = (
            "camera=(), display-capture=(), microphone=(self), geolocation=(), "
            "payment=(), usb=(), serial=(), bluetooth=()"
        )
        return resposta

    @app.post("/api/session")
    async def api_session(request: Request):
        if (
            not local_security.origin_allowed(request.headers.get("origin"))
            or not local_security.client_allowed(request.headers.get("x-condor-client"))
        ):
            return JSONResponse({"erro": "origem local invalida"}, status_code=403)
        # Duas provas aceitas, nenhuma delas forjavel so com cabecalho:
        #   1. o segredo de boot, que exige ler um arquivo do perfil do dono —
        #      e como a janela do Condor abre a primeira sessao;
        #   2. um cookie de sessao ainda valido, que so existe se a prova 1 ja
        #      foi dada nesta execucao — e como o Hub em /hub renova a dele sem
        #      precisar do arquivo, por estar na mesma origem e na mesma aba.
        renovacao = local_security.token_valid(request.cookies.get(local_security.COOKIE))
        if not renovacao and not local_security.boot_token_valid(
            request.headers.get(local_security.CLIENT_HEADER)
        ):
            guarda.auditar("security", "session", "DENIED: sem segredo de boot", False, False)
            return JSONResponse(
                {"erro": "cliente local nao autorizado; abra o Condor pela janela"},
                status_code=403,
            )
        response = JSONResponse({"ok": True, "nome": "Condor"})
        response.set_cookie(
            local_security.COOKIE,
            local_security.issue(),
            httponly=True,
            secure=False,
            samesite="strict",
            path="/",
            max_age=local_security.SESSION_TTL_SECONDS,
        )
        return response

    app.mount("/ui", StaticFiles(directory=str(Path(__file__).parent / "ui"), html=True),
              name="ui")

    if HUB_OUT.exists():
        app.mount("/hub", StaticFiles(directory=str(HUB_OUT), html=True), name="hub")

    @app.get("/")
    async def raiz():
        return RedirectResponse("/ui/index.html")

    @app.post("/api/app/abrir")
    async def api_app_open():
        if not sessao.abrir_aplicativo():
            return JSONResponse({"erro": "janela local indisponivel"}, status_code=503)
        return {"ok": True, "app": "Condor", "url": "/ui/index.html"}

    @app.get("/api/estado")
    async def api_estado():
        return {**sessao.snapshot(),
                "memoria": memoria.estatisticas(),
                 "custo": memoria.custo_hoje()}

    @app.get("/api/seguranca/estado")
    async def api_security_state():
        audit_ok, audit_count = guarda.verificar_auditoria()
        return {
            "owner_configured": guarda.configurada,
            "owner_session_active": guarda.owner_session_active,
            "vault_exists": vault.exists,
            "vault_unlocked": vault.unlocked,
            "profile": config.seguranca.perfil,
            "simulation": config.seguranca.simulacao,
            "memory_sharing": config.cerebro.compartilhar_memoria_com_conector,
            "connector_learning": config.cerebro.aprendizado_automatico_por_conector,
            "provider": cerebro.provedor,
            "model": cerebro.modelo_ativo,
            "emergency_stop": guarda.stopped,
            "audit_ok": audit_ok,
            "audit_events": audit_count,
            "device_id": identity.device_id if vault.unlocked else None,
            "allowed_roots": guarda.allowed_roots,
            "code_integrity": (
                dict(zip(("ok", "detail", "files"), integrity.verify()))
                if vault.unlocked else {"ok": None, "detail": "cofre bloqueado", "files": 0}
            ),
        }

    @app.get("/api/mobile/access")
    async def api_mobile_access():
        if not config.visualizacao_movel.ativa:
            return JSONResponse({"erro": "visualizacao movel desativada"}, status_code=404)
        return mobile_viewer.access.details()

    @app.post("/api/seguranca/configurar")
    async def api_security_setup(payload: dict):
        if guarda.configurada or vault.exists:
            return JSONResponse({"erro": "seguranca ja configurada"}, status_code=409)
        if response := _auth_wait("setup"):
            return response
        # A frase secreta e validada sozinha. Antes, um endpoint local mal
        # digitado levantava ValueError no mesmo bloco e contava como tentativa
        # de senha errada — o dono ficava de castigo por um erro de formulario.
        try:
            passphrase = _passphrase(payload, 12)
        except ValueError:
            local_security.auth_failed("setup")
            return JSONResponse({"erro": "frase secreta fora do limite seguro"}, status_code=400)
        try:
            brain_data = config.cerebro.model_dump()
            if payload.get("local_endpoint"):
                brain_data["endpoint_local"] = _texto(payload, "local_endpoint", 500)
            if "local_model" in payload:
                brain_data["modelo_local"] = _texto(payload, "local_model", 200, False)
            config.cerebro = type(config.cerebro)(**brain_data)
            guarda.configurar_dono(passphrase)
            vault.initialize(passphrase, {
                "CONDOR_DONO": _texto(payload, "owner", 200, False) or "Kaua",
                "OPENAI_API_KEY": _texto(payload, "openai_api_key", 16384, False),
                "PICOVOICE_ACCESS_KEY": _texto(payload, "picovoice_access_key", 16384, False),
                "CONDOR_SAFETY_ID": base64.urlsafe_b64encode(os.urandom(24)).decode(),
                "MEMORY_KEY": base64.b64encode(os.urandom(32)).decode(),
            })
            identity.ensure()
            integrity.refresh()
            memoria.unlock(base64.b64decode(vault.get("MEMORY_KEY")))
            guarda.unlock_owner_session()
            salvar_config(config)
            await _ensure_voice()
        except (ValueError, VaultError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        local_security.auth_succeeded("setup")
        return {"ok": True}

    @app.post("/api/seguranca/desbloquear")
    async def api_security_unlock(payload: dict):
        if response := _auth_wait("unlock"):
            return response
        try:
            vault.unlock(_passphrase(payload))
            identity.ensure()
            memoria.unlock(base64.b64decode(vault.get("MEMORY_KEY")))
            guarda.unlock_owner_session()
            salvar_config(config)
            await _ensure_voice()
            if not guarda.stopped:
                escuta.voltar_a_ouvir()
        except (ValueError, VaultError):
            return _auth_failed("unlock")
        local_security.auth_succeeded("unlock")
        return {"ok": True}

    @app.post("/api/seguranca/bloquear")
    async def api_security_lock():
        guarda.lock_owner_session()
        memoria.lock()
        vault.lock()
        return {"ok": True}

    @app.post("/api/seguranca/segredos")
    async def api_security_secrets(payload: dict):
        if not vault.unlocked:
            return JSONResponse({"erro": "cofre bloqueado"}, status_code=423)
        if response := _verify_owner("secret_update", payload):
            return response
        try:
            brain_data = config.cerebro.model_dump()
            if "local_endpoint" in payload:
                brain_data["endpoint_local"] = _texto(payload, "local_endpoint", 500, False)
            if "local_model" in payload:
                brain_data["modelo_local"] = _texto(payload, "local_model", 200, False)
            config.cerebro = type(config.cerebro)(**brain_data)
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        # _texto valida tamanho e pode levantar ValueError; fora do try isso
        # virava 500 em vez de um 400 explicando o problema.
        changed: list[str] = []
        try:
            novos = {
                secret_name: _texto(payload, field, 16384, False)
                for field, secret_name in (
                    ("openai_api_key", "OPENAI_API_KEY"),
                    ("picovoice_access_key", "PICOVOICE_ACCESS_KEY"),
                )
                if field in payload
            }
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        for secret_name, valor in novos.items():
            vault.set(secret_name, valor)
            changed.append(secret_name)
        salvar_config(config)
        cerebro.reset_connection()
        await _ensure_voice()
        guarda.auditar("security", "secret_update", ",".join(changed), True, True)
        return {
            "ok": True,
            "changed": changed,
            "provider": cerebro.provedor,
            "model": cerebro.modelo_ativo,
        }

    @app.post("/api/emergencia/parar")
    async def api_emergency_stop():
        # Falha pro lado seguro (tranca tudo), entao nao pede frase secreta —
        # mas sem limite qualquer processo local desligaria o Condor em loop.
        if not local_security.rate_allowed("emergency-stop", 6, 60):
            return JSONResponse(
                {"erro": "muitas paradas seguidas"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        guarda.emergency_stop()
        guarda.lock_owner_session()
        escuta.silenciar()
        voz.calar()
        await sessao.dormir("interruptor de emergencia")
        memoria.lock()
        vault.lock()
        return {"ok": True}

    @app.post("/api/emergencia/retomar")
    async def api_emergency_resume(payload: dict):
        if response := _auth_wait("emergency_resume"):
            return response
        try:
            passphrase = _passphrase(payload)
        except ValueError:
            return _auth_failed("emergency_resume")
        ok = guarda.emergency_resume(passphrase)
        if not ok:
            return _auth_failed("emergency_resume")
        local_security.auth_succeeded("emergency_resume")
        return {"ok": True, "vault_unlocked": False}

    @app.post("/api/seguranca/integridade/recriar")
    async def api_integrity_refresh(payload: dict):
        if not vault.unlocked:
            return JSONResponse({"erro": "cofre bloqueado"}, status_code=423)
        if response := _verify_owner("integrity_refresh", payload):
            return response
        count = integrity.refresh()
        guarda.auditar("security", "integrity_refresh", f"{count} arquivos", True, True)
        return {"ok": True, "files": count}

    @app.get("/api/memoria/grafo")
    async def api_grafo():
        return memoria.grafo()

    @app.get("/api/memoria/fluxo")
    async def api_fluxo():
        return {"itens": memoria.fluxo_recente(12)}

    @app.get("/api/memoria/fatos")
    async def api_fatos(categoria: str | None = None, limite: int = 50):
        return {"fatos": memoria.fatos_recentes(limite, categoria)}

    @app.delete("/api/memoria/fatos/{fato_id}")
    async def api_esquecer(fato_id: int):
        return {"ok": memoria.esquecer_fato(fato_id)}

    @app.get("/api/projetos")
    async def api_projetos():
        return {"projetos": memoria.projetos()}

    # ── Condor Core API ───────────────────────────────────────────────────

    @app.get("/api/core/status")
    async def api_core_status():
        permissions = memoria.permissions() if memoria.unlocked else []
        session_state = sessao.snapshot()
        return {
            "core": "online",
            "ai": cerebro.status(),
            "context": context_engine.snapshot(),
            "device_bridge": device_bridge.status() if memoria.unlocked else {
                "bridge": "locked", "connected": [], "known": []
            },
            "voice": {
                "stt": bool(session_state.get("stt_local_pronto")),
                "tts": bool(session_state.get("tts_local_pronto")),
                "wake_word": bool(session_state.get("escuta_ativa")),
                "wake_reason": session_state.get("motivo_escuta") or "",
            },
            "vision": "ready" if await provider.visao_pronta() else "not_ready",
            "gesture": "not_configured",
            "wearable": "not_connected",
            "permissions": permissions,
        }

    @app.get("/api/context")
    async def api_context_get():
        return {"context": context_engine.snapshot()}

    @app.get("/api/human-model")
    async def api_human_model():
        return human_model_contract()

    @app.patch("/api/context")
    async def api_context_update(payload: dict):
        allowed = ContextEngine.FIELDS - {"updated_at"}
        changes = {key: value for key, value in payload.items() if key in allowed}
        if set(payload) - allowed:
            return JSONResponse({"erro": "campo de contexto inválido"}, status_code=400)
        context = context_engine.update(**changes)
        await event_bus.publish("CONTEXT_UPDATED", {"changes": changes}, source="api", project_id=context.get("project_id"))
        return {"context": context}

    @app.get("/api/projects/{project_id}")
    async def api_project_snapshot(project_id: str):
        if response := _memoria_pronta():
            return response
        snapshot = project_engine.snapshot(project_id[:80])
        if snapshot["project"] is None:
            return JSONResponse({"erro": "projeto não encontrado"}, status_code=404)
        return snapshot

    @app.post("/api/projects/{project_id}/open")
    async def api_project_open(project_id: str):
        if response := _memoria_pronta():
            return response
        try:
            return await project_engine.open(project_id[:80])
        except KeyError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=404)

    @app.post("/api/projects/{project_id}/regions/{region_id}/select")
    async def api_project_region_select(project_id: str, region_id: str):
        if project_id != "condor-x" or region_id not in CONDOR_X_REGIONS:
            return JSONResponse({"erro": "projeto ou região inválida"}, status_code=404)
        return {"context": await project_engine.select_region(project_id, region_id)}

    @app.post("/api/projects/{project_id}/parts")
    async def api_project_part_create(project_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            region = _texto(payload, "region", 80)
            name = _texto(payload, "name", 180)
            if project_id != "condor-x" or region not in CONDOR_X_REGIONS:
                raise ValueError("projeto ou região inválida")
            part = await project_engine.create_draft(project_id, region, {**payload, "name": name})
            return {"part": part}
        except (ValueError, KeyError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.get("/api/parts/{part_id}/versions")
    async def api_part_versions(part_id: str):
        if response := _memoria_pronta():
            return response
        return {"versions": memoria.part_versions(part_id[:80])}

    @app.post("/api/parts/{part_id}/versions")
    async def api_part_version_create(part_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            return {"version": await project_engine.create_version(part_id[:80], payload)}
        except KeyError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=404)

    @app.post("/api/parts/{part_id}/integrate")
    async def api_part_integrate(part_id: str):
        if response := _memoria_pronta():
            return response
        try:
            return {"part": await project_engine.integrate(part_id[:80])}
        except KeyError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=404)

    @app.get("/api/events")
    async def api_events(limite: int = 50):
        if response := _memoria_pronta():
            return response
        return {"events": memoria.eventos_recentes(limite)}

    @app.get("/api/devices")
    async def api_devices():
        if response := _memoria_pronta():
            return response
        return device_bridge.status()

    @app.post("/api/devices/scan")
    async def api_devices_scan():
        if response := _memoria_pronta():
            return response
        return await device_bridge.scan()

    @app.post("/api/devices/{device_id}/commands/plan")
    async def api_device_command_plan(device_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        return await device_bridge.plan_command(device_id[:80], payload)

    @app.get("/api/cameras")
    async def api_cameras():
        if response := _memoria_pronta():
            return response
        state = camera_bridge.status()
        state["vision_ready"] = await provider.visao_pronta()
        return state

    @app.post("/api/cameras")
    async def api_camera_create(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            source = await camera_bridge.add_source(
                _texto(payload, "name", 120),
                _texto(payload, "protocol", 20).lower(),
                _texto(payload, "endpoint", 1200),
                _texto(payload, "zone", 120, obrigatorio=False),
            )
            return {"camera": source}
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.post("/api/cameras/{camera_id}/events")
    async def api_camera_event(camera_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            confidence = payload.get("confidence")
            if confidence is not None:
                confidence = max(0.0, min(1.0, float(confidence)))
            return await camera_bridge.record_event(
                camera_id[:80], _texto(payload, "event_type", 40), confidence
            )
        except KeyError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=404)
        except (TypeError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.post("/api/cameras/{camera_id}/frame")
    async def api_camera_frame(camera_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            return await camera_bridge.analyze_frame(
                camera_id[:80], _texto(payload, "image_b64", 8_000_000)
            )
        except KeyError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=404)
        except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.get("/api/alerts")
    async def api_alerts(limite: int = 50):
        if response := _memoria_pronta():
            return response
        return {"alerts": memoria.security_alerts(limite)}

    @app.get("/api/permissions")
    async def api_permissions():
        if response := _memoria_pronta():
            return response
        return {"permissions": memoria.permissions()}

    @app.patch("/api/permissions/{capability}")
    async def api_permission_update(capability: str, payload: dict):
        if response := _memoria_pronta():
            return response
        if response := _verify_owner("permission_change", payload):
            return response
        if not isinstance(payload.get("allowed"), bool):
            return JSONResponse({"erro": "allowed deve ser booleano"}, status_code=400)
        updated = memoria.set_permission(capability[:80], payload["allowed"])
        if not updated:
            return JSONResponse({"erro": "permissão desconhecida"}, status_code=404)
        event = "PERMISSION_GRANTED" if payload["allowed"] else "PERMISSION_REVOKED"
        await event_bus.publish(event, {"capability": capability}, source="security")
        return {"ok": True, "permissions": memoria.permissions()}

    @app.get("/api/biometrics")
    async def api_biometrics():
        permission = next((item for item in memoria.permissions() if item["capability"] == "health_data"), None) if memoria.unlocked else None
        return {
            "connected": False,
            "authorized": bool(permission and permission["allowed"]),
            "readings": [],
            "medical_diagnosis": False,
        }

    @app.get("/api/hub")
    async def api_hub():
        from condor.actions.executor import info_sistema

        snapshot = memoria.hub_snapshot()
        audit_ok, audit_count = guarda.verificar_auditoria()
        vision_ready = await cerebro.visao_pronta()
        # psutil varre processos e bloqueia; numa async def isso trava o laco de
        # eventos e a interface inteira para junto.
        diagnostico = await asyncio.to_thread(info_sistema)
        snapshot["system"] = {
            "name": "Condor",
            "local": True,
            "platform": platform.system(),
            "host": config.servidor.host,
            "port": config.servidor.porta,
            "provider": cerebro.provedor,
            "model": cerebro.modelo_ativo,
            "brain_ready": cerebro.pronto,
            "voice_ready": ouvidos.pronto and voz.pronto,
            "wake_ready": escuta.ativa,
            "voice_detail": (
                "STT Faster Whisper e TTS Piper locais prontos; ativacao por clique disponivel"
                if ouvidos.pronto and voz.pronto
                else escuta.motivo_inativa
            ),
            "vision_ready": vision_ready,
            "vision_model": cerebro.modelo_visao,
            "vault_unlocked": vault.unlocked,
            "emergency_stop": guarda.stopped,
            "simulation": config.seguranca.simulacao,
            "profile": config.seguranca.perfil,
            "audit_ok": audit_ok,
            "audit_events": audit_count,
            "hub_build": HUB_OUT.exists(),
            "device_id": identity.device_id if vault.unlocked else None,
            "diagnostic": diagnostico["saida"],
        }
        return snapshot

    @app.post("/api/hub/tasks")
    async def api_hub_task_create(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            item = memoria.hub_create_task(
                _texto(payload, "titulo", 180),
                _texto(payload, "projeto", 40, False) or "condor",
                _texto(payload, "prioridade", 16, False) or "media",
            )
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        return {"ok": True, "item": item}

    @app.patch("/api/hub/tasks/{item_id}")
    async def api_hub_task_update(item_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        status = str(payload.get("status") or "")
        if status not in {"pendente", "fazendo", "concluida", "bloqueada"}:
            return JSONResponse({"erro": "status de tarefa invalido"}, status_code=400)
        return {"ok": memoria.hub_update_task(item_id[:80], status)}

    @app.delete("/api/hub/tasks/{item_id}")
    async def api_hub_task_delete(item_id: str):
        if response := _memoria_pronta():
            return response
        return {"ok": memoria.hub_delete_task(item_id[:80])}

    @app.post("/api/hub/notes")
    async def api_hub_note_create(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            item = memoria.hub_create_note(
                _texto(payload, "titulo", 180),
                _texto(payload, "conteudo", 12000),
                _texto(payload, "projeto", 40, False) or "condor",
            )
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        return {"ok": True, "item": item}

    @app.delete("/api/hub/notes/{item_id}")
    async def api_hub_note_delete(item_id: str):
        if response := _memoria_pronta():
            return response
        return {"ok": memoria.hub_delete_note(item_id[:80])}

    @app.patch("/api/hub/notes/{item_id}")
    async def api_hub_note_update(item_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            titulo = _texto(payload, "titulo", 180)
            conteudo = _texto(payload, "conteudo", 12000)
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        return {"ok": memoria.hub_update_note(item_id[:80], titulo, conteudo)}

    @app.patch("/api/hub/condor-x/{item_id}")
    async def api_hub_part_update(item_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        # Os irmaos (tarefas, missoes, criativo) validam contra lista fechada;
        # so este aceitava qualquer string truncada em 30 chars.
        status = str(payload.get("status") or "")
        if status not in {"conceito", "simulacao", "prototipo", "bloqueado", "validado"}:
            return JSONResponse({"erro": "status de peca invalido"}, status_code=400)
        try:
            progresso = max(0, min(100, int(payload.get("progresso", 0))))
        except (TypeError, ValueError):
            return JSONResponse({"erro": "progresso invalido"}, status_code=400)
        return {"ok": memoria.hub_update_part(item_id[:80], status, progresso)}

    @app.get("/api/condor-x/regions/{regiao}/items")
    async def api_condor_x_region_items(regiao: str):
        if response := _memoria_pronta():
            return response
        if regiao not in CONDOR_X_REGIONS:
            return JSONResponse({"erro": "regiao invalida"}, status_code=404)
        return {"items": memoria.condor_x_region_items(regiao)}

    @app.post("/api/condor-x/regions/{regiao}/items")
    async def api_condor_x_region_item_create(regiao: str, payload: dict):
        if response := _memoria_pronta():
            return response
        if regiao not in CONDOR_X_REGIONS:
            return JSONResponse({"erro": "regiao invalida"}, status_code=404)
        tipo = str(payload.get("tipo") or "")
        if tipo not in CONDOR_X_ITEM_TYPES:
            return JSONResponse({"erro": "tipo de registro invalido"}, status_code=400)
        try:
            item = memoria.condor_x_create_region_item(
                regiao,
                tipo,
                _texto(payload, "titulo", 180),
                _texto(payload, "detalhes", 4000, False),
            )
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        return {"ok": True, "item": item}

    @app.patch("/api/condor-x/region-items/{item_id}")
    async def api_condor_x_region_item_update(item_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        status = str(payload.get("status") or "")
        if status not in CONDOR_X_ITEM_STATUSES:
            return JSONResponse({"erro": "status de registro invalido"}, status_code=400)
        try:
            titulo = _texto(payload, "titulo", 180)
            detalhes = _texto(payload, "detalhes", 4000, False)
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        return {
            "ok": memoria.condor_x_update_region_item(
                item_id[:80], titulo, detalhes, status
            )
        }

    @app.delete("/api/condor-x/region-items/{item_id}")
    async def api_condor_x_region_item_delete(item_id: str):
        if response := _memoria_pronta():
            return response
        return {"ok": memoria.condor_x_delete_region_item(item_id[:80])}

    @app.post("/api/hub/creator")
    async def api_hub_creator_create(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            item = memoria.hub_create_creator_item(
                _texto(payload, "titulo", 180),
                _texto(payload, "etapa", 40, False) or "ideia",
                _texto(payload, "notas", 4000, False),
            )
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        return {"ok": True, "item": item}

    @app.patch("/api/hub/creator/{item_id}")
    async def api_hub_creator_update(item_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        status = str(payload.get("status") or "")
        if status not in {"ideia", "roteiro", "gravacao", "edicao", "publicado"}:
            return JSONResponse({"erro": "status criativo invalido"}, status_code=400)
        return {"ok": memoria.hub_update_creator_item(item_id[:80], status)}

    @app.post("/api/hub/missions")
    async def api_hub_mission_create(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            item = memoria.hub_create_mission(
                _texto(payload, "titulo", 180),
                _texto(payload, "detalhe", 4000, False),
            )
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        return {"ok": True, "item": item}

    @app.patch("/api/hub/missions/{item_id}")
    async def api_hub_mission_update(item_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        estado = str(payload.get("estado") or "planejada")
        if estado not in {"planejada", "ativa", "pausada", "concluida"}:
            return JSONResponse({"erro": "estado de missao invalido"}, status_code=400)
        try:
            progresso = max(0, min(100, int(payload.get("progresso", 0))))
        except (TypeError, ValueError):
            return JSONResponse({"erro": "progresso invalido"}, status_code=400)
        return {"ok": memoria.hub_update_mission(item_id[:80], estado, progresso)}

    @app.post("/api/voice/transcribe")
    async def api_voice_transcribe(request: Request):
        """Push-to-talk local; áudio bruto nunca sai do loopback deste PC."""
        length = int(request.headers.get("content-length") or 0)
        if length > 20 * 1024 * 1024:
            return JSONResponse({"erro": "audio excede 20 MB"}, status_code=413)
        audio = await request.body()
        if not audio or len(audio) > 20 * 1024 * 1024:
            return JSONResponse({"erro": "audio ausente ou grande demais"}, status_code=400)
        texto = await ouvidos.transcrever(audio)
        if not texto:
            return JSONResponse({"erro": "nao entendi a fala"}, status_code=422)
        tarefa = asyncio.create_task(sessao.processar(texto, por_voz=True), name="condor-voz-local")
        _EM_VOO.add(tarefa)
        tarefa.add_done_callback(_EM_VOO.discard)
        return {"ok": True, "texto": texto, "local": True}

    @app.get("/api/acoes")
    async def api_acoes(limite: int = 40):
        return {"acoes": memoria.acoes_recentes(limite)}

    @app.get("/api/saude")
    async def api_saude():
        from condor.actions.executor import info_sistema
        sistema = await asyncio.to_thread(info_sistema)
        acoes = memoria.acoes_recentes(60)
        falhas = [a for a in acoes if not a["sucesso"]]
        pontos = 100
        if not cerebro.pronto:
            pontos -= 45
        if not (ouvidos.pronto and voz.pronto):
            pontos -= 25
        pontos -= min(20, len(falhas) * 3)
        return {
            "pontos": max(0, pontos),
            "cerebro": cerebro.pronto,
            "escuta": escuta.ativa,
            "voz_local": ouvidos.pronto and voz.pronto,
            "motivo_escuta": escuta.motivo_inativa,
            "falhas": falhas[:15],
            "criticos": 0 if cerebro.pronto else 1,
            "avisos": (0 if (ouvidos.pronto and voz.pronto) else 1) + min(9, len(falhas)),
            "sistema": sistema["saida"],
        }

    @app.post("/api/dormir")
    async def api_dormir():
        await sessao.dormir("pedido pela interface")
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        if (
            not local_security.host_allowed(socket.headers.get("host"))
            or not local_security.origin_allowed(socket.headers.get("origin"))
            or not local_security.token_valid(socket.cookies.get(local_security.COOKIE))
            or not local_security.rate_allowed("ws-connect", 20, 60)
            or conexoes.total >= 4
        ):
            await socket.close(code=1008)
            return
        await conexoes.entrar(socket)
        try:
            await socket.send_text(json.dumps(
                {"tipo": "estado", **sessao.snapshot()}, ensure_ascii=False))
            await socket.send_text(json.dumps(
                {"tipo": "memoria.stats", **memoria.estatisticas()}, ensure_ascii=False))
            await socket.send_text(json.dumps(
                {"tipo": "custo", **memoria.custo_hoje()}, ensure_ascii=False))

            while True:
                bruto = await socket.receive_text()
                if len(bruto) > 64 * 1024:
                    await socket.close(code=1009)
                    return
                if (
                    not local_security.token_valid(socket.cookies.get(local_security.COOKIE))
                    or not local_security.rate_allowed("ws-message", 180, 60)
                ):
                    await socket.close(code=1008)
                    return
                try:
                    msg = json.loads(bruto)
                except json.JSONDecodeError:
                    continue
                if msg.get("tipo") == "senha" and not local_security.rate_allowed("ws-password", 10, 60):
                    await socket.send_text(json.dumps({
                        "tipo": "erro", "mensagem": "Muitas tentativas de aprovação. Aguarde."
                    }, ensure_ascii=False))
                    continue
                await _tratar(msg, sessao, socket)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            log.debug("WebSocket caiu: %s", exc)
        finally:
            conexoes.sair(socket)

    # O asyncio só guarda referência fraca das tarefas: sem manter a referência
    # aqui, o coletor de lixo pode matar o vigia no meio do caminho e o Condor
    # nunca mais dormiria sozinho.
    tarefas: set[asyncio.Task] = set()

    @app.on_event("startup")
    async def _subir():
        sessao.guardar_loop(asyncio.get_running_loop())
        extrator.iniciar()

        vigia = asyncio.create_task(sessao.vigia(), name="condor-vigia")
        tarefas.add(vigia)
        vigia.add_done_callback(tarefas.discard)

        await _ensure_voice()
        if not escuta.ativa and escuta.motivo_inativa:
            log.warning("Escuta inativa: %s", escuta.motivo_inativa)

        ok, detalhe = await cerebro.testar_chave()
        log.info("Conector de IA: %s (%s)", "ok" if ok else "PROBLEMA", detalhe)
        await conexoes.transmitir({"tipo": "estado", **sessao.snapshot()})

    @app.on_event("shutdown")
    async def _descer():
        escuta.encerrar()
        await sessao.dormir("servidor encerrando")
        memoria.lock()
        vault.lock()

    return app, sessao


# Mesma história do vigia: sem referência forte, um turno inteiro pode sumir
# no meio por coleta de lixo.
_EM_VOO: set[asyncio.Task] = set()


async def _tratar(msg: dict, sessao: Sessao, socket: WebSocket) -> None:
    tipo = msg.get("tipo")

    if tipo == "texto":
        texto = (msg.get("texto") or "").strip()
        if len(texto) > 8000:
            await socket.send_text(json.dumps({
                "tipo": "erro", "mensagem": "Mensagem excede 8000 caracteres."
            }, ensure_ascii=False))
            return
        if texto:
            # Solto numa tarefa pra não travar o WebSocket enquanto ele pensa —
            # é o que mantém a interface respondendo durante a resposta.
            tarefa = asyncio.create_task(sessao.processar_texto(texto))
            _EM_VOO.add(tarefa)
            tarefa.add_done_callback(_EM_VOO.discard)

    elif tipo == "senha":
        texto = (msg.get("texto") or "").strip()
        if 0 < len(texto) <= 512:
            sessao.responder_senha(texto)

    elif tipo == "acordar":
        await sessao.acordar()

    elif tipo == "dormir":
        await sessao.dormir("pedido pela janela")

    elif tipo == "ping":
        await socket.send_text(json.dumps({"tipo": "pong"}))


async def rodar(app: FastAPI, config: Config) -> None:
    cfg = uvicorn.Config(app, host=config.servidor.host, port=config.servidor.porta,
                          log_config=None, log_level="warning",
                          server_header=False, date_header=False,
                          ws_max_size=1024 * 1024,
                          ws_ping_interval=20, ws_ping_timeout=40,
                          limit_concurrency=64, backlog=32,
                          timeout_keep_alive=5)
    servidor = uvicorn.Server(cfg)
    servidor.install_signal_handlers = lambda: None
    mobile_server = None
    mobile_task = None
    if config.visualizacao_movel.ativa:
        mobile_cfg = uvicorn.Config(
            app.state.mobile_viewer.app,
            host="0.0.0.0",
            port=config.visualizacao_movel.porta,
            log_config=None,
            log_level="error",
            server_header=False,
            date_header=False,
            limit_concurrency=24,
            backlog=16,
            timeout_keep_alive=4,
        )
        mobile_server = uvicorn.Server(mobile_cfg)
        mobile_server.install_signal_handlers = lambda: None

        async def _serve_mobile() -> None:
            try:
                await mobile_server.serve()
            except Exception:
                log.exception(
                    "A visualizacao movel nao iniciou na porta %s",
                    config.visualizacao_movel.porta,
                )

        mobile_task = asyncio.create_task(_serve_mobile())
        log.info(
            "Visualizacao movel somente leitura preparada na porta %s",
            config.visualizacao_movel.porta,
        )

    try:
        await servidor.serve()
    finally:
        if mobile_server is not None and mobile_task is not None:
            mobile_server.should_exit = True
            await mobile_task
