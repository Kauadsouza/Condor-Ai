"""
Ponto de entrada: python -m condor
Inicia o servidor FastAPI + todos os subsistemas.
"""
from __future__ import annotations

import asyncio
import logging
import sys


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Silencia logs muito verbosos de bibliotecas externas
    for noisy in ("httpx", "httpcore", "uvicorn.access", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def _main() -> None:
    from condor.config import load_config
    from condor.server import create_app, run_server

    config = load_config()
    app = await create_app(config)
    await run_server(app, config)


if __name__ == "__main__":
    _setup_logging()
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("\n[condor] Encerrado pelo usuário.")
