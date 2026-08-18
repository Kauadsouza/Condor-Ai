#!/usr/bin/env sh
set -eu
if ! command -v ollama >/dev/null 2>&1; then
  printf '%s\n' "Instale o Ollama local conforme https://docs.ollama.com/linux" >&2
  exit 1
fi
export OLLAMA_HOST="127.0.0.1:11434"
export OLLAMA_MODELS="${CONDOR_HOME:-$HOME/.condor}/models"
export OLLAMA_NO_CLOUD="1"
export OLLAMA_NOHISTORY="1"
export OLLAMA_CONTEXT_LENGTH="32768"
exec ollama serve
