"""
Voz — o Condor falando, pela API da OpenAI.

O áudio toca direto no alto-falante pelo winsound (nativo do Windows, sem
dependência e sem janela). Enquanto ele fala, a escuta fica muda: senão a
própria voz dele no alto-falante dispararia a wake word de novo.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys

log = logging.getLogger("condor.voz")

CUSTO_POR_MILHAO_CHARS = 15.0     # tts-1

if sys.platform == "win32":
    import winsound
else:
    winsound = None


def _preparar(texto: str) -> str:
    """Tira o que não se fala: markdown, caminho gigante, bloco de código."""
    t = re.sub(r"```.*?```", " (código na tela) ", texto, flags=re.DOTALL)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"[*_#>|]", "", t)
    t = re.sub(r"https?://\S+", "o link que está na tela", t)
    t = re.sub(r"[A-Za-z]:\\[^\s]{25,}", "o caminho que está na tela", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


class Voz:
    def __init__(self, config, cerebro) -> None:
        self._cfg = config
        self._cerebro = cerebro
        self._tocando = False

    @property
    def tocando(self) -> bool:
        return self._tocando

    async def sintetizar(self, texto: str) -> bytes | None:
        limpo = _preparar(texto)
        if not limpo:
            return None
        # Resposta muito longa vira maratona falada. Corta no fim de frase.
        if len(limpo) > 1200:
            corte = limpo[:1200].rsplit(".", 1)[0]
            limpo = (corte or limpo[:1200]) + ". O resto está na tela."

        try:
            resposta = await self._cerebro.cliente.audio.speech.create(
                model=self._cfg.voz.modelo_tts,
                voice=self._cfg.voz.voz,
                input=limpo,
                speed=self._cfg.voz.velocidade,
                response_format="wav",
            )
            audio = resposta.content
        except Exception as exc:
            log.error("TTS falhou: %s", exc)
            return None

        try:
            self._cerebro.memoria.registrar_uso(
                self._cfg.voz.modelo_tts, 0, 0,
                len(limpo) * CUSTO_POR_MILHAO_CHARS / 1_000_000)
        except Exception:
            pass
        return audio

    def _tocar_bloqueante(self, audio: bytes) -> None:
        if winsound is None:
            return
        try:
            winsound.PlaySound(audio, winsound.SND_MEMORY)
        except Exception as exc:
            log.error("Não consegui tocar o áudio: %s", exc)

    async def falar(self, texto: str) -> bool:
        """Sintetiza e toca até o fim. Devolve se conseguiu falar."""
        audio = await self.sintetizar(texto)
        if not audio:
            return False
        self._tocando = True
        try:
            await asyncio.to_thread(self._tocar_bloqueante, audio)
        finally:
            self._tocando = False
        return True

    def calar(self) -> None:
        """Corta a fala no meio — usado quando você chama ele de novo."""
        if winsound is not None:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        self._tocando = False
