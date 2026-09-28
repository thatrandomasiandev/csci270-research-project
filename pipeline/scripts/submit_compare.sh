#!/usr/bin/env bash
# Print (or, with --submit, later actually queue) comparison jobs.
# Default is --dry-run: print rsync/sbatch lines, do not SSH, rsync, or sbatch.
# Account biyik_1165. See docs/CARC_PLAN.md.
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
Environment:
  ACTS_SAVINGS_DEPS  optional Slurm afterany list, e.g. 123:124:125:126
  ACTS_CMP_BUILD_ID  optional afterok id for cmp_build once it is queued
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

if [[ "$DRY" -eq 0 ]]; then
  mkdir -p "${ROOT}/pipeline/results/compare"
  printf '%s\n' "$HASH" > "${ROOT}/pipeline/results/compare/GIT_HASH"
fi

SAV_DEP="${ACTS_SAVINGS_DEPS:-SAV_A_SCAN:SAV_A_SEARCH:SAV_B_SCAN:SAV_B_SEARCH}"
BUILD_DEP="${ACTS_CMP_BUILD_ID:-CMP_BUILD}"

echo "=== comparison submit (git ${HASH}) mode=${MODE} ==="
echo "# Placeholders SAV_* / CMP_BUILD become real ids after squeue. docs/CARC_PLAN.md."

run "ssh carc-transfer \"mkdir -p '${REMOTE}'/{scripts,jobs,acts,docs,results/compare/logs,data/hmmer,data/recurrence/A,data/recurrence/B,data/kprot,data/vep_chr22/subsets,builds/snpeff,data_compare}\""
run "rsync -avz --exclude '__pycache__' --exclude '*.pyc' '${ROOT}/pipeline/scripts/' 'carc-transfer:${REMOTE}/scripts/'"
run "rsync -avz --exclude '__pycache__' --exclude '*.pyc' '${ROOT}/pipeline/acts/' 'carc-transfer:${REMOTE}/acts/'"
run "rsync -avz '${ROOT}/pipeline/jobs/compare_build.job' '${ROOT}/pipeline/jobs/compare_hmmer.job' '${ROOT}/pipeline/jobs/compare_snpeff.job' 'carc-transfer:${REMOTE}/jobs/'"
run "rsync -avz '${ROOT}/pipeline/docs/CARC_PLAN.md' '${ROOT}/pipeline/docs/COMPARISON_PROTOCOL.md' 'carc-transfer:${REMOTE}/docs/'"
run "rsync -avz '${ROOT}/pipeline/results/headline_screen.json' '${ROOT}/pipeline/results/recurrence_accessions.json' '${ROOT}/pipeline/results/hmmer_predicted_speedup.json' 'carc-transfer:${REMOTE}/results/'"
run "rsync -avz '${ROOT}/pipeline/results/compare/GIT_HASH' 'carc-transfer:${REMOTE}/results/compare/'"

sbatch_cmd() {
  local extra="$1" name="$2" time="$3" jobfile="$4" export_extra="$5"
  printf "ssh discovery \"sbatch %s --job-name='%s' --time='%s' --export=ALL,ACTS_GIT_HASH=%s%s '%s/jobs/%s'\"" \
    "$extra" "$name" "$time" "$HASH" "$export_extra" "$REMOTE" "$jobfile"
  printf '\n'
}

echo "=== sbatch --test-only ==="
sbatch_cmd "--test-only --dependency=afterany:${SAV_DEP}" "cmp_build" "04:00:00" "compare_build.job" ""
sbatch_cmd "--test-only --dependency=afterok:${BUILD_DEP},afterany:${SAV_DEP}" "cmp_A_scan" "41:00:00" "compare_hmmer.job" ",ACTS_COMPARE_COLLECTION=A,ACTS_COMPARE_MODE=hmmscan"
sbatch_cmd "--test-only --dependency=afterok:${BUILD_DEP},afterany:${SAV_DEP}" "cmp_A_search" "12:00:00" "compare_hmmer.job" ",ACTS_COMPARE_COLLECTION=A,ACTS_COMPARE_MODE=hmmsearch"
sbatch_cmd "--test-only --dependency=afterok:${BUILD_DEP},afterany:${SAV_DEP}" "cmp_B_scan" "21:00:00" "compare_hmmer.job" ",ACTS_COMPARE_COLLECTION=B,ACTS_COMPARE_MODE=hmmscan"
sbatch_cmd "--test-only --dependency=afterok:${BUILD_DEP},afterany:${SAV_DEP}" "cmp_B_search" "09:00:00" "compare_hmmer.job" ",ACTS_COMPARE_COLLECTION=B,ACTS_COMPARE_MODE=hmmsearch"
sbatch_cmd "--test-only --dependency=afterok:${BUILD_DEP}" "cmp_snpeff" "02:00:00" "compare_snpeff.job" ""

if [[ "$DRY" -eq 1 ]]; then
  echo "=== live sbatch (not executed; --submit would run these without --test-only) ==="
  sbatch_cmd "--dependency=afterany:${SAV_DEP}" "cmp_build" "04:00:00" "compare_build.job" ""
  echo "# After cmp_build is queued, re-run with ACTS_CMP_BUILD_ID=<id> for the five timing jobs."
  echo "Requested exclusive node-hours (this script): 4+41+12+21+9+2 = 89"
  echo "Mordred / Whisper / F6: submit_fourth.sh / submit_f6.sh"
  exit 0
fi

echo "=== sbatch ==="
run "$(sbatch_cmd "--dependency=afterany:${SAV_DEP}" "cmp_build" "04:00:00" "compare_build.job" "")"
if [[ -z "${ACTS_CMP_BUILD_ID:-}" ]]; then
  echo "cmp_build submitted. Export ACTS_CMP_BUILD_ID and re-run $0 --submit for timing jobs."
  exit 0
fi
run "$(sbatch_cmd "--dependency=afterok:${BUILD_DEP},afterany:${SAV_DEP}" "cmp_A_scan" "41:00:00" "compare_hmmer.job" ",ACTS_COMPARE_COLLECTION=A,ACTS_COMPARE_MODE=hmmscan")"
run "$(sbatch_cmd "--dependency=afterok:${BUILD_DEP},afterany:${SAV_DEP}" "cmp_A_search" "12:00:00" "compare_hmmer.job" ",ACTS_COMPARE_COLLECTION=A,ACTS_COMPARE_MODE=hmmsearch")"
run "$(sbatch_cmd "--dependency=afterok:${BUILD_DEP},afterany:${SAV_DEP}" "cmp_B_scan" "21:00:00" "compare_hmmer.job" ",ACTS_COMPARE_COLLECTION=B,ACTS_COMPARE_MODE=hmmscan")"
run "$(sbatch_cmd "--dependency=afterok:${BUILD_DEP},afterany:${SAV_DEP}" "cmp_B_search" "09:00:00" "compare_hmmer.job" ",ACTS_COMPARE_COLLECTION=B,ACTS_COMPARE_MODE=hmmsearch")"
run "$(sbatch_cmd "--dependency=afterok:${BUILD_DEP}" "cmp_snpeff" "02:00:00" "compare_snpeff.job" "")"
