"""
Ponto de entrada: python -m condor

Não abre janela e não imprime nada obrigatório. Tudo vai pro log em
~/.condor/logs/condor.log. Pra acompanhar em tempo real no Windows:

    Get-Content $HOME\\.condor\\logs\\condor.log -Wait -Tail 30
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import sys
from pathlib import Path

from condor.config import carregar_config
from condor.paths import state_root
from condor.server import montar, rodar

ROOT = Path(__file__).parent.parent
LOG = state_root() / "logs" / "condor.log"


def preparar_log(verboso: bool = False) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    formato = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)-22s %(message)s", "%H:%M:%S")

    arquivo = logging.handlers.RotatingFileHandler(
        LOG, maxBytes=3_000_000, backupCount=2, encoding="utf-8")
    arquivo.setFormatter(formato)

    raiz = logging.getLogger()
    raiz.setLevel(logging.DEBUG if verboso else logging.INFO)
    raiz.addHandler(arquivo)

    # Só imprime no terminal quando você roda à mão (python -m condor).
    # Pelo launcher .pyw não existe terminal, então nem tenta.
    try:
        if sys.stdout is not None and sys.stdout.isatty():
            console = logging.StreamHandler()
            console.setFormatter(formato)
            raiz.addHandler(console)
    except Exception:
        pass

    for barulhento in ("httpx", "httpcore", "openai", "urllib3", "asyncio",
                       "uvicorn.access", "multipart"):
        logging.getLogger(barulhento).setLevel(logging.WARNING)


async def principal() -> None:
    config = carregar_config()
    app, _sessao = montar(config)
    logging.getLogger("condor").info(
        "CONDOR de pé em http://%s:%s", config.servidor.host, config.servidor.porta)
    await rodar(app, config)


def main() -> None:
    from condor.instance import acquire
    if not acquire("condor-server"):
        return
    preparar_log("-v" in sys.argv)
    try:
        asyncio.run(principal())
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.getLogger("condor").exception("Falha no boot do Condor")
        raise


if __name__ == "__main__":
    main()
