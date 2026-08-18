"""Caminhos de estado portaveis.

O codigo pode ser clonado em qualquer lugar. Os dados privados ficam fora do
repositorio por padrao, em ``~/.condor``. CONDOR_HOME permite apontar para um
disco ou volume administrado pelo proprio dono.
"""

from __future__ import annotations

import os
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent.parent


def state_root() -> Path:
    configured = (os.getenv("CONDOR_HOME") or "").strip()
    root = Path(configured).expanduser() if configured else Path.home() / ".condor"
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root.resolve()


def state_path(*parts: str) -> Path:
    path = state_root().joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def resolver_alvo(bruto: str) -> Path:
    """Resolucao unica de caminho para ferramentas do agente.

    A politica e o executor precisam enxergar exatamente o mesmo destino. Quando
    cada lado normalizava por conta propria, ``%USERPROFILE%`` passava batido na
    politica (que so via um caminho relativo inofensivo) e virava a pasta pessoal
    de verdade na hora de gravar. Todo mundo passa por aqui agora.

    Nao chama ``resolve()``: quem valida precisa comparar as duas formas, com e
    sem link simbolico seguido.
    """
    texto = os.path.expandvars(str(bruto).strip().strip('"').strip("'"))
    caminho = Path(texto).expanduser()
    if not caminho.is_absolute():
        caminho = CODE_ROOT / caminho
    return Path(os.path.normpath(caminho))
