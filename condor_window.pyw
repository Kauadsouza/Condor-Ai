"""
A janela do Condor.

App de verdade, não aba de navegador: renderiza a interface sem barra de
endereço, com perfil efêmero (nada de cache servindo versão velha da UI).

Quem abre isto é a própria sessão, quando o Condor acorda. Você não precisa
rodar à mão — mas se quiser: pythonw condor_window.pyw [http://127.0.0.1:7777]

Instância única: chamar de novo com a janela aberta só traz ela pra frente.
"""

from __future__ import annotations

import ctypes
import sys

import webview

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7777"

TITULO = "Condor"
MUTEX = "CondorWindowSingleton"
JA_EXISTE = 183


def _trazer_pra_frente() -> None:
    try:
        user32 = ctypes.windll.user32
        janela = user32.FindWindowW(None, TITULO)
        if janela:
            user32.ShowWindow(janela, 9)        # SW_RESTORE
            user32.SetForegroundWindow(janela)
    except Exception:
        pass


def main() -> None:
    # use_last_error + get_last_error é a forma confiável de ler o
    # ERROR_ALREADY_EXISTS logo após o CreateMutexW.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, MUTEX)
    if ctypes.get_last_error() == JA_EXISTE:
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
    webview.start(private_mode=True, gui="edgechromium")


if __name__ == "__main__":
    main()
