"""
Speech-to-Text usando faster-whisper.
Carregamento lazy — só carrega o modelo na primeira transcrição (não bloqueia o boot).
"""

from __future__ import annotations

import logging
import os
import tempfile
from condor.config import VoiceConfig

log = logging.getLogger("condor.voice.stt")

try:
    from faster_whisper import WhisperModel
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    log.warning("faster-whisper não instalado. STT desativado.")


class STTEngine:
    def __init__(self, config: VoiceConfig) -> None:
        self._config  = config
        self._model   = None
        self._loaded  = False
        self._tried   = False   # tentou carregar ao menos uma vez?

    def _ensure_loaded(self) -> bool:
        """Carrega o modelo na primeira chamada (lazy)."""
        if self._tried:
            return self._loaded
        self._tried = True

        if not _AVAILABLE:
            return False

        device = self._config.stt_device
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"

        compute = "float16" if device == "cuda" else "int8"
        model   = self._config.stt_model  # tiny, base, small, medium

        log.info("Carregando Whisper '%s' (%s)...", model, device)
        try:
            self._model  = WhisperModel(model, device=device, compute_type=compute)
            self._loaded = True
            log.info("Whisper pronto.")
        except Exception as exc:
            log.error("Falha ao carregar Whisper: %s", exc)

        return self._loaded

    @property
    def available(self) -> bool:
        # Reporta como disponível enquanto não tentou — evita falso negativo no boot
        return _AVAILABLE and (not self._tried or self._loaded)

    def transcribe_bytes(self, audio_bytes: bytes) -> str:
        if not self._ensure_loaded() or not audio_bytes:
            return ""

        suffix = _detect_suffix(audio_bytes)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            segments, info = self._model.transcribe(
                tmp_path,
                language="pt",
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )
            text = " ".join(seg.text for seg in segments).strip()
            log.debug("STT: '%s' (%.2fs)", text, info.duration)
            return text
        except Exception as exc:
            log.error("Erro na transcrição: %s", exc)
            return ""
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _detect_suffix(data: bytes) -> str:
    if data[:4] == b"RIFF":
        return ".wav"
    if data[:4] == b"fLaC":
        return ".flac"
    if data[:3] == b"ID3" or data[:2] == b"\xff\xfb":
        return ".mp3"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return ".webm"
    return ".webm"
