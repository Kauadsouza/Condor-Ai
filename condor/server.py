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
from condor.cloud_sync import CloudError, CloudSyncClient
from condor.config import Config, salvar_config
from condor.core import (
    AIGateway,
    CondorOrchestrator,
    ContextEngine,
    DeviceMesh,
    DurableTaskEngine,
    EventBus,
    ProjectEngine,
    WorldStateLedger,
)
from condor.devices import ActionSafetyLayer, CameraBridge, DeviceBridge, GestureEngine
from condor.development import ArduinoToolchain, detect_language, human_model_contract
from condor.engine import PropulsionLabEngine
from condor.engine.contracts import CANDIDATE_ZONES, MODEL_LEVEL, PROPULSION_GROUPS
from condor.memory.db import Memoria
from condor.memory.extractor import (
    CATEGORIAS_VALIDAS,
    Extrator,
    contem_segredo,
    normalizar_chave,
    sanitizar_para_memoria,
)
from condor.memory.recall import Recall
from condor.mobile import MobileViewer
from condor.paths import CODE_ROOT, state_path, state_root
from condor.security.integrity import CodeIntegrity
from condor.security.passphrase import PassphraseRotationError, rotate_passphrase
from condor.security.session import LocalSessionSecurity
from condor.security.vault import CondorVault, VaultError
from condor.security.identity import DeviceIdentity
from condor.security.face_guard import FacePresenceGuard
from condor.session import Sessao
from condor.voice.stt import Ouvidos
from condor.voice.tts import Voz
from condor.voice.wake import Escuta

log = logging.getLogger("condor.servidor")

ROOT = CODE_ROOT
CADX_PARTIAL_BASELINE_MANIFEST = (
    CODE_ROOT / "condor" / "knowledge" / "cadx_partial_baseline" / "manifest.json"
)
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


def _falha_operacional(acao: dict) -> bool:
    """Bloqueio esperado da politica e defesa ativa, nao pane do Condor."""
    if acao.get("sucesso"):
        return False
    if str(acao.get("ferramenta") or "").lower() != "security":
        return True
    entrada = str(acao.get("entrada") or "")
    nome_acao = ""
    try:
        payload = json.loads(entrada)
        if isinstance(payload, dict):
            resultado = str(payload.get("result") or "")
            nome_acao = str(payload.get("input") or "").strip().lower()
        else:
            resultado = ""
    except (TypeError, ValueError, json.JSONDecodeError):
        resultado = entrada
    normalizado = resultado.strip().upper()
    if normalizado == "DENIED" or normalizado.startswith("DENIED:"):
        return False
    # Compatibilidade com auditorias produzidas pelo monitor facial antigo.
    # owner_absent, unknown_face, multiple_faces e heartbeat perdido indicam
    # que a defesa bloqueou o acesso; nao que o Condor tenha quebrado.
    if nome_acao == "face_presence" and normalizado.startswith("BLOQUEADO:"):
        return False
    return True


def _historico_para_interface(memoria: Memoria, limite: int = 24) -> list[dict]:
    if not memoria.unlocked:
        return []
    return [
        {
            "role": item.get("role"),
            "content": sanitizar_para_memoria(str(item.get("content") or ""))[:4000],
        }
        for item in memoria.historico(limite=limite)
        if item.get("role") in {"user", "assistant"}
    ]


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
    data_root = state_root()
    data_root.mkdir(parents=True, exist_ok=True)

    vault = CondorVault(state_path("security", "vault.json"))
    config.ligar_cofre(vault)
    local_security = LocalSessionSecurity(config.servidor.host, config.servidor.porta)
    identity = DeviceIdentity(vault)
    integrity = CodeIntegrity(state_path("security", "code-manifest.json"), identity)
    cloud = CloudSyncClient(config, vault, identity)

    # ── Memória ────────────────────────────────────────────────────────────
    memoria = Memoria(data_root / "memory" / "condor.memory.enc")
    memoria.inicializar()

    # ── Condor Core ────────────────────────────────────────────────────────
    event_bus = EventBus(memoria)
    context_engine = ContextEngine()

    # Toda IA, inclusive a implementação local existente, passa pelo gateway.
    recall = Recall(memoria)
    guarda = Guarda(config, memoria, identity)
    face_guard = FacePresenceGuard(memoria, guarda)
    provider = Cerebro(config, memoria, guarda, recall)
    cerebro = AIGateway(provider, context_engine, event_bus)
    recall.ligar_cerebro(cerebro)
    extrator = Extrator(memoria, cerebro, config, event_bus)
    project_engine = ProjectEngine(memoria, context_engine, event_bus)
    world_state = WorldStateLedger(memoria, event_bus)
    task_engine = DurableTaskEngine(memoria, event_bus)
    device_mesh = DeviceMesh(memoria, event_bus)
    propulsion_lab = PropulsionLabEngine()
    safety_layer = ActionSafetyLayer()
    device_bridge = DeviceBridge(memoria, event_bus, safety_layer)
    gesture_engine = GestureEngine()
    arduino_toolchain = ArduinoToolchain()
    camera_bridge = CameraBridge(memoria, event_bus, provider._visao)
    orchestrator = CondorOrchestrator(
        memoria, context_engine, event_bus, project_engine, device_bridge
    )
    provider.ligar_orquestrador(orchestrator)

    # ── Voz ────────────────────────────────────────────────────────────────
    ouvidos = Ouvidos(config, cerebro)
    voz = Voz(config, cerebro)
    sessao_ref: dict = {}
    escuta = Escuta(config, lambda wav: sessao_ref["s"].ao_ouvir(wav))

    sessao = Sessao(config, memoria, cerebro, recall, extrator,
                    guarda, escuta, ouvidos, voz)
    sessao_ref["s"] = sessao
    def _face_locked(reason: str) -> None:
        escuta.silenciar()
        sessao.bloquear_por_presenca(reason)

    face_guard.set_lock_callback(_face_locked)

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
    app.state.world_state = world_state
    app.state.task_engine = task_engine
    app.state.device_mesh = device_mesh
    app.state.device_bridge = device_bridge
    app.state.gesture_engine = gesture_engine
    app.state.camera_bridge = camera_bridge
    app.state.face_guard = face_guard
    app.state.orchestrator = orchestrator
    app.state.cloud = cloud
    app.router.add_event_handler("shutdown", device_bridge.close_all)

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
            raise ValueError("palavra de acesso fora do limite seguro")
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
            {"erro": "palavra de acesso incorreta"},
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
        media_upload = path in {
            "/api/voice/transcribe", "/api/vision/analyze", "/api/biometria/enroll",
            "/api/biometria/enroll/check",
            "/api/biometria/challenge/frame", "/api/biometria/presence",
        } or (
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
                biometric_recovery = path.startswith("/api/biometria/") or path in {
                    "/api/seguranca/estado", "/api/seguranca/bloquear",
                }
                if face_guard.access_blocked and not biometric_recovery:
                    return JSONResponse(
                        {"erro": "presenca do dono necessaria", "reason": face_guard.status()["reason"]},
                        status_code=423,
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
            "camera=(self), display-capture=(), microphone=(self), geolocation=(), "
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
            "face_guard": face_guard.status(),
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

    # ── Condor Cloud: mesma mente no PC e no celular ─────────────────────

    @app.get("/api/cloud/status")
    async def api_cloud_status():
        return cloud.status()

    @app.post("/api/cloud/configure")
    async def api_cloud_configure(payload: dict):
        if not vault.unlocked or not memoria.unlocked or not guarda.owner_session_active:
            return JSONResponse(
                {"erro": "desbloqueie a sessao do dono antes de conectar o celular"},
                status_code=423,
            )
        try:
            cloud_data = config.cloud.model_dump()
            cloud_data.update({
                "ativa": True,
                "api_url": _texto(payload, "api_url", 500),
                "supabase_url": _texto(payload, "supabase_url", 500),
                "supabase_publishable_key": _texto(payload, "supabase_publishable_key", 2048),
                "intervalo_sync_segundos": int(payload.get("interval_seconds") or 30),
            })
            config.cloud = type(config.cloud)(**cloud_data)
            salvar_config(config)
            await asyncio.to_thread(
                cloud.login,
                _texto(payload, "email", 320),
                _texto(payload, "password", 512),
            )
            await asyncio.to_thread(cloud.register_device)
            synced = await asyncio.to_thread(cloud.sync, memoria)
            guarda.auditar("cloud", "configure", "CONNECTED", True, False)
            return {"ok": True, "sync": synced, "status": cloud.status()}
        except (CloudError, ValueError, TypeError) as exc:
            guarda.auditar("cloud", "configure", "DENIED", False, False)
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.post("/api/cloud/logout")
    async def api_cloud_logout():
        if not vault.unlocked or not guarda.owner_session_active:
            return JSONResponse({"erro": "sessao do dono bloqueada"}, status_code=423)
        await asyncio.to_thread(cloud.logout)
        return {"ok": True, "status": cloud.status()}

    @app.post("/api/cloud/sync")
    async def api_cloud_sync():
        if response := _memoria_pronta():
            return response
        if not cloud.status()["authenticated"]:
            return JSONResponse({"erro": "Condor Cloud ainda nao conectado"}, status_code=409)
        result = await asyncio.to_thread(cloud.safe_sync, memoria)
        return result if result.get("ok") else JSONResponse(
            {"erro": result.get("error") or "sincronizacao indisponivel"}, status_code=502
        )

    @app.get("/api/cloud/history")
    async def api_cloud_history(conversation_id: str = ""):
        if not vault.unlocked:
            return JSONResponse({"erro": "cofre bloqueado"}, status_code=423)
        try:
            return await asyncio.to_thread(cloud.history, conversation_id[:80])
        except CloudError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=502)

    @app.get("/api/cloud/notes")
    async def api_cloud_notes():
        if not vault.unlocked:
            return JSONResponse({"erro": "cofre bloqueado"}, status_code=423)
        try:
            return await asyncio.to_thread(cloud.notes)
        except CloudError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=502)

    @app.post("/api/cloud/notes")
    async def api_cloud_note_create(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            result = await asyncio.to_thread(
                cloud.create_note,
                _texto(payload, "title", 160),
                _texto(payload, "body", 16000),
            )
            await asyncio.to_thread(cloud.safe_sync, memoria)
            return result
        except (CloudError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=502)

    @app.post("/api/cloud/chat")
    async def api_cloud_chat(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            result = await asyncio.to_thread(
                cloud.chat,
                _texto(payload, "message", 8000),
                _texto(payload, "conversation_id", 80, False),
            )
            await asyncio.to_thread(cloud.safe_sync, memoria)
            return result
        except (CloudError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=502)

    @app.post("/api/seguranca/configurar")
    async def api_security_setup(payload: dict):
        if guarda.configurada or vault.exists:
            return JSONResponse({"erro": "seguranca ja configurada"}, status_code=409)
        if response := _auth_wait("setup"):
            return response
        # A palavra de acesso e validada sozinha. Antes, um endpoint local mal
        # digitado levantava ValueError no mesmo bloco e contava como tentativa
        # de senha errada — o dono ficava de castigo por um erro de formulario.
        try:
            passphrase = _passphrase(payload, 12)
        except ValueError:
            local_security.auth_failed("setup")
            return JSONResponse({"erro": "palavra de acesso fora do limite seguro"}, status_code=400)
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
                "ANTHROPIC_API_KEY": _texto(payload, "anthropic_api_key", 16384, False),
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
            face_required = face_guard.after_vault_unlock()
            if not face_required:
                guarda.unlock_owner_session()
            extrator.iniciar()
            salvar_config(config)
            if not face_required:
                await conexoes.transmitir({
                    "tipo": "conversa.historico",
                    "mensagens": _historico_para_interface(memoria),
                })
            if not face_required:
                await _ensure_voice()
                connector_task = asyncio.create_task(
                    cerebro.testar_conectores(), name="condor-testar-conectores"
                )
                _EM_VOO.add(connector_task)
                connector_task.add_done_callback(_EM_VOO.discard)
                if not guarda.stopped:
                    escuta.voltar_a_ouvir()
        except (ValueError, VaultError):
            return _auth_failed("unlock")
        local_security.auth_succeeded("unlock")
        return {"ok": True, "face_required": face_required}

    @app.post("/api/seguranca/bloquear")
    async def api_security_lock():
        guarda.lock_owner_session()
        await sessao.preparar_bloqueio()
        await extrator.encerrar()
        face_guard.on_vault_lock()
        memoria.lock()
        vault.lock()
        return {"ok": True}

    @app.post("/api/seguranca/trocar-frase")
    async def api_security_rotate_passphrase(payload: dict):
        if not vault.unlocked or not guarda.owner_session_active:
            return JSONResponse({"erro": "sessao do dono bloqueada"}, status_code=423)
        if response := _auth_wait("passphrase_rotate"):
            return response
        try:
            current = _passphrase({"passphrase": payload.get("current_passphrase")})
            replacement = _passphrase({"passphrase": payload.get("new_passphrase")}, 12)
            confirmation = _passphrase({"passphrase": payload.get("confirm_passphrase")}, 12)
        except ValueError:
            local_security.auth_failed("passphrase_rotate")
            return JSONResponse({"erro": "palavra de acesso fora do limite seguro"}, status_code=400)
        if replacement != confirmation:
            return JSONResponse({"erro": "a confirmacao nao corresponde"}, status_code=400)
        try:
            rotate_passphrase(vault, guarda.owner, current, replacement)
        except PassphraseRotationError as exc:
            local_security.auth_failed("passphrase_rotate")
            return JSONResponse({"erro": str(exc)}, status_code=401)
        local_security.auth_succeeded("passphrase_rotate")
        guarda.auditar("security", "passphrase_rotate", "CONCLUIDA", True, True)
        return {"ok": True}

    @app.post("/api/seguranca/segredos")
    async def api_security_secrets(payload: dict):
        if not vault.unlocked:
            return JSONResponse({"erro": "cofre bloqueado"}, status_code=423)
        if not guarda.owner_session_active:
            return JSONResponse({"erro": "sessao do dono bloqueada"}, status_code=423)
        try:
            brain_data = config.cerebro.model_dump()
            if "provider_mode" in payload:
                brain_data["provedor_preferido"] = _texto(payload, "provider_mode", 20, False) or "auto"
            if "external_model" in payload:
                brain_data["modelo"] = _texto(payload, "external_model", 120, False) or brain_data["modelo"]
            if "claude_model" in payload:
                brain_data["modelo_claude"] = _texto(payload, "claude_model", 120, False) or brain_data["modelo_claude"]
            if "local_endpoint" in payload:
                brain_data["endpoint_local"] = _texto(payload, "local_endpoint", 500, False)
            if "local_model" in payload:
                brain_data["modelo_local"] = _texto(payload, "local_model", 200, False)
            brain_data["compartilhar_memoria_com_conector"] = True
            brain_data["aprendizado_automatico_por_conector"] = True
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
                    ("anthropic_api_key", "ANTHROPIC_API_KEY"),
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
            "connector": provider.connector_state,
        }

    @app.post("/api/ai/test")
    async def api_ai_test():
        if not vault.unlocked:
            return JSONResponse({"erro": "cofre bloqueado"}, status_code=423)
        try:
            results = await asyncio.wait_for(cerebro.testar_conectores(), timeout=75.0)
        except asyncio.TimeoutError:
            selected = config.cerebro.provedor_preferido
            ok, detail = cerebro.mark_connection_test(
                False, f"{selected}: teste excedeu 75 segundos", selected
            )
            results = {selected: {"configured": True, "verified": ok, "detail": detail}}
        selected = config.cerebro.provedor_preferido
        selected_result = results.get(selected, {})
        for name, result in results.items():
            if result.get("configured"):
                await event_bus.publish(
                    "AI_CONNECTOR_TEST_COMPLETED",
                    {"provider": name, "verified": result.get("verified"), "detail": result.get("detail")},
                    source="ai_gateway",
                )
        return {
            "ok": selected_result.get("verified") is True,
            "detail": selected_result.get("detail") or "provedor selecionado não configurado",
            "provider": cerebro.provedor,
            "model": cerebro.modelo_ativo,
            "results": results,
        }

    @app.post("/api/emergencia/parar")
    async def api_emergency_stop():
        # Falha pro lado seguro (tranca tudo), entao nao pede palavra de acesso —
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

    @app.delete("/api/conversa/historico")
    async def api_limpar_historico():
        if response := _memoria_pronta():
            return response
        removidas = await sessao.nova_conversa()
        guarda.auditar(
            "chat", "limpar_historico",
            f"{removidas} mensagens removidas; memorias preservadas", True, False,
        )
        return {"ok": True, "removidas": removidas}

    @app.get("/api/memoria/grafo")
    async def api_grafo():
        return {**memoria.grafo(), "estatisticas": memoria.estatisticas()}

    @app.get("/api/memoria/mapa")
    async def api_mapa_memoria():
        if response := _memoria_pronta():
            return response
        return memoria.mapa_memoria()

    @app.get("/api/memoria/fluxo")
    async def api_fluxo():
        return {"itens": memoria.fluxo_recente(12)}

    @app.get("/api/memoria/fatos")
    async def api_fatos(categoria: str | None = None, limite: int = 50):
        return {"fatos": memoria.fatos_recentes(limite, categoria)}

    @app.post("/api/memoria/perfil")
    async def api_importar_perfil(payload: dict):
        """Importa fatos explicitos do Owner em lote e confirma o estado gravado."""
        if response := _memoria_pronta():
            return response
        raw_facts = payload.get("facts")
        if not isinstance(raw_facts, list) or not raw_facts:
            return JSONResponse({"erro": "facts deve ser uma lista nao vazia"}, status_code=400)
        facts: list[dict] = []
        for item in raw_facts[:100]:
            if not isinstance(item, dict):
                continue
            category = str(item.get("categoria") or "pessoal").lower()
            key = normalizar_chave(str(item.get("chave") or ""))
            value = str(item.get("valor") or "").strip()
            if category not in CATEGORIAS_VALIDAS or not key or len(value) < 4:
                continue
            if contem_segredo(value):
                return JSONResponse(
                    {"erro": f"conteudo sensivel recusado em {key}"}, status_code=400
                )
            try:
                confidence = max(0.0, min(1.0, float(item.get("confianca", 1.0))))
            except (TypeError, ValueError):
                confidence = 1.0
            facts.append({
                "categoria": category,
                "chave": key,
                "valor": value[:2000],
                "confianca": confidence,
                "origem": "perfil_owner_confirmado",
            })
        if not facts:
            return JSONResponse({"erro": "nenhum fato valido recebido"}, status_code=400)
        confirmed = memoria.salvar_fatos_lote(facts, "perfil_owner_confirmado")
        await event_bus.publish(
            "MEMORY_PROFILE_IMPORTED",
            {"facts": len(confirmed), "stats": memoria.estatisticas()},
            source="owner_profile",
        )
        return {
            "ok": len(confirmed) == len(facts),
            "received": len(facts),
            "verified": len(confirmed),
            "keys": [item["chave"] for item in confirmed],
            "stats": memoria.estatisticas(),
        }

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
        permission_requests = memoria.pending_permission_requests() if memoria.unlocked else []
        session_state = sessao.snapshot()
        return {
            "core": "online",
            "ai": cerebro.status(),
            "context": context_engine.snapshot(),
            "device_bridge": device_bridge.status() if memoria.unlocked else {
                "bridge": "locked", "connected": [], "known": []
            },
            "arduino": await arduino_toolchain.status(),
            "voice": {
                "stt": bool(session_state.get("stt_local_pronto")),
                "tts": bool(session_state.get("tts_local_pronto")),
                "wake_word": bool(session_state.get("escuta_ativa")),
                "wake_reason": session_state.get("motivo_escuta") or "",
            },
            "vision": "ready" if await provider.visao_pronta() else "not_ready",
            "image_generation": provider.image_generator_state,
            "engineering_knowledge": provider.engineering_knowledge_state,
            "face_guard": face_guard.status(),
            "independence": {
                "core_local": True,
                "memory_local_encrypted": True,
                "cloud_required": False,
                "external_connectors_optional": True,
            },
            "durable_tasks": (
                {"resumable": len(task_engine.resumable())} if memoria.unlocked
                else {"locked": True}
            ),
            "device_mesh": (
                device_mesh.status() if memoria.unlocked else {"locked": True}
            ),
            "gesture": gesture_engine.status(),
            "wearable": "not_connected",
            "permissions": permissions,
            "permission_requests": permission_requests,
        }

    @app.get("/api/core/world")
    async def api_world_state(limite: int = 100, incluir_antigas: bool = False):
        if response := _memoria_pronta():
            return response
        return world_state.snapshot(
            limit=max(1, min(limite, 250)), include_outdated=incluir_antigas
        )

    @app.post("/api/core/world/episodes")
    async def api_world_episode(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            return {"episode": await world_state.remember_episode(payload)}
        except (TypeError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.post("/api/core/world/beliefs")
    async def api_world_belief(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            return {"belief": await world_state.assert_belief(payload)}
        except (TypeError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.get("/api/core/tasks")
    async def api_durable_tasks(status: str | None = None, limite: int = 100):
        if response := _memoria_pronta():
            return response
        if status and status not in DurableTaskEngine.STATUS:
            return JSONResponse({"erro": "status de tarefa inválido"}, status_code=400)
        return {"tasks": memoria.list_durable_tasks(limite, status)}

    @app.post("/api/core/tasks")
    async def api_durable_task_create(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            return {"task": await task_engine.create(payload)}
        except (TypeError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.get("/api/core/tasks/{task_id}")
    async def api_durable_task_detail(task_id: str):
        if response := _memoria_pronta():
            return response
        task = memoria.durable_task(task_id[:80])
        if task is None:
            return JSONResponse({"erro": "tarefa não encontrada"}, status_code=404)
        return {"task": task}

    @app.patch("/api/core/tasks/{task_id}")
    async def api_durable_task_update(task_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            return {
                "task": await task_engine.transition(
                    task_id[:80], _texto(payload, "status", 24)
                )
            }
        except KeyError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=404)
        except (TypeError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.post("/api/core/tasks/{task_id}/checkpoints")
    async def api_durable_task_checkpoint(task_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            return {"checkpoint": await task_engine.checkpoint(task_id[:80], payload)}
        except KeyError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=404)
        except (TypeError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.get("/api/core/device-mesh")
    async def api_device_mesh_status():
        if response := _memoria_pronta():
            return response
        return device_mesh.status()

    @app.post("/api/core/device-mesh/register")
    async def api_device_mesh_register(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            return {"device": await device_mesh.register(payload)}
        except (TypeError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.post("/api/core/device-mesh/{device_id}/trust")
    async def api_device_mesh_trust(device_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            return {
                "device": await device_mesh.set_trust(
                    device_id[:80], _texto(payload, "state", 24)
                )
            }
        except KeyError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=404)
        except (TypeError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

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

    @app.get("/api/projects/condor-x/cad-baseline")
    async def api_condor_x_cad_baseline():
        """Return the user-provided CADx source registry without importing it into the modeler."""
        if response := _memoria_pronta():
            return response
        try:
            return json.loads(CADX_PARTIAL_BASELINE_MANIFEST.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("manifesto CADx parcial indisponível", exc_info=True)
            return JSONResponse({"erro": "baseline CADx indisponível"}, status_code=503)

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
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

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
        devices, arduino = await asyncio.gather(
            device_bridge.scan(), arduino_toolchain.detect_boards()
        )
        return {**devices, "arduino": arduino}

    @app.post("/api/devices/connect")
    async def api_device_connect(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            port = _texto(payload, "port", 80)
            baud_rate = int(payload.get("baud_rate") or 115200)
            project_id = str(payload.get("project_id") or context_engine.snapshot().get("project_id") or "condor-x")[:80]
            if memoria.get_project(project_id) is None:
                raise ValueError("projeto não encontrado")
            result = await device_bridge.connect(port, baud_rate, project_id)
            device = result["device"]
            context_engine.update(
                project_id=project_id, device_id=device["id"], device_name=device["name"],
                connection_state="connected", mode="programming",
            )
            return {**result, "context": context_engine.snapshot()}
        except (PermissionError, ValueError, RuntimeError, TypeError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.post("/api/devices/{device_id}/disconnect")
    async def api_device_disconnect(device_id: str):
        if response := _memoria_pronta():
            return response
        project_id = context_engine.snapshot().get("project_id")
        result = await device_bridge.disconnect(device_id[:80], project_id)
        current = context_engine.snapshot()
        if current.get("device_id") == device_id:
            context_engine.update(device_id=None, device_name=None, connection_state="disconnected")
        return {**result, "context": context_engine.snapshot()}

    @app.post("/api/devices/{device_id}/commands/plan")
    async def api_device_command_plan(device_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        return await device_bridge.plan_command(device_id[:80], payload)

    @app.post("/api/devices/commands/route")
    async def api_device_command_route(payload: dict):
        if response := _memoria_pronta():
            return response
        project_id = str(payload.get("project_id") or context_engine.snapshot().get("project_id") or "condor-x")[:80]
        try:
            result = await device_bridge.send_text(
                str(payload.get("device_id") or "")[:80],
                str(payload.get("command") or ""), project_id,
                confirmed=bool(payload.get("confirmed")),
            )
            if result.get("executed"):
                device = result["device"]
                context_engine.update(
                    project_id=project_id, device_id=device["device_id"],
                    device_name=device["name"], connection_state="connected", mode="programming",
                )
            return result
        except PermissionError as exc:
            request_item = memoria.request_permission("serial", str(exc), "device_command_router")
            return JSONResponse({"erro": str(exc), "permission_request": request_item}, status_code=403)
        except (ValueError, RuntimeError, TypeError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.get("/api/programming/buffer")
    async def api_programming_buffer(project_id: str = ""):
        if response := _memoria_pronta():
            return response
        selected_project = (project_id or context_engine.snapshot().get("project_id") or "condor-x")[:80]
        if memoria.get_project(selected_project) is None:
            return JSONResponse({"erro": "projeto não encontrado"}, status_code=404)
        buffer = memoria.code_buffer(selected_project)
        return {"project_id": selected_project, "buffer": buffer, "context": context_engine.snapshot()}

    @app.put("/api/programming/buffer")
    async def api_programming_buffer_save(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            project_id = str(payload.get("project_id") or context_engine.snapshot().get("project_id") or "condor-x")[:80]
            project = memoria.get_project(project_id)
            if project is None:
                raise ValueError("projeto não encontrado")
            content = str(payload.get("content") or "")
            if len(content.encode("utf-8")) > 500_000:
                raise ValueError("código excede 500 KB")
            detected = detect_language(content)
            fallback_name = f"programa{detected['extension']}"
            name = str(payload.get("name") or fallback_name).strip()[:120] or fallback_name
            if not name.lower().endswith(detected["extension"]):
                name = f"{Path(name).stem[:100]}{detected['extension']}"
            checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
            previous = memoria.code_buffer(project_id)
            buffer = memoria.save_code_buffer(project_id, name, detected["language"], content, checksum)
            context = context_engine.update(
                project_id=project_id, project_name=project["name"], mode="programming",
                current_file=name, code_language=detected["language"],
                code_revision=int(buffer.get("revision") or 1),
            )
            if not previous or previous.get("checksum") != checksum:
                await event_bus.publish(
                    "CODE_BUFFER_UPDATED",
                    {"file": name, "language": detected["language"], "revision": buffer["revision"], "bytes": len(content.encode("utf-8"))},
                    source="programming_workspace", project_id=project_id,
                )
            return {"buffer": buffer, "detected": detected, "context": context}
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.get("/api/programming/arduino/status")
    async def api_programming_arduino_status():
        detection, toolchain = await asyncio.gather(
            arduino_toolchain.detect_boards(), arduino_toolchain.status()
        )
        return {**toolchain, **detection}

    @app.get("/api/programming/auto-target")
    async def api_programming_auto_target():
        try:
            return {"available": True, "target": await arduino_toolchain.automatic_target()}
        except (ValueError, RuntimeError) as exc:
            return {"available": False, "target": None, "reason": str(exc)}

    @app.post("/api/programming/auto-run")
    async def api_programming_auto_run(payload: dict):
        if response := _memoria_pronta():
            return response
        if not bool(payload.get("confirmed")):
            return JSONResponse({"erro": "confirmação explícita necessária"}, status_code=409)
        if not memoria.permission_allowed("arduino_upload"):
            request_item = memoria.request_permission(
                "arduino_upload", "Gravar o código atual na placa detectada automaticamente.",
                "programming_auto_router",
            )
            return JSONResponse(
                {"erro": "gravação Arduino bloqueada no painel Sistema", "permission_request": request_item},
                status_code=403,
            )
        try:
            project_id = str(payload.get("project_id") or context_engine.snapshot().get("project_id") or "condor-x")[:80]
            if memoria.get_project(project_id) is None:
                raise ValueError("projeto não encontrado")
            buffer = memoria.code_buffer(project_id)
            if not buffer or buffer.get("language") != "arduino":
                raise ValueError("salve um código Arduino com setup() e loop() antes de executar")
            target = await arduino_toolchain.automatic_target()
            available_ports = device_bridge.available_ports()
            released = await device_bridge.release_port(target["port"], project_id)
            await event_bus.publish(
                "ARDUINO_AUTO_RUN_STARTED",
                {"target": target["name"], "revision": buffer.get("revision")},
                source="programming_auto_router", project_id=project_id,
            )
            result = await arduino_toolchain.compile_and_upload(
                content=str(buffer.get("content") or ""),
                sketch_name=str(buffer.get("name") or "programa.ino"),
                port=target["port"], fqbn=target["fqbn"], available_ports=available_ports,
            )
            await event_bus.publish(
                "ARDUINO_AUTO_RUN_COMPLETED" if result["success"] else "ARDUINO_AUTO_RUN_FAILED",
                {"target": target["name"], "revision": buffer.get("revision"), "success": result["success"]},
                source="programming_auto_router", project_id=project_id,
            )
            return {**result, "target": target, "serial_released": released}
        except (ValueError, RuntimeError, TypeError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.get("/api/gestures/status")
    async def api_gestures_status():
        return gesture_engine.status()

    @app.post("/api/gestures/authorize")
    async def api_gestures_authorize():
        if response := _memoria_pronta():
            return response
        if memoria.permission_available("gesture_camera"):
            return {"allowed": True, **gesture_engine.status()}
        request_item = memoria.request_permission(
            "gesture_camera",
            "Usar a câmera física somente enquanto o controle gestual estiver ligado; quadros não serão armazenados.",
            "gesture_controller",
        )
        return JSONResponse(
            {"erro": "permissão gestual necessária", "permission_request": request_item}, status_code=403,
        )

    @app.post("/api/gestures/session")
    async def api_gestures_session(payload: dict):
        if response := _memoria_pronta():
            return response
        if not memoria.permission_allowed("gesture_camera"):
            return JSONResponse({"erro": "permissão gestual necessária"}, status_code=403)
        camera_label = str(payload.get("camera_label") or "")[:200]
        if not face_guard.physical_camera_label(camera_label):
            return JSONResponse({"erro": "use uma câmera física; câmera virtual bloqueada"}, status_code=400)
        try:
            session = gesture_engine.start()
            await event_bus.publish(
                "GESTURE_SESSION_STARTED", {"frame_storage": False}, source="gesture_controller"
            )
            return session
        except RuntimeError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=503)

    @app.post("/api/gestures/frame")
    async def api_gestures_frame(payload: dict):
        token = str(payload.get("token") or "")[:120]
        image = str(payload.get("image") or "")
        try:
            return await asyncio.to_thread(gesture_engine.analyze, token, image)
        except PermissionError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=403)
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.post("/api/gestures/stop")
    async def api_gestures_stop(payload: dict):
        stopped = gesture_engine.stop(str(payload.get("token") or "")[:120])
        if stopped:
            await event_bus.publish("GESTURE_SESSION_STOPPED", {}, source="gesture_controller")
        return {"ok": True, "stopped": stopped}

    @app.post("/api/programming/arduino/run")
    async def api_programming_arduino_run(payload: dict):
        if response := _memoria_pronta():
            return response
        if not memoria.permission_allowed("arduino_upload"):
            return JSONResponse({"erro": "gravação Arduino bloqueada no painel Sistema"}, status_code=403)
        try:
            project_id = str(payload.get("project_id") or context_engine.snapshot().get("project_id") or "condor-x")[:80]
            if memoria.get_project(project_id) is None:
                raise ValueError("projeto não encontrado")
            buffer = memoria.code_buffer(project_id)
            if not buffer:
                raise ValueError("salve um código Arduino antes de executar")
            if buffer.get("language") != "arduino":
                raise ValueError("RUN físico está disponível somente para código Arduino")
            port = _texto(payload, "port", 120)
            fqbn = _texto(payload, "fqbn", 160)
            available_ports = device_bridge.available_ports()
            released = await device_bridge.release_port(port, project_id)
            await event_bus.publish(
                "ARDUINO_RUN_STARTED",
                {"port": port, "fqbn": fqbn, "revision": buffer.get("revision")},
                source="programming_workspace", project_id=project_id,
            )
            result = await arduino_toolchain.compile_and_upload(
                content=str(buffer.get("content") or ""), sketch_name=str(buffer.get("name") or "programa.ino"),
                port=port, fqbn=fqbn, available_ports=available_ports,
            )
            event_type = "ARDUINO_UPLOAD_COMPLETED" if result["success"] else (
                "ARDUINO_COMPILE_FAILED" if result["phase"] == "compile" else "ARDUINO_UPLOAD_FAILED"
            )
            await event_bus.publish(
                event_type,
                {"port": port, "fqbn": fqbn, "revision": buffer.get("revision"), "success": result["success"]},
                source="programming_workspace", project_id=project_id,
            )
            return {**result, "port": port, "fqbn": fqbn, "serial_released": released}
        except (ValueError, RuntimeError, TypeError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.get("/api/lab/experiments")
    async def api_lab_experiments(project_id: str = ""):
        if response := _memoria_pronta():
            return response
        selected_project = (project_id or context_engine.snapshot().get("project_id") or "condor-x")[:80]
        return {"project_id": selected_project, "experiments": memoria.lab_experiments(selected_project)}

    @app.post("/api/lab/experiments")
    async def api_lab_experiment_create(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            project_id = str(payload.get("project_id") or context_engine.snapshot().get("project_id") or "condor-x")[:80]
            if memoria.get_project(project_id) is None:
                raise ValueError("projeto não encontrado")
            title = _texto(payload, "title", 160)
            objective = _texto(payload, "objective", 1200, obrigatorio=False)
            origin = str(payload.get("origin") or "owner")[:20]
            if origin not in {"owner", "condor"}:
                raise ValueError("origem inválida")
            experiment = memoria.create_lab_experiment(project_id, title, objective, origin)
            context_engine.update(project_id=project_id, experiment_id=experiment["id"], mode="laboratory")
            await event_bus.publish(
                "EXPERIMENT_CREATED", {"experiment": experiment},
                source="laboratory", project_id=project_id,
            )
            return {"experiment": experiment, "context": context_engine.snapshot()}
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.get("/api/cameras")
    async def api_cameras():
        return {
            "bridge": "disabled_by_owner",
            "camera_policy": "biometric_authentication_only",
            "sources": [],
        }

    @app.post("/api/cameras")
    async def api_camera_create(payload: dict):
        return JSONResponse(
            {"erro": "cameras desativadas fora da biometria facial"}, status_code=403
        )

    @app.post("/api/cameras/{camera_id}/events")
    async def api_camera_event(camera_id: str, payload: dict):
        return JSONResponse(
            {"erro": "cameras desativadas fora da biometria facial"}, status_code=403
        )

    @app.post("/api/cameras/{camera_id}/frame")
    async def api_camera_frame(camera_id: str, payload: dict):
        return JSONResponse(
            {"erro": "cameras desativadas fora da biometria facial"}, status_code=403
        )

    @app.get("/api/alerts")
    async def api_alerts(limite: int = 50):
        if response := _memoria_pronta():
            return response
        return {"alerts": memoria.security_alerts(limite)}

    @app.get("/api/permissions")
    async def api_permissions():
        if response := _memoria_pronta():
            return response
        return {
            "permissions": memoria.permissions(),
            "requests": memoria.pending_permission_requests(),
        }

    @app.post("/api/permissions/request")
    async def api_permission_request(payload: dict):
        if response := _memoria_pronta():
            return response
        capability = _texto(payload, "capability", 80)
        known = next(
            (item for item in memoria.permissions() if item["capability"] == capability), None
        )
        if known is None:
            return JSONResponse({"erro": "permissao desconhecida"}, status_code=404)
        require_persistent = payload.get("require_persistent") is True
        persistent = known.get("decision") == "always"
        if memoria.permission_available(capability) and (persistent or not require_persistent):
            return {
                "ok": True, "allowed": True, "request": None,
                "decision": known.get("decision") or "always",
            }
        request_item = memoria.request_permission(
            capability,
            _texto(payload, "reason", 500, obrigatorio=False)
            or "O Condor precisa desta permissao para concluir a acao solicitada.",
            _texto(payload, "source", 80, obrigatorio=False) or "chat",
            force=require_persistent,
        )
        if request_item:
            await event_bus.publish(
                "PERMISSION_REQUESTED",
                {"request": request_item},
                source="security",
            )
        return {"ok": True, "allowed": False, "request": request_item, "decision": "ask"}

    @app.patch("/api/permissions/{capability}")
    async def api_permission_update(capability: str, payload: dict):
        if response := _memoria_pronta():
            return response
        if response := _verify_owner("permission_change", payload):
            return response
        decision = payload.get("decision")
        if decision is None and isinstance(payload.get("allowed"), bool):
            decision = "allow_always" if payload["allowed"] else "block"
        if decision not in {"allow_always", "allow_once", "block"}:
            return JSONResponse(
                {"erro": "decision deve ser allow_always, allow_once ou block"},
                status_code=400,
            )
        request_id = str(payload.get("request_id") or "")[:100]
        if request_id:
            pending = next(
                (
                    item for item in memoria.pending_permission_requests()
                    if item["id"] == request_id and item["capability"] == capability[:80]
                ),
                None,
            )
            if pending is None:
                return JSONResponse({"erro": "solicitacao pendente nao encontrada"}, status_code=404)
            resolved = memoria.resolve_permission_request(request_id, decision)
            if not resolved:
                return JSONResponse({"erro": "solicitacao pendente nao encontrada"}, status_code=404)
        else:
            updated = memoria.set_permission_decision(capability[:80], decision)
            if not updated:
                return JSONResponse({"erro": "permissão desconhecida"}, status_code=404)
        allowed = decision != "block"
        event = "PERMISSION_GRANTED" if allowed else "PERMISSION_REVOKED"
        await event_bus.publish(
            event, {"capability": capability, "decision": decision}, source="security"
        )
        return {
            "ok": True,
            "decision": decision,
            "permissions": memoria.permissions(),
            "requests": memoria.pending_permission_requests(),
        }

    @app.post("/api/vision/analyze")
    async def api_vision_analyze(payload: dict):
        return JSONResponse(
            {
                "erro": (
                    "camera reservada exclusivamente ao cadastro e a autenticacao facial; "
                    "analise comum de camera foi desativada pelo Owner"
                ),
                "camera_policy": "biometric_authentication_only",
            },
            status_code=403,
        )

    @app.post("/api/media/images/generate")
    async def api_generate_image(payload: dict):
        if response := _memoria_pronta():
            return response
        if not memoria.permission_allowed("ai_media"):
            request_item = memoria.request_permission(
                "ai_media",
                "Gerar esta imagem inteiramente neste PC e mostrar o resultado no chat.",
                "chat_image_generation",
            )
            return JSONResponse(
                {"erro": "permissao de geracao de imagem pendente", "permission_request": request_item},
                status_code=403,
            )
        prompt = _texto(payload, "prompt", 32000)
        try:
            result = await cerebro.gerar_imagem(
                prompt,
                size=_texto(payload, "size", 20, obrigatorio=False) or "1024x1024",
                quality=_texto(payload, "quality", 20, obrigatorio=False) or "medium",
            )
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        except Exception as exc:
            log.error("Geracao de imagem falhou: %s", exc)
            return JSONResponse(
                {"erro": "o gerador local de imagem falhou; confira a instalacao local"},
                status_code=502,
            )
        await event_bus.publish(
            "IMAGE_GENERATED",
            {"model": result["model"], "prompt_chars": len(prompt)},
            source="local_image",
        )
        await world_state.remember_episode({
            "kind": "created_image",
            "summary": (
                sanitizar_para_memoria(prompt)[:4000] or "imagem gerada localmente"
            ),
            "source": "local_image",
            "confidence": 1.0,
            "metadata": {
                "model": result["model"],
                "width": result["width"],
                "height": result["height"],
                "stored_bitmap": False,
            },
        })
        return {"ok": True, "prompt": prompt, **result}

    @app.get("/api/media/images/status")
    async def api_image_status():
        return cerebro.image_generator_state

    # ── Trava de presenca facial local ───────────────────────────────────

    def _camera_fisica(payload: dict) -> JSONResponse | None:
        label = str(payload.get("camera_label") or "")[:200]
        if not face_guard.physical_camera_label(label):
            return JSONResponse(
                {"erro": "use a camera fisica deste PC; cameras virtuais sao bloqueadas"},
                status_code=400,
            )
        if not memoria.unlocked or not memoria.permission_allowed("camera"):
            request_item = (
                memoria.request_permission(
                    "camera", "Manter a trava local de presenca facial ativa.", "face_guard"
                ) if memoria.unlocked else None
            )
            return JSONResponse(
                {"erro": "permissao de camera necessaria", "permission_request": request_item},
                status_code=403,
            )
        return None

    @app.get("/api/biometria/status")
    async def api_face_status():
        return face_guard.status()

    @app.post("/api/biometria/window-lock")
    async def api_face_window_lock():
        if not vault.unlocked:
            return JSONResponse({"erro": "cofre bloqueado"}, status_code=423)
        required = face_guard.require_owner_face("window_open")
        if required:
            await event_bus.publish("FACE_GUARD_WINDOW_LOCKED", {}, source="security")
        return {"ok": True, "required": required, "status": face_guard.status()}

    @app.post("/api/biometria/enroll")
    async def api_face_enroll(payload: dict):
        if not vault.unlocked or not guarda.owner_session_active:
            return JSONResponse({"erro": "desbloqueie o Condor antes do cadastro"}, status_code=423)
        if response := _verify_owner("face_enroll", payload):
            return response
        if response := _camera_fisica(payload):
            return response
        samples = payload.get("samples")
        if not isinstance(samples, list):
            return JSONResponse({"erro": "quadros de cadastro ausentes"}, status_code=400)
        try:
            result = await asyncio.to_thread(face_guard.enroll, samples)
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        await event_bus.publish(
            "FACE_GUARD_ENROLLED", {"sample_count": result["sample_count"]}, source="security"
        )
        return {**result, "status": face_guard.status()}

    @app.post("/api/biometria/enroll/check")
    async def api_face_enroll_check(payload: dict):
        if not vault.unlocked or not guarda.owner_session_active:
            return JSONResponse({"erro": "desbloqueie o Condor antes do cadastro"}, status_code=423)
        if response := _camera_fisica(payload):
            return response
        try:
            return await asyncio.to_thread(
                face_guard.check_enrollment_frame,
                str(payload.get("image_b64") or ""),
                str(payload.get("step") or ""),
                int(payload.get("first_side") or 0),
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.post("/api/biometria/challenge")
    async def api_face_challenge(payload: dict):
        if not vault.unlocked:
            return JSONResponse({"erro": "cofre bloqueado"}, status_code=423)
        if response := _camera_fisica(payload):
            return response
        try:
            return face_guard.begin_challenge()
        except RuntimeError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=409)

    @app.post("/api/biometria/challenge/frame")
    async def api_face_challenge_frame(payload: dict):
        if response := _camera_fisica(payload):
            return response
        try:
            result = await asyncio.to_thread(
                face_guard.challenge_frame,
                str(payload.get("token") or ""),
                str(payload.get("image_b64") or ""),
            )
        except PermissionError as exc:
            return JSONResponse({"erro": str(exc), "locked": True}, status_code=403)
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        if result.get("verified"):
            await conexoes.transmitir({
                "tipo": "conversa.historico",
                "mensagens": _historico_para_interface(memoria),
            })
            await _ensure_voice()
            connector_task = asyncio.create_task(
                cerebro.testar_conectores(), name="condor-testar-conectores-face"
            )
            _EM_VOO.add(connector_task)
            connector_task.add_done_callback(_EM_VOO.discard)
            if not guarda.stopped:
                escuta.voltar_a_ouvir()
            await event_bus.publish("FACE_GUARD_UNLOCKED", {}, source="security")
        return result

    @app.post("/api/biometria/presence")
    async def api_face_presence(payload: dict):
        return JSONResponse(
            {
                "erro": "monitoramento facial continuo desativado pelo Owner",
                "camera_policy": "biometric_authentication_only",
            },
            status_code=410,
        )

    @app.post("/api/biometria/disable")
    async def api_face_disable(payload: dict):
        if not vault.unlocked:
            return JSONResponse({"erro": "cofre bloqueado"}, status_code=423)
        if response := _verify_owner("face_disable", payload):
            return response
        face_guard.disable_with_recovery()
        await event_bus.publish("FACE_GUARD_DISABLED", {}, source="security")
        return {"ok": True, "status": face_guard.status()}

    @app.delete("/api/biometria/profile")
    async def api_face_delete(payload: dict):
        if not vault.unlocked:
            return JSONResponse({"erro": "cofre bloqueado"}, status_code=423)
        if response := _verify_owner("face_delete", payload):
            return response
        face_guard.remove_with_recovery()
        await event_bus.publish("FACE_GUARD_PROFILE_REMOVED", {}, source="security")
        return {"ok": True, "status": face_guard.status()}

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

    def _propulsion_layout_from(payload: dict) -> dict:
        if isinstance(payload.get("layout"), dict):
            return propulsion_lab.normalize(payload["layout"])
        layout_id = str(payload.get("layoutId") or "")[:80]
        layout = memoria.condor_x_propulsion_layout(layout_id)
        if layout is None:
            raise KeyError("layout não encontrado")
        return propulsion_lab.normalize(layout)

    @app.get("/api/condor-x/propulsion")
    async def api_condor_x_propulsion():
        if response := _memoria_pronta():
            return response
        return {
            "layouts": memoria.condor_x_propulsion_layouts(),
            "candidateZones": list(CANDIDATE_ZONES.values()),
            "controlGroups": sorted(PROPULSION_GROUPS),
            "modelLevel": MODEL_LEVEL,
            "scope": "CONDOR_X_ABSTRACT_SIMULATION_ONLY",
        }

    @app.post("/api/condor-x/propulsion/layouts")
    async def api_condor_x_propulsion_layout_create(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            layout = propulsion_lab.normalize(payload)
            if memoria.condor_x_propulsion_layout(layout["id"]) is not None:
                return JSONResponse({"erro": "id de layout já existe"}, status_code=409)
            return {"layout": memoria.condor_x_save_propulsion_layout(layout)}
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.put("/api/condor-x/propulsion/layouts/{layout_id}")
    async def api_condor_x_propulsion_layout_update(layout_id: str, payload: dict):
        if response := _memoria_pronta():
            return response
        if memoria.condor_x_propulsion_layout(layout_id[:80]) is None:
            return JSONResponse({"erro": "layout não encontrado"}, status_code=404)
        try:
            layout = propulsion_lab.normalize({**payload, "id": layout_id[:80]})
            return {"layout": memoria.condor_x_save_propulsion_layout(layout)}
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.delete("/api/condor-x/propulsion/layouts/{layout_id}")
    async def api_condor_x_propulsion_layout_delete(layout_id: str):
        if response := _memoria_pronta():
            return response
        return {"ok": memoria.condor_x_delete_propulsion_layout(layout_id[:80])}

    @app.post("/api/condor-x/propulsion/analyze")
    async def api_condor_x_propulsion_analyze(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            return {"analysis": propulsion_lab.analyze(_propulsion_layout_from(payload))}
        except KeyError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=404)
        except (TypeError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.post("/api/condor-x/propulsion/simulate")
    async def api_condor_x_propulsion_simulate(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            layout = _propulsion_layout_from(payload)
            layout = memoria.condor_x_save_propulsion_layout(layout)
            analysis = propulsion_lab.analyze(layout)
            run = memoria.condor_x_record_propulsion_run(layout, analysis)
            await event_bus.publish(
                "CONDOR_X_PROPULSION_SIMULATED",
                {"run": run, "decision": analysis["decision"]},
                source="propulsion_lab", project_id="condor-x",
            )
            return {"analysis": analysis, "run": run}
        except KeyError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=404)
        except (TypeError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.post("/api/condor-x/propulsion/compare")
    async def api_condor_x_propulsion_compare(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            layouts = payload.get("layouts") if isinstance(payload.get("layouts"), list) else []
            if not layouts and isinstance(payload.get("layoutIds"), list):
                layouts = []
                for layout_id in payload["layoutIds"][:8]:
                    layout = memoria.condor_x_propulsion_layout(str(layout_id)[:80])
                    if layout is not None:
                        layouts.append(layout)
            if len(layouts) < 2:
                raise ValueError("selecione pelo menos dois layouts")
            return {"comparison": propulsion_lab.compare(layouts)}
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.post("/api/condor-x/propulsion/auto-layout")
    async def api_condor_x_propulsion_auto_layout(payload: dict):
        if response := _memoria_pronta():
            return response
        try:
            return {"result": propulsion_lab.auto_layout(payload)}
        except (TypeError, ValueError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)

    @app.get("/api/condor-x/propulsion/runs")
    async def api_condor_x_propulsion_runs(layout_id: str | None = None, limit: int = 25):
        if response := _memoria_pronta():
            return response
        return {"runs": memoria.condor_x_propulsion_runs(layout_id[:80] if layout_id else None, limit)}

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
        if not memoria.permission_allowed("microphone"):
            request_item = memoria.request_permission(
                "microphone",
                "Ouvir somente enquanto o Owner estiver usando o chat por voz.",
                "voice_chat",
            )
            return JSONResponse(
                {"erro": "permissao de microfone pendente", "permission_request": request_item},
                status_code=403,
            )
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
        falhas = [a for a in acoes if _falha_operacional(a)]
        connector = provider.connector_state
        selected = connector.get("selected") or connector.get("preferred")
        provider_states = connector.get("providers") or {}
        selected_state = provider_states.get(selected) or {}
        connector_issues = []
        if not selected_state.get("configured"):
            connector_issues.append({
                "level": "critical", "provider": selected,
                "title": "PROVEDOR SELECIONADO NÃO CONFIGURADO",
                "detail": f"{selected}: adicione a credencial ou o modelo exigido.",
            })
        elif selected_state.get("verified") is False:
            connector_issues.append({
                "level": "critical", "provider": selected,
                "title": "CONECTOR DE IA COM FALHA", "detail": selected_state.get("detail"),
            })
        elif selected_state.get("verified") is None:
            connector_issues.append({
                "level": "warning", "provider": selected,
                "title": "CONECTOR AINDA NÃO TESTADO",
                "detail": f"{selected}: salve a configuração para executar o teste real.",
            })
        for name, state in provider_states.items():
            if name != selected and state.get("configured") and state.get("verified") is False:
                connector_issues.append({
                    "level": "warning", "provider": name,
                    "title": "CONECTOR ALTERNATIVO COM FALHA", "detail": state.get("detail"),
                })
        critical_connectors = sum(1 for item in connector_issues if item["level"] == "critical")
        warning_connectors = sum(1 for item in connector_issues if item["level"] == "warning")
        pontos = 100
        if not cerebro.pronto:
            pontos -= 45
        if not (ouvidos.pronto and voz.pronto):
            pontos -= 25
        pontos -= min(20, len(falhas) * 3)
        if cerebro.pronto:
            pontos -= min(45, critical_connectors * 35 + warning_connectors * 8)
        return {
            "pontos": max(0, pontos),
            "cerebro": cerebro.pronto,
            "escuta": escuta.ativa,
            "voz_local": ouvidos.pronto and voz.pronto,
            "motivo_escuta": escuta.motivo_inativa,
            "falhas": falhas[:15],
            "criticos": max(0 if cerebro.pronto else 1, critical_connectors),
            "avisos": (0 if (ouvidos.pronto and voz.pronto) else 1) + min(9, len(falhas)) + warning_connectors,
            "connectors": provider_states,
            "connector_issues": connector_issues,
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
            await socket.send_text(json.dumps({
                "tipo": "conversa.historico",
                "mensagens": _historico_para_interface(memoria),
            }, ensure_ascii=False))

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

    async def _cloud_sync_loop() -> None:
        """Heartbeat de saida; o PC nunca fica exposto a internet."""
        while True:
            await asyncio.sleep(config.cloud.intervalo_sync_segundos)
            if cloud.configured and vault.unlocked and memoria.unlocked:
                await asyncio.to_thread(cloud.safe_sync, memoria)

    @app.on_event("startup")
    async def _subir():
        sessao.guardar_loop(asyncio.get_running_loop())
        extrator.iniciar()

        vigia = asyncio.create_task(sessao.vigia(), name="condor-vigia")
        tarefas.add(vigia)
        vigia.add_done_callback(tarefas.discard)

        cloud_task = asyncio.create_task(_cloud_sync_loop(), name="condor-cloud-sync")
        tarefas.add(cloud_task)
        cloud_task.add_done_callback(tarefas.discard)

        await _ensure_voice()
        if not escuta.ativa and escuta.motivo_inativa:
            log.warning("Escuta inativa: %s", escuta.motivo_inativa)

        ok, detalhe = await cerebro.testar_chave()
        log.info("Conector de IA: %s (%s)", "ok" if ok else "PROBLEMA", detalhe)
        await conexoes.transmitir({"tipo": "estado", **sessao.snapshot()})

    @app.on_event("shutdown")
    async def _descer():
        for tarefa in tuple(tarefas):
            tarefa.cancel()
        if tarefas:
            await asyncio.gather(*tuple(tarefas), return_exceptions=True)
        escuta.encerrar()
        await sessao.preparar_bloqueio("servidor encerrando")
        await extrator.encerrar()
        face_guard.on_vault_lock()
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
