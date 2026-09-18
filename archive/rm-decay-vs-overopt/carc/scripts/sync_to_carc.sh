#!/usr/bin/env bash
# Sync this repo to CARC via transfer node (Host carc-transfer in ~/.ssh/config).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=/dev/null
source "${ROOT}/carc/env.sh"

REMOTE_HOST="${CARC_RSYNC_HOST:-discovery}"
REMOTE_DIR="${CARC_REPO_DIR}"

echo "Syncing ${ROOT} -> ${REMOTE_HOST}:${REMOTE_DIR}"
# Prefer discovery login (BatchMode-friendly). Transfer node often requires Duo.
ssh -o BatchMode=yes "${REMOTE_HOST}" "mkdir -p '${REMOTE_DIR}'"
rsync -avz --progress \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.git' \
  --exclude 'results/raw' \
  --exclude 'results/sweep_*.log' \
  --exclude '.DS_Store' \
  "${ROOT}/" \
  "${REMOTE_HOST}:${REMOTE_DIR}/"
echo "Synced to ${REMOTE_DIR}"
