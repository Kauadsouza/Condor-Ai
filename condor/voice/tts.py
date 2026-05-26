"""
Text-to-Speech — A Voz do Condor.

Pipeline:
  1. Microsoft Daniel (voz masculina PT-BR, OneCore) gera fala base
  2. _condor_voice_fx() processa o áudio:
       • pitch shift  -4 semitons  → voz ainda mais grossa e única
       • bass boost   150 Hz +5dB  → grave profundo e ressonante
       • echo metálico 10ms/20%    → caráter de IA único
  3. Resultado: voz masculina, grave, ressonante e inconfundível

Otimizações de velocidade:
  - Engine pyttsx3 em cache por thread (evita re-init COM a cada chamada)
  - Fala apenas as primeiras frases (~250 chars) para respostas longas
  - Taxa de fala aumentada para 185 WPM
"""

from __future__ import annotations

import io
import logging
import os
import re
import struct
import tempfile
import threading

import numpy as np

from condor.config import VoiceConfig

log = logging.getLogger("condor.voice.tts")

# ── ID da voz masculina (OneCore — Daniel PT-BR) ──────────────────────────────
_DANIEL_ID = (
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft"
    r"\Speech_OneCore\Voices\Tokens\MSTTS_V110_ptBR_DanielM"
)

# ── Parâmetros da Voz do Condor ───────────────────────────────────────────────
_PITCH_SEMITONES  = -4       # -4 semitons: Daniel já é grave, deixa mais único
_BASS_FREQ_HZ     = 150      # Boost de graves em 150 Hz
_BASS_GAIN_DB     = 5        # +5 dB de grave extra
_ECHO_DELAY_MS    = 10       # Echo metálico curto (ms) — caráter de IA
_ECHO_DECAY       = 0.20     # Volume do echo (sutil)
_SPEAK_RATE       = 185      # Palavras por minuto (aumentado de 150 → mais rápido)
_OUTPUT_NORMALIZE = 0.88     # Limita picos para evitar clipping
_TTS_MAX_CHARS    = 280      # Limite de caracteres para síntese (primeiras frases)

# ── Cache de engine por thread — evita re-init pyttsx3/COM a cada chamada ─────
_tls = threading.local()


def _get_tts_engine():
    """
    Retorna o engine pyttsx3 para a thread atual.
    Cria uma vez por thread e reutiliza — elimina o custo de init por chamada.
    """
    if getattr(_tls, "engine", None) is not None:
        return _tls.engine

    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate",   _SPEAK_RATE)
        engine.setProperty("volume", 1.0)

        # Daniel OneCore (masculino PT-BR) — prioridade máxima
        daniel_ok = False
        for v in engine.getProperty("voices"):
            if "daniel" in (v.id or "").lower() or "daniel" in (v.name or "").lower():
                engine.setProperty("voice", v.id)
                daniel_ok = True
                break

        if not daniel_ok:
            try:
                engine.setProperty("voice", _DANIEL_ID)
                daniel_ok = True
            except Exception:
                pass

        if not daniel_ok:
            for v in engine.getProperty("voices"):
                if "pt" in (v.id or "").lower() or "brazil" in (v.name or "").lower():
                    engine.setProperty("voice", v.id)
                    break

        _tls.engine = engine
        log.info("pyttsx3 engine inicializado na thread %s", threading.current_thread().name)
        return engine

    except Exception as exc:
        log.error("Falha ao inicializar pyttsx3: %s", exc)
        return None


def _first_sentences(text: str, max_chars: int = _TTS_MAX_CHARS) -> str:
    """
    Retorna as primeiras frases do texto até max_chars.
    Corta em limite de frase para não truncar no meio de uma palavra.
    """
    if len(text) <= max_chars:
        return text

    # Tenta cortar em fim de frase próximo ao limite
    for end_marker in ('. ', '! ', '? ', '.\n', '!\n', '?\n'):
        # Procura a última ocorrência antes do limite
        idx = text.rfind(end_marker, 0, max_chars + 60)
        if idx != -1 and idx >= max_chars // 2:
            return text[:idx + 1].strip()

    # Fallback: corta na última palavra antes do limite
    snippet = text[:max_chars]
    last_space = snippet.rfind(' ')
    if last_space > max_chars // 2:
        return snippet[:last_space].strip()

    return snippet.strip()


class TTSEngine:
    def __init__(self, config: VoiceConfig) -> None:
        self._config  = config
        self._backend = _detect_backend()
        log.info("TTS backend: %s | Daniel PT-BR + Voz do Condor FX", self._backend)

    @property
    def available(self) -> bool:
        return self._backend != "none"

    def synthesize(self, text: str) -> bytes | None:
        """Gera fala e aplica os efeitos da Voz do Condor."""
        if not text.strip():
            return None

        # Remove blocos de action/JSON antes de falar
        clean = re.sub(r'\{[^}]*"action"[^}]*\}', '', text, flags=re.DOTALL).strip()
        clean = clean or text

        # Pega só as primeiras frases — respostas longas só falam o início
        clean = _first_sentences(clean, _TTS_MAX_CHARS)
        if not clean:
            return None

        raw_wav = self._synth_raw(clean)
        if not raw_wav:
            return None

        # Aplica A Voz do Condor
        try:
            return _condor_voice_fx(raw_wav)
        except Exception as exc:
            log.warning("Voice FX falhou (%s) — usando voz sem efeitos", exc)
            return raw_wav

    def _synth_raw(self, text: str) -> bytes | None:
        """Gera WAV cru via pyttsx3 com Daniel (PT-BR masculino)."""
        try:
            engine = _get_tts_engine()
            if engine is None:
                return None

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp = f.name

            engine.save_to_file(text, tmp)
            engine.runAndWait()

            with open(tmp, "rb") as f:
                data = f.read()
            os.unlink(tmp)
            return data if len(data) > 200 else None

        except Exception as exc:
            log.error("pyttsx3 erro: %s", exc)
            # Invalida o engine da thread para forçar recriação na próxima chamada
            _tls.engine = None
            return None


# ══════════════════════════════════════════════════════════════════════════════
# Voz do Condor — pipeline de efeitos de áudio
# ══════════════════════════════════════════════════════════════════════════════

def _condor_voice_fx(wav_bytes: bytes) -> bytes:
    """
    Transforma o WAV do Daniel na Voz do Condor:
      1. Pitch shift   → voz ainda mais grave e única
      2. Bass boost    → grave profundo e ressonante
      3. Echo metálico → caráter de IA inconfundível
      4. Normaliza e exporta WAV
    """
    audio, sr = _wav_to_float32(wav_bytes)

    audio = _pitch_shift(audio, sr, _PITCH_SEMITONES)
    audio = _bass_boost(audio, sr, _BASS_FREQ_HZ, _BASS_GAIN_DB)
    audio = _metallic_echo(audio, sr, _ECHO_DELAY_MS, _ECHO_DECAY)
    audio = _normalize(audio, _OUTPUT_NORMALIZE)

    return _float32_to_wav(audio, sr)


def _pitch_shift(audio: np.ndarray, sr: int, semitones: float) -> np.ndarray:
    """
    Desloca o tom sem alterar a duração (time-preserving pitch shift).
    """
    from scipy.signal import resample

    factor  = 2.0 ** (semitones / 12.0)
    n_orig  = len(audio)
    n_short = max(1, int(n_orig * factor))
    pitched = resample(audio, n_short)
    return resample(pitched, n_orig)


def _bass_boost(audio: np.ndarray, sr: int,
                cutoff_hz: float, gain_db: float) -> np.ndarray:
    """Reforça os graves abaixo de cutoff_hz."""
    from scipy.signal import butter, sosfilt

    nyq    = sr / 2.0
    norm_c = min(cutoff_hz / nyq, 0.99)
    sos    = butter(2, norm_c, btype="low", output="sos")
    bass   = sosfilt(sos, audio)
    gain   = 10.0 ** (gain_db / 20.0)
    return audio + bass * (gain - 1.0)


def _metallic_echo(audio: np.ndarray, sr: int,
                   delay_ms: float, decay: float) -> np.ndarray:
    """
    Eco curto e metálico — dá o caráter único de IA ao Condor.
    """
    delay_samples = int(sr * delay_ms / 1000.0)
    out = audio.copy()
    if delay_samples < len(audio):
        out[delay_samples:] += audio[:-delay_samples] * decay
    return out


def _normalize(audio: np.ndarray, peak: float = 0.9) -> np.ndarray:
    mx = np.max(np.abs(audio))
    if mx > 1e-6:
        audio = audio / mx * peak
    return audio


# ══════════════════════════════════════════════════════════════════════════════
# Helpers WAV
# ══════════════════════════════════════════════════════════════════════════════

def _wav_to_float32(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    import wave
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        sr     = wf.getframerate()
        n_ch   = wf.getnchannels()
        sw     = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

    if sw == 2:
        pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        pcm = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2**31
    else:
        pcm = np.frombuffer(frames, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

    if n_ch > 1:
        pcm = pcm.reshape(-1, n_ch).mean(axis=1)

    return pcm, sr


def _float32_to_wav(audio: np.ndarray, sr: int) -> bytes:
    pcm  = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    data = pcm.tobytes()
    buf  = io.BytesIO()
    buf.write(b"RIFF"); buf.write(struct.pack("<I", 36 + len(data)))
    buf.write(b"WAVE"); buf.write(b"fmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16))
    buf.write(b"data"); buf.write(struct.pack("<I", len(data))); buf.write(data)
    return buf.getvalue()


def _detect_backend() -> str:
    try:
        import pyttsx3
        return "pyttsx3"
    except ImportError:
        return "none"
