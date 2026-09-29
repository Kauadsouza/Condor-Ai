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
import base64
import binascii
import logging
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from condor.brain.offline import responder_offline
from condor.brain.persona import conversa_leve
from condor.voice.fala import FalaEmFluxo
from condor.memory.extractor import (
    pedido_explicito_memoria,
    pergunta_confirmacao_memoria,
    sanitizar_para_memoria,
)

log = logging.getLogger("condor.sessao")


def chamou_condor(texto: str) -> bool:
    """O nome precisa abrir a frase (até a 4ª palavra): "ei Condor, ..." vale;
    "falei do condor dos Andes no vídeo de ontem" no meio de uma conversa não."""
    palavras = re.findall(r"[a-zà-ÿ]+", str(texto or "").casefold())[:4]
    return "condor" in palavras

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
        # Pedidos de foto em voo, por id: a janela responde o mesmo id e
        # qualquer quadro com id desconhecido é descartado.
        self._fotos_pendentes: dict[str, asyncio.Future] = {}
        self._tem_janela: Callable[[], bool] = lambda: False
        self._avisar: Callable[[dict], Awaitable[None]] | None = None
        self._ultimo_aprendizado: dict | None = None
        self._tem_player: Callable[[], bool] = lambda: False
        self._fala: FalaEmFluxo | None = None

        guarda.registrar_pedido_senha(self._pedir_senha)

    # ── Ligações com o servidor ────────────────────────────────────────────

    def ligar_avisos(self, fn: Callable[[dict], Awaitable[None]]) -> None:
        """O servidor registra aqui como mandar evento pra interface."""
        self._avisar = fn

    def ligar_player(self, fn: Callable[[], bool],
                     entregar: Callable[[dict], Awaitable[None]] | None = None) -> None:
        """O servidor informa se alguma janela toca a voz e como mandar só para ela."""
        self._tem_player = fn
        self._entregar_audio = entregar

    def ligar_janelas(self, fn: Callable[[], bool]) -> None:
        """O servidor informa se existe alguma janela conectada agora."""
        self._tem_janela = fn

    def _nova_fala(self) -> FalaEmFluxo | None:
        if not getattr(self.voz, "pronto", False):
            return None
        destino = getattr(self, "_entregar_audio", None) or self._avisar
        entregar = destino if (destino and self._tem_player()) else None
        self._fala = FalaEmFluxo(self.voz, entregar)
        return self._fala

    async def _falar_ate_o_fim(self, fala: FalaEmFluxo, texto_final: str) -> None:
        await self._mudar_estado(FALANDO)
        self.escuta.silenciar()
        try:
            await fala.terminar(texto_final)
        finally:
            if self._fala is fala:
                self._fala = None
            self.escuta.voltar_a_ouvir()

    async def interromper_fala(self) -> None:
        """O dono falou por cima ou apertou Esc: o Condor cala na hora."""
        fala, self._fala = self._fala, None
        if fala is not None:
            fala.cancelar()
            await self._evento("voz.parar", turno=fala.turno)
        self.voz.calar()

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

    def bloquear_por_presenca(self, motivo: str) -> None:
        """Agenda o sono a partir da thread local de visao, sem bloquear inferencia."""
        if self._loop is None or self._loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(
            self.preparar_bloqueio(f"trava facial: {motivo}"), self._loop
        )

    def ao_ouvir(self, wav: bytes, confirmar_nome: bool = False) -> None:
        """Chamado DE DENTRO da thread do microfone. Só empurra pro laço
        de eventos e sai — nada pesado pode rodar aqui."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._processar_voz(wav, confirmar_nome=confirmar_nome), self._loop
        )

    async def _processar_voz(self, wav: bytes, confirmar_nome: bool = False) -> None:
        try:
            if confirmar_nome:
                # Detector sem chave: "com dor" e "Condor" soam iguais. Só
                # responde se o Whisper confirmar que o nome foi dito, e sem
                # mudar a tela antes disso (nada pisca num alarme falso).
                texto = await self.ouvidos.transcrever(wav)
                if not chamou_condor(texto):
                    log.info("Palavra de ativação não confirmada; ignorado.")
                    return
                await self._mudar_estado(PENSANDO)
            else:
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

    async def processar(self, texto: str, por_voz: bool, *, reproduzir_voz: bool = True) -> None:
        # asyncio.Lock e justo: pedidos simultaneos aguardam aqui na ordem em
        # que chegaram. Nada e descartado se voz, outra janela ou uma corrida de
        # rede enviar enquanto o Condor ainda esta fechando a resposta anterior.
        async with self._ocupado:
            if not self.acordado:
                await self.acordar()
            self.ultimo_contato = time.time()
            await self._mudar_estado(PENSANDO)

            # Fatos pessoais inequívocos são registrados antes da resposta. É
            # rápido, local e funciona até quando Ollama ou uma API falham.
            aprendizado = await self.extrator.aprender_local(texto)
            pedido_de_memoria = pedido_explicito_memoria(texto)
            verificacao_de_memoria = pergunta_confirmacao_memoria(texto)
            if (aprendizado.get("saved") or aprendizado.get("unchanged")
                    or pedido_de_memoria):
                self._ultimo_aprendizado = dict(aprendizado)

            aprendizado_resposta = aprendizado
            if verificacao_de_memoria:
                aprendizado_resposta = dict(self._ultimo_aprendizado or {
                    "saved": [], "unchanged": [], "complete": False,
                    "verified_count": 0,
                })
                aprendizado_resposta["verification"] = True

            # Credencial digitada no chat nunca segue para modelo/conector e
            # também não fica escondida dentro do histórico cifrado.
            # Aprender um fato durante uma conversa normal nao substitui mais a
            # resposta inteligente. A confirmacao deterministica assume o turno
            # inteiro apenas quando o dono pediu explicitamente para salvar ou
            # verificar, quando um segredo foi bloqueado, ou quando nao ha IA.
            if (aprendizado.get("blocked")
                    or not bool(getattr(self.memoria, "unlocked", True))
                    or not self.cerebro.pronto
                    or pedido_de_memoria
                    or verificacao_de_memoria):
                resposta = await responder_offline(
                    texto, self.memoria, self.guarda, aprendizado=aprendizado_resposta,
                )
                fala_dono = sanitizar_para_memoria(texto)
                fala_condor = sanitizar_para_memoria(resposta)
                self._salvar_turno_seguro("user", fala_dono)
                self._salvar_turno_seguro("assistant", fala_condor)
                self.historico.extend((
                    {"role": "user", "content": fala_dono},
                    {"role": "assistant", "content": fala_condor},
                ))
                self._podar_historico()
                if not aprendizado.get("blocked") and not verificacao_de_memoria:
                    # "Lembra que..." e conversa sem cérebro também são
                    # analisados: a fila cifrada espera o modelo ficar pronto.
                    self.extrator.enfileirar(texto, resposta)
                await self._evento("resposta.fim", texto=resposta, fontes=[])
                if por_voz and reproduzir_voz and (fala := self._nova_fala()):
                    await self._falar_ate_o_fim(fala, resposta)
                await self._mudar_estado(OUVINDO)
                await self._evento("memoria.stats", **self.memoria.estatisticas())
                await self._evento("custo", **self.memoria.custo_hoje())
                return

            self.historico.append({"role": "user", "content": texto})
            self._podar_historico()

            # A memória é sempre do Condor. O provedor ativo recebe somente os
            # trechos relevantes recuperados do banco cifrado local.
            # A fala atual ainda não foi persistida, portanto não reaparece
            # falsamente dentro de "conversas anteriores" no próprio prompt.
            # "oi", "valeu", "tudo bem?": resposta curta, sem memória nem
            # ferramentas. "sim"/"ok" logo depois de uma pergunta dele são
            # resposta a ela, não papo, e seguem o caminho normal.
            anterior = next((m.get("content", "") for m in reversed(self.historico[:-1])
                             if m.get("role") == "assistant"), "")
            leve = conversa_leve(texto) and not str(anterior).rstrip().endswith("?")
            referencia = "" if leve else await self.recall.contexto_para(texto)
            self._salvar_turno_seguro("user", texto)

            # Voz: cada frase pronta já vai sendo falada enquanto o resto é gerado.
            fala = self._nova_fala() if (por_voz and reproduzir_voz) else None

            async def on_token(t: str) -> None:
                await self._evento("resposta.token", texto=t)
                if fala is not None:
                    fala.alimentar(t)

            ferramentas_usadas = 0
            anteriores = [dict(m) for m in self.historico[:-1]]

            async def on_evento(ev: dict) -> None:
                nonlocal ferramentas_usadas
                if ev.get("tipo") == "ferramenta.inicio":
                    ferramentas_usadas += 1
                await self._evento(ev.pop("tipo"), **ev)

            try:
                resposta = await self.cerebro.responder(
                    self.historico, memoria_relevante=referencia, modo_voz=por_voz,
                    on_token=on_token, on_evento=on_evento, conversa_leve=leve)
            except BaseException:
                if fala is not None:
                    fala.cancelar()
                    self._fala = None
                raise

            treino_id = self._registrar_exemplo(
                texto, resposta, referencia, anteriores, por_voz, ferramentas_usadas,
            )
            await self._evento(
                "resposta.fim", texto=resposta,
                fontes=list(getattr(self.cerebro, "ultimas_fontes", []) or []),
                treino_id=treino_id,
            )
            resposta_memoria = sanitizar_para_memoria(resposta)
            self._salvar_turno_seguro("assistant", resposta_memoria)
            if self.historico and self.historico[-1].get("role") == "assistant":
                self.historico[-1]["content"] = resposta_memoria
            else:
                self.historico.append({"role": "assistant", "content": resposta_memoria})
                self._podar_historico()
            self.ultimo_contato = time.time()

            self.extrator.enfileirar(texto, resposta)

            if fala is not None:
                if resposta:
                    await self._falar_ate_o_fim(fala, resposta)
                else:
                    fala.cancelar()
                    self._fala = None

            self.ultimo_contato = time.time()
            await self._mudar_estado(OUVINDO)
            await self._evento("memoria.stats", **self.memoria.estatisticas())
            await self._evento("custo", **self.memoria.custo_hoje())

    def _registrar_exemplo(self, pedido: str, resposta: str, contexto: str,
                           anteriores: list[dict], por_voz: bool, ferramentas: int) -> str:
        """Guarda a troca como exemplo de treino, quando ela pode ensinar algo.

        Fica de fora: resposta que não veio de um modelo (erro, reserva offline),
        turno com ferramenta (treinar "abri o Spotify" sem a chamada real
        ensinaria o modelo a fingir que executou) e qualquer segredo.
        """
        if (ferramentas or not resposta.strip()
                or not bool(getattr(self.cerebro, "ultimo_turno_valido", False))
                or not bool(getattr(self.memoria, "unlocked", False))
                or sanitizar_para_memoria(pedido) != pedido
                or sanitizar_para_memoria(resposta) != resposta):
            return ""
        try:
            return self.memoria.registrar_exemplo(
                pedido, resposta, contexto=contexto, anteriores=anteriores,
                provedor=str(getattr(self.cerebro, "provedor", "")),
                modelo=str(getattr(self.cerebro, "modelo_ativo", "")),
                por_voz=por_voz,
            )
        except Exception as exc:
            log.warning("Exemplo de treino não registrado: %s", exc)
            return ""

    def _salvar_turno_seguro(self, papel: str, conteudo: str) -> None:
        """Não cria a ilusão de persistência quando o cofre já foi bloqueado."""
        if not bool(getattr(self.memoria, "unlocked", True)):
            return
        self.memoria.salvar_turno(papel, sanitizar_para_memoria(conteudo))

    def _podar_historico(self, maximo: int = 30) -> None:
        """Segura o custo: mantém as últimas trocas, mas nunca corta no meio
        de uma chamada de ferramenta (deixaria mensagem órfã e a API recusa)."""
        if len(self.historico) <= maximo:
            return
        corte = len(self.historico) - maximo
        while corte < len(self.historico) and self.historico[corte].get("role") == "tool":
            corte += 1
        self.historico = self.historico[corte:]

    async def nova_conversa(self, preservar_historico: bool = False) -> int:
        """Encerra o fio atual e começa outro sem apagar a memória aprendida."""
        async with self._ocupado:
            if not bool(getattr(self.memoria, "unlocked", False)):
                raise RuntimeError("cofre bloqueado")
            self.memoria.fechar_sessao("nova conversa iniciada pelo dono")
            if preservar_historico:
                self.memoria.arquivar_conversa()
                removidas = 0
            else:
                removidas = self.memoria.limpar_conversas()
            self.historico = []
            if self.acordado:
                self.memoria.abrir_sessao()
                self.ultimo_contato = time.time()
            await self._evento("conversa.limpa", removidas=removidas)
            await self._evento("memoria.stats", **self.memoria.estatisticas())
            return removidas

    # ── Acordar e dormir ───────────────────────────────────────────────────

    async def acordar(self) -> None:
        if self.acordado:
            return
        self.acordado = True
        self.ultimo_contato = time.time()
        self.historico = []
        self.memoria.abrir_sessao()

        # Retoma o fio só se a última mensagem foi há pouco (ele dorme em 2 min).
        # Conversa de horas atrás no contexto fazia o modelo responder a ela
        # junto com o "oi" novo.
        anterior = self.memoria.historico(limite=6)
        ultimo = float(getattr(self.memoria, "ultimo_turno_em", lambda: 0.0)() or 0.0)
        if anterior and (not ultimo or time.time() - ultimo < 15 * 60):
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

    async def preparar_bloqueio(self, motivo: str = "cofre bloqueado") -> None:
        """Espera o turno em voo terminar antes de fechar a memória persistente."""
        async with self._ocupado:
            await self.dormir(motivo)

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

    # ── A câmera amiga ─────────────────────────────────────────────────────

    FOTO_MAX_BYTES = 3 * 1024 * 1024

    @property
    def aguardando_foto(self) -> bool:
        return bool(self._fotos_pendentes)

    async def capturar_camera(self, timeout: float = 15) -> str:
        """Pede UMA foto à janela e devolve o JPEG/PNG em base64.

        Só o navegador abre a webcam (no Windows ela é exclusiva e a janela já
        sabe recusar câmera virtual). A janela liga, tira a foto e desliga na
        hora; aqui a foto só passa, nunca é gravada.
        """
        if not self._tem_janela():
            raise RuntimeError("a janela do Condor não está aberta; abra ela para eu usar a câmera")
        pedido_id = uuid.uuid4().hex
        futuro = asyncio.get_running_loop().create_future()
        self._fotos_pendentes[pedido_id] = futuro
        try:
            await self._evento("camera.capturar", id=pedido_id)
            return await asyncio.wait_for(futuro, timeout=float(timeout))
        except asyncio.TimeoutError:
            raise RuntimeError("a câmera não respondeu a tempo") from None
        finally:
            self._fotos_pendentes.pop(pedido_id, None)

    def responder_camera(self, pedido_id: str, image_b64: str | None = None,
                         erro: str | None = None) -> bool:
        """A janela mandou a foto (ou o motivo de não ter tirado)."""
        futuro = self._fotos_pendentes.get(str(pedido_id or ""))
        if futuro is None or futuro.done():
            return False
        if erro or not image_b64:
            motivo = str(erro or "a janela não mandou a foto").strip()[:200]
            futuro.set_exception(RuntimeError(f"câmera: {motivo}"))
            return True
        try:
            valido = self._foto_valida(image_b64)
        except ValueError as exc:
            futuro.set_exception(RuntimeError(f"câmera: {exc}"))
            return True
        futuro.set_result(valido)
        return True

    @classmethod
    def _foto_valida(cls, image_b64: str) -> str:
        texto = str(image_b64).strip()
        if texto.startswith("data:"):
            texto = texto.split(",", 1)[-1]
        # Base64 de 3 MB passa de 4 MB: corta antes de decodificar lixo gigante.
        if len(texto) > (cls.FOTO_MAX_BYTES * 4) // 3 + 8:
            raise ValueError("foto grande demais")
        try:
            bruto = base64.b64decode(texto, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("foto em formato inválido") from None
        if len(bruto) > cls.FOTO_MAX_BYTES:
            raise ValueError("foto grande demais")
        if not (bruto.startswith(b"\xff\xd8\xff") or bruto.startswith(b"\x89PNG\r\n\x1a\n")):
            raise ValueError("a foto precisa ser JPEG ou PNG")
        return texto

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
