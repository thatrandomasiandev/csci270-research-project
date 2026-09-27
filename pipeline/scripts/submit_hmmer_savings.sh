#!/usr/bin/env bash
# From the Mac: rsync via carc-transfer, then four paired sbatch on discovery.
# Addendum 2026-09-27: stock sample + cached on the same exclusive epyc-7542 node.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REMOTE=/project2/biyik_1165/jjt_373/csci270-star/pipeline
HASH="$(git -C "$ROOT" rev-parse HEAD)"
TEST_ONLY=0
if [[ "${1:-}" == "--test-only" ]]; then
  TEST_ONLY=1
fi
mkdir -p "${ROOT}/pipeline/results/savings"
printf '%s\n' "$HASH" > "${ROOT}/pipeline/results/savings/GIT_HASH"

ssh carc-transfer "mkdir -p '${REMOTE}'/{scripts,jobs,acts,results/savings/logs,data/hmmer,data/recurrence/A,data/recurrence/B}"

rsync -avz --exclude '__pycache__' --exclude '*.pyc' \
  "${ROOT}/pipeline/scripts/" "carc-transfer:${REMOTE}/scripts/"
rsync -avz --exclude '__pycache__' --exclude '*.pyc' \
  "${ROOT}/pipeline/acts/" "carc-transfer:${REMOTE}/acts/"
rsync -avz \
  "${ROOT}/pipeline/jobs/hmmer_savings.job" \
  "carc-transfer:${REMOTE}/jobs/"
rsync -avz \
  "${ROOT}/pipeline/results/headline_screen.json" \
  "${ROOT}/pipeline/results/recurrence_accessions.json" \
  "${ROOT}/pipeline/results/hmmer_predicted_speedup.json" \
  "${ROOT}/pipeline/results/savings/GIT_HASH" \
  "carc-transfer:${REMOTE}/results/"
rsync -avz "${ROOT}/pipeline/results/savings/GIT_HASH" \
  "carc-transfer:${REMOTE}/results/savings/"
rsync -avz "${ROOT}/pipeline/data/recurrence/A/" "carc-transfer:${REMOTE}/data/recurrence/A/"
rsync -avz "${ROOT}/pipeline/data/recurrence/B/" "carc-transfer:${REMOTE}/data/recurrence/B/"
if [[ -f "${ROOT}/pipeline/data/hmmer/Pfam-A.hmm.gz" ]]; then
  rsync -avz "${ROOT}/pipeline/data/hmmer/Pfam-A.hmm.gz" \
    "carc-transfer:${REMOTE}/data/hmmer/"
fi
if [[ -f "${ROOT}/pipeline/data/hmmer/Pfam.version.gz" ]]; then
  rsync -avz "${ROOT}/pipeline/data/hmmer/Pfam.version.gz" \
    "carc-transfer:${REMOTE}/data/hmmer/"
fi

sbatch_cmd() {
  local extra="$1" name="$2" time="$3" coll="$4" mode="$5"
  ssh discovery "sbatch ${extra} --job-name='${name}' --time='${time}' \
    --export=ALL,ACTS_SAVINGS_COLLECTION=${coll},ACTS_SAVINGS_MODE=${mode},ACTS_GIT_HASH=${HASH} \
    '${REMOTE}/jobs/hmmer_savings.job'"
}

# --time from addendum 2026-09-27 (1.5× combined predicted wall + 1 h, snapped).
JOBS=(
  "sav_A_scan 22:00:00 A hmmscan"
  "sav_A_search 07:00:00 A hmmsearch"
  "sav_B_scan 12:00:00 B hmmscan"
  "sav_B_search 06:00:00 B hmmsearch"
)

echo "=== sbatch --test-only (git ${HASH}) ==="
for spec in "${JOBS[@]}"; do
  # shellcheck disable=SC2086
  set -- $spec
  echo "--- $1 ---"
  sbatch_cmd "--test-only" "$1" "$2" "$3" "$4"
done

if [[ "$TEST_ONLY" -eq 1 ]]; then
  exit 0
fi

echo "=== sbatch ==="
for spec in "${JOBS[@]}"; do
  # shellcheck disable=SC2086
  set -- $spec
  sbatch_cmd "" "$1" "$2" "$3" "$4"
done
