#!/bin/bash
# Stage the TARE release chain through the discovery host and sbatch one mode.
# Uses ssh/rsync to the host alias "discovery". Does not use carc-transfer.
# Usage: submit_release_chain.sh pilot|measured
set -euo pipefail

MODE="${1:-}"
if [[ "${MODE}" != "pilot" && "${MODE}" != "measured" ]]; then
  echo "usage: $0 pilot|measured" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="/project2/biyik_1165/jjt_373/csci270-star/release_chain"
GIT_HEAD="$(git -C "${ROOT}" rev-parse HEAD)"
if [[ -n "$(git -C "${ROOT}" status --porcelain -- pipeline/acts pipeline/scripts/release_chain_carc.py pipeline/scripts/headline_carc_measured.py pipeline/scripts/headline_carc_pilot.py pipeline/jobs/release_chain_pilot.job pipeline/jobs/release_chain_measured.job)" ]]; then
  echo "STOP: runner or acts is dirty; commit before sbatch" >&2
  exit 2
fi

ssh -o BatchMode=yes -o ConnectTimeout=20 discovery "mkdir -p '${DEST}/acts' '${DEST}/scripts' '${DEST}/jobs' '${DEST}/results' '${DEST}/logs' '${DEST}/data/37.0' '${DEST}/data/37.1' '${DEST}/data/37.2' '${DEST}/data/37.3' '${DEST}/data/37.4' '${DEST}/data/38.0' '${DEST}/data/38.1' '${DEST}/data/38.2'"
rsync -a --delete --exclude '__pycache__' \
  "${ROOT}/pipeline/acts/" "discovery:${DEST}/acts/"
rsync -a \
  "${ROOT}/pipeline/scripts/release_chain_carc.py" \
  "${ROOT}/pipeline/scripts/headline_carc_measured.py" \
  "${ROOT}/pipeline/scripts/headline_carc_pilot.py" \
  "discovery:${DEST}/scripts/"
rsync -a \
  "${ROOT}/pipeline/jobs/release_chain_${MODE}.job" \
  "discovery:${DEST}/jobs/release_chain_${MODE}.job"
rsync -a \
  "${ROOT}/pipeline/results/release_chain/pairs.json" \
  "discovery:${DEST}/pairs.json"
printf '%s\n' "${GIT_HEAD}" | ssh -o BatchMode=yes discovery "cat > '${DEST}/GIT_HEAD'"

# Six approved archives. 38.1 and 38.2 are already on the project; link them.
DATA="${HOME}/tmp/tare_c"
for ver in 37.0 37.1 37.2 37.3 37.4 38.0; do
  rsync -a "${DATA}/Pfam${ver}/Pfam-A.hmm.gz" "discovery:${DEST}/data/${ver}/Pfam-A.hmm.gz"
done
ssh -o BatchMode=yes discovery "mkdir -p '${DEST}/data/38.1' '${DEST}/data/38.2' && ln -sfn /project2/biyik_1165/jjt_373/csci270-star/reference_reannot/data/pfam38.1/Pfam-A.hmm.gz '${DEST}/data/38.1/Pfam-A.hmm.gz' && ln -sfn /project2/biyik_1165/jjt_373/csci270-star/pipeline/data/hmmer/Pfam-A.hmm.gz '${DEST}/data/38.2/Pfam-A.hmm.gz'"

ssh -o BatchMode=yes discovery \
  "export ACTS_GIT_HEAD='${GIT_HEAD}' ACTS_GIT_DIRTY='false'; sbatch --export=ALL,ACTS_GIT_HEAD='${GIT_HEAD}',ACTS_GIT_DIRTY='false' '${DEST}/jobs/release_chain_${MODE}.job'"
