#!/usr/bin/env bash
# Dry-run helper for the confirmatory hmmscan jobs (docs/CONFIRM_PROTOCOL.md).
# Default is --dry-run: print commands, bash -n the job file, do not ssh, do not sbatch.
# --submit is the only path that would rsync/sbatch; this agent does not invoke it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REMOTE=/project2/biyik_1165/jjt_373/csci270-star/pipeline
HASH="$(git -C "$ROOT" rev-parse HEAD)"
JOB="${ROOT}/pipeline/jobs/confirm_scan.job"
MODE="dry-run"

usage() {
  cat <<EOF
Usage: $0 [--dry-run|--submit]
  --dry-run   (default) validate job file and print planned sbatch lines; no ssh, no sbatch
  --submit    rsync + sbatch on discovery (do not run until Josh approves CONFIRM_PLAN.md)
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ "${1:-}" == "--submit" ]]; then
  MODE="submit"
elif [[ -z "${1:-}" || "${1:-}" == "--dry-run" ]]; then
  MODE="dry-run"
else
  usage >&2
  exit 2
fi

bash -n "$JOB"
echo "bash -n ok: $JOB"

mkdir -p "${ROOT}/pipeline/results/confirm/logs"
printf '%s\n' "$HASH" > "${ROOT}/pipeline/results/confirm/GIT_HASH"

# --time from docs/CONFIRM_PLAN.md (ceil_hours on locked confirm_predictions.json).
JOBS=(
  "conf_E_scan 36:00:00 confirm_E hmmscan"
  "conf_C_scan 16:00:00 confirm_C hmmscan"
)

sbatch_line() {
  local extra="$1" name="$2" time="$3" coll="$4" mode="$5"
  printf 'sbatch %s --job-name=%q --time=%q --export=ALL,ACTS_CONFIRM_COLLECTION=%s,ACTS_CONFIRM_MODE=%s,ACTS_GIT_HASH=%s %q\n' \
    "$extra" "$name" "$time" "$coll" "$mode" "$HASH" "${REMOTE}/jobs/confirm_scan.job"
}

echo "=== ${MODE} (git ${HASH}) ==="
echo "Would mkdir ${REMOTE}/{scripts,jobs,acts,results/confirm/logs,data/hmmer,data/recurrence/C,data_confirm/E}"
echo "Would rsync pipeline/scripts/ pipeline/acts/ pipeline/jobs/confirm_scan.job"
echo "Would rsync results/headline_screen.json results/recurrence_accessions.json results/confirm_predictions.json results/confirm/GIT_HASH"
echo "Would rsync pipeline/data_confirm/E/ and pipeline/data/recurrence/C/ (C read-only from data/)"
echo "Would rsync Pfam-A if present under data/hmmer/"
for spec in "${JOBS[@]}"; do
  # shellcheck disable=SC2086
  set -- $spec
  echo "--- $1 ---"
  sbatch_line "--test-only" "$1" "$2" "$3" "$4"
done

if [[ "$MODE" == "dry-run" ]]; then
  echo "dry-run: no ssh, no sbatch, no rsync."
  exit 0
fi

echo "=== submit blocked in this checkout until Josh approves docs/CONFIRM_PLAN.md ==="
echo "Not running ssh/sbatch. Re-run from the Mac after approval."
exit 2
