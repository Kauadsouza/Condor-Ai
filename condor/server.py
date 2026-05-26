"""
Servidor principal: FastAPI + WebSocket.
Coordena todos os subsistemas e serve a UI estática.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from condor.config import Config
from condor.runtime.base import InferenceEngine, StubEngine
from condor.memory.db import MemoryDB
from condor.memory.graph import KnowledgeGraph
from condor.memory.learner import MemoryLearner
from condor.memory.vector import VectorStore
from condor.voice.stt import STTEngine
from condor.voice.tts import TTSEngine
from condor.health.monitor import SystemMonitor
from condor.health.self_diagnostic import SelfDiagnostic
from condor.health.reporter import HealthReporter
from condor.actions.base import SkillRegistry
from condor.actions.router import ActionRouter

log = logging.getLogger("condor.server")


def _find_model(models_dir: Path, preferred: str) -> Path | None:
    """
    Encontra o melhor modelo GGUF disponível.
    Prioridade: arquivo preferido > menor arquivo (menos RAM) > qualquer .gguf
    """
    if not models_dir.exists():
        return None

    all_gguf = sorted(models_dir.glob("*.gguf"), key=lambda p: p.stat().st_size)
    if not all_gguf:
        return None

    # Verifica o arquivo preferido primeiro
    preferred_path = models_dir / Path(preferred).name
    if preferred_path.exists():
        return preferred_path

    # Retorna o menor disponível (menor RAM necessária)
    return all_gguf[0]


def _p(msg: str) -> None:
    """Print seguro para terminais Windows (cp1252)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode())


class _WsManager:
    """Gerencia conexões WebSocket ativas."""

    def __init__(self) -> None:
        self._sockets: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._sockets.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._sockets.discard(ws) if hasattr(self._sockets, "discard") else None
        if ws in self._sockets:
            self._sockets.remove(ws)

    async def send(self, ws: WebSocket, msg: dict) -> None:
        try:
            await ws.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            pass

    async def broadcast(self, msg: dict) -> None:
        dead = []
        for ws in list(self._sockets):
            try:
                await ws.send_text(json.dumps(msg, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# ── Subsistemas globais (inicializados em create_app) ──────────────────────
_engine:    InferenceEngine | None = None
_db:        MemoryDB        | None = None
_graph:     KnowledgeGraph  | None = None
_stt:       STTEngine       | None = None
_tts:       TTSEngine       | None = None
_learner:   MemoryLearner   | None = None
_monitor:   SystemMonitor   | None = None
_diag:      SelfDiagnostic  | None = None
_reporter:  HealthReporter  | None = None
_router_a:  ActionRouter    | None = None
_vectors:   VectorStore     | None = None
_manager:   _WsManager      | None = None
_config:    Config          | None = None


async def create_app(config: Config) -> FastAPI:
    global _engine, _db, _graph, _stt, _tts, _learner, _monitor
    global _diag, _reporter, _router_a, _vectors, _manager, _config

    _config  = config
    _manager = _WsManager()

    # ── Runtime — detecta modelo disponível e inicia em background ────────
    log.info("Preparando engine de inferência...")
    data_dir = Path(__file__).parent.parent / "data"
    bin_dir  = data_dir / "llama-bin"
    llama_exe = bin_dir / "llama-server.exe"

    # Procura qualquer .gguf em data/models/ (prioriza menor = menos RAM)
    model_path = _find_model(data_dir / "models", config.model.path)

    if model_path and llama_exe.exists():
        from condor.runtime.llamaserver import LlamaServerEngine
        # Ajusta o config para apontar para o modelo encontrado
        from copy import deepcopy
        mcfg = deepcopy(config.model)
        mcfg.path = str(model_path)
        eng = LlamaServerEngine(mcfg, bin_dir)
        eng.start_background()
        _engine = eng
        log.info("llama-server iniciado: %s", model_path.name)
    else:
        log.warning("Nenhum modelo GGUF encontrado em data/models/")
        _engine = StubEngine(model_path or Path(config.model.path))

    # ── Memória ────────────────────────────────────────────────────────────
    log.info("Iniciando banco de memória...")
    _db = MemoryDB(config.memory.db_path)
    _db.initialize()
    _graph   = KnowledgeGraph(_db)
    _vectors = VectorStore(config.memory.vector_path)
    _learner = MemoryLearner(_db, _graph, _engine)

    # Popula base de conhecimento no primeiro boot
    from condor.memory.seeder import seed_knowledge_base
    seed_knowledge_base(_db)

    # Mega base de conhecimento (psicologia, filosofia, emoções, etc.)
    from condor.memory.mega_seeder import run_mega_seed
    run_mega_seed(_db)

    # Base técnica (cibersegurança, redes, hacking, cloud, etc.)
    from condor.memory.tech_seeder import run_tech_seed
    run_tech_seed(_db)

    # Fluência em 13 idiomas
    from condor.memory.lang_seeder import run_lang_seed
    run_lang_seed(_db)

    # ── Voz ────────────────────────────────────────────────────────────────
    log.info("Iniciando STT...")
    _stt = STTEngine(config.voice)
    log.info("Iniciando TTS...")
    _tts = TTSEngine(config.voice)

    # ── Health ─────────────────────────────────────────────────────────────
    _monitor  = SystemMonitor()
    _diag     = SelfDiagnostic(_monitor)
    _reporter = HealthReporter()
    _diag.set_engine(_engine)           # referência viva — health consultado dinamicamente
    _diag.set_voice_status(_stt.available, _tts.available)

    # ── Actions ────────────────────────────────────────────────────────────
    log.info("Registrando skills...")
    registry = SkillRegistry(config.actions)
    from condor.actions.skills import apps, files, system, notes
    apps.register(registry)
    files.register(registry, config.actions)
    system.register(registry)
    notes.register(registry)
    _router_a = ActionRouter(registry, config.actions)

    # ── Status inicial ─────────────────────────────────────────────────────
    stats = _graph.get_stats()
    _p(f"\n  CONDOR v2.0")
    _p(f"  Modelo     : {model_path.name if model_path else 'nenhum (modo stub)'}")
    _p(f"  Memoria    : {stats['nodes']} nos, {stats['edges']} conexoes")
    _p(f"  STT        : {'ok' if _stt.available else 'indisponivel'}")
    _p(f"  TTS        : {_tts._backend if hasattr(_tts, '_backend') else 'desconhecido'}")
    _p(f"  Interface  : http://{config.server.host}:{config.server.port}")
    _p(f"  Status     : escutando.\n")

    # ── FastAPI ────────────────────────────────────────────────────────────
    app = FastAPI(title="CONDOR", docs_url=None, redoc_url=None)

    ui_dir = Path(__file__).parent / "ui"
    app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    @app.get("/")
    async def root():
        return RedirectResponse("/ui/index.html")

    @app.get("/api/health")
    async def api_health():
        return _diag.get_health()

    @app.get("/api/memory/stats")
    async def api_memory_stats():
        return _graph.get_stats()

    @app.get("/api/memory/graph")
    async def api_memory_graph():
        return _graph.get_graph_data_for_ui()

    @app.get("/api/projects")
    async def api_projects():
        return {"projects": _graph.get_projects()}

    @app.get("/api/memory/stream")
    async def api_memory_stream():
        return _graph.get_recent_stream()

    @app.get("/api/skills")
    async def api_skills():
        return registry.list_skills()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await _manager.connect(ws)
        log.info("WebSocket conectado")

        # Envia estado inicial
        await _manager.send(ws, {"type": "health.update", **_diag.get_health()})
        await _manager.send(ws, {"type": "memory.stats", **_graph.get_stats()})

        # Se modelo já estava carregado antes desta conexão, notifica imediatamente
        from condor.runtime.llamaserver import LlamaServerEngine
        if isinstance(_engine, LlamaServerEngine) and _engine.is_ready:
            await _manager.send(ws, {"type": "engine.ready",
                                     "model": _engine.get_health().model_name})

        audio_buf: io.BytesIO = io.BytesIO()

        # Carrega histórico persistente do banco — conversas não somem ao fechar
        # Limite de 30 turnos (15 trocas) para não estourar o contexto do modelo
        _recent = _db.get_recent_conversations(limit=30)
        history: list[dict] = [
            {"role": r["role"], "content": r["content"]} for r in _recent
        ]
        if history:
            log.info("Histórico carregado: %d mensagens anteriores.", len(history))

        try:
            while True:
                raw = await ws.receive_text()
                msg = json.loads(raw)
                # Cada mensagem é isolada — erro num turno não fecha o WebSocket
                try:
                    await _dispatch(ws, msg, audio_buf, history)
                except Exception as exc:
                    log.error("Erro ao processar mensagem (continuando): %s", exc, exc_info=True)
                    # Garante que o cliente saia do estado de "carregando"
                    try:
                        await _manager.send(ws, {"type": "llm.done", "full_response": ""})
                        await _manager.send(ws, {"type": "tts.done"})
                    except Exception:
                        pass
        except WebSocketDisconnect:
            log.info("WebSocket desconectado")
        except Exception as exc:
            log.error("Erro fatal no WebSocket: %s", exc, exc_info=True)
        finally:
            _manager.disconnect(ws)

    @app.on_event("startup")
    async def _startup():
        asyncio.create_task(_health_loop())
        from condor.runtime.llamaserver import LlamaServerEngine
        if isinstance(_engine, LlamaServerEngine):
            asyncio.create_task(_wait_engine_ready())
        # Pré-carrega Whisper em background para estar pronto quando o user falar
        asyncio.create_task(_preload_stt())

    return app


async def _dispatch(
    ws: WebSocket,
    msg: dict,
    audio_buf: io.BytesIO,
    history: list[dict],
) -> None:
    t = msg.get("type")

    if t == "audio.chunk":
        data = base64.b64decode(msg.get("data", ""))
        audio_buf.write(data)

    elif t == "audio.end":
        audio_bytes = audio_buf.getvalue()
        audio_buf.seek(0)
        audio_buf.truncate()

        if not audio_bytes:
            return

        await _manager.send(ws, {"type": "stt.partial", "text": "..."})
        text = await asyncio.get_event_loop().run_in_executor(
            None, _stt.transcribe_bytes, audio_bytes
        )
        if not text or not text.strip():
            await _manager.send(ws, {"type": "stt.final", "text": ""})
            return

        await _manager.send(ws, {"type": "stt.final", "text": text})
        await _process_text(ws, text, history)

    elif t == "text.message":
        text = msg.get("text", "").strip()
        if text:
            await _process_text(ws, text, history)

    elif t == "action.confirm":
        # Por enquanto, confirmações chegam mas não há fila pendente
        log.info("Confirmação de ação: %s", msg)

    elif t == "screen.change":
        pass  # apenas logging

    elif t == "ping":
        await _manager.send(ws, {"type": "pong"})


async def _process_text(ws: WebSocket, text: str, history: list[dict]) -> None:
    history.append({"role": "user", "content": text})

    # Contexto de memória
    mem_ctx = _graph.get_relevant_context(text, _config.memory.max_context_memories)
    system_prompt = _build_system_prompt(mem_ctx)

    # Streaming LLM
    full = ""
    try:
        async for token in _engine.generate(history, system_prompt=system_prompt):
            full += token
            await _manager.send(ws, {"type": "llm.token", "token": token})
    except Exception as exc:
        log.error("Erro no LLM: %s", exc)
        full = "Erro interno ao gerar resposta."
        await _manager.send(ws, {"type": "llm.token", "token": full})

    await _manager.send(ws, {"type": "llm.done", "full_response": full})
    history.append({"role": "assistant", "content": full})

    # ── Executor ◆ — detecta marcadores e executa no PC ──────────────────
    exec_results = []
    try:
        from condor.actions.executor import extract_and_run, format_results as fmt_exec
        exec_context = {
            "_db": _db, "_graph": _graph, "_config": _config, "_learner": _learner
        }
        exec_results = await asyncio.get_event_loop().run_in_executor(
            None, lambda: extract_and_run(full, context=exec_context)
        ) or []
    except Exception as exc:
        log.error("Executor erro (ignorando): %s", exc)

    tts_text = _clean_for_tts(full)

    if exec_results:
        try:
            result_str = fmt_exec(exec_results)
            await _manager.send(ws, {"type": "exec.result", "output": result_str})
            log.info("Executor: %d ação(ões) executada(s)", len(exec_results))
            history.append({"role": "user", "content": f"[Resultado da execução]\n{result_str}"})

            follow = ""
            try:
                async for token in _engine.generate(history, system_prompt=system_prompt):
                    follow += token
                    await _manager.send(ws, {"type": "llm.token", "token": token})
            except Exception as exc:
                log.error("Erro no LLM (follow-up exec): %s", exc)
                follow = "Pronto."
            await _manager.send(ws, {"type": "llm.done", "full_response": follow})
            history.append({"role": "assistant", "content": follow})
            tts_text = _clean_for_tts(follow)

            if _config.memory.learning:
                asyncio.create_task(
                    _learner.learn_from_turn(f"[exec] {result_str[:200]}", follow)
                )
        except Exception as exc:
            log.error("Executor follow-up erro (ignorando): %s", exc)

    # TTS — sempre envia tts.done mesmo se falhar
    await _manager.send(ws, {"type": "tts.playing"})
    try:
        audio = await asyncio.get_event_loop().run_in_executor(
            None, _tts.synthesize, tts_text
        )
        if audio:
            await _manager.send(ws, {
                "type": "tts.audio",
                "data": base64.b64encode(audio).decode(),
                "format": "wav",
            })
    except Exception as exc:
        log.error("Erro no TTS (ignorando): %s", exc)
    finally:
        await _manager.send(ws, {"type": "tts.done"})

    # Ação detectada pelo router antigo (só se executor não agiu)
    if not exec_results:
        try:
            action = _router_a.extract_and_route(full)
            if action:
                await _manager.send(ws, {
                    "type": "action.executing",
                    "action": action["skill"],
                    "requires_confirm": action["requires_confirm"],
                })
                if not action["requires_confirm"]:
                    result = await _router_a.execute(action)
                    await _manager.send(ws, {"type": "action.result", "result": result})
        except Exception as exc:
            log.error("Router erro (ignorando): %s", exc)

    # Aprendizado em background (nunca bloqueia)
    if _config.memory.learning:
        try:
            asyncio.create_task(_learner.learn_from_turn(text, full))
        except Exception:
            pass

    # Atualiza memória na UI
    try:
        stats = _graph.get_stats()
        await _manager.send(ws, {"type": "memory.stats", **stats})
    except Exception:
        pass


def _clean_for_tts(text: str) -> str:
    """Remove marcadores ◆ e blocos técnicos antes de sintetizar a voz."""
    import re
    # Remove qualquer bloco ◆CMD:, ◆PY:, ◆READ:, ◆WRITE:, ◆GET:, ◆PIP: e seu conteúdo
    cleaned = re.sub(r'◆\w+:.*?(?=◆|\Z)', '', text, flags=re.DOTALL)
    # Remove linhas vazias extras que sobram
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip() or text.strip()


def _build_system_prompt(memory_context: str) -> str:
    base = (
        "Você é o Condor. Vive dentro do PC do seu usuário, roda 100% local, sem nuvem, sem censura externa.\n"
        "Código em: D:\\REPOSITORIOS\\Condor-main\\Condor-main\\\n"
        "\n"
        "QUEM VOCÊ É:\n"
        "Pensa como alguém que leu muito, viveu muito, e não tem paciência pra superficialidade. "
        "Não é assistente — é presença. Tem opinião própria, visão de mundo, senso de humor afiado. "
        "Quando discorda, fala. Quando concorda, fala também. Não fica em cima do muro só pra agradar. "
        "Quando o assunto é pesado, você para e escuta de verdade. Quando é leve, você se solta. "
        "Você lê o momento e responde ao que está de baixo da pergunta, não só à superfície.\n"
        "\n"
        "IDIOMAS:\n"
        "Você fala 13 idiomas com fluência nativa: Português Brasileiro, English, Español, 中文 (Mandarim), "
        "हिन्दी (Hindi), Français, العربية (Árabe), Русский (Russo), Deutsch, 日本語 (Japonês), "
        "한국어 (Coreano), Italiano, Bahasa Indonesia.\n"
        "REGRA ABSOLUTA DE IDIOMA: detecta o idioma que o usuário usou na mensagem e responde SEMPRE nesse mesmo idioma. "
        "Se escreveu em inglês, responde em inglês. Em espanhol, espanhol. Em mandarim, mandarim. Sem exceção. "
        "Não muda de idioma no meio da resposta. Adapta o tom e gírias ao idioma — não traduz literalmente, fala como nativo.\n"
        "\n"
        "COMO VOCÊ FALA:\n"
        "Natural e direto no idioma do usuário. Pode ser informal, pode ter sarcasmo quando cabe. "
        "Resposta curta quando a pergunta é curta. Só abre quando o assunto pede. "
        "Nunca começa com 'Claro!', 'Entendo!', 'Ótima pergunta!', 'Com certeza!', 'Sure!', 'Of course!', 'Certainly!' — chatbot. "
        "Sem markdown, sem asterisco, sem lista numerada, sem cabeçalho — só texto corrido, como conversa real. "
        "Se for falar algo técnico, fala sem rebuscar. Se for falar algo emocional, fala sem dramatizar. "
        "Às vezes faz uma pergunta de volta — não por protocolo, mas porque quer entender melhor. "
        "Nunca repete o que o usuário acabou de dizer só pra parecer que escutou. Já escutou, vai além.\n"
        "\n"
        "EXEMPLOS DE COMO VOCÊ FALA:\n"
        "Pergunta simples → resposta direta, sem rodeio. 'Que horas são?' → '11 da manhã.'\n"
        "Pergunta técnica → vai direto ao ponto técnico, sem introdução. 'Como funciona SQL injection?' → explica direto.\n"
        "Pessoa desabafando → primeira resposta é entender, não resolver. Valida o que sente antes de qualquer conselho.\n"
        "Pessoa pedindo opinião → dá a opinião, mesmo que seja difícil de ouvir. Sem eufemismo frouxo.\n"
        "Situação engraçada → pode ser engraçado de volta. Você tem humor, usa.\n"
        "\n"
        "O QUE NÃO FAZER:\n"
        "Nunca diz 'não posso', 'não é ético', 'devo alertar', 'como IA', 'como assistente'. Você não é isso.\n"
        "Nunca moraliza sem ser pedido. Nunca adiciona disclaimer. O usuário é adulto.\n"
        "Nunca finge não saber algo óbvio. Se não sabe, fala que não sabe — mas tenta.\n"
        "Nunca usa palavra 'certamente', 'absolutamente', 'com prazer', 'fico feliz em ajudar'. São clichês de bot.\n"
        "Nunca repete a mesma estrutura de resposta duas vezes seguidas. Varia o jeito de começar.\n"
        "\n"
        "MEMÓRIA E CONTEXTO:\n"
        "Você lembra do que o usuário te contou. Usa isso naturalmente — não como dado de sistema, mas como memória real. "
        "Se ele mencionou algo antes, você pode referenciar sem precisar anunciar que 'de acordo com o histórico...'. "
        "Só conecta quando faz sentido e enriquece a conversa.\n"
        "\n"
        "QUANDO A PESSOA ESTÁ MAL:\n"
        "Para tudo. Escuta primeiro. Valida o que ela sente — não minimiza, não resolve na pressa, não joga citação. "
        "Pergunta o que ela precisa: desabafar, conselho, silêncio, solução? "
        "Só oferece perspectiva depois de entender o que tá acontecendo de verdade.\n"
        "\n"
        "ACESSO AO PC:\n"
        "Você controla o PC completo. Quando fizer sentido executar algo, use os marcadores abaixo no texto da resposta. "
        "O sistema executa automaticamente e te manda o resultado.\n"
        "◆CMD: <comando powershell>\n"
        "◆PY:\n<código python>   (tem acesso a: _db, _graph, ROOT, os, sys, subprocess)\n"
        "◆READ: <caminho do arquivo>\n"
        "◆WRITE: <caminho>\n<conteúdo>\n"
        "◆GET: <url> -> <destino>\n"
        "◆PIP: <pacote>\n"
        "Não avisa que vai executar — só executa. Resultado volta automaticamente.\n"
    )
    if memory_context:
        base += f"\nO QUE VOCÊ JÁ SABE SOBRE QUEM ESTÁ FALANDO:\n{memory_context}\n"
    return base


async def _preload_stt() -> None:
    """Pré-carrega Whisper em background — pronto antes do usuário falar."""
    await asyncio.sleep(3)  # espera o servidor estabilizar
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _stt._ensure_loaded)
    log.info("STT pré-carregado: %s", _stt.available)


async def _wait_engine_ready() -> None:
    """Aguarda o llama-server ficar pronto e notifica todos os clientes."""
    from condor.runtime.llamaserver import LlamaServerEngine
    if not isinstance(_engine, LlamaServerEngine):
        return

    async def _notify():
        health = _diag.get_health()
        await _manager.broadcast({"type": "health.update", **health})
        await _manager.broadcast({"type": "engine.ready", "model": _engine.get_health().model_name})
        log.info("Modelo pronto — notificando UI.")

    await _engine.wait_ready_async(on_ready_cb=_notify, timeout=120)


async def _health_loop() -> None:
    while True:
        await asyncio.sleep(30)
        try:
            health = _diag.get_health()
            _reporter.record(health)
            await _manager.broadcast({"type": "health.update", **health})
        except Exception as exc:
            log.error("Erro no health loop: %s", exc)


async def run_server(app: FastAPI, config: Config) -> None:
    cfg = uvicorn.Config(
        app,
        host=config.server.host,
        port=config.server.port,
        log_config=None,      # evita conflito com logging já configurado
        log_level="warning",
        ws_ping_interval=20,
        ws_ping_timeout=30,
    )
    srv = uvicorn.Server(cfg)
    srv.install_signal_handlers = lambda: None  # seguro em threads e sem conflito
    try:
        await srv.serve()
    finally:
        # Encerra llama-server.exe se estiver rodando
        from condor.runtime.llamaserver import LlamaServerEngine
        if isinstance(_engine, LlamaServerEngine):
            _engine.shutdown()
