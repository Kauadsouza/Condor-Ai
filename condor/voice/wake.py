"""
Detecção de wake word.
Tenta openWakeWord → fallback para detecção por texto no STT.
"""

from __future__ import annotations

import logging

log = logging.getLogger("condor.voice.wake")

try:
    import openwakeword
    _OWW = True
except ImportError:
    _OWW = False


class WakeWordDetector:
    """
    Detecta wake word no áudio ou no texto transcrito.

    Modo texto (fallback): verifica se o texto contém a wake word.
    Modo áudio (openWakeWord): analisa frames de áudio bruto.
    """

    def __init__(self, wake_word: str = "condor") -> None:
        self._word    = wake_word.lower()
        self._model   = None
        self._backend = "text"

        if _OWW:
            try:
                self._model   = openwakeword.Model(wakeword_models=["hey_jarvis"])
                self._backend = "oww"
                log.info("openWakeWord iniciado.")
            except Exception as exc:
                log.warning("openWakeWord falhou (%s), usando fallback por texto.", exc)

    def detect_in_text(self, text: str) -> bool:
        """Retorna True se o texto contém a wake word."""
        return self._word in text.lower()

    def detect_in_audio(self, audio_chunk: bytes) -> bool:
        """
        Retorna True se o chunk de áudio PCM contém wake word.
        Só funciona se openWakeWord estiver instalado.
        """
        if self._backend != "oww" or self._model is None:
            return False
        try:
            import numpy as np
            samples = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
            preds   = self._model.predict(samples)
            return any(v > 0.5 for v in preds.values())
        except Exception:
            return False

    @property
    def backend(self) -> str:
        return self._backend
