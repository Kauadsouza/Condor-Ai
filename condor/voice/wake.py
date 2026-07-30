"""
A escuta — o que fica ligado o tempo todo esperando você chamar.

Uma thread só, dona do microfone, fazendo duas coisas:
  1. joga cada quadro de áudio no Porcupine até ele reconhecer a palavra
  2. reconhecida a palavra, grava o que você falou até você parar de falar

Enquanto ela espera, nada sai do PC: o Porcupine roda local. Só o trecho
gravado depois do chamado é enviado pra transcrição.

A palavra "Condor" precisa ser treinada por você no console.picovoice.ai
(grátis) e o arquivo .ppn colocado em data/wake/. Sem ele, cai na palavra
embutida do config (padrão: "jarvis").
"""

from __future__ import annotations

import concurrent.futures
import io
import logging
import struct
import threading
import time
import wave
from pathlib import Path
from typing import Callable

log = logging.getLogger("condor.escuta")

TAXA = 16000        # Porcupine só trabalha em 16 kHz mono
ROOT = Path(__file__).parent.parent.parent
PASTA_WAKE = ROOT / "data" / "wake"


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


class Escuta(threading.Thread):
    daemon = True

    def __init__(self, config, ao_ouvir: Callable[[bytes], None]) -> None:
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

    # ── Controle externo ───────────────────────────────────────────────────

    def silenciar(self) -> None:
        """Para de reagir à wake word. Usado enquanto ele fala, senão a própria
        voz dele no alto-falante dispara o gatilho."""
        self._mudo.set()

    def voltar_a_ouvir(self) -> None:
        self._mudo.clear()

    def encerrar(self) -> None:
        self._parar.set()

    def capturar_fala(self, timeout: float = 30.0) -> bytes | None:
        """Grava uma fala AGORA, sem esperar a wake word.
        É o que a trava de segurança usa pra ouvir a senha."""
        # Sem a thread do microfone viva, ninguém vai atender o pedido — não
        # adianta prender uma thread do pool esperando o timeout inteiro.
        if not self.ativa:
            return None

        futuro: concurrent.futures.Future = concurrent.futures.Future()
        with self._pedido_lock:
            self._pedido = futuro
        estava_mudo = self._mudo.is_set()
        self._mudo.clear()
        try:
            return futuro.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            with self._pedido_lock:
                self._pedido = None
            return None
        finally:
            if estava_mudo:
                self._mudo.set()

    # ── A thread ───────────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            import pvporcupine
            from pvrecorder import PvRecorder
        except ImportError as exc:
            self.motivo_inativa = f"pvporcupine/pvrecorder não instalados ({exc})"
            log.error(self.motivo_inativa)
            return

        chave = self._cfg.chave_picovoice
        if not chave:
            self.motivo_inativa = "sem PICOVOICE_ACCESS_KEY no .env"
            log.warning("Escuta desligada: %s", self.motivo_inativa)
            return

        try:
            porcupine = self._criar_porcupine(pvporcupine, chave)
        except Exception as exc:
            self.motivo_inativa = f"Porcupine não iniciou: {exc}"
            log.error(self.motivo_inativa)
            return

        try:
            gravador = PvRecorder(frame_length=porcupine.frame_length,
                                  device_index=self._cfg.escuta.indice_microfone)
            gravador.start()
        except Exception as exc:
            self.motivo_inativa = f"microfone indisponível: {exc}"
            log.error(self.motivo_inativa)
            porcupine.delete()
            return

        self.ativa = True
        log.info("Escutando por '%s' no microfone '%s'.", self.palavra,
                 getattr(gravador, "selected_device", "padrão"))

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
                    continue

                if porcupine.process(quadro) >= 0:
                    log.info("Chamou.")
                    self._mudo.set()                    # não escuta a si mesmo
                    try:
                        audio = self._gravar_fala(gravador, None)
                        if audio:
                            self._ao_ouvir(audio)
                        else:
                            self._mudo.clear()
                    except Exception as exc:
                        log.error("Falha ao gravar a fala: %s", exc)
                        self._mudo.clear()
        finally:
            self.ativa = False
            try:
                gravador.stop()
                gravador.delete()
            except Exception:
                pass
            porcupine.delete()
            log.info("Escuta encerrada.")

    # ── Peças ──────────────────────────────────────────────────────────────

    def _criar_porcupine(self, pvporcupine, chave: str):
        """Prefere a palavra 'Condor' treinada por você; senão usa a embutida."""
        PASTA_WAKE.mkdir(parents=True, exist_ok=True)
        ppn = sorted(PASTA_WAKE.glob("*.ppn"))
        pv = sorted(PASTA_WAKE.glob("*.pv"))

        if ppn:
            self.palavra = ppn[0].stem.split("_")[0].capitalize()
            log.info("Usando palavra treinada: %s", ppn[0].name)
            return pvporcupine.create(
                access_key=chave,
                keyword_paths=[str(p) for p in ppn],
                model_path=str(pv[0]) if pv else None,
                sensitivities=[self._cfg.escuta.sensibilidade] * len(ppn),
            )

        self.palavra = self._cfg.escuta.palavra_embutida
        log.warning("Nenhum .ppn em data/wake/ — usando a palavra embutida '%s'. "
                    "Treine 'Condor' no console.picovoice.ai pra trocar.", self.palavra)
        return pvporcupine.create(
            access_key=chave,
            keywords=[self.palavra],
            sensitivities=[self._cfg.escuta.sensibilidade],
        )

    def _gravar_fala(self, gravador, primeiro_quadro: list[int] | None) -> bytes | None:
        """Grava até você calar a boca (ou até o limite de segurança)."""
        cfg = self._cfg.voz
        quadros: list[list[int]] = []
        if primeiro_quadro:
            quadros.append(primeiro_quadro)

        duracao_quadro = gravador.frame_length / TAXA
        quadros_silencio_para_parar = int(cfg.silencio_para_parar / duracao_quadro)
        max_quadros = int(cfg.fala_maxima / duracao_quadro)
        # Antes de começar a falar, dá um tempo maior — você pode demorar a
        # emendar a frase depois de chamar.
        max_espera_inicio = int(3.5 / duracao_quadro)

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
        return _para_wav(quadros)
