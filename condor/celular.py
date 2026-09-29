"""O CONDOR no iPhone: a mesma mente, por chat e por voz, em qualquer lugar.

O caminho é o Tailscale: o PC e o iPhone entram na mesma rede privada dele e o
``tailscale serve`` publica este app **só dentro dessa rede**, com HTTPS de
verdade (o Safari só libera o microfone com HTTPS). Nada fica aberto na
internet nem no Wi-Fi de casa: o servidor daqui escuta apenas no 127.0.0.1.

Mesmo dentro da rede privada, ninguém conversa sem parear: o QR code da aba
CELL traz um convite de uso único, de 5 minutos, e o pareamento ainda pede a
palavra de acesso do dono. O celular recebe um token longo, guardado num cookie
HttpOnly; aqui fica só o hash dele, e a aba CELL revoga quando quiser.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import math
import mimetypes
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from condor.paths import CODE_ROOT

log = logging.getLogger("condor.celular")
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")

UI_CELULAR = CODE_ROOT / "condor" / "celular_ui"
COOKIE = "__Host-condor_celular"
TOKEN_DIAS = 180
# Celular esquecido numa gaveta: sem uso por 14 dias, precisa parear de novo.
OCIOSO_DIAS = 14
CONVITE_SEGUNDOS = 5 * 60
CONVITE_TENTATIVAS = 5
MAX_APARELHOS = 8
MAX_SOCKETS = 6
# ~12 s de fala em WAV 16 kHz mono são ~384 KB; em base64, ~512 KB.
AUDIO_MAX_BYTES = 1_200_000
WS_MAX = 1_700_000
TEXTO_MAX = 8000

# O que o celular recebe do que a sessão anuncia. Só a conversa principal:
# eventos internos (core.event, custo, aba Programação) ficam no PC.
EVENTOS_DO_CELULAR = {
    "estado", "acordou", "dormiu", "transcricao", "resposta.token", "resposta.fim",
    "erro", "ocupado", "ferramenta.inicio", "ferramenta.fim", "senha.pedido",
    "senha.fim", "voz.parar", "conversa.historico", "conversa.limpa",
    "seguranca.bloqueado", "memoria.aprendeu",
}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def nome_seguro(valor: Any) -> str:
    limpo = re.sub(r"[^\w .'-]", "", str(valor or ""), flags=re.UNICODE)
    return " ".join(limpo.split())[:40] or "iPhone"


class Aparelhos:
    """Celulares pareados e o convite em aberto.

    Os hashes ficam num arquivo fora do cofre de propósito: com o PC recém
    ligado o cofre está trancado, e o celular precisa conseguir provar quem é
    para então destrancá-lo com a palavra de acesso. Um hash de token não
    serve para entrar; quem escreve nesta pasta já é dono do PC.
    """

    def __init__(self, arquivo: Path, relogio: Callable[[], float] = time.time) -> None:
        self.arquivo = arquivo
        self._relogio = relogio
        self._lock = threading.Lock()
        self._convite: tuple[str, float] | None = None
        self._tentativas = 0
        self._lista: list[dict] = self._ler()

    # ── Disco ──────────────────────────────────────────────────────────────

    def _ler(self) -> list[dict]:
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        lista = dados.get("aparelhos") if isinstance(dados, dict) else None
        if not isinstance(lista, list):
            return []
        validos = []
        for item in lista:
            if not (isinstance(item, dict) and re.fullmatch(r"[0-9a-f]{64}", str(item.get("hash") or ""))
                    and re.fullmatch(r"[0-9a-f]{12}", str(item.get("id") or ""))):
                continue
            try:
                datas = {k: float(item.get(k) or 0) for k in ("criado", "visto", "expira")}
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(v) for v in datas.values()):
                continue
            validos.append({"id": item["id"], "hash": item["hash"],
                            "nome": nome_seguro(item.get("nome")), **datas})
        return validos[:MAX_APARELHOS]

    def _gravar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.arquivo.with_suffix(".tmp")
        temporario.write_text(json.dumps({"versao": 1, "aparelhos": self._lista}, indent=2),
                              encoding="utf-8")
        temporario.replace(self.arquivo)
        try:
            self.arquivo.chmod(0o600)
        except OSError:
            pass

    # ── Convite (QR code) ──────────────────────────────────────────────────

    def novo_convite(self) -> dict:
        with self._lock:
            codigo = secrets.token_urlsafe(12)
            self._convite = (codigo, self._relogio() + CONVITE_SEGUNDOS)
            self._tentativas = 0
            return {"codigo": codigo, "expira_em": int(self._convite[1])}

    def convite_aberto(self) -> dict | None:
        with self._lock:
            if self._convite and self._convite[1] > self._relogio():
                return {"codigo": self._convite[0], "expira_em": int(self._convite[1])}
            return None

    def parear(self, codigo: str, senha_confere: Callable[[], bool], nome: str) -> tuple[str, dict]:
        """Troca convite válido + palavra de acesso por um token do aparelho."""
        with self._lock:
            convite = self._convite
            if not convite or convite[1] <= self._relogio():
                self._convite = None
                raise PermissionError("convite expirado; gere outro QR code no PC")
            if not secrets.compare_digest(str(codigo or "").encode("utf-8"), convite[0].encode("utf-8")):
                raise PermissionError("código ou palavra de acesso incorretos")
            if not senha_confere():
                self._tentativas += 1
                if self._tentativas >= CONVITE_TENTATIVAS:
                    # Chute demais queima o convite: força voltar ao PC.
                    self._convite = None
                raise PermissionError("código ou palavra de acesso incorretos")
            self._convite = None
            token = secrets.token_urlsafe(32)
            agora = self._relogio()
            aparelho = {
                "id": uuid.uuid4().hex[:12], "hash": _hash(token), "nome": nome_seguro(nome),
                "criado": agora, "visto": agora, "expira": agora + TOKEN_DIAS * 86400,
            }
            self._lista = [a for a in self._lista if a["expira"] > agora][-(MAX_APARELHOS - 1):]
            self._lista.append(aparelho)
            self._gravar()
            return token, self._publico(aparelho)

    # ── Uso ────────────────────────────────────────────────────────────────

    def validar(self, token: str | None) -> dict | None:
        if not token or len(token) > 200:
            return None
        procurado = _hash(token)
        agora = self._relogio()
        with self._lock:
            for aparelho in self._lista:
                if (secrets.compare_digest(aparelho["hash"], procurado) and aparelho["expira"] > agora
                        and agora - aparelho["visto"] < OCIOSO_DIAS * 86400):
                    # "Visto" vai ao disco no máximo a cada 10 min.
                    if agora - aparelho["visto"] > 600:
                        aparelho["visto"] = agora
                        try:
                            self._gravar()
                        except OSError:
                            pass
                    return self._publico(aparelho)
        return None

    def listar(self) -> list[dict]:
        agora = self._relogio()
        with self._lock:
            return [self._publico(a) for a in self._lista
                    if a["expira"] > agora and agora - a["visto"] < OCIOSO_DIAS * 86400]

    def revogar(self, aparelho_id: str) -> bool:
        with self._lock:
            antes = len(self._lista)
            self._lista = [a for a in self._lista if a["id"] != aparelho_id]
            if len(self._lista) != antes:
                self._gravar()
                return True
            return False

    @staticmethod
    def _publico(aparelho: dict) -> dict:
        return {k: aparelho[k] for k in ("id", "nome", "criado", "visto")}


class CanalCelular:
    """Os celulares conectados agora e quem recebe a voz do turno atual."""

    def __init__(self) -> None:
        self._sockets: list[WebSocket] = []
        self.alvo_voz = ""      # celular_id de quem fez o último pedido

    @property
    def total(self) -> int:
        return len(self._sockets)

    def entrar(self, ws: WebSocket, aparelho_id: str) -> None:
        ws.state.celular_id = uuid.uuid4().hex
        ws.state.aparelho_id = aparelho_id
        self._sockets.append(ws)

    def sair(self, ws: WebSocket) -> None:
        if ws in self._sockets:
            self._sockets.remove(ws)

    def derrubar(self, aparelho_id: str) -> None:
        """Aparelho revogado sai na hora, sem esperar reconectar."""
        for ws in [w for w in self._sockets if getattr(w.state, "aparelho_id", "") == aparelho_id]:
            self.sair(ws)
            tarefa = asyncio.ensure_future(_fechar(ws))
            _EM_VOO.add(tarefa)
            tarefa.add_done_callback(_EM_VOO.discard)

    @property
    def tem_player(self) -> bool:
        return any(getattr(ws.state, "voz_player", False) for ws in self._sockets)

    async def _enviar(self, ws: WebSocket, texto: str) -> None:
        try:
            await ws.send_text(texto)
        except Exception:
            self.sair(ws)

    async def transmitir(self, msg: dict) -> None:
        if msg.get("tipo") not in EVENTOS_DO_CELULAR or msg.get("contexto") == "programacao":
            return
        texto = json.dumps(msg, ensure_ascii=False)
        for ws in list(self._sockets):
            await self._enviar(ws, texto)

    async def entregar_voz(self, msg: dict) -> None:
        """Voz do turno pedido pelo celular: só no aparelho que toca áudio."""
        texto = json.dumps(msg, ensure_ascii=False)
        tocam = [w for w in self._sockets if getattr(w.state, "voz_player", False)]
        pediu = [w for w in tocam if getattr(w.state, "celular_id", "") == self.alvo_voz]
        for ws in (pediu or tocam)[:1]:
            await self._enviar(ws, texto)


async def _fechar(ws: WebSocket) -> None:
    try:
        await ws.close(code=1008)
    except Exception:
        pass


# ── Tailscale ──────────────────────────────────────────────────────────────

def _tailscale_exe() -> str | None:
    candidatos = []
    if sys.platform == "win32":
        candidatos.append(r"C:\Program Files\Tailscale\tailscale.exe")
    candidatos.append(shutil.which("tailscale"))
    for caminho in candidatos:
        if caminho and Path(caminho).is_file():
            return caminho
    return None


def _rodar_tailscale(*args: str, timeout: float = 15) -> tuple[int, str]:
    exe = _tailscale_exe()
    if not exe:
        return 127, "Tailscale não instalado"
    opcoes: dict[str, Any] = {}
    if sys.platform == "win32":
        opcoes["creationflags"] = 0x08000000   # CREATE_NO_WINDOW: nada pisca
    try:
        feito = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout, stdin=subprocess.DEVNULL, **opcoes)
        return feito.returncode, (feito.stdout or "") + (feito.stderr or "")
    except subprocess.TimeoutExpired as exc:
        saida = exc.stdout or ""
        if isinstance(saida, bytes):
            saida = saida.decode("utf-8", "replace")
        return 124, str(saida)
    except OSError as exc:
        return 126, str(exc)


_URL_TAILSCALE = re.compile(r"https://login\.tailscale\.com/[^\s\"']+")


def estado_tailscale() -> dict:
    """Instalado? Logado? Qual o endereço HTTPS deste PC na rede privada?"""
    if not _tailscale_exe():
        return {"instalado": False, "logado": False, "dns": "", "url": ""}
    codigo, saida = _rodar_tailscale("status", "--json")
    try:
        dados = json.loads(saida[saida.index("{"):]) if "{" in saida else {}
    except ValueError:
        dados = {}
    estado = str(dados.get("BackendState") or "")
    dns = str((dados.get("Self") or {}).get("DNSName") or "").rstrip(".")
    logado = estado == "Running" and bool(dns)
    return {
        "instalado": True, "logado": logado, "backend": estado, "dns": dns,
        "url": f"https://{dns}" if logado else "",
        "auth_url": url if (url := str(dados.get("AuthURL") or "")) and _URL_TAILSCALE.fullmatch(url) else "",
    }


def entrar_tailscale() -> str:
    """Pede o link de login do Tailscale (abre no navegador do PC)."""
    _, saida = _rodar_tailscale("up", "--json", "--timeout=8s", timeout=12)
    achado = _URL_TAILSCALE.search(saida)
    if achado:
        return achado.group(0)
    return str(estado_tailscale().get("auth_url") or "")


def publicar_no_tailscale(porta: int) -> dict:
    """``tailscale serve`` em segundo plano: HTTPS do tailnet → 127.0.0.1:porta.

    Se o HTTPS ainda não foi liberado na conta, o Tailscale devolve um link de
    uma vez só para o dono clicar; a configuração fica gravada e sobrevive a
    reinícios.
    """
    codigo, saida = _rodar_tailscale("serve", "--bg", "--yes", f"http://127.0.0.1:{porta}", timeout=20)
    if codigo == 0:
        return {"ok": True, "precisa_liberar": ""}
    achado = _URL_TAILSCALE.search(saida)
    if achado:
        # Desfaz só o que este pedido deixou pendurado, não o resto do serve do dono.
        _rodar_tailscale("serve", "--https=443", "off", timeout=10)
        return {"ok": False, "precisa_liberar": achado.group(0)}
    return {"ok": False, "precisa_liberar": "", "erro": saida.strip()[-300:]}


def publicado_no_tailscale(porta: int) -> bool:
    _, saida = _rodar_tailscale("serve", "status", "--json", timeout=8)
    return f"127.0.0.1:{porta}" in saida or f"localhost:{porta}" in saida


def qr_svg(texto: str) -> str:
    """QR code como data URI de SVG: entra num <img>, nunca como HTML."""
    import segno
    return segno.make(texto, error="m").svg_data_uri(scale=6, dark="#0b1220", light="#ffffff", border=2)


# ── O app que o iPhone abre ────────────────────────────────────────────────

def wav_valido(b64: Any) -> bytes | None:
    """Só WAV PCM razoável chega ao Whisper; o resto é descartado."""
    if not isinstance(b64, str) or len(b64) > (AUDIO_MAX_BYTES * 4) // 3 + 8:
        return None
    try:
        bruto = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(bruto) < 1000 or len(bruto) > AUDIO_MAX_BYTES:
        return None
    if not (bruto[:4] == b"RIFF" and bruto[8:12] == b"WAVE"):
        return None
    return bruto


class Pontes:
    """O que o app do celular precisa do núcleo, sem importar o servidor inteiro."""

    def __init__(self, *, pronto: Callable[[], bool], motivo: Callable[[], str],
                 destrancar: Callable[[str], Awaitable[dict]],
                 senha_confere: Callable[[str], bool],
                 texto: Callable[[str], Awaitable[None]],
                 audio: Callable[[bytes, bool], Awaitable[None]],
                 senha: Callable[[str], None], calar: Callable[[], Awaitable[None]],
                 estado: Callable[[], dict], historico: Callable[[], list[dict]]) -> None:
        self.pronto = pronto
        self.motivo = motivo
        self.destrancar = destrancar
        self.senha_confere = senha_confere
        self.texto = texto
        self.audio = audio
        self.senha = senha
        self.calar = calar
        self.estado = estado
        self.historico = historico


class _Limite:
    def __init__(self, quantos: int, janela: float) -> None:
        self.quantos, self.janela = quantos, janela
        self._marcas: deque[float] = deque()

    def pode(self) -> bool:
        agora = time.monotonic()
        while self._marcas and agora - self._marcas[0] > self.janela:
            self._marcas.popleft()
        if len(self._marcas) >= self.quantos:
            return False
        self._marcas.append(agora)
        return True


def host_permitido(host: str | None, porta: int) -> bool:
    """Só o nome do tailnet (via tailscale serve) ou o próprio PC."""
    host = str(host or "").strip().lower()
    nome = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    return nome.endswith(".ts.net") or host in {f"127.0.0.1:{porta}", f"localhost:{porta}"}


def montar_app_celular(aparelhos: Aparelhos, canal: CanalCelular, pontes: Pontes,
                       porta: int) -> FastAPI:
    app = FastAPI(title="CONDOR no celular", docs_url=None, redoc_url=None, openapi_url=None)
    limite_parear = _Limite(10, 600)
    limite_destrancar = _Limite(8, 600)

    def aparelho_de(request_ou_ws) -> dict | None:
        return aparelhos.validar(request_ou_ws.cookies.get(COOKIE))

    def mesma_origem(request_ou_ws) -> bool:
        """Origin (quando o navegador manda) precisa ser o próprio endereço.

        Compara só o nome: "host:443" e "host" são o mesmo lugar.
        """
        origem = request_ou_ws.headers.get("origin")
        if origem is None:
            return True
        try:
            partes = urlsplit(origem)
            porta_origem = partes.port
        except ValueError:
            return False
        host = str(request_ou_ws.headers.get("host") or "").lower()
        nome_host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        if not nome_host or (partes.hostname or "") != nome_host or partes.path not in {"", "/"}:
            return False
        if nome_host.endswith(".ts.net"):
            # Outra porta do mesmo nome é outro app (outro serve, um dev server).
            return partes.scheme == "https" and porta_origem in {None, 443}
        return partes.scheme in {"http", "https"} and partes.netloc == host

    @app.middleware("http")
    async def _guarda(request: Request, call_next):
        if not host_permitido(request.headers.get("host"), porta):
            return JSONResponse({"erro": "host inválido"}, status_code=400)
        try:
            tamanho = int(request.headers.get("content-length") or 0)
        except ValueError:
            return JSONResponse({"erro": "requisição inválida"}, status_code=400)
        if request.method not in {"GET", "HEAD"} and "content-length" not in request.headers:
            return JSONResponse({"erro": "tamanho obrigatório"}, status_code=411)
        if tamanho < 0 or tamanho > 8192:
            return JSONResponse({"erro": "requisição grande demais"}, status_code=413)
        if request.method != "GET" and not mesma_origem(request):
            return JSONResponse({"erro": "origem inválida"}, status_code=403)
        resposta = await call_next(request)
        resposta.headers["Cache-Control"] = "no-store"
        resposta.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; media-src 'self' blob: data:; worker-src 'self'; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["Referrer-Policy"] = "no-referrer"
        resposta.headers["X-Robots-Tag"] = "noindex, nofollow"
        resposta.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
        return resposta

    @app.get("/")
    async def _raiz():
        return RedirectResponse("/app/", status_code=307)

    @app.get("/api/eu")
    async def eu(request: Request):
        aparelho = aparelho_de(request)
        if aparelho is None:
            return JSONResponse({"pareado": False}, status_code=401)
        return {"pareado": True, "aparelho": aparelho, "pronto": pontes.pronto(),
                "motivo": pontes.motivo()}

    @app.post("/api/parear")
    async def parear(request: Request):
        if not limite_parear.pode():
            return JSONResponse({"erro": "muitas tentativas; espere alguns minutos"}, status_code=429)
        try:
            dados = await request.json()
            codigo = str(dados.get("codigo") or "")[:64]
            senha = str(dados.get("senha") or "")
            nome = str(dados.get("nome") or "")
        except Exception:
            return JSONResponse({"erro": "pedido inválido"}, status_code=400)
        if not 0 < len(senha) <= 512:
            return JSONResponse({"erro": "digite a palavra de acesso"}, status_code=400)
        try:
            token, aparelho = await asyncio.to_thread(
                aparelhos.parear, codigo, lambda: pontes.senha_confere(senha), nome)
        except PermissionError as exc:
            await asyncio.sleep(1.0)     # chute em série fica lento
            return JSONResponse({"erro": str(exc)}, status_code=403)
        log.info("Celular pareado: %s", aparelho["nome"])
        resposta = JSONResponse({"ok": True, "aparelho": aparelho})
        resposta.set_cookie(COOKIE, token, max_age=TOKEN_DIAS * 86400, httponly=True,
                            secure=True, samesite="strict", path="/")
        return resposta

    @app.post("/api/destrancar")
    async def destrancar(request: Request):
        if aparelho_de(request) is None:
            return JSONResponse({"erro": "pareie o celular primeiro"}, status_code=401)
        if not limite_destrancar.pode():
            return JSONResponse({"erro": "muitas tentativas; espere alguns minutos"}, status_code=429)
        try:
            senha = str((await request.json()).get("senha") or "")
        except Exception:
            return JSONResponse({"erro": "pedido inválido"}, status_code=400)
        if not 0 < len(senha) <= 512:
            return JSONResponse({"erro": "digite a palavra de acesso"}, status_code=400)
        resultado = await pontes.destrancar(senha)
        if not resultado.get("ok"):
            await asyncio.sleep(1.0)
            return JSONResponse({"erro": resultado.get("erro") or "palavra de acesso incorreta"},
                                status_code=403)
        return {"ok": True, "pronto": pontes.pronto(), "motivo": pontes.motivo()}

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        aparelho = aparelho_de(socket)
        if (aparelho is None or not host_permitido(socket.headers.get("host"), porta)
                or not mesma_origem(socket) or canal.total >= MAX_SOCKETS):
            await socket.close(code=1008)
            return
        await socket.accept()
        canal.entrar(socket, aparelho["id"])
        limite = _Limite(120, 60)
        try:
            await socket.send_text(json.dumps({"tipo": "estado", **pontes.estado()}, ensure_ascii=False))
            if pontes.motivo() == "trancado":
                await socket.send_text(json.dumps({"tipo": "seguranca.bloqueado"}))
            elif pontes.pronto():
                await socket.send_text(json.dumps(
                    {"tipo": "conversa.historico", "mensagens": pontes.historico()}, ensure_ascii=False))
            while True:
                bruto = await socket.receive_text()
                if len(bruto) > WS_MAX or not limite.pode() or aparelhos.validar(socket.cookies.get(COOKIE)) is None:
                    await socket.close(code=1008)
                    return
                try:
                    msg = json.loads(bruto)
                except ValueError:
                    continue
                if isinstance(msg, dict):
                    await _tratar(msg, socket)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            log.debug("Celular caiu: %s", exc)
        finally:
            canal.sair(socket)

    async def _responder(socket: WebSocket, msg: dict) -> None:
        try:
            await socket.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            pass

    async def _tratar(msg: dict, socket: WebSocket) -> None:
        tipo = msg.get("tipo")
        if tipo == "ping":
            await _responder(socket, {"tipo": "pong"})
            return
        if tipo == "voz.player":
            socket.state.voz_player = msg.get("ativo") is True
            return
        if tipo == "voz.parar":
            await pontes.calar()
            return
        if tipo == "senha":
            texto = str(msg.get("texto") or "").strip()
            if 0 < len(texto) <= 512:
                pontes.senha(texto)
            return
        if tipo not in {"texto", "audio"}:
            return
        if not pontes.pronto():
            await _responder(socket, {"tipo": "erro", "mensagem": pontes.motivo() or "Destranque o Condor."})
            return
        if getattr(socket.state, "em_voo", False):
            if tipo == "audio" and msg.get("com_nome") is True:
                return        # conversa ao redor durante a resposta: nem avisa
            await _responder(socket, {"tipo": "ocupado", "mensagem": "Espere eu terminar a resposta anterior."})
            return
        if tipo == "texto":
            texto = str(msg.get("texto") or "").strip()
            if not texto:
                return
            if len(texto) > TEXTO_MAX:
                await _responder(socket, {"tipo": "erro", "mensagem": "Mensagem grande demais."})
                return
            _soltar(pontes.texto(texto), socket)
            return
        wav = wav_valido(msg.get("wav"))
        if wav is None:
            await _responder(socket, {"tipo": "erro", "mensagem": "Não entendi o áudio; tente de novo."})
            return
        # com_nome: veio da escuta contínua, então precisa ter chamado "Condor".
        _soltar(pontes.audio(wav, msg.get("com_nome") is True), socket)

    def _soltar(coro: Awaitable[None], socket: WebSocket) -> None:
        socket.state.em_voo = True
        canal.alvo_voz = getattr(socket.state, "celular_id", "")

        async def rodar():
            try:
                await coro
            except Exception as exc:
                log.error("Turno do celular falhou: %s", type(exc).__name__)
                await _responder(socket, {"tipo": "erro",
                                          "mensagem": "Não consegui concluir esta resposta. Tente novamente."})
            finally:
                socket.state.em_voo = False
        tarefa = asyncio.create_task(rodar())
        _EM_VOO.add(tarefa)
        tarefa.add_done_callback(_EM_VOO.discard)

    app.mount("/app", StaticFiles(directory=str(UI_CELULAR), html=True), name="app")
    return app


_EM_VOO: set[asyncio.Task] = set()
