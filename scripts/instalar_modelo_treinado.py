"""Registra no Ollama o modelo que o notebook do Colab treinou.

Uso (com o Ollama do Condor ligado):

    .venv\\Scripts\\python.exe scripts\\instalar_modelo_treinado.py C:\\Downloads\\condor-q4_k_m.gguf

Copia do modelo base (qwen3:4b-instruct) o molde de conversa, os parâmetros e
o suporte a ferramentas, trocando só os pesos. Depois, na aba Sistema do
Condor, escolha "CONDOR TREINADO" como modelo local. Para voltar, escolha de
novo o QWEN3 4B: o modelo original continua instalado.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
OLLAMA = "http://127.0.0.1:11434"
NOME = "condor-treinado"


def _api(caminho: str, dados: dict, timeout: float = 120) -> dict:
    pedido = urllib.request.Request(
        f"{OLLAMA}{caminho}", data=json.dumps(dados).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def _ollama_exe() -> str:
    local = RAIZ / "runtime" / "ollama" / "windows" / "ollama.exe"
    if local.is_file():
        return str(local)
    achado = shutil.which("ollama")
    if not achado:
        raise SystemExit("ollama.exe não encontrado (rode scripts\\install_local_ai.ps1).")
    return achado


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("gguf", type=Path, help="arquivo .gguf devolvido pelo notebook")
    parser.add_argument("--base", default="qwen3:4b-instruct", help="modelo base usado no treino")
    parser.add_argument("--nome", default=NOME, help="nome do modelo no Ollama")
    args = parser.parse_args()

    gguf = args.gguf.expanduser().resolve()
    if not gguf.is_file() or gguf.suffix.lower() != ".gguf":
        raise SystemExit(f"arquivo .gguf não encontrado: {gguf}")
    try:
        base = _api("/api/show", {"model": args.base}, timeout=20)
    except OSError as exc:
        raise SystemExit(f"Ollama fora do ar em {OLLAMA} ({exc}). Abra o Condor e tente de novo.")

    modelfile, trocas = re.subn(r"(?m)^FROM .*$", f"FROM {gguf.as_posix()}", base["modelfile"], count=1)
    if not trocas:
        raise SystemExit("o Modelfile do modelo base não tem linha FROM; nada foi alterado.")

    with tempfile.TemporaryDirectory() as tmp:
        arquivo = Path(tmp) / "Modelfile"
        arquivo.write_text(modelfile, encoding="utf-8")
        print(f"Registrando {args.nome} a partir de {gguf.name} (molde de {args.base})...")
        env = {**os.environ, "OLLAMA_HOST": OLLAMA.removeprefix("http://")}
        resultado = subprocess.run([_ollama_exe(), "create", args.nome, "-f", str(arquivo)], env=env)
        if resultado.returncode != 0:
            raise SystemExit("o Ollama recusou o modelo; confira se o .gguf veio do notebook do Condor.")

    print("Teste rápido:")
    resposta = _api("/api/chat", {
        "model": args.nome, "stream": False,
        "messages": [{"role": "user", "content": "Em uma frase: quem é você e quem é o seu dono?"}],
    }, timeout=180)
    print("  ", resposta.get("message", {}).get("content", "").strip()[:400])
    print(f"\nPronto. Na aba Sistema do Condor escolha MODELO LOCAL = CONDOR TREINADO.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
