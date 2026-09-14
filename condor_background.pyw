"""Inicia e supervisiona o nucleo no Windows sem criar um console."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.resolve()


def main() -> int:
    # pythonw nao cria console; CREATE_NO_WINDOW estende isso ao PowerShell
    # e ao Python do servidor. Esperar preserva a supervisao do Agendador.
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    powershell = (
        Path(os.environ["SystemRoot"])
        / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    )
    return subprocess.call(
        [
            str(powershell), "-NoProfile", "-NonInteractive",
            "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
            "-File", str(ROOT / "scripts" / "run.ps1"),
        ],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        startupinfo=startup,
    )


if __name__ == "__main__":
    raise SystemExit(main())
