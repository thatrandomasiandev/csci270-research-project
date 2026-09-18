#!/usr/bin/env bash
# Sync course STAR tree + Suite B data needed for graded Linux bake-off.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=/dev/null
source "${ROOT}/carc/env.sh"
REMOTE_HOST="${CARC_RSYNC_HOST:-discovery}"
echo "Syncing ${ROOT} -> ${REMOTE_HOST}:${CARC_REPO_DIR}"
ssh -o BatchMode=yes "${REMOTE_HOST}" "mkdir -p '${CARC_REPO_DIR}' '${CARC_REPO_DIR}/carc/logs'"
# Keep star/upstream/.git so the build job can reset to tag 2.7.11b.
# Protect remote-built binaries and logs from --delete.
rsync -avz --delete \
  --exclude '/.git/' \
  --exclude 'archive/' \
  --exclude '.cursor/' \
  --exclude '**/__pycache__/' \
  --exclude 'carc/logs/' \
  --exclude 'star/src/STAR_stock' \
  --exclude 'star/src/STAR_opt*' \
  --exclude 'star/src/STAR_optimized' \
  --exclude 'star/src/STAR_*mac*' \
  --exclude 'star/src/STAR_mac*' \
  --exclude 'star/upstream/source/STAR' \
  --exclude 'star/upstream/source/STARlong' \
  --exclude 'star/upstream/source/*.o' \
  --exclude 'star/upstream/source/*.a' \
  --exclude 'star/upstream/source/htslib/*.o' \
  --exclude 'star/bench/results/**' \
  --include 'star/bench/results/.gitkeep' \
  --exclude 'star/bench/datasets/suiteB/*/genome/' \
  --exclude 'star/bench/datasets/suiteB/*/genome_nb14_archived/' \
  --exclude 'star/bench/datasets/suiteB/*/fastq_sub*/' \
  --exclude 'star/writeup/paper/*.pdf' \
  --exclude 'star/writeup/paper/*.aux' \
  --exclude 'star/writeup/paper/*.out' \
  --exclude 'star/writeup/paper/*.log' \
  "${ROOT}/" "${REMOTE_HOST}:${CARC_REPO_DIR}/"
echo "Done."
