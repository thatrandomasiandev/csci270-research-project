#!/bin/bash
# Stage the TARE W8 release chain through the discovery host.
# Uses ssh/rsync to the host alias "discovery". Does not use carc-transfer.
# Usage: submit_release_chain.sh stage|pilot|measured [--submit]
# Without --submit the script stages, checks md5, and dry-runs imports.
# It does not sbatch. --submit sbatches only after that dry run passes.
set -euo pipefail

MODE="${1:-}"
SUBMIT="${2:-}"
if [[ "${MODE}" != "stage" && "${MODE}" != "pilot" && "${MODE}" != "measured" ]]; then
  echo "usage: $0 stage|pilot|measured [--submit]" >&2
  exit 2
fi
if [[ -n "${SUBMIT}" && "${SUBMIT}" != "--submit" ]]; then
  echo "usage: $0 stage|pilot|measured [--submit]" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="/project2/biyik_1165/jjt_373/csci270-star/tare-w8"
DATA="/scratch1/jjt_373/tare-w8/data"
GIT_HEAD="$(git -C "${ROOT}" rev-parse HEAD)"
DIRTY_PATHS=(
  pipeline/acts
  pipeline/scripts/release_chain_carc.py
  pipeline/scripts/headline_carc_measured.py
  pipeline/scripts/headline_analysis.py
  pipeline/scripts/headline_carc_pilot.py
  pipeline/jobs/release_chain_pilot.job
  pipeline/jobs/release_chain_measured.job
)
if [[ -n "$(git -C "${ROOT}" status --porcelain -- "${DIRTY_PATHS[@]}")" ]]; then
  echo "STOP: runner or acts is dirty; commit before staging" >&2
  exit 2
fi

ssh -o BatchMode=yes -o ConnectTimeout=20 discovery "mkdir -p \
  '${DEST}/acts' '${DEST}/scripts' '${DEST}/jobs' '${DEST}/results' '${DEST}/logs' \
  '${DATA}/37.3' '${DATA}/37.4' '${DATA}/38.0' '${DATA}/38.1' '${DATA}/38.2'"

rsync -a --delete --exclude '__pycache__' \
  "${ROOT}/pipeline/acts/" "discovery:${DEST}/acts/"
rsync -a \
  "${ROOT}/pipeline/scripts/release_chain_carc.py" \
  "${ROOT}/pipeline/scripts/headline_carc_measured.py" \
  "${ROOT}/pipeline/scripts/headline_analysis.py" \
  "${ROOT}/pipeline/scripts/headline_carc_pilot.py" \
  "discovery:${DEST}/scripts/"
rsync -a \
  "${ROOT}/pipeline/jobs/release_chain_pilot.job" \
  "${ROOT}/pipeline/jobs/release_chain_measured.job" \
  "discovery:${DEST}/jobs/"
rsync -a \
  "${ROOT}/pipeline/results/release_chain/pairs.json" \
  "discovery:${DEST}/pairs.json"
rsync -a \
  "${ROOT}/pipeline/results/diverse_genomes/draw.json" \
  "discovery:${DEST}/diverse_draw.json"
printf '%s\n' "${GIT_HEAD}" | ssh -o BatchMode=yes -o ConnectTimeout=20 discovery "cat > '${DEST}/GIT_HEAD'"

LOCAL="${HOME}/tmp/tare_c"
for ver in 37.3 37.4 38.0; do
  rsync -a "${LOCAL}/Pfam${ver}/Pfam-A.hmm.gz" "discovery:${DATA}/${ver}/Pfam-A.hmm.gz"
done
ssh -o BatchMode=yes -o ConnectTimeout=20 discovery "ln -sfn \
  /project2/biyik_1165/jjt_373/csci270-star/reference_reannot/data/pfam38.1/Pfam-A.hmm.gz \
  '${DATA}/38.1/Pfam-A.hmm.gz' && ln -sfn \
  /project2/biyik_1165/jjt_373/csci270-star/pipeline/data/hmmer/Pfam-A.hmm.gz \
  '${DATA}/38.2/Pfam-A.hmm.gz'"

echo "=== remote md5 ==="
ssh -o BatchMode=yes -o ConnectTimeout=20 discovery "md5sum \
  '${DATA}/37.3/Pfam-A.hmm.gz' \
  '${DATA}/37.4/Pfam-A.hmm.gz' \
  '${DATA}/38.0/Pfam-A.hmm.gz' \
  '${DATA}/38.1/Pfam-A.hmm.gz' \
  '${DATA}/38.2/Pfam-A.hmm.gz'"

echo "=== dry run in the staged tree ==="
ssh -o BatchMode=yes -o ConnectTimeout=30 discovery "bash -lc '
set -euo pipefail
if [[ -f /etc/profile.d/modules.sh ]]; then source /etc/profile.d/modules.sh; fi
module load python/3.11.9
cd ${DEST}
export PYTHONPATH=${DEST}:${DEST}/scripts
export ACTS_GENOMES=/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/recurrence/A
export ACTS_DIVERSE_DRAW=${DEST}/diverse_draw.json
python3 -c \"import headline_analysis, headline_carc_measured, acts\"
python3 scripts/release_chain_carc.py --self-test
python3 scripts/release_chain_carc.py --check-draw
python3 -m acts run --help >/dev/null
echo DRY_RUN_OK
'"

if [[ "${SUBMIT}" != "--submit" ]]; then
  echo "staged ${GIT_HEAD}; dry run done; not submitted"
  exit 0
fi
if [[ "${MODE}" == "stage" ]]; then
  echo "stage does not sbatch" >&2
  exit 2
fi

echo "=== exclusive-node count before sbatch ==="
ssh -o BatchMode=yes -o ConnectTimeout=20 discovery 'squeue -u $USER -h -t R,PD -o "%i %j %D %T"' \
  | awk '$2 ~ /^(tare-w8|tare-w12a|tare-w5x|tare-w12b|tare-w6)/ {n+=$3; c++} END {print "matched_jobs", c+0, "nodes", n+0}'

JOB="${DEST}/jobs/release_chain_${MODE}.job"
ssh -o BatchMode=yes -o ConnectTimeout=20 discovery \
  "sbatch --export=ALL,ACTS_GIT_HEAD='${GIT_HEAD}',ACTS_GIT_DIRTY='false' '${JOB}'"
