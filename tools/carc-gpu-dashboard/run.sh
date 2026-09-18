#!/usr/bin/env bash
# Launch the CARC GPU dashboard from this directory.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "$ROOT/.env"
  set +a
fi

exec python3 "$ROOT/server.py" "$@"
