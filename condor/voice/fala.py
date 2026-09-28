"""Fala em tempo real: o Condor começa a falar enquanto ainda está pensando.

O texto chega token a token. Cada frase completa vai para o Piper assim que
fecha, e o áudio segue para quem toca:

- a janela do Condor, quando está aberta e com áudio liberado — ela toca em
  fila, respeita o cancelamento de eco do microfone e pode ser interrompida;
- o próprio PC (winsound), quando não há janela, como na palavra de ativação.

Enquanto uma frase toca, a próxima já está sendo sintetizada.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import re
import uuid
import wave
from typing import Awaitable, Callable

from condor.voice.tts import _preparar

log = logging.getLogger("condor.voz")

# Frase fecha em . ! ? … ou quebra de linha, seguida de espaço/fim.
_FIM_DE_FRASE = re.compile(r"[.!?…]+[\"')\]]*(?=\s)|\n+")
_LIMITE_FALADO = 1500     # o resto fica na tela, como antes
_PRIMEIRA_MINIMA = 12     # começa rápido...
_DEMAIS_MINIMA = 45       # ...e depois junta frases curtas para soar natural

Entrega = Callable[[dict], Awaitable[None]]


def duracao_wav(audio: bytes) -> float:
    try:
        with wave.open(io.BytesIO(audio), "rb") as arquivo:
            return arquivo.getnframes() / float(arquivo.getframerate() or 1)
    except Exception:
        return 0.0


class FalaEmFluxo:
    def __init__(self, voz, entregar_na_janela: Entrega | None = None) -> None:
        self._voz = voz
        self._entregar = entregar_na_janela
        self.turno = uuid.uuid4().hex[:12]
        self._buffer = ""
        self._em_codigo = False
        self._falado = 0
        self._esgotado = False
        self._seq = 0
        self._enfileiradas = 0
        self._inicio_janela = 0.0
        self._recebeu = False
        self._frases: asyncio.Queue[str | None] = asyncio.Queue()
        self._audios: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._duracao_enviada = 0.0
        self._cancelado = asyncio.Event()
        self._sintese = asyncio.create_task(self._sintetizar())
        self._tocador = None if self._entregar else asyncio.create_task(self._tocar_no_pc())

    @property
    def recebeu_texto(self) -> bool:
        return self._recebeu

    @property
    def cancelado(self) -> bool:
        return self._cancelado.is_set()

    def alimentar(self, trecho: str) -> None:
        if not trecho or self.cancelado or self._esgotado:
            return
        self._recebeu = True
        self._buffer += trecho
        self._cortar(final=False)

    def _cortar(self, final: bool) -> None:
        while True:
            texto = self._buffer
            if "```" in texto:
                antes, _, depois = texto.partition("```")
                if not self._em_codigo:
                    self._buffer = antes
                    self._cortar(final=True)
                    self._enfileirar("O código está na tela.")
                self._em_codigo = not self._em_codigo
                self._buffer = depois
                continue
            if self._em_codigo:
                # Descarta o código, mas guarda um possível ``` partido ao meio.
                self._buffer = texto[-2:]
                return
            minima = _PRIMEIRA_MINIMA if self._enfileiradas == 0 else _DEMAIS_MINIMA
            corte = None
            for fim in _FIM_DE_FRASE.finditer(texto):
                if fim.end() >= minima:
                    corte = fim.end()
                    break
            if corte is None:
                if final and texto.strip():
                    self._buffer = ""
                    self._enfileirar(texto)
                return
            self._buffer = texto[corte:]
            self._enfileirar(texto[:corte])

    def _enfileirar(self, frase: str) -> None:
        limpa = _preparar(frase)
        if len(limpa) < 2 or self._esgotado:
            return
        if self._falado + len(limpa) > _LIMITE_FALADO:
            self._esgotado = True
            limpa = "O resto está na tela."
        self._falado += len(limpa)
        self._enfileiradas += 1
        self._frases.put_nowait(limpa)

    async def terminar(self, texto_final: str = "") -> None:
        """Fecha o fluxo e espera o Condor terminar de falar (ou ser interrompido)."""
        if not self._recebeu and texto_final:
            self.alimentar(texto_final)
        if not self.cancelado:
            self._cortar(final=True)
        self._frases.put_nowait(None)
        cancelado = asyncio.create_task(self._cancelado.wait())
        try:
            await asyncio.wait({self._sintese, cancelado}, return_when=asyncio.FIRST_COMPLETED)
            if self._tocador is not None:
                await asyncio.wait({self._tocador, cancelado}, return_when=asyncio.FIRST_COMPLETED)
            elif not self.cancelado and self._duracao_enviada:
                # A janela toca no tempo dela; a sessão fica em FALANDO até lá.
                restante = self._duracao_enviada - (asyncio.get_running_loop().time() - self._inicio_janela)
                if restante > 0:
                    try:
                        await asyncio.wait_for(self._cancelado.wait(), timeout=restante + 0.3)
                    except asyncio.TimeoutError:
                        pass
        finally:
            cancelado.cancel()
            for tarefa in (self._sintese, self._tocador):
                if tarefa is not None and not tarefa.done() and self.cancelado:
                    tarefa.cancel()

    def cancelar(self) -> None:
        """Interrupção pelo dono: para de sintetizar e cala o que estiver tocando."""
        if self.cancelado:
            return
        self._cancelado.set()
        self._voz.calar()
        for tarefa in (self._sintese, self._tocador):
            if tarefa is not None and not tarefa.done():
                tarefa.cancel()

    async def _sintetizar(self) -> None:
        try:
            while True:
                frase = await self._frases.get()
                if frase is None or self.cancelado:
                    break
                audio = await self._voz.sintetizar(frase)
                if not audio or self.cancelado:
                    continue
                if self._entregar is not None:
                    await self._enviar_para_janela(audio)
                else:
                    await self._audios.put(audio)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("Fala em fluxo falhou: %s", exc)
        finally:
            if self._entregar is None:
                self._audios.put_nowait(None)

    async def _enviar_para_janela(self, audio: bytes) -> None:
        agora = asyncio.get_running_loop().time()
        if self._seq == 0:
            self._inicio_janela = agora
        elif agora - self._inicio_janela > self._duracao_enviada:
            # A janela ficou sem áudio esperando esta frase: o relógio anda.
            self._inicio_janela = agora - self._duracao_enviada
        duracao = duracao_wav(audio)
        await self._entregar({
            "tipo": "voz.audio",
            "turno": self.turno,
            "seq": self._seq,
            "wav": base64.b64encode(audio).decode("ascii"),
            "duracao": round(duracao, 3),
        })
        self._seq += 1
        self._duracao_enviada += duracao

    async def _tocar_no_pc(self) -> None:
        while True:
            audio = await self._audios.get()
            if audio is None or self.cancelado:
                return
            self._voz.marcar_tocando(True)
            try:
                await asyncio.to_thread(self._voz._tocar_bloqueante, audio)
            finally:
                self._voz.marcar_tocando(False)
