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
from condor.memory.db import Memoria
from condor.memory.extractor import Extrator
from condor.memory.recall import Recall
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


def _hub_inline_script_sources() -> str:
    """Retorna hashes CSP dos scripts inline exatos exportados pelo Next.js."""
    index = HUB_OUT / "index.html"
    if not index.is_file():
        return ""
    try:
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
    return " ".join(sources)


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

    # ── Cérebro ────────────────────────────────────────────────────────────
    recall = Recall(memoria)
    guarda = Guarda(config, memoria)
    cerebro = Cerebro(config, memoria, guarda, recall)
    recall.ligar_cerebro(cerebro)
    extrator = Extrator(memoria, cerebro, config)

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

    # ── App ────────────────────────────────────────────────────────────────
    app = FastAPI(title="CONDOR", docs_url=None, redoc_url=None)

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

    @app.middleware("http")
    async def _sem_cache(request, call_next):
        if not local_security.host_allowed(request.headers.get("host")):
            return JSONResponse({"erro": "host local invalido"}, status_code=400)
        if request.url.path.startswith("/api/") and request.url.path != "/api/session":
            if not local_security.token_valid(request.cookies.get(local_security.COOKIE)):
                return JSONResponse({"erro": "sessao local ausente"}, status_code=401)
        resposta = await call_next(request)
        if request.url.path.startswith(("/ui", "/hub")):
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
            "object-src 'none'; base-uri 'none'; frame-ancestors 'self'"
        )
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "SAMEORIGIN"
        resposta.headers["Referrer-Policy"] = "no-referrer"
        resposta.headers["Permissions-Policy"] = (
            "camera=(self), microphone=(self), geolocation=(), payment=()"
        )
        return resposta

    @app.post("/api/session")
    async def api_session(request: Request):
        if not local_security.origin_allowed(request.headers.get("origin")):
            return JSONResponse({"erro": "origem local invalida"}, status_code=403)
        response = JSONResponse({"ok": True, "nome": "Condor"})
        response.set_cookie(
            local_security.COOKIE,
            local_security.token,
            httponly=True,
            secure=False,
            samesite="strict",
            path="/",
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

    @app.post("/api/seguranca/configurar")
    async def api_security_setup(payload: dict):
        if guarda.configurada or vault.exists:
            return JSONResponse({"erro": "seguranca ja configurada"}, status_code=409)
        passphrase = str(payload.get("passphrase") or "")
        try:
            brain_data = config.cerebro.model_dump()
            brain_data["endpoint_local"] = str(
                payload.get("local_endpoint") or brain_data["endpoint_local"]
            )
            brain_data["modelo_local"] = str(payload.get("local_model") or "").strip()
            config.cerebro = type(config.cerebro)(**brain_data)
            guarda.configurar_dono(passphrase)
            vault.initialize(passphrase, {
                "CONDOR_DONO": str(payload.get("owner") or "Kaua"),
                "OPENAI_API_KEY": str(payload.get("openai_api_key") or ""),
                "PICOVOICE_ACCESS_KEY": str(payload.get("picovoice_access_key") or ""),
                "CONDOR_SAFETY_ID": base64.urlsafe_b64encode(os.urandom(24)).decode(),
                "MEMORY_KEY": base64.b64encode(os.urandom(32)).decode(),
            })
            identity.ensure()
            integrity.refresh()
            memoria.unlock(base64.b64decode(vault.get("MEMORY_KEY")))
            salvar_config(config)
            await _ensure_voice()
        except (ValueError, VaultError) as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        return {"ok": True}

    @app.post("/api/seguranca/desbloquear")
    async def api_security_unlock(payload: dict):
        try:
            vault.unlock(str(payload.get("passphrase") or ""))
            identity.ensure()
            memoria.unlock(base64.b64decode(vault.get("MEMORY_KEY")))
            await _ensure_voice()
        except VaultError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=403)
        return {"ok": True}

    @app.post("/api/seguranca/bloquear")
    async def api_security_lock():
        memoria.lock()
        vault.lock()
        return {"ok": True}

    @app.post("/api/seguranca/segredos")
    async def api_security_secrets(payload: dict):
        if not vault.unlocked:
            return JSONResponse({"erro": "cofre bloqueado"}, status_code=423)
        if not guarda.owner.verify(str(payload.get("passphrase") or "")):
            return JSONResponse({"erro": "frase secreta incorreta"}, status_code=403)
        try:
            brain_data = config.cerebro.model_dump()
            if "local_endpoint" in payload:
                brain_data["endpoint_local"] = str(payload.get("local_endpoint") or "")
            if "local_model" in payload:
                brain_data["modelo_local"] = str(payload.get("local_model") or "").strip()
            config.cerebro = type(config.cerebro)(**brain_data)
        except ValueError as exc:
            return JSONResponse({"erro": str(exc)}, status_code=400)
        changed: list[str] = []
        for field, secret_name in (
            ("openai_api_key", "OPENAI_API_KEY"),
            ("picovoice_access_key", "PICOVOICE_ACCESS_KEY"),
        ):
            if field in payload:
                vault.set(secret_name, str(payload.get(field) or "").strip())
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
        guarda.emergency_stop()
        await sessao.dormir("interruptor de emergencia")
        return {"ok": True}

    @app.post("/api/emergencia/retomar")
    async def api_emergency_resume(payload: dict):
        ok = guarda.emergency_resume(str(payload.get("passphrase") or ""))
        return JSONResponse({"ok": ok}, status_code=200 if ok else 403)

    @app.post("/api/seguranca/politica")
    async def api_security_policy(payload: dict):
        profile = str(payload.get("profile") or "")
        try:
            ok = guarda.update_policy(
                profile,
                bool(payload.get("simulation")),
                str(payload.get("passphrase") or ""),
            )
        except ValueError:
            return JSONResponse({"erro": "perfil de autonomia invalido"}, status_code=400)
        if not ok:
            return JSONResponse({"erro": "frase secreta incorreta"}, status_code=403)
        if "memory_sharing" in payload:
            config.cerebro.compartilhar_memoria_com_conector = bool(payload["memory_sharing"])
        if "connector_learning" in payload:
            config.cerebro.aprendizado_automatico_por_conector = bool(payload["connector_learning"])
        salvar_config(config)
        return {
            "ok": True,
            "profile": profile,
            "simulation": config.seguranca.simulacao,
            "memory_sharing": config.cerebro.compartilhar_memoria_com_conector,
            "connector_learning": config.cerebro.aprendizado_automatico_por_conector,
        }

    @app.post("/api/seguranca/integridade/recriar")
    async def api_integrity_refresh(payload: dict):
        if not vault.unlocked:
            return JSONResponse({"erro": "cofre bloqueado"}, status_code=423)
        if not guarda.owner.verify(str(payload.get("passphrase") or "")):
            return JSONResponse({"erro": "frase secreta incorreta"}, status_code=403)
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

    @app.get("/api/hub")
    async def api_hub():
        from condor.actions.executor import info_sistema

        snapshot = memoria.hub_snapshot()
        audit_ok, audit_count = guarda.verificar_auditoria()
        vision_ready = await cerebro.visao_pronta()
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
            "diagnostic": info_sistema()["saida"],
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
        status = str(payload.get("status") or "conceito")[:30]
        try:
            progresso = max(0, min(100, int(payload.get("progresso", 0))))
        except (TypeError, ValueError):
            return JSONResponse({"erro": "progresso invalido"}, status_code=400)
        return {"ok": memoria.hub_update_part(item_id[:80], status, progresso)}

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
            "sistema": info_sistema()["saida"],
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
                try:
                    msg = json.loads(bruto)
                except json.JSONDecodeError:
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
        if texto:
            # Solto numa tarefa pra não travar o WebSocket enquanto ele pensa —
            # é o que mantém a interface respondendo durante a resposta.
            tarefa = asyncio.create_task(sessao.processar_texto(texto))
            _EM_VOO.add(tarefa)
            tarefa.add_done_callback(_EM_VOO.discard)

    elif tipo == "senha":
        sessao.responder_senha((msg.get("texto") or "").strip())

    elif tipo == "acordar":
        await sessao.acordar()

    elif tipo == "dormir":
        await sessao.dormir("pedido pela janela")

    elif tipo == "ping":
        await socket.send_text(json.dumps({"tipo": "pong"}))


async def rodar(app: FastAPI, config: Config) -> None:
    cfg = uvicorn.Config(app, host=config.servidor.host, port=config.servidor.porta,
                         log_config=None, log_level="warning",
                         ws_ping_interval=20, ws_ping_timeout=40)
    servidor = uvicorn.Server(cfg)
    servidor.install_signal_handlers = lambda: None
    await servidor.serve()
