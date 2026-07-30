"""
Janela nativa do Condor (pywebview).

App local de verdade: renderiza a UI HTML sem barra de navegador, em janela
própria, com cache ISOLADO (não compartilha o perfil do Edge de navegação).
É isso que mata o bug de "puxar versão antiga" — cada abertura usa um perfil
efêmero (private_mode), então nunca serve HTML/JS velho de cache.

Instância única: se já houver uma janela aberta, traz ela pra frente e sai.
Assim o comando `open condor` nunca empilha janelas.

Roda como processo separado: o launcher (ou o `open condor`) spawna este script.
Recebe a URL como primeiro argumento.

Uso: pythonw condor_window.pyw [http://127.0.0.1:7777]
"""
from __future__ import annotations

import ctypes
import os
import sys

import webview

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7777"


def _with_owner_token(url: str) -> str:
    """Anexa o token de dono (data/owner.token) como fragmento #k=...
    Fragmento NÃO vai pro servidor nem pra rede — só o navegador local lê.
    É o que faz ESTA janela (rodando no PC do dono) entrar como dono automático.
    Convidado remoto abre no navegador sem token → cai na tela de senha."""
    try:
        tok_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "data", "owner.token")
        if os.path.exists(tok_file):
            with open(tok_file, encoding="utf-8") as f:
                tok = f.read().strip()
            if tok and "#" not in url:
                return f"{url}#k={tok}"
    except Exception:
        pass
    return url


URL = _with_owner_token(URL)
_TITLE = "Condor"
_MUTEX_NAME = "CondorWindowSingleton"   # sessão-local basta; todas as janelas são do mesmo usuário
_ERROR_ALREADY_EXISTS = 183


def _focus_existing() -> None:
    """Traz a janela já aberta pra frente (restaura se minimizada)."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, _TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)          # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def main() -> None:
    # Instância única via mutex nomeado do Windows.
    # use_last_error=True + ctypes.get_last_error() é a forma confiável de ler
    # o ERROR_ALREADY_EXISTS logo após CreateMutexW (windll.GetLastError() perde o valor).
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        _focus_existing()
        sys.exit(0)

    webview.create_window(
        _TITLE,
        URL,
        width=1280,
        height=820,
        min_size=(900, 600),
        background_color="#0a0a14",
        text_select=True,
    )
    # private_mode=True  -> perfil efêmero, cache não persiste = sem versão velha
    # gui="edgechromium" -> usa o runtime WebView2 do Windows (nativo, leve)
    webview.start(private_mode=True, gui="edgechromium")


if __name__ == "__main__":
    main()
