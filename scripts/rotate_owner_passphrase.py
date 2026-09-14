"""Troca a frase de acesso do dono do Condor neste PC, sem precisar do app aberto.

Reaproveita a mesma logica usada por /api/seguranca/trocar-frase em condor/server.py
(condor.security.passphrase.rotate_passphrase), rodando localmente e sem rede.

Uso:
    python scripts/rotate_owner_passphrase.py

Feche o Condor (janela e processo em segundo plano) antes de rodar este script.
Se o app estiver aberto ao mesmo tempo, ele pode reescrever o cofre com a chave
antiga por cima e travar tudo.
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from condor.paths import state_path
from condor.security.approval import OwnerAuth
from condor.security.passphrase import PassphraseRotationError, rotate_passphrase
from condor.security.vault import CondorVault


def main() -> int:
    owner = OwnerAuth(state_path("security", "owner.json"))
    vault = CondorVault(state_path("security", "vault.json"))

    if not owner.configured or not vault.exists:
        print("Identidade do dono ainda nao foi configurada neste PC.")
        return 1

    print("Confirme que o Condor esta fechado (janela e processo em segundo plano).")
    input("Pressione Enter para continuar...")

    current = getpass.getpass("Frase atual: ")
    replacement = getpass.getpass("Nova frase (12+ caracteres): ")
    confirm = getpass.getpass("Confirme a nova frase: ")
    if replacement != confirm:
        print("As novas frases nao coincidem.")
        return 1

    try:
        rotate_passphrase(vault, owner, current, replacement)
    except PassphraseRotationError as exc:
        print(f"Falha: {exc}")
        return 1

    vault.lock()
    print("Frase trocada. Guarde a nova frase em um cofre de senhas, fora deste PC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
