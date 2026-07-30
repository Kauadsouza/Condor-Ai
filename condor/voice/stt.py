"""
Ouvidos — transforma o WAV gravado em texto, pela API da OpenAI.

Só o trecho que você falou depois de chamar o Condor sobe pra nuvem.
O resto do tempo o microfone fica sendo processado localmente pelo Porcupine.
"""

from __future__ import annotations

import io
import logging
import wave

log = logging.getLogger("condor.ouvidos")

# whisper-1 cobra por minuto de áudio.
CUSTO_POR_MINUTO = 0.006

# Alucinação clássica do Whisper em áudio curto/silencioso: ele "ouve" a
# assinatura de legendas de vídeo. Se vier só isso, foi ruído.
LIXO = {
    "legendas pela comunidade amara.org", "legendado pela comunidade amara.org",
    "subtitles by the amara.org community", "obrigado", "tchau", "...",
    "legendas pela comunidade amara org", "amara.org",
}


def _duracao(wav: bytes) -> float:
    try:
        with wave.open(io.BytesIO(wav), "rb") as w:
            return w.getnframes() / float(w.getframerate() or 16000)
    except Exception:
        return 0.0


class Ouvidos:
    def __init__(self, config, cerebro) -> None:
        self._cfg = config
        self._cerebro = cerebro

    async def transcrever(self, wav: bytes) -> str:
        if not wav:
            return ""

        segundos = _duracao(wav)
        if segundos < 0.35:
            return ""      # clique, tosse, batida na mesa

        arquivo = io.BytesIO(wav)
        arquivo.name = "fala.wav"

        try:
            resposta = await self._cerebro.cliente.audio.transcriptions.create(
                model=self._cfg.voz.modelo_stt,
                file=arquivo,
                language=self._cfg.voz.idioma,
                # Dá contexto ao Whisper: nomes próprios que ele erraria sozinho.
                prompt="Condor, Kauã, PowerShell, Windows, Python, arquivo, pasta.",
            )
        except Exception as exc:
            log.error("Transcrição falhou: %s", exc)
            return ""

        try:
            self._cerebro.memoria.registrar_uso(
                self._cfg.voz.modelo_stt, 0, 0, (segundos / 60) * CUSTO_POR_MINUTO)
        except Exception:
            pass

        texto = (getattr(resposta, "text", "") or "").strip()
        if texto.lower().strip(" .!") in LIXO:
            log.debug("Transcrição descartada (alucinação de silêncio): %r", texto)
            return ""
        log.info("Ouvi: %s", texto[:120])
        return texto
