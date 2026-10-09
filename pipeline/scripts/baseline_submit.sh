#!/bin/bash
# Stage baseline files through discovery. Do not use carc-transfer.
set -euo pipefail

REMOTE_HOST=discovery
ROOT=/project2/biyik_1165/jjt_373/csci270-star/acts-baselines-20261009
LOCAL="$(cd "$(dirname "$0")/../.." && pwd)"
HASH="$(git -C "${LOCAL}" rev-parse HEAD)"

ssh "${REMOTE_HOST}" "mkdir -p '${ROOT}/'{scripts,jobs,results,logs,bin,data,src}"
rsync -a \
  "${LOCAL}/pipeline/scripts/baseline_match.py" \
  "${LOCAL}/pipeline/scripts/baseline_smoke.py" \
  "${LOCAL}/pipeline/scripts/baseline_build_report.py" \
  "${LOCAL}/pipeline/scripts/baseline_submit.sh" \
  "${REMOTE_HOST}:${ROOT}/scripts/"
rsync -a \
  "${LOCAL}/pipeline/jobs/baseline_build.job" \
  "${LOCAL}/pipeline/jobs/baseline_smoke.job" \
  "${REMOTE_HOST}:${ROOT}/jobs/"
printf '%s\n' "${HASH}" | ssh "${REMOTE_HOST}" "cat > '${ROOT}/ACTS_GIT_HASH'"
echo "staged ${HASH} at ${ROOT}"

phase="${1:-stage}"
if [[ "${phase}" == "stage" ]]; then
  exit 0
fi
if [[ "${phase}" == "build" ]]; then
  ssh "${REMOTE_HOST}" "sbatch --export=ALL,ACTS_GIT_HASH_FILE=${ROOT}/ACTS_GIT_HASH '${ROOT}/jobs/baseline_build.job'"
  exit 0
fi
echo "unknown phase ${phase}" >&2
exit 2
