"""
CONDOR — launcher silencioso.

Dois cliques neste arquivo e pronto: nenhum console, nenhuma janela piscando.
Ele fica de pé em segundo plano escutando a palavra de chamada. A janela só
aparece quando você chama.

Como .pyw, o Windows abre com pythonw.exe, que não cria terminal. Toda a
saida vai para ~/.condor/logs/condor.log. No Linux, use scripts/run.sh.

Pra parar: encerre o processo pythonw.exe pelo Gerenciador de Tarefas, ou rode
    Get-Process pythonw | Stop-Process
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from condor.instance import acquire

if not acquire("condor-server"):
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
            if os.name == "nt":
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    None,
                    "O Condor não conseguiu iniciar. Consulte ~/.condor/logs/condor.log.",
                    "CONDOR", 0x10)
        except Exception:
            pass


if __name__ == "__main__":
    main()
