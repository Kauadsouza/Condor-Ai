#!/usr/bin/env sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python3 -m venv "$PROJECT_ROOT/.venv"
"$PROJECT_ROOT/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_ROOT/.venv/bin/python" -m pip install -e "$PROJECT_ROOT"
"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/install_voice_models.py"
"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/testes/rodar_testes.py"
sh "$PROJECT_ROOT/scripts/install_app_shortcut.sh"
printf '%s\n' "Condor instalado em $PROJECT_ROOT/.venv"
