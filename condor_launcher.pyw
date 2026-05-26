"""
CONDOR Launcher + Interface Nativa
===================================
Roda silenciosamente em background (sem console).
- Inicia o servidor FastAPI em subprocess
- Abre janela de chat tkinter (nativa no Windows)
- Escuta microfone: ao ouvir "condor na escuta" mostra a janela
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import queue
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.request
from tkinter import scrolledtext

# ── Raiz do projeto ──────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── Logging ───────────────────────────────────────────────────────────────────
_log_dir = os.path.join(ROOT, "data")
os.makedirs(_log_dir, exist_ok=True)
LOG_FILE  = os.path.join(_log_dir, "launcher.log")
LOCK_FILE = os.path.join(_log_dir, "launcher.lock")   # garante instância única
UI_PID_FILE = os.path.join(_log_dir, "ui_window.pid") # PID da janela Edge aberta


def _pid_alive(pid: int) -> bool:
    """Retorna True se o PID ainda está rodando no Windows."""
    try:
        import ctypes
        SYNCHRONIZE = 0x100000
        h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def _acquire_lock() -> bool:
    """
    Garante que só UMA instância do launcher rode por vez.
    Retorna True se esta instância pode continuar, False se deve sair.
    """
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                old_pid = int(f.read().strip())
            if _pid_alive(old_pid):
                return False   # já tem uma instância rodando
        except Exception:
            pass  # arquivo corrompido — sobrescreve

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True


def _cleanup_lock():
    """Remove o lock file ao encerrar."""
    try:
        if os.path.exists(LOCK_FILE):
            with open(LOCK_FILE) as f:
                pid = int(f.read().strip())
            if pid == os.getpid():
                os.unlink(LOCK_FILE)
    except Exception:
        pass
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
log = logging.getLogger("condor.launcher")

# ── Config ────────────────────────────────────────────────────────────────────
SERVER_URL   = "http://127.0.0.1:7777"
WS_URL       = "ws://127.0.0.1:7777/ws"
SAMPLE_RATE   = 16000
CLAP_BLOCK    = 512              # 32ms @ 16kHz — captura picos curtos de palma
ENERGY_THRESH = 0.00008          # energy mínima para considerar voz ativa (mean squared)
SILENCE_LIMIT = int(SAMPLE_RATE * 1.5 // CLAP_BLOCK)  # ≈1.5s de silêncio → 46 chunks de 32ms

# legado — alinhado ao CLAP_BLOCK
BLOCK_SIZE = CLAP_BLOCK

# ── Wake word: frase de voz ────────────────────────────────────────────────────
# Diz "condor ativo" (ou qualquer variante) para abrir
WAKE_VOICE_PRIMARY   = "condor"   # palavra principal (fuzzy)
WAKE_VOICE_SECONDARY = "ativo"    # confirmação — mais simples e clara que "escuta"

# ── Detecção de palmas ─────────────────────────────────────────────────────────
CLAP_ENERGY_THRESH   = 0.005    # energia mínima de uma palma (calibrado para mic distante)
CLAP_MAX_DURATION_MS = 200      # palma dura < 200ms
CLAP_MIN_GAP_MS      = 150      # gap mínimo entre palmas (ms)
CLAP_MAX_GAP_MS      = 1500     # gap máximo entre duas palmas (ms)

# Sempre usar python.exe (com console) para o servidor — pythonw.exe age como
# launcher e pode sair antes, fazendo o watchdog pensar que o servidor morreu.
_pydir  = os.path.dirname(sys.executable)
PYTHON  = os.path.join(_pydir, "python.exe")
if not os.path.exists(PYTHON):
    PYTHON = sys.executable   # fallback
PYTHONW = os.path.join(_pydir, "pythonw.exe")
if not os.path.exists(PYTHONW):
    PYTHONW = sys.executable

# ── Cores (tema escuro) ───────────────────────────────────────────────────────
C_BG        = "#0d1117"
C_PANEL     = "#161b22"
C_BORDER    = "#30363d"
C_TEXT      = "#e6edf3"
C_TEXT_DIM  = "#8b949e"
C_USER_BG   = "#1f4068"
C_BOT_BG    = "#161b22"
C_INPUT_BG  = "#21262d"
C_ACCENT    = "#58a6ff"
C_SEND      = "#238636"
C_SEND_HOV  = "#2ea043"
C_STATUS_OK = "#3fb950"
C_STATUS_ERR= "#f85149"

# ══════════════════════════════════════════════════════════════════════════════
# WebSocket client
# ══════════════════════════════════════════════════════════════════════════════

class WSClient:
    """Cliente WebSocket assíncrono rodando numa thread dedicada."""

    def __init__(self, on_message):
        self._on_msg  = on_message
        self._ws      = None
        self._loop    = asyncio.new_event_loop()
        self._connected = False
        t = threading.Thread(target=self._run, daemon=True, name="ws-client")
        t.start()

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self):
        while True:
            try:
                import websockets
                async with websockets.connect(WS_URL, ping_interval=20) as ws:
                    self._ws = ws
                    self._connected = True
                    log.info("WebSocket conectado.")
                    self._on_msg({"type": "_connected"})
                    async for raw in ws:
                        try:
                            self._on_msg(json.loads(raw))
                        except Exception:
                            pass
            except Exception as exc:
                self._connected = False
                self._ws = None
                self._on_msg({"type": "_disconnected"})
                log.debug("WebSocket desconectado: %s — reconectando em 3s", exc)
                await asyncio.sleep(3)

    def send(self, msg: dict):
        if self._ws and self._connected:
            asyncio.run_coroutine_threadsafe(
                self._ws.send(json.dumps(msg, ensure_ascii=False)),
                self._loop,
            )

    def send_audio(self, pcm_bytes: bytes):
        """Envia áudio PCM int16 como chunks base64."""
        wav = _make_wav(pcm_bytes)
        b64 = base64.b64encode(wav).decode()
        self.send({"type": "audio.chunk", "data": b64})
        self.send({"type": "audio.end"})


# ══════════════════════════════════════════════════════════════════════════════
# Servidor FastAPI
# ══════════════════════════════════════════════════════════════════════════════

_server_proc: subprocess.Popen | None = None
_server_lock = threading.Lock()

# Browsers em ordem de preferência (modo --app = janela limpa sem barra)
_BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
]

# Referência ao processo do browser aberto — evita abrir múltiplas janelas
_ui_proc: subprocess.Popen | None = None


def _ui_already_open() -> bool:
    """
    Retorna True se a janela do Condor ainda está aberta.
    Usa tanto o _ui_proc desta instância quanto o UI_PID_FILE (compartilhado
    entre instâncias), para garantir que múltiplos launchers nunca abram janelas duplas.
    """
    global _ui_proc
    # Verifica processo desta instância
    if _ui_proc is not None and _ui_proc.poll() is None:
        return True
    # Verifica PID salvo em arquivo (pode ter sido aberto por outra instância/session)
    if os.path.exists(UI_PID_FILE):
        try:
            with open(UI_PID_FILE) as f:
                saved_pid = int(f.read().strip())
            if _pid_alive(saved_pid):
                return True
            else:
                os.unlink(UI_PID_FILE)   # processo morreu, limpa o arquivo
        except Exception:
            pass
    return False


def _open_original_ui() -> None:
    """Abre o layout original do Condor em tela cheia, sem barra de browser.
    Se já estiver aberto (por qualquer instância do launcher), não abre segunda janela."""
    global _ui_proc

    if _ui_already_open():
        log.info("UI ja esta aberta — ignorando acionamento duplo.")
        return

    for browser in _BROWSERS:
        if os.path.exists(browser):
            log.info("Abrindo UI: %s", os.path.basename(browser))
            _ui_proc = subprocess.Popen(
                [browser, f"--app={SERVER_URL}", "--new-window", "--start-fullscreen"],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            # Salva PID em arquivo para que outros launchers/sessões saibam
            try:
                with open(UI_PID_FILE, "w") as f:
                    f.write(str(_ui_proc.pid))
            except Exception:
                pass
            return
    # Fallback: abre no browser padrão (sem controle de processo)
    import webbrowser
    webbrowser.open(SERVER_URL)
    _ui_proc = None
    log.info("UI aberta via webbrowser padrao.")


def _start_server() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen(
        [PYTHON, "-m", "condor"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    log.info("Servidor iniciado (PID %s)", proc.pid)
    return proc


def _server_alive() -> bool:
    try:
        urllib.request.urlopen(f"{SERVER_URL}/api/health", timeout=2)
        return True
    except Exception:
        return False


def _server_watchdog(app: "CondorApp"):
    """Thread que mantém o servidor vivo, checando por URL (não por PID)."""
    global _server_proc
    _connected_notified = False

    log.info("Aguardando servidor subir...")
    for i in range(60):
        if _server_alive():
            log.info("Servidor pronto (%ss).", i)
            app.schedule(app._on_server_ready)
            _connected_notified = True
            break
        time.sleep(1)
    else:
        log.error("Servidor nao respondeu em 60s.")

    while True:
        time.sleep(15)
        if not _server_alive():
            log.warning("Servidor nao responde — reiniciando...")
            with _server_lock:
                _server_proc = _start_server()
            # Aguarda subir antes de continuar
            for _ in range(30):
                if _server_alive():
                    if not _connected_notified:
                        app.schedule(app._on_server_ready)
                        _connected_notified = True
                    break
                time.sleep(1)


# ══════════════════════════════════════════════════════════════════════════════
# Wake Word
# ══════════════════════════════════════════════════════════════════════════════

def _make_wav(pcm_int16: bytes, sr: int = SAMPLE_RATE) -> bytes:
    ch, sw = 1, 2
    ds = len(pcm_int16)
    buf = io.BytesIO()
    buf.write(b"RIFF"); buf.write(struct.pack("<I", 36 + ds))
    buf.write(b"WAVE"); buf.write(b"fmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, ch, sr, sr * ch * sw, ch * sw, sw * 8))
    buf.write(b"data"); buf.write(struct.pack("<I", ds)); buf.write(pcm_int16)
    return buf.getvalue()



def _wake_loop(on_wake, on_status):
    """
    Microfone SEMPRE ativo. Dois gatilhos:
      1. PALMAS: dois picos de energia 8x acima do ruido de fundo, com gap 150-1500ms
      2. VOZ curta: frase <= 5 palavras com variante de 'condor' + 'ativo/escuta'
    """
    import difflib, re as _re

    try:
        import numpy as np
        import sounddevice as sd
        from faster_whisper import WhisperModel
    except ImportError as exc:
        log.error("Dep ausente: %s", exc)
        on_status("Erro: falta pacote")
        return

    log.info("Carregando Whisper small...")
    on_status("Carregando Whisper...")
    try:
        model = WhisperModel("small", device="cpu", compute_type="int8")
    except Exception as exc:
        log.error("Whisper falhou: %s", exc)
        on_status("Whisper falhou")
        return

    log.info("Microfone ativo — diga 'papai chegou' ou 2 palmas para abrir.")
    on_status("Ouvindo...")

    # Estado de palmas
    _clap_last_ts = [0.0]
    _clap_count   = [0]
    _in_loud      = [False]

    # Threshold fixo calibrado para o microfone (palma chega a ~0.0004)
    # Aumentado para evitar falsos positivos com sons de fundo/teclado/TV
    CLAP_THRESH_FIXED = 0.0006    # valor conservador — só palma real passa

    CHUNK_MS = BLOCK_SIZE / SAMPLE_RATE * 1000.0

    # Fila de frames para processamento
    _frame_q: queue.Queue = queue.Queue(maxsize=300)

    def _processor():
        speech:  list = []
        silence: int  = 0

        while True:
            try:
                chunk = _frame_q.get(timeout=1.0)
            except queue.Empty:
                continue

            energy = float(np.mean(chunk ** 2))
            now    = time.time()

            # ------- DETECCAO DE PALMAS ---------
            if energy > CLAP_THRESH_FIXED:
                if not _in_loud[0]:
                    _in_loud[0] = True
                    gap_ms = (now - _clap_last_ts[0]) * 1000.0
                    log.debug("Pico! energy=%.5f gap=%.0fms count=%d",
                              energy, gap_ms, _clap_count[0])

                    if _clap_count[0] == 1 and 150 <= gap_ms <= 1500:
                        _clap_count[0]   = 0
                        _clap_last_ts[0] = 0.0
                        log.info("PALMAS 2x! gap=%.0fms Abrindo...", gap_ms)
                        on_wake()
                    else:
                        _clap_count[0]   = 1
                        _clap_last_ts[0] = now
            else:
                _in_loud[0] = False
                # Reset se passou mais de 1.5s sem segunda palma
                if _clap_count[0] == 1 and (now - _clap_last_ts[0]) * 1000.0 > 1500:
                    _clap_count[0] = 0

            # ------- DETECCAO DE VOZ (Whisper) ---------
            if energy > ENERGY_THRESH:
                speech.append(chunk)
                silence = 0
            elif speech:
                silence += 1
                if silence >= SILENCE_LIMIT:
                    combined = np.concatenate(speech)
                    speech = []; silence = 0
                    _check_voice(combined)

    def _check_voice(samples):
        dur_s = len(samples) / SAMPLE_RATE
        if dur_s < 0.8:
            return

        pcm = (samples * 32767).clip(-32768, 32767).astype("int16").tobytes()
        wav = _make_wav(pcm)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(wav); tmp.close()
        try:
            segs, _ = model.transcribe(
                tmp.name, language="pt", beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
                no_speech_threshold=0.6,
                log_prob_threshold=-1.0,
            )
            text = " ".join(s.text for s in segs).strip().lower()
            txt  = _re.sub(r"[^\w\s]", " ", text).strip()
            if not text:
                return
            words = txt.split()
            log.info("STT ouviu: %r (%d palavras, %.1fs)", text, len(words), dur_s)

            # IMPORTANTE: ignora frases longas (> 6 palavras = conversa de fundo)
            if len(words) > 6:
                log.debug("Frase longa ignorada (%d palavras)", len(words))
                return

            # ── Wake word: "papai chegou" ────────────────────────────────────
            # Variantes fonéticas de "papai" (o que o Whisper pode transcrever)
            _papai_v = {
                "papai", "papá", "papa", "papi", "papaí", "papãe",
                "papae", "pa pai", "pa pá",
            }
            # Variantes fonéticas de "chegou" / "chego"
            _chegou_v = {
                "chegou", "chego", "chegô", "chegando", "shegou",
                "xegou", "chegão",
            }

            def _has_papai(t):
                # Direto no texto completo (captura "papai", "papá", etc.)
                for v in _papai_v:
                    if v in t:
                        return True
                # Fuzzy: qualquer palavra com ≥70% similaridade com "papai"
                for word in words:
                    w = _re.sub(r"[^\w]", "", word)
                    if len(w) >= 4:
                        ratio = difflib.SequenceMatcher(None, w, "papai").ratio()
                        if ratio >= 0.70:
                            log.info("Fuzzy papai: %r ratio=%.2f", w, ratio)
                            return True
                return False

            def _has_chegou(t):
                for v in _chegou_v:
                    if v in t:
                        return True
                for word in words:
                    w = _re.sub(r"[^\w]", "", word)
                    if len(w) >= 5:
                        ratio = difflib.SequenceMatcher(None, w, "chegou").ratio()
                        if ratio >= 0.70:
                            log.info("Fuzzy chegou: %r ratio=%.2f", w, ratio)
                            return True
                return False

            hp = _has_papai(txt)
            hc = _has_chegou(txt)
            if hp and hc:
                log.info("Wake word 'papai chegou'! Abrindo...")
                on_wake()
            elif hp:
                log.info("'papai' ouvido, falta 'chegou'")
            elif hc:
                log.debug("'chegou' ouvido sem 'papai' — ignorando")
        except Exception as exc:
            log.error("Transcricao: %s", exc)
        finally:
            try: os.unlink(tmp.name)
            except OSError: pass

    threading.Thread(target=_processor, daemon=True, name="wake-proc").start()

    def _cb(indata, frames, time_info, status):
        try:
            _frame_q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    try:
        # CLAP_BLOCK = 512 = 32ms por chunk — resolução necessária para detectar
        # duas palmas separadas por 150-1500ms sem que caiam no mesmo chunk
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=CLAP_BLOCK, callback=_cb):
            while True:
                sd.sleep(500)
    except Exception as exc:
        log.error("InputStream: %s", exc)
        on_status("Microfone indisponivel")

class CondorApp:
    def __init__(self):
        self._ws: WSClient | None = None
        self._bot_buf = ""          # acumula tokens do LLM
        self._recording = False
        self._audio_frames: list = []
        self._mic_stream = None

        # ── Janela principal ─────────────────────────────────────────────────
        self.root = tk.Tk()
        self.root.title("CONDOR")
        self.root.geometry("780x560")
        self.root.configure(bg=C_BG)
        self.root.minsize(520, 400)
        # X fecha pra bandeja (não mata o processo)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.withdraw()   # começa oculto — aparece na wake word

        self._build_ui()
        # Janela fica oculta — a UI real é o layout original abrindo em Edge --app

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = self.root

        # ── Topo: título + status ────────────────────────────────────────────
        top = tk.Frame(root, bg=C_PANEL, height=42)
        top.pack(fill=tk.X, side=tk.TOP)
        top.pack_propagate(False)

        tk.Label(top, text="  CONDOR", bg=C_PANEL, fg=C_ACCENT,
                 font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT, pady=8)

        self._status_var = tk.StringVar(value="Iniciando...")
        self._status_lbl = tk.Label(top, textvariable=self._status_var,
                                    bg=C_PANEL, fg=C_TEXT_DIM,
                                    font=("Segoe UI", 9))
        self._status_lbl.pack(side=tk.RIGHT, padx=12)

        tk.Frame(root, bg=C_BORDER, height=1).pack(fill=tk.X)

        # ── Área de chat ─────────────────────────────────────────────────────
        chat_frame = tk.Frame(root, bg=C_BG)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        self._chat = tk.Text(
            chat_frame, bg=C_BG, fg=C_TEXT, wrap=tk.WORD,
            font=("Segoe UI", 10), state=tk.DISABLED,
            relief=tk.FLAT, borderwidth=0,
            padx=16, pady=10,
            cursor="arrow",
        )
        self._chat.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        sb = tk.Scrollbar(chat_frame, command=self._chat.yview,
                          bg=C_PANEL, troughcolor=C_BG,
                          activebackground=C_BORDER, relief=tk.FLAT)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._chat.configure(yscrollcommand=sb.set)

        # Tags de estilo
        self._chat.tag_config("user",  foreground=C_ACCENT,
                               font=("Segoe UI", 10, "bold"))
        self._chat.tag_config("user_text", foreground=C_TEXT,
                               font=("Segoe UI", 10),
                               lmargin1=20, lmargin2=20)
        self._chat.tag_config("bot",   foreground=C_STATUS_OK,
                               font=("Segoe UI", 10, "bold"))
        self._chat.tag_config("bot_text", foreground=C_TEXT,
                               font=("Segoe UI", 10),
                               lmargin1=20, lmargin2=20)
        self._chat.tag_config("dim",   foreground=C_TEXT_DIM,
                               font=("Segoe UI", 9, "italic"),
                               lmargin1=20, lmargin2=20)

        tk.Frame(root, bg=C_BORDER, height=1).pack(fill=tk.X)

        # ── Barra de entrada ─────────────────────────────────────────────────
        bottom = tk.Frame(root, bg=C_PANEL, pady=10)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)

        # Botão de voz
        self._mic_btn = tk.Button(
            bottom, text="🎙", width=3, height=1,
            bg=C_INPUT_BG, fg=C_TEXT, relief=tk.FLAT,
            activebackground=C_BORDER, activeforeground=C_TEXT,
            font=("Segoe UI", 12),
            cursor="hand2",
            command=self._toggle_mic,
        )
        self._mic_btn.pack(side=tk.LEFT, padx=(12, 4))

        self._input = tk.Entry(
            bottom, bg=C_INPUT_BG, fg=C_TEXT,
            insertbackground=C_TEXT,
            relief=tk.FLAT, font=("Segoe UI", 11),
            borderwidth=0,
        )
        self._input.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=7, padx=4)
        self._input.bind("<Return>", lambda _: self._send())

        self._send_btn = tk.Button(
            bottom, text="Enviar", bg=C_SEND, fg="white",
            relief=tk.FLAT, font=("Segoe UI", 10, "bold"),
            activebackground=C_SEND_HOV, activeforeground="white",
            padx=14, pady=6, cursor="hand2",
            command=self._send,
        )
        self._send_btn.pack(side=tk.LEFT, padx=(4, 12))

    # ── Helpers de chat ───────────────────────────────────────────────────────

    def _chat_insert(self, text: str, tag: str = ""):
        self._chat.configure(state=tk.NORMAL)
        if tag:
            self._chat.insert(tk.END, text, tag)
        else:
            self._chat.insert(tk.END, text)
        self._chat.configure(state=tk.DISABLED)
        self._chat.see(tk.END)

    def _append_user(self, text: str):
        self._chat_insert("\nVocê\n", "user")
        self._chat_insert(text + "\n", "user_text")

    def _append_bot(self, text: str):
        self._chat_insert("\nCONDOR\n", "bot")
        self._chat_insert(text + "\n", "bot_text")

    def _append_dim(self, text: str):
        self._chat_insert(text + "\n", "dim")

    # ── Envio de texto ────────────────────────────────────────────────────────

    def _send(self):
        text = self._input.get().strip()
        if not text or not self._ws:
            return
        self._input.delete(0, tk.END)
        self._append_user(text)
        self._bot_buf = ""
        self._chat_insert("\nCONDOR\n", "bot")
        self._ws.send({"type": "text.message", "text": text})

    # ── Microfone (gravar e enviar) ───────────────────────────────────────────

    def _toggle_mic(self):
        if not self._recording:
            self._start_mic()
        else:
            self._stop_mic()

    def _start_mic(self):
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            self._append_dim("sounddevice nao instalado.")
            return

        self._recording = True
        self._audio_frames = []
        self._mic_btn.configure(bg="#b91c1c", fg="white")
        self._set_status("Gravando...")

        def _cb(indata, frames, t, status):
            self._audio_frames.append(indata[:, 0].copy())

        self._mic_stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1,
            dtype="float32", blocksize=1024, callback=_cb,
        )
        self._mic_stream.start()

    def _stop_mic(self):
        import numpy as np
        self._recording = False
        self._mic_btn.configure(bg=C_INPUT_BG, fg=C_TEXT)
        if self._mic_stream:
            self._mic_stream.stop()
            self._mic_stream.close()
            self._mic_stream = None

        if not self._audio_frames:
            return

        combined = np.concatenate(self._audio_frames)
        pcm = (combined * 32767).clip(-32768, 32767).astype("int16").tobytes()
        self._audio_frames = []

        if self._ws:
            self._append_dim("(enviando audio...)")
            self._bot_buf = ""
            self._chat_insert("\nCONDOR\n", "bot")
            self._ws.send_audio(pcm)
        self._set_status("Ouvindo...")

    # ── WebSocket events ──────────────────────────────────────────────────────

    def _on_ws_message(self, data: dict):
        t = data.get("type", "")

        if t == "_connected":
            self.schedule(lambda: self._set_status("Conectado"))
            self.schedule(lambda: self._append_dim("Servidor conectado."))

        elif t == "_disconnected":
            self.schedule(lambda: self._set_status("Reconectando..."))

        elif t == "llm.token":
            token = data.get("token", "")
            self._bot_buf += token
            self.schedule(lambda tok=token: self._stream_token(tok))

        elif t == "llm.done":
            self.schedule(lambda: self._chat_insert("\n", ""))

        elif t == "tts.audio":
            # Toca o áudio recebido
            self.schedule(lambda d=data: self._play_audio(d))

        elif t == "stt.final":
            txt = data.get("text", "")
            if txt:
                self.schedule(lambda t=txt: self._append_user(f"(voz) {t}"))

        elif t == "health.update":
            score = data.get("score", 0)
            status = data.get("status", "")
            self.schedule(lambda s=score, st=status: self._set_status(f"{st} ({s}%)"))

        elif t == "memory.stats":
            nodes = data.get("nodes", 0)
            edges = data.get("edges", 0)
            self.schedule(lambda n=nodes, e=edges:
                          self._set_status(f"Conectado  |  Memoria: {n} nos"))

    def _stream_token(self, tok: str):
        self._chat.configure(state=tk.NORMAL)
        self._chat.insert(tk.END, tok, "bot_text")
        self._chat.configure(state=tk.DISABLED)
        self._chat.see(tk.END)

    def _play_audio(self, data: dict):
        try:
            import sounddevice as sd
            import numpy as np
            raw = base64.b64decode(data.get("data", ""))
            if raw[:4] == b"RIFF":
                import wave
                with wave.open(io.BytesIO(raw)) as wf:
                    frames = wf.readframes(wf.getnframes())
                    sr = wf.getframerate()
                    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                    sd.play(samples, samplerate=sr)
        except Exception as exc:
            log.debug("Audio playback: %s", exc)

    # ── Controle da janela ────────────────────────────────────────────────────

    def _on_close(self):
        """X fecha a janela mas não encerra o processo."""
        self.root.withdraw()

    def show(self):
        """Abre a interface original do Condor (layout roxo) em janela nativa."""
        _open_original_ui()

    def schedule(self, fn):
        """Agenda execução no thread principal do tkinter."""
        self.root.after(0, fn)

    def _set_status(self, txt: str):
        self._status_var.set(txt)

    # ── Servidor pronto ───────────────────────────────────────────────────────

    def _on_server_ready(self):
        # Servidor pronto — aguarda wake word para abrir a tela (não abre automaticamente)
        log.info("Servidor pronto. Aguardando wake word 'papai chegou' ou 2 palmas...")

    # ── Loop principal ────────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global _server_proc

    # ── Instância única — sai silenciosamente se já há um launcher rodando ──
    if not _acquire_lock():
        log.info("Launcher ja esta rodando — saindo (PID %s).", os.getpid())
        sys.exit(0)

    import atexit
    atexit.register(lambda: _cleanup_lock())

    log.info("=== Condor Launcher iniciado (PID %s) ===", os.getpid())

    # Cria a janela (ainda oculta)
    app = CondorApp()

    # Inicia servidor
    _server_proc = _start_server()

    # Watchdog do servidor (aguarda subir e cria WS client)
    threading.Thread(
        target=_server_watchdog, args=(app,), daemon=True, name="watchdog"
    ).start()

    # Wake word listener
    threading.Thread(
        target=_wake_loop,
        args=(
            lambda: app.schedule(app.show),          # on_wake
            lambda s: app.schedule(lambda st=s: app._set_status(st)),  # on_status
        ),
        daemon=True, name="wake-word"
    ).start()

    # Tkinter main loop (bloqueia aqui)
    app.run()


if __name__ == "__main__":
    main()