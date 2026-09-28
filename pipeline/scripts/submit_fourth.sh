#!/usr/bin/env bash
# Print (or, with --submit, later actually queue) fourth-tool screen jobs.
# Default --dry-run: no SSH. Whisper is BLOCKED unless ACTS_WHISPER_SUBMIT=1,
# and docs/CARC_PLAN.md still says BLOCKED even then.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REMOTE=/project2/biyik_1165/jjt_373/csci270-star/pipeline
HASH="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
MODE="${1:-"--dry-run"}"

usage() {
  cat <<EOF
Usage: $0 [--dry-run|--submit]
  --dry-run  (default) print commands; no SSH, no sbatch, no rsync
  --submit   rsync + sbatch Mordred only
Whisper: refused unless ACTS_WHISPER_SUBMIT=1. CARC_PLAN.md remains BLOCKED.
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

mkdir -p "${ROOT}/pipeline/results/fourth"

echo "=== fourth-tool submit (git ${HASH}) mode=${MODE} ==="
echo "# Mordred is the only screen that may be queued. Whisper is BLOCKED."

run "ssh carc-transfer \"mkdir -p '${REMOTE}'/{scripts,jobs,results/fourth/logs,data_carcjobs/chembl}\""
run "rsync -avz '${ROOT}/pipeline/jobs/fourth_mordred.job' '${ROOT}/pipeline/jobs/fourth_whisper.job' 'carc-transfer:${REMOTE}/jobs/'"
run "rsync -avz '${ROOT}/pipeline/docs/CARC_PLAN.md' '${ROOT}/pipeline/docs/FOURTH_SCREEN.md' 'carc-transfer:${REMOTE}/docs/'"

sbatch_cmd() {
  local extra="$1" name="$2" time="$3" jobfile="$4"
  printf "ssh discovery \"sbatch %s --job-name='%s' --time='%s' --export=ALL,ACTS_GIT_HASH=%s '%s/jobs/%s'\"" \
    "$extra" "$name" "$time" "$HASH" "$REMOTE" "$jobfile"
  printf '\n'
}

echo "=== sbatch --test-only (Mordred) ==="
sbatch_cmd "--test-only" "fourth_mordred" "12:00:00" "fourth_mordred.job"

echo "=== Whisper (BLOCKED) ==="
if [[ "${ACTS_WHISPER_SUBMIT:-}" != "1" ]]; then
  echo "REFUSING Whisper submit. docs/CARC_PLAN.md: BLOCKED until Josh approves"
  echo "--model small and the openai-whisper PyTorch wheel (may be >1 GB)."
  echo "To even print a Whisper sbatch line, export ACTS_WHISPER_SUBMIT=1."
  echo "The plan still says BLOCKED if that flag is set."
else
  echo "WARNING: ACTS_WHISPER_SUBMIT=1 is set, but docs/CARC_PLAN.md still says BLOCKED."
  echo "Josh has not approved the wheel. Printing --test-only only; live sbatch still skipped."
  sbatch_cmd "--test-only" "fourth_whisper" "24:00:00" "fourth_whisper.job"
  echo "Not submitting fourth_whisper.job (plan = BLOCKED)."
fi

if [[ "$DRY" -eq 1 ]]; then
  echo "=== live sbatch (not executed) ==="
  sbatch_cmd "" "fourth_mordred" "12:00:00" "fourth_mordred.job"
  echo "Requested exclusive node-hours (Mordred): 12. Whisper: 0 (BLOCKED)."
  exit 0
fi

echo "=== sbatch Mordred ==="
run "$(sbatch_cmd "" "fourth_mordred" "12:00:00" "fourth_mordred.job")"
echo "Whisper not submitted (BLOCKED)."
