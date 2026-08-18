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
from urllib.parse import urlsplit

import webview

from condor.paths import state_path
from condor.windows_identity import apply_window, prepare_process

PADRAO = "http://127.0.0.1:7777/ui/index.html"


def _url_local(bruto: str) -> str:
    """So aceita o servidor local do Condor.

    A URL chega por argv, entao quem conseguir lancar este processo escolheria a
    pagina renderizada dentro da janela do Condor — que roda com WebView2 e a
    identidade do aplicativo. Fora do loopback, cai no padrao.
    """
    partes = urlsplit(bruto)
    if partes.scheme != "http" or partes.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return PADRAO
    return bruto


def _com_segredo_de_boot(url: str) -> str:
    """Anexa o segredo do boot como fragmento (nunca vai pro servidor na URL).

    O arquivo so e legivel pelo dono; e assim que a janela prova pra API que e
    o cliente local de verdade, e nao outro programa qualquer da maquina. O
    session.js le, manda no cabecalho e limpa o fragmento na hora.
    """
    try:
        token = state_path("security", "ui-token").read_text(encoding="utf-8").strip()
    except OSError:
        return url
    return f"{url}#t={token}" if token else url


URL = _com_segredo_de_boot(_url_local(sys.argv[1] if len(sys.argv) > 1 else PADRAO))

TITULO = "Condor"
ROOT = Path(__file__).resolve().parent
ICON_PATH = ROOT / "condor" / "ui" / "assets" / (
    "condor-logo.ico" if os.name == "nt" else "condor-logo.png"
)


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

    prepare_process()
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
    webview.start(apply_window, args=(TITULO, ROOT), **options)


if __name__ == "__main__":
    main()
