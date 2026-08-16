#!/usr/bin/env sh
set -eu
if ! command -v ollama >/dev/null 2>&1; then
  printf '%s\n' "Instale o Ollama local primeiro." >&2
  exit 1
fi
export OLLAMA_HOST="127.0.0.1:11434"
ollama pull qwen3:4b-instruct
exec ollama pull qwen3-vl:2b
