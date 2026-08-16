#!/usr/bin/env sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$PROJECT_ROOT/../.." && pwd)
HUB_ROOT=${CONDOR_HUB_SOURCE:-"$REPOSITORY_ROOT/ARTX Hub"}
if [ ! -f "$HUB_ROOT/package.json" ]; then
  printf '%s\n' "ARTX Hub nao encontrado em $HUB_ROOT." >&2
  exit 1
fi
cd "$HUB_ROOT"
npm install
CONDOR_LOCAL_BUILD=1 npm run build
printf '%s\n' "ARTX Command Center pronto em $HUB_ROOT/out"
