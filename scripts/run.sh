#!/usr/bin/env sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ ! -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  printf '%s\n' "Execute scripts/install.sh primeiro." >&2
  exit 1
fi

port_open() {
  "$PROJECT_ROOT/.venv/bin/python" -c \
    'import socket; s=socket.socket(); s.settimeout(.3); raise SystemExit(s.connect_ex(("127.0.0.1", 11434)))'
}

LOCAL_AI_PID=""
if command -v ollama >/dev/null 2>&1 && ! port_open; then
  CONDOR_STATE="${CONDOR_HOME:-$HOME/.condor}"
  mkdir -p "$CONDOR_STATE/logs" "$CONDOR_STATE/models"
  OLLAMA_HOST="127.0.0.1:11434" \
  OLLAMA_MODELS="$CONDOR_STATE/models" \
  OLLAMA_NO_CLOUD="1" OLLAMA_NOHISTORY="1" \
    ollama serve >>"$CONDOR_STATE/logs/ollama.log" 2>&1 &
  LOCAL_AI_PID=$!
  attempt=0
  while ! port_open && [ "$attempt" -lt 80 ]; do
    sleep 0.25
    attempt=$((attempt + 1))
  done
  if ! port_open; then
    kill "$LOCAL_AI_PID" 2>/dev/null || true
    printf '%s\n' "A IA local nao iniciou em 127.0.0.1:11434." >&2
    exit 1
  fi
fi

cleanup() {
  if [ -n "$LOCAL_AI_PID" ]; then
    kill "$LOCAL_AI_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM
"$PROJECT_ROOT/.venv/bin/python" -m condor
