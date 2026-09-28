#!/usr/bin/env bash
# Print (or, with --submit, later actually queue) the non-exclusive F6 strace job.
# Default --dry-run: no SSH. See docs/CARC_PLAN.md for the JSON path mapping:
#   scripts/run_f6_trace_linux.py -> results/probe_eval_f6file_linux.json
#   jobs/f6_trace.job copies that file to results/f6_trace_linux.json
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REMOTE=/project2/biyik_1165/jjt_373/csci270-star/pipeline
HASH="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
MODE="${1:-"--dry-run"}"

usage() {
  cat <<EOF
Usage: $0 [--dry-run|--submit]
  --dry-run  (default) print commands; no SSH, no sbatch, no rsync
  --submit   rsync via carc-transfer and sbatch on discovery (Josh, after VPN + approval)
EOF
}

if [[ "$MODE" == "-h" || "$MODE" == "--help" ]]; then
  usage
  exit 0
fi
if [[ "$MODE" != "--dry-run" && "$MODE" != "--submit" ]]; then
  usage >&2
  exit 2
fi

DRY=1
[[ "$MODE" == "--submit" ]] && DRY=0

run() {
  if [[ "$DRY" -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
  else
    eval "$@"
  fi
}

echo "=== F6 submit (git ${HASH}) mode=${MODE} ==="
echo "# Non-exclusive. Script JSON: results/probe_eval_f6file_linux.json"
echo "# Job landing:   results/f6_trace_linux.json"

run "ssh carc-transfer \"mkdir -p '${REMOTE}'/{scripts,jobs,acts,fixtures/probe_eval,results/f6/logs,tools}\""
run "rsync -avz '${ROOT}/pipeline/scripts/run_f6_trace_linux.py' 'carc-transfer:${REMOTE}/scripts/'"
run "rsync -avz --exclude '__pycache__' --exclude '*.pyc' '${ROOT}/pipeline/acts/' 'carc-transfer:${REMOTE}/acts/'"
run "rsync -avz '${ROOT}/pipeline/fixtures/probe_eval/' 'carc-transfer:${REMOTE}/fixtures/probe_eval/'"
run "rsync -avz '${ROOT}/pipeline/jobs/f6_trace.job' 'carc-transfer:${REMOTE}/jobs/'"
run "rsync -avz '${ROOT}/pipeline/docs/CARC_PLAN.md' 'carc-transfer:${REMOTE}/docs/'"

sbatch_cmd() {
  local extra="$1"
  printf "ssh discovery \"sbatch %s --job-name='f6_trace' --time='00:30:00' --export=ALL,ACTS_GIT_HASH=%s '%s/jobs/f6_trace.job'\"" \
    "$extra" "$HASH" "$REMOTE"
  printf '\n'
}

echo "=== sbatch --test-only ==="
sbatch_cmd "--test-only"

if [[ "$DRY" -eq 1 ]]; then
  echo "=== live sbatch (not executed) ==="
  sbatch_cmd ""
  echo "Requested wall (shared node, not exclusive): 0.5 h. Est. actual 0.1 h."
  exit 0
fi

echo "=== sbatch ==="
run "$(sbatch_cmd "")"
