#!/usr/bin/env sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SERVICE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$SERVICE_DIR"
SERVICE_FILE="$SERVICE_DIR/condor.service"
ESCAPED_ROOT=$(printf '%s' "$PROJECT_ROOT" | sed 's/ /\\x20/g')
{
  printf '%s\n' '[Unit]'
  printf '%s\n' 'Description=Condor local e ARTX Hub'
  printf '%s\n' 'After=graphical-session.target network.target'
  printf '%s\n' '' '[Service]'
  printf '%s\n' 'Type=simple'
  printf 'WorkingDirectory=%s\n' "$ESCAPED_ROOT"
  printf 'ExecStart=%s/scripts/run.sh\n' "$ESCAPED_ROOT"
  printf '%s\n' 'Restart=on-failure' 'RestartSec=5'
  printf '%s\n' '' '[Install]' 'WantedBy=default.target'
} >"$SERVICE_FILE"
systemctl --user daemon-reload
systemctl --user enable --now condor.service
printf '%s\n' "Inicializacao local instalada em $SERVICE_FILE"
