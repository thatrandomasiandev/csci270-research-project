#!/bin/bash
# Stage the headline pilot through discovery and sbatch it.
# Does not use carc-transfer. Does not run the scan on the login node.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="/project2/biyik_1165/jjt_373/csci270-star/headline_exact"
GIT_HEAD="$(git -C "${ROOT}" rev-parse HEAD)"
if [[ -n "$(git -C "${ROOT}" status --porcelain -- pipeline/acts pipeline/scripts/headline_carc_pilot.py pipeline/jobs/headline_carc_pilot.job)" ]]; then
  GIT_DIRTY="true"
else
  GIT_DIRTY="false"
fi

ssh -o BatchMode=yes -o ConnectTimeout=20 discovery "mkdir -p '${DEST}/acts' '${DEST}/scripts' '${DEST}/jobs' '${DEST}/results' '${DEST}/logs'"
rsync -a --delete --exclude '__pycache__' \
  "${ROOT}/pipeline/acts/" "discovery:${DEST}/acts/"
rsync -a \
  "${ROOT}/pipeline/scripts/headline_carc_pilot.py" \
  "discovery:${DEST}/scripts/headline_carc_pilot.py"
rsync -a \
  "${ROOT}/pipeline/jobs/headline_carc_pilot.job" \
  "discovery:${DEST}/jobs/headline_carc_pilot.job"
printf '%s\n' "${GIT_HEAD}" | ssh -o BatchMode=yes discovery "cat > '${DEST}/GIT_HEAD'"

ssh -o BatchMode=yes discovery \
  "export ACTS_GIT_HEAD='${GIT_HEAD}' ACTS_GIT_DIRTY='${GIT_DIRTY}'; sbatch --export=ALL,ACTS_GIT_HEAD='${GIT_HEAD}',ACTS_GIT_DIRTY='${GIT_DIRTY}' '${DEST}/jobs/headline_carc_pilot.job'"
