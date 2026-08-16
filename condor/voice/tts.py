"""Voz neural privada do Condor com Piper executado no próprio PC."""

from __future__ import annotations

import asyncio
import io
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

from condor.paths import state_root

log = logging.getLogger("condor.voz")

if sys.platform == "win32":
    import winsound
else:
    winsound = None


def _preparar(texto: str) -> str:
    t = re.sub(r"```.*?```", " (código na tela) ", texto, flags=re.DOTALL)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"[*_#>|]", "", t)
    t = re.sub(r"https?://\S+", "o link que está na tela", t)
    t = re.sub(r"[A-Za-z]:\\[^\s]{25,}", "o caminho que está na tela", t)
    return re.sub(r"\s+", " ", t).strip()


class Voz:
    def __init__(self, config, cerebro) -> None:
        self._cfg = config
        self._cerebro = cerebro
        self._tocando = False
        self._voice = None
        self._lock = threading.Lock()

    @property
    def model_path(self) -> Path:
        configured = str(self._cfg.voz.modelo_tts or "").strip()
        if configured in {"", "tts-1", "pt_BR-faber-medium"}:
            configured = "pt_BR-faber-medium"
        candidate = Path(configured).expanduser()
        if candidate.is_absolute():
            return candidate
        return state_root() / "models" / "tts" / f"{configured}.onnx"

    @property
    def pronto(self) -> bool:
        return self.model_path.is_file() and Path(str(self.model_path) + ".json").is_file()

    @property
    def tocando(self) -> bool:
        return self._tocando

    def _carregar(self):
        if self._voice is not None:
            return self._voice
        if not self.pronto:
            raise RuntimeError(f"voz Piper ausente em {self.model_path}")
        from piper import PiperVoice

        self._voice = PiperVoice.load(self.model_path, use_cuda=False)
        return self._voice

    def _sintetizar_local(self, texto: str) -> bytes:
        from piper.config import SynthesisConfig

        with self._lock:
            voice = self._carregar()
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                voice.synthesize_wav(
                    texto,
                    wav_file,
                    syn_config=SynthesisConfig(
                        length_scale=max(0.55, min(1.8, 1 / self._cfg.voz.velocidade)),
                        normalize_audio=True,
                        volume=1.0,
                    ),
                )
            return buffer.getvalue()

    async def sintetizar(self, texto: str) -> bytes | None:
        limpo = _preparar(texto)
        if not limpo:
            return None
        if len(limpo) > 1200:
            corte = limpo[:1200].rsplit(".", 1)[0]
            limpo = (corte or limpo[:1200]) + ". O resto está na tela."
        try:
            return await asyncio.to_thread(self._sintetizar_local, limpo)
        except Exception as exc:
            log.error("TTS local falhou: %s", exc)
            return None

    def _tocar_bloqueante(self, audio: bytes) -> bool:
        try:
            if winsound is not None:
                winsound.PlaySound(audio, winsound.SND_MEMORY)
                return True
            player = next((name for name in ("pw-play", "paplay", "aplay", "afplay") if shutil.which(name)), None)
            if not player:
                log.error("Nenhum tocador WAV local encontrado.")
                return False
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as stream:
                stream.write(audio)
                temporary = Path(stream.name)
            try:
                result = subprocess.run([player, str(temporary)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180, check=False)
                return result.returncode == 0
            finally:
                temporary.unlink(missing_ok=True)
        except Exception as exc:
            log.error("Nao consegui tocar o audio: %s", exc)
            return False

    async def falar(self, texto: str) -> bool:
        audio = await self.sintetizar(texto)
        if not audio:
            return False
        self._tocando = True
        try:
            return await asyncio.to_thread(self._tocar_bloqueante, audio)
        finally:
            self._tocando = False

    def calar(self) -> None:
        if winsound is not None:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        self._tocando = False
