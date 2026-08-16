"""Transcrição privada do Condor com Faster Whisper executado no próprio PC."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import threading
import wave
from pathlib import Path

from condor.paths import state_root

log = logging.getLogger("condor.ouvidos")

LIXO = {
    "legendas pela comunidade amara.org", "legendado pela comunidade amara.org",
    "subtitles by the amara.org community", "obrigado", "tchau", "...",
    "legendas pela comunidade amara org", "amara.org",
}


def _duracao(wav: bytes) -> float | None:
    """Duração quando é WAV. WebM/Opus do navegador é aceito pelo PyAV depois."""
    try:
        with wave.open(io.BytesIO(wav), "rb") as stream:
            return stream.getnframes() / float(stream.getframerate() or 16000)
    except Exception:
        return None


class Ouvidos:
    def __init__(self, config, cerebro) -> None:
        self._cfg = config
        self._cerebro = cerebro
        self._model = None
        self._lock = threading.Lock()

    @property
    def model_path(self) -> Path:
        configured = str(self._cfg.voz.modelo_stt or "").strip()
        if configured in {"", "whisper-1", "small", "faster-whisper-small"}:
            configured = "faster-whisper-small"
        candidate = Path(configured).expanduser()
        if candidate.is_absolute():
            return candidate
        return state_root() / "models" / "stt" / configured

    @property
    def pronto(self) -> bool:
        return (self.model_path / "model.bin").is_file()

    def _carregar(self):
        if self._model is not None:
            return self._model
        if not self.pronto:
            raise RuntimeError(f"modelo STT local ausente em {self.model_path}")
        from faster_whisper import WhisperModel

        # A GPU fica reservada ao cérebro/visão; o STT int8 evita estouro de VRAM.
        self._model = WhisperModel(
            str(self.model_path),
            device="cpu",
            compute_type="int8",
            cpu_threads=max(2, min(8, (os.cpu_count() or 4) - 1)),
            num_workers=1,
            local_files_only=True,
        )
        return self._model

    def _transcrever_local(self, audio: bytes) -> str:
        with self._lock:
            model = self._carregar()
            segments, _info = model.transcribe(
                io.BytesIO(audio),
                language="pt",
                beam_size=5,
                best_of=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 420},
                condition_on_previous_text=False,
                initial_prompt="Condor, Kauã, Oxford, computador, Linux, projeto e canal KauaArtx.",
            )
            return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()

    async def transcrever(self, wav: bytes) -> str:
        if not wav:
            return ""
        segundos = _duracao(wav)
        if segundos is not None and segundos < 0.35:
            return ""
        try:
            texto = await asyncio.to_thread(self._transcrever_local, wav)
        except Exception as exc:
            log.error("Transcrição local falhou: %s", exc)
            return ""
        if texto.lower().strip(" .!") in LIXO:
            return ""
        log.info("Ouvi localmente: %s", texto[:120])
        return texto
