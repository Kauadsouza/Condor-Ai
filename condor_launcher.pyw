"""
CONDOR — launcher silencioso.

Dois cliques neste arquivo e pronto: nenhum console, nenhuma janela piscando.
Ele fica de pé em segundo plano escutando a palavra de chamada. A janela só
aparece quando você chama.

Como .pyw, o Windows abre com pythonw.exe, que não cria terminal. Toda a
saída vai pra data/condor.log.

Pra parar: encerre o processo pythonw.exe pelo Gerenciador de Tarefas, ou rode
    Get-Process pythonw | Stop-Process
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Instância única: chamar de novo não sobe um segundo Condor disputando o
# microfone e a porta 7777.
_MUTEX = "CondorServidorSingleton"
_JA_EXISTE = 183

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW(None, False, _MUTEX)
if ctypes.get_last_error() == _JA_EXISTE:
    sys.exit(0)


def main() -> None:
    import asyncio

    from condor.__main__ import preparar_log, principal

    preparar_log()
    try:
        asyncio.run(principal())
    except KeyboardInterrupt:
        pass
    except Exception:
        import logging
        logging.getLogger("condor").exception("Caí no boot")
        # Sem console pra mostrar o erro: avisa numa caixa do Windows mesmo.
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                "O Condor não conseguiu iniciar.\n\n"
                "O motivo está em data\\condor.log.",
                "CONDOR", 0x10)
        except Exception:
            pass


if __name__ == "__main__":
    main()
