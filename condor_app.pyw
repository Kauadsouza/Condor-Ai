"""Abre o Condor como aplicativo local em Windows ou Linux.

Este é o ponto de entrada visual. Ele garante que o núcleo local esteja ativo
e abre somente /ui/index.html em uma janela própria, nunca o ARTX Hub.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.resolve()


def _hidden_options() -> dict:
    if os.name != "nt":
        return {"start_new_session": True}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": 0x08000000, "startupinfo": startup}


def _ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.45) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _start_core() -> None:
    if os.name == "nt":
        runner = ROOT / "scripts" / "run.ps1"
        command = [
            "powershell.exe", "-NoProfile", "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass", "-File", str(runner),
        ]
    else:
        runner = ROOT / "scripts" / "run.sh"
        command = ["sh", str(runner)]
    subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **_hidden_options(),
    )


def _notify_failure() -> None:
    message = "O Condor não conseguiu iniciar. Consulte ~/.condor/logs/condor.log."
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "Condor", 0x10)
            return
        except Exception:
            pass
    try:
        print(message, file=sys.stderr)
    except Exception:
        pass


def main() -> None:
    from condor.config import carregar_config

    config = carregar_config()
    base_url = f"http://{config.servidor.host}:{config.servidor.porta}"
    app_url = f"{base_url}/ui/index.html"

    if not _ready(app_url):
        _start_core()
        for _ in range(120):
            if _ready(app_url):
                break
            time.sleep(0.2)

    if not _ready(app_url):
        _notify_failure()
        return

    window_script = ROOT / "condor_window.pyw"
    subprocess.Popen(
        [sys.executable, str(window_script), app_url],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **_hidden_options(),
    )


if __name__ == "__main__":
    main()
