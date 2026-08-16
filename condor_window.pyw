"""
A janela do Condor.

App de verdade, não aba de navegador: renderiza a interface sem barra de
endereço, com perfil efêmero (nada de cache servindo versão velha da UI).

Quem abre isto é a própria sessão, quando o Condor acorda. Você não precisa
rodar à mão — mas se quiser: pythonw condor_window.pyw [http://127.0.0.1:7777]

Instância única: chamar de novo com a janela aberta só traz ela pra frente.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import webview

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7777/ui/index.html"

TITULO = "Condor"
ROOT = Path(__file__).resolve().parent
ICON_PATH = ROOT / "condor" / "ui" / "assets" / (
    "condor-logo.ico" if os.name == "nt" else "condor-logo.png"
)


def _preparar_identidade_windows() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ARTX.Condor.Local")
    except Exception:
        pass


def _trazer_pra_frente() -> None:
    try:
        if os.name != "nt":
            return
        import ctypes
        user32 = ctypes.windll.user32
        janela = user32.FindWindowW(None, TITULO)
        if janela:
            user32.ShowWindow(janela, 9)        # SW_RESTORE
            user32.SetForegroundWindow(janela)
    except Exception:
        pass


def main() -> None:
    from condor.instance import acquire

    _preparar_identidade_windows()
    if not acquire("condor-window"):
        _trazer_pra_frente()
        sys.exit(0)

    webview.create_window(
        TITULO, URL,
        width=1280, height=820, min_size=(900, 600),
        background_color="#02030A",
        text_select=True,
    )
    # private_mode=True  → perfil descartável, sem cache velho
    # gui="edgechromium" → WebView2, o runtime nativo do Windows
    options = {"private_mode": True}
    if ICON_PATH.is_file():
        options["icon"] = str(ICON_PATH)
    if os.name == "nt":
        options["gui"] = "edgechromium"
    webview.start(**options)


if __name__ == "__main__":
    main()
