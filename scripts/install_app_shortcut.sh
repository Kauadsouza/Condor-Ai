#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON="$PROJECT_ROOT/.venv/bin/python"
APP_ENTRY="$PROJECT_ROOT/condor_app.pyw"
APPLICATION_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
APPLICATION_FILE="$APPLICATION_DIR/condor.desktop"

if [ ! -x "$PYTHON" ]; then
  printf '%s\n' "Execute scripts/install.sh antes de criar o aplicativo." >&2
  exit 1
fi

mkdir -p "$APPLICATION_DIR"
{
  printf '%s\n' '[Desktop Entry]'
  printf '%s\n' 'Type=Application'
  printf '%s\n' 'Name=Condor'
  printf '%s\n' 'Comment=Sistema local privado Condor'
  printf 'Exec="%s" "%s"\n' "$PYTHON" "$APP_ENTRY"
  printf '%s\n' 'Terminal=false'
  printf '%s\n' 'Categories=Utility;Development;'
} >"$APPLICATION_FILE"
chmod 700 "$APPLICATION_FILE"

if [ -d "$HOME/Desktop" ]; then
  cp "$APPLICATION_FILE" "$HOME/Desktop/Condor.desktop"
  chmod 700 "$HOME/Desktop/Condor.desktop"
fi

printf '%s\n' "Aplicativo Condor criado em $APPLICATION_FILE"
