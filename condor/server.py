"""
Servidor do Condor — FastAPI + WebSocket.

Monta todos os pedaços na ordem certa, serve a interface e mantém a janela
sincronizada com o que está acontecendo por voz.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from condor.actions.guard import Guarda
from condor.brain.client import Cerebro
from condor.config import Config
from condor.memory.db import Memoria
from condor.memory.extractor import Extrator
from condor.memory.migrar import migrar_se_preciso
from condor.memory.recall import Recall
from condor.session import Sessao
from condor.voice.stt import Ouvidos
from condor.voice.tts import Voz
from condor.voice.wake import Escuta

log = logging.getLogger("condor.servidor")

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"


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

    # ── Memória ────────────────────────────────────────────────────────────
    memoria = Memoria(DATA / "condor.db")
    memoria.inicializar()
    trazidas = migrar_se_preciso(memoria, DATA / "memory.db")
    if trazidas:
        log.info("Trouxe %d conversas do banco antigo.", trazidas)

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

    conexoes = Conexoes()
    sessao.ligar_avisos(conexoes.transmitir)

    # ── App ────────────────────────────────────────────────────────────────
    app = FastAPI(title="CONDOR", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def _sem_cache(request, call_next):
        resposta = await call_next(request)
        if request.url.path.startswith("/ui"):
            resposta.headers["Cache-Control"] = "no-store, must-revalidate"
            resposta.headers["Pragma"] = "no-cache"
        return resposta

    app.mount("/ui", StaticFiles(directory=str(Path(__file__).parent / "ui"), html=True),
              name="ui")

    @app.get("/")
    async def raiz():
        return RedirectResponse("/ui/index.html")

    @app.get("/api/estado")
    async def api_estado():
        return {**sessao.snapshot(),
                "memoria": memoria.estatisticas(),
                "custo": memoria.custo_hoje()}

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
        if not escuta.ativa:
            pontos -= 25
        pontos -= min(20, len(falhas) * 3)
        return {
            "pontos": max(0, pontos),
            "cerebro": cerebro.pronto,
            "escuta": escuta.ativa,
            "motivo_escuta": escuta.motivo_inativa,
            "falhas": falhas[:15],
            "criticos": 0 if cerebro.pronto else 1,
            "avisos": (0 if escuta.ativa else 1) + min(9, len(falhas)),
            "sistema": info_sistema()["saida"],
        }

    @app.post("/api/dormir")
    async def api_dormir():
        await sessao.dormir("pedido pela interface")
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
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

        if config.escuta.ativa:
            escuta.start()
            await asyncio.sleep(0.5)
            if not escuta.ativa and escuta.motivo_inativa:
                log.warning("Escuta inativa: %s", escuta.motivo_inativa)

        ok, detalhe = await cerebro.testar_chave()
        log.info("OpenAI: %s (%s)", "ok" if ok else "PROBLEMA", detalhe)
        await conexoes.transmitir({"tipo": "estado", **sessao.snapshot()})

    @app.on_event("shutdown")
    async def _descer():
        escuta.encerrar()
        await sessao.dormir("servidor encerrando")

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
