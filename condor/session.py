"""
A sessão — o ciclo de vida do Condor no dia a dia.

    DORMINDO ──(você fala "Condor ...")──► ACORDADO
       ▲                                       │
       └──────(2 min sem te ouvir)─────────────┘

Dormindo ele não gasta nada: nenhuma chamada de API, nenhuma janela aberta.
Só o detector local rodando no microfone. Acordado, a janela abre e ele
responde. Passados 2 minutos sem você chamar, ele fecha tudo e volta a dormir.

Todo pedido começa chamando o nome dele — é a própria wake word que separa
"estou falando com o Condor" de "estou falando na sala".
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from condor.brain.offline import responder_offline

log = logging.getLogger("condor.sessao")

ROOT = Path(__file__).parent.parent

DORMINDO = "dormindo"
OUVINDO = "ouvindo"
PENSANDO = "pensando"
FALANDO = "falando"
SENHA = "senha"


class Sessao:
    def __init__(self, config, memoria, cerebro, recall, extrator,
                 guarda, escuta, ouvidos, voz) -> None:
        self._cfg = config
        self.memoria = memoria
        self.cerebro = cerebro
        self.recall = recall
        self.extrator = extrator
        self.guarda = guarda
        self.escuta = escuta
        self.ouvidos = ouvidos
        self.voz = voz

        self.estado = DORMINDO
        self.acordado = False
        self.ultimo_contato = 0.0
        self.historico: list[dict] = []
        self._janela: subprocess.Popen | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ocupado = asyncio.Lock()
        self._futuro_senha: asyncio.Future | None = None
        self._avisar: Callable[[dict], Awaitable[None]] | None = None

        guarda.registrar_pedido_senha(self._pedir_senha)

    # ── Ligações com o servidor ────────────────────────────────────────────

    def ligar_avisos(self, fn: Callable[[dict], Awaitable[None]]) -> None:
        """O servidor registra aqui como mandar evento pra interface."""
        self._avisar = fn

    async def _evento(self, tipo: str, **dados) -> None:
        if self._avisar:
            try:
                await self._avisar({"tipo": tipo, **dados})
            except Exception:
                pass

    async def _mudar_estado(self, novo: str) -> None:
        if novo != self.estado:
            self.estado = novo
            await self._evento("estado", estado=novo,
                               acordado=self.acordado,
                               restam=self.segundos_restantes())

    def segundos_restantes(self) -> int:
        if not self.acordado:
            return 0
        passou = time.time() - self.ultimo_contato
        return max(0, int(self._cfg.sessao.timeout_segundos - passou))

    # ── Entrada de voz (vem da thread da escuta) ───────────────────────────

    def guardar_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def ao_ouvir(self, wav: bytes) -> None:
        """Chamado DE DENTRO da thread do microfone. Só empurra pro laço
        de eventos e sai — nada pesado pode rodar aqui."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._processar_voz(wav), self._loop)

    async def _processar_voz(self, wav: bytes) -> None:
        try:
            await self._mudar_estado(PENSANDO)
            texto = await self.ouvidos.transcrever(wav)

            if not texto:
                log.info("Chamou mas não entendi nada.")
                await self._mudar_estado(OUVINDO if self.acordado else DORMINDO)
                return

            await self._evento("transcricao", texto=texto)
            await self.processar(texto, por_voz=True)
        finally:
            self.escuta.voltar_a_ouvir()

    # ── Entrada de texto (vem da janela) ───────────────────────────────────

    async def processar_texto(self, texto: str) -> None:
        if texto.strip():
            await self.processar(texto.strip(), por_voz=False)

    # ── O caminho comum ────────────────────────────────────────────────────

    async def processar(self, texto: str, por_voz: bool) -> None:
        if self._ocupado.locked():
            # Antes isto era um return mudo: quem digitava durante uma resposta
            # via a mensagem sumir da interface sem nenhum sinal, e nao tinha
            # como saber se o Condor recebeu.
            log.info("Já estou no meio de um pedido — avisando e ignorando o novo.")
            await self._evento(
                "ocupado",
                mensagem="Ainda estou terminando o pedido anterior. Manda de novo daqui a pouco.",
                texto=texto,
            )
            return

        async with self._ocupado:
            if not self.acordado:
                await self.acordar()
            self.ultimo_contato = time.time()

            if not self.cerebro.pronto:
                resposta = await responder_offline(texto, self.memoria, self.guarda)
                self.memoria.salvar_turno("user", texto)
                self.memoria.salvar_turno("assistant", resposta)
                await self._evento("resposta.fim", texto=resposta)
                if por_voz:
                    await self.voz.falar(resposta)
                await self._mudar_estado(OUVINDO)
                return

            await self._mudar_estado(PENSANDO)
            self.memoria.salvar_turno("user", texto)
            self.historico.append({"role": "user", "content": texto})
            self._podar_historico()

            referencia = ""
            if self._cfg.cerebro.compartilhar_memoria_com_conector:
                referencia = await self.recall.contexto_para(texto)

            async def on_token(t: str) -> None:
                await self._evento("resposta.token", texto=t)

            async def on_evento(ev: dict) -> None:
                await self._evento(ev.pop("tipo"), **ev)

            resposta = await self.cerebro.responder(
                self.historico, memoria_relevante=referencia, modo_voz=por_voz,
                on_token=on_token, on_evento=on_evento)

            await self._evento("resposta.fim", texto=resposta)
            self.memoria.salvar_turno("assistant", resposta)
            self.ultimo_contato = time.time()

            if self._cfg.cerebro.aprendizado_automatico_por_conector:
                self.extrator.enfileirar(texto, resposta)

            if por_voz and resposta:
                await self._mudar_estado(FALANDO)
                self.escuta.silenciar()
                try:
                    await self.voz.falar(resposta)
                finally:
                    self.escuta.voltar_a_ouvir()

            self.ultimo_contato = time.time()
            await self._mudar_estado(OUVINDO)
            await self._evento("memoria.stats", **self.memoria.estatisticas())
            await self._evento("custo", **self.memoria.custo_hoje())

    def _podar_historico(self, maximo: int = 30) -> None:
        """Segura o custo: mantém as últimas trocas, mas nunca corta no meio
        de uma chamada de ferramenta (deixaria mensagem órfã e a API recusa)."""
        if len(self.historico) <= maximo:
            return
        corte = len(self.historico) - maximo
        while corte < len(self.historico) and self.historico[corte].get("role") == "tool":
            corte += 1
        self.historico = self.historico[corte:]

    # ── Acordar e dormir ───────────────────────────────────────────────────

    async def acordar(self) -> None:
        if self.acordado:
            return
        self.acordado = True
        self.ultimo_contato = time.time()
        self.historico = []
        self.memoria.abrir_sessao()

        # Retoma o fio da última conversa, pra ele não parecer amnésico.
        anterior = self.memoria.historico(limite=6)
        if anterior:
            self.historico = anterior

        log.info("Acordei.")
        await self._evento("acordou")
        await self._mudar_estado(OUVINDO)

        if self._cfg.sessao.abrir_janela_ao_acordar:
            self._abrir_janela()

    async def dormir(self, motivo: str = "silêncio") -> None:
        if not self.acordado:
            return
        self.acordado = False
        log.info("Dormindo (%s).", motivo)

        self.memoria.fechar_sessao()
        self.historico = []
        await self._evento("dormiu", motivo=motivo)
        await self._mudar_estado(DORMINDO)

        if self._cfg.sessao.fechar_janela_ao_dormir:
            self._fechar_janela()

    async def vigia(self) -> None:
        """Roda pra sempre: cobra o relógio da sessão."""
        while True:
            await asyncio.sleep(3)
            try:
                if not self.acordado:
                    continue
                if self.estado in (PENSANDO, FALANDO, SENHA) or self._ocupado.locked():
                    self.ultimo_contato = time.time()
                    continue
                if self.segundos_restantes() <= 0:
                    await self.dormir("2 minutos sem chamado")
                else:
                    await self._evento("tique", restam=self.segundos_restantes())
            except Exception as exc:
                log.error("Vigia tropeçou: %s", exc)

    # ── A janela ───────────────────────────────────────────────────────────

    def _abrir_janela(self) -> None:
        script = ROOT / "condor_window.pyw"
        if not script.exists():
            return
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        executavel = str(pythonw if sys.platform == "win32" and pythonw.exists() else sys.executable)
        url = f"http://{self._cfg.servidor.host}:{self._cfg.servidor.porta}/ui/index.html"
        try:
            options = {"cwd": str(ROOT)}
            if sys.platform == "win32":
                options["creationflags"] = 0x08000000
            else:
                options["start_new_session"] = True
            process = subprocess.Popen([executavel, str(script), url], **options)
            if self._janela is None or self._janela.poll() is not None:
                self._janela = process
                log.info("Aplicativo local aberto.")
            else:
                log.info("Aplicativo local trazido para frente.")
        except Exception as exc:
            log.error("Não consegui abrir a janela: %s", exc)

    def abrir_aplicativo(self) -> bool:
        """Abre ou traz para frente somente a interface operacional local."""
        self._abrir_janela()
        return self._janela is not None and self._janela.poll() is None

    def _fechar_janela(self) -> None:
        if self._janela is None:
            return
        try:
            if self._janela.poll() is None:
                self._janela.terminate()
                try:
                    self._janela.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._janela.kill()
        except Exception as exc:
            log.debug("Falha ao fechar a janela: %s", exc)
        self._janela = None

    # ── A senha ────────────────────────────────────────────────────────────

    async def _pedir_senha(self, motivo: str, desafio: str) -> str | None:
        """Aprovacao local digitada.

        Voz nunca autoriza uma acao sensivel: gravacoes podem ser reproduzidas
        e transcricoes passam por um provedor externo.
        """
        estado_antes = self.estado
        await self._mudar_estado(SENHA)
        await self._evento("senha.pedido", motivo=motivo, desafio=desafio)

        laco = asyncio.get_running_loop()
        self._futuro_senha = laco.create_future()

        try:
            return await asyncio.wait_for(
                self._futuro_senha,
                timeout=float(self._cfg.seguranca.timeout_aprovacao),
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return None
        finally:
            self._futuro_senha = None
            await self._evento("senha.fim")
            await self._mudar_estado(estado_antes if self.acordado else DORMINDO)

    def responder_senha(self, texto: str) -> None:
        """A janela mandou a senha digitada."""
        if self._futuro_senha and not self._futuro_senha.done():
            self._futuro_senha.set_result(texto)

    # ── Estado pra interface ───────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        return {
            "estado": self.estado,
            "acordado": self.acordado,
            "restam": self.segundos_restantes(),
            "escuta_ativa": self.escuta.ativa if self.escuta else False,
            "stt_local_pronto": bool(getattr(self.ouvidos, "pronto", False)),
            "tts_local_pronto": bool(getattr(self.voz, "pronto", False)),
            "palavra": self.escuta.palavra if self.escuta else "",
            "motivo_escuta": self.escuta.motivo_inativa if self.escuta else "",
            "modelo": self.cerebro.modelo_ativo,
            "provedor": self.cerebro.provedor,
            "cerebro_pronto": self.cerebro.pronto,
            "timeout": self._cfg.sessao.timeout_segundos,
        }
