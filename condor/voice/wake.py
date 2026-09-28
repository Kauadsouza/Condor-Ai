"""
A escuta — o que fica ligado o tempo todo esperando você chamar "Condor".

Uma thread só, dona do microfone, fazendo duas coisas:
  1. joga cada quadro de áudio no detector até ele reconhecer a palavra
  2. reconhecida a palavra, grava o que você falou até você parar de falar

Dois detectores, escolhidos sozinhos:
  - Picovoice Porcupine, quando existem a chave no cofre e o modelo
    ``~/.condor/wake/condor*.ppn``: instantâneo e muito preciso.
  - Vosk, sem chave nem conta, com o modelo pt-BR pequeno em
    ``~/.condor/models/wake``. Em português "Condor" e "com dor" soam quase
    iguais, então o Vosk é só o porteiro: ele separa a frase candidata e o
    Whisper confirma se o nome foi mesmo dito antes de qualquer resposta.

Enquanto espera, nada sai do PC. O assistente nunca responde por outro nome.
"""

from __future__ import annotations

import collections
import concurrent.futures
import io
import json
import logging
import struct
import threading
import time
import wave
from pathlib import Path
from typing import Callable

from condor.paths import state_root

log = logging.getLogger("condor.escuta")

TAXA = 16000        # os dois detectores trabalham em 16 kHz mono
QUADRO_VOSK = 512   # 32 ms
ROOT = Path(__file__).parent.parent.parent
PASTA_WAKE = state_root() / "wake"
PASTA_VOSK = state_root() / "models" / "wake"

# Palavras parecidas entram na gramática para não virarem "condor" à força.
_GRAMATICA_VOSK = json.dumps([
    "condor", "com dor", "cantor", "computador", "conta", "contar", "com", "dor",
    "conversar", "conversa", "comprar", "condição", "controle", "corredor",
    "[unk]",
], ensure_ascii=False)


def _para_wav(quadros: list[list[int]]) -> bytes:
    """Junta os quadros int16 num WAV completo, na memória."""
    amostras = [a for quadro in quadros for a in quadro]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(struct.pack(f"{len(amostras)}h", *amostras))
    return buf.getvalue()


def _volume(quadro: list[int]) -> float:
    """RMS do quadro — é assim que a gente sabe se você parou de falar."""
    if not quadro:
        return 0.0
    return (sum(a * a for a in quadro) / len(quadro)) ** 0.5


def _caminho_ascii(caminho: Path) -> str:
    """O Vosk (C++) não abre caminhos com acento no Windows (perfil "Kauã", por exemplo).
    O nome curto 8.3 do mesmo diretório é só ASCII."""
    texto = str(caminho)
    if texto.isascii() or not hasattr(__import__("ctypes"), "windll"):
        return texto
    import ctypes
    buffer = ctypes.create_unicode_buffer(1024)
    if ctypes.windll.kernel32.GetShortPathNameW(texto, buffer, len(buffer)):
        return buffer.value
    return texto


class _Porcupine:
    """Detector preciso; dispara no instante em que a palavra termina."""

    nome = "picovoice"
    confirmar_nome = False

    def __init__(self, pvporcupine, chave: str, sensibilidade: float) -> None:
        PASTA_WAKE.mkdir(parents=True, exist_ok=True)
        ppn = sorted(PASTA_WAKE.glob("condor*.ppn"))
        pv = sorted(PASTA_WAKE.glob("*.pv"))
        if not ppn:
            raise RuntimeError(f"modelo condor*.ppn ausente em {PASTA_WAKE}")
        log.info("Usando modelo de ativacao Condor: %s", ppn[0].name)
        self._motor = pvporcupine.create(
            access_key=chave,
            keyword_paths=[str(ppn[0])],
            model_path=str(pv[0]) if pv else None,
            sensitivities=[sensibilidade],
        )
        self.frame_length = self._motor.frame_length

    def processar(self, quadro: list[int]) -> bool:
        return self._motor.process(quadro) >= 0

    def frase_candidata(self) -> list[list[int]]:
        return []

    def reiniciar(self) -> None:
        pass

    def fechar(self) -> None:
        self._motor.delete()


class _Vosk:
    """Porteiro sem chave: avisa quando uma frase pode ter começado por "Condor"."""

    nome = "vosk"
    confirmar_nome = True
    frame_length = QUADRO_VOSK

    def __init__(self, modelo: Path) -> None:
        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)
        self._Recognizer = KaldiRecognizer
        self._modelo = Model(_caminho_ascii(modelo))
        self._rec = None
        # Áudio da frase atual (até ~12 s): vira o começo da gravação, para
        # "Condor, abre o Spotify" dito de uma vez chegar inteiro ao Whisper.
        self._frase: collections.deque[list[int]] = collections.deque(maxlen=int(12 * TAXA / QUADRO_VOSK))
        self.reiniciar()

    def reiniciar(self) -> None:
        self._rec = self._Recognizer(self._modelo, TAXA, _GRAMATICA_VOSK)
        self._rec.SetWords(True)
        self._frase.clear()

    def processar(self, quadro: list[int]) -> bool:
        self._frase.append(quadro)
        if not self._rec.AcceptWaveform(struct.pack(f"{len(quadro)}h", *quadro)):
            return False
        texto = str(json.loads(self._rec.Result()).get("text") or "")
        candidata = "condor" in texto.split() or "com dor" in texto
        if not candidata:
            self._frase.clear()
        return candidata

    def frase_candidata(self) -> list[list[int]]:
        return list(self._frase)

    def fechar(self) -> None:
        self._rec = None


class Escuta(threading.Thread):
    daemon = True

    def __init__(self, config, ao_ouvir: Callable[..., None]) -> None:
        super().__init__(name="condor-escuta")
        self._cfg = config
        self._ao_ouvir = ao_ouvir          # recebe o WAV do que você falou
        self._parar = threading.Event()
        self._mudo = threading.Event()     # ligado enquanto o Condor fala/pensa
        self._pedido: concurrent.futures.Future | None = None
        self._pedido_lock = threading.Lock()
        self.ativa = False
        self.motivo_inativa = ""
        self.palavra = ""
        self.motor = ""

    # ── Controle externo ───────────────────────────────────────────────────

    def silenciar(self) -> None:
        """Para de reagir à wake word. Usado enquanto ele fala, senão a própria
        voz dele no alto-falante dispara o gatilho."""
        self._mudo.set()

    def voltar_a_ouvir(self) -> None:
        self._mudo.clear()

    def encerrar(self) -> None:
        self._parar.set()

    # ── A thread ───────────────────────────────────────────────────────────

    def _criar_detector(self):
        """Picovoice quando configurado; senão Vosk. Explica o motivo se nenhum der."""
        motivos = []
        chave = self._cfg.chave_picovoice
        if chave:
            try:
                import pvporcupine
                return _Porcupine(pvporcupine, chave, self._cfg.escuta.sensibilidade)
            except Exception as exc:
                motivos.append(f"Picovoice: {exc}")
        modelos = sorted(PASTA_VOSK.glob("vosk-model*"))
        if modelos:
            try:
                return _Vosk(modelos[-1])
            except Exception as exc:
                motivos.append(f"Vosk: {exc}")
        else:
            motivos.append(f"modelo Vosk ausente em {PASTA_VOSK} (rode scripts/install_voice_models.py)")
        raise RuntimeError("; ".join(motivos))

    def run(self) -> None:
        try:
            from pvrecorder import PvRecorder
        except ImportError as exc:
            self.motivo_inativa = f"pvrecorder não instalado ({exc})"
            log.error(self.motivo_inativa)
            return

        try:
            detector = self._criar_detector()
        except Exception as exc:
            self.motivo_inativa = f"detector da palavra Condor indisponível: {exc}"
            log.warning("Escuta desligada: %s", self.motivo_inativa)
            return

        try:
            gravador = PvRecorder(frame_length=detector.frame_length,
                                  device_index=self._cfg.escuta.indice_microfone)
            gravador.start()
        except Exception as exc:
            self.motivo_inativa = f"microfone indisponível: {exc}"
            log.error(self.motivo_inativa)
            detector.fechar()
            return

        self.palavra = "Condor"
        self.motor = detector.nome
        self.ativa = True
        log.info("Escutando por 'Condor' (%s) no microfone '%s'.", detector.nome,
                 getattr(gravador, "selected_device", "padrão"))

        estava_mudo = False
        try:
            while not self._parar.is_set():
                quadro = gravador.read()

                # Alguém pediu uma captura direta (senha)
                with self._pedido_lock:
                    pedido = self._pedido
                    self._pedido = None
                if pedido is not None and not pedido.cancelled():
                    try:
                        pedido.set_result(self._gravar_fala(gravador, quadro))
                    except Exception as exc:
                        pedido.set_exception(exc)
                    continue

                if self._mudo.is_set():
                    estava_mudo = True
                    continue
                if estava_mudo:
                    detector.reiniciar()   # descarta o que ouviu enquanto ele falava
                    estava_mudo = False

                if detector.processar(quadro):
                    log.info("Chamou (%s).", detector.nome)
                    self._mudo.set()                    # não escuta a si mesmo
                    try:
                        inicio = detector.frase_candidata()
                        # Vosk só avisa no fim da frase: se o pedido veio junto,
                        # ele já está no início; se você pausou, grava o resto.
                        resto = self._gravar_quadros(
                            gravador, None, espera_inicio=1.2 if inicio else 3.5,
                        )
                        quadros = inicio + (resto or [])
                        if quadros and (resto or inicio):
                            self._ao_ouvir(_para_wav(quadros),
                                           confirmar_nome=detector.confirmar_nome)
                        else:
                            self._mudo.clear()
                    except Exception as exc:
                        log.error("Falha ao gravar a fala: %s", exc)
                        self._mudo.clear()
                    finally:
                        detector.reiniciar()
        finally:
            self.ativa = False
            try:
                gravador.stop()
                gravador.delete()
            except Exception:
                pass
            detector.fechar()
            log.info("Escuta encerrada.")

    # ── Peças ──────────────────────────────────────────────────────────────

    def _gravar_quadros(self, gravador, primeiro_quadro: list[int] | None,
                        espera_inicio: float = 3.5) -> list[list[int]] | None:
        """Grava até você parar de falar (ou até o limite de segurança)."""
        cfg = self._cfg.voz
        quadros: list[list[int]] = []
        if primeiro_quadro:
            quadros.append(primeiro_quadro)

        duracao_quadro = gravador.frame_length / TAXA
        quadros_silencio_para_parar = int(cfg.silencio_para_parar / duracao_quadro)
        max_quadros = int(cfg.fala_maxima / duracao_quadro)
        # Antes de começar a falar, dá um tempo maior — você pode demorar a
        # emendar a frase depois de chamar.
        max_espera_inicio = int(espera_inicio / duracao_quadro)

        silencio_seguido = 0
        falou = False
        inicio = time.time()

        for i in range(max_quadros):
            quadro = gravador.read()
            quadros.append(quadro)
            alto = _volume(quadro) > cfg.limiar_silencio

            if alto:
                falou = True
                silencio_seguido = 0
            else:
                silencio_seguido += 1

            if falou and silencio_seguido >= quadros_silencio_para_parar:
                break
            if not falou and i >= max_espera_inicio:
                return None          # chamou e não falou nada

        if not falou:
            return None

        log.debug("Fala capturada: %.1fs", time.time() - inicio)
        return quadros

    def _gravar_fala(self, gravador, primeiro_quadro: list[int] | None) -> bytes | None:
        quadros = self._gravar_quadros(gravador, primeiro_quadro)
        return _para_wav(quadros) if quadros else None
