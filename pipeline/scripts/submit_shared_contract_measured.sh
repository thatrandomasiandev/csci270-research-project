#!/bin/bash
# Stage exp/shared-contract to tare-sharedcontract/, smoke now, measured after
# smoke OK and W13 array 13260162. Never force-push; never touch live jobs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="/project2/biyik_1165/jjt_373/csci270-star/tare-sharedcontract"
GENOMES="/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/recurrence/A"
W13_JOB="13260162"
GIT_HEAD="$(git -C "${ROOT}" rev-parse HEAD)"
GIT_DIRTY="$(git -C "${ROOT}" status --porcelain -- pipeline/acts pipeline/scripts/shared_contract_measured.py pipeline/jobs/shared_contract_smoke.job pipeline/jobs/shared_contract_measured.job pipeline/results/shared_contract/measured_draw.json pipeline/docs/SHARED_CONTRACT_MEASURED.md | grep -q . && echo true || echo false)"

if [[ "${GIT_DIRTY}" == "true" ]]; then
  echo "STOP: staged paths are dirty; commit first" >&2
  git -C "${ROOT}" status --porcelain -- pipeline/acts pipeline/scripts/shared_contract_measured.py pipeline/jobs pipeline/results/shared_contract/measured_draw.json pipeline/docs/SHARED_CONTRACT_MEASURED.md
  exit 2
fi

echo "=== local check-draw against CARC genome listing ==="
python3 - "${ROOT}" "${GENOMES}" << 'PY'
import json, hashlib, random, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
remote = sys.argv[2]
draw = json.loads((root / "pipeline/results/shared_contract/measured_draw.json").read_text())
listing = subprocess.check_output(
    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "discovery",
     f"ls -1 {remote}/*_protein.faa.gz"],
    text=True,
)
stems = sorted(
    Path(line.strip()).name[: -len("_protein.faa.gz")]
    for line in listing.splitlines()
    if line.strip()
)
exclude = set(draw["exclude_reasons"])
pool = [s for s in stems if s not in exclude]
digest = hashlib.sha256("\n".join(pool).encode()).hexdigest()
if len(pool) != draw["pool_n"] or digest != draw["pool_sha256"]:
    raise SystemExit(f"STOP: CARC pool {len(pool)} {digest} != {draw['pool_n']} {draw['pool_sha256']}")
drawn = sorted(random.Random(draw["seed_proteome"]).sample(pool, draw["n_draw"]))
if drawn != list(draw["draws"]):
    raise SystemExit(f"STOP: CARC draw {drawn} != {draw['draws']}")
print(f"CARC pool {len(pool)} {digest} matches; draw matches")
PY

echo "=== bash -n job scripts ==="
bash -n "${ROOT}/pipeline/jobs/shared_contract_smoke.job"
bash -n "${ROOT}/pipeline/jobs/shared_contract_measured.job"

echo "=== stage to ${DEST} ==="
ssh -o BatchMode=yes -o ConnectTimeout=20 discovery \
  "mkdir -p '${DEST}/pipeline/acts' '${DEST}/pipeline/scripts' '${DEST}/pipeline/jobs' '${DEST}/pipeline/results/shared_contract' '${DEST}/results' '${DEST}/logs'"

rsync -a --delete --exclude '__pycache__' \
  "${ROOT}/pipeline/acts/" "discovery:${DEST}/pipeline/acts/"
rsync -a \
  "${ROOT}/pipeline/scripts/shared_contract_measured.py" \
  "discovery:${DEST}/pipeline/scripts/"
rsync -a \
  "${ROOT}/pipeline/jobs/shared_contract_smoke.job" \
  "${ROOT}/pipeline/jobs/shared_contract_measured.job" \
  "discovery:${DEST}/pipeline/jobs/"
rsync -a \
  "${ROOT}/pipeline/results/shared_contract/measured_draw.json" \
  "${ROOT}/pipeline/docs/SHARED_CONTRACT_MEASURED.md" \
  "discovery:${DEST}/pipeline/results/shared_contract/"
# protocol doc also under docs for humans
ssh -o BatchMode=yes discovery "mkdir -p '${DEST}/pipeline/docs'"
rsync -a "${ROOT}/pipeline/docs/SHARED_CONTRACT_MEASURED.md" "discovery:${DEST}/pipeline/docs/"

# Prefer existing pinned tarball if present on project
ssh -o BatchMode=yes discovery \
  "if [[ -f /project2/biyik_1165/jjt_373/csci270-star/pipeline/builds/hmmer-3.4.tar.gz ]]; then
     ln -sfn /project2/biyik_1165/jjt_373/csci270-star/pipeline/builds/hmmer-3.4.tar.gz '${DEST}/hmmer-3.4.tar.gz'
   elif [[ -f /project2/biyik_1165/jjt_373/csci270-star/builds/hmmer-3.4.tar.gz ]]; then
     ln -sfn /project2/biyik_1165/jjt_373/csci270-star/builds/hmmer-3.4.tar.gz '${DEST}/hmmer-3.4.tar.gz'
   fi; true"

printf '%s\n' "${GIT_HEAD}" | ssh -o BatchMode=yes discovery "cat > '${DEST}/GIT_HEAD'"
echo "GIT_HEAD=${GIT_HEAD}"

echo "=== dry-run: import + check-draw on login (no compute) ==="
ssh -o BatchMode=yes -o ConnectTimeout=20 discovery \
  "source /etc/profile.d/modules.sh 2>/dev/null; module load python/3.11.9 || module load python; \
   export PYTHONPATH='${DEST}/pipeline'; python3 '${DEST}/pipeline/scripts/shared_contract_measured.py' --mode check-draw --genomes '${GENOMES}'"

echo "=== sbatch smoke (non-exclusive) ==="
SMOKE_OUT="$(ssh -o BatchMode=yes discovery \
  "export ACTS_GIT_HEAD='${GIT_HEAD}' ACTS_GIT_DIRTY='false' ACTS_CODE_ROOT='${DEST}'; \
   sbatch --export=ALL,ACTS_GIT_HEAD='${GIT_HEAD}',ACTS_GIT_DIRTY='false',ACTS_CODE_ROOT='${DEST}' \
   '${DEST}/pipeline/jobs/shared_contract_smoke.job")"
echo "${SMOKE_OUT}"
SMOKE_ID="$(echo "${SMOKE_OUT}" | awk '{print $4}')"
if [[ -z "${SMOKE_ID}" ]]; then
  echo "STOP: could not parse smoke job id" >&2
  exit 2
fi

echo "=== sbatch measured N=1,5,20 (afterok smoke + afterany W13) ==="
# Times: N=1 8h floor; N=5 24h; N=20 72h (pre-reg). Serialize N tasks via afterok
# so exclusive nodes stay within cap while W13 drains.
submit_n() {
  local n="$1"
  local time_lim="$2"
  local deps="$3"
  local out
  out="$(ssh -o BatchMode=yes discovery \
    "export ACTS_GIT_HEAD='${GIT_HEAD}' ACTS_GIT_DIRTY='false' ACTS_CODE_ROOT='${DEST}' ONLY_N='${n}'; \
     sbatch --export=ALL,ACTS_GIT_HEAD='${GIT_HEAD}',ACTS_GIT_DIRTY='false',ACTS_CODE_ROOT='${DEST}',ONLY_N='${n}' \
       --time='${time_lim}' \
       --dependency='${deps}' \
       --job-name=\"tare-sc-N${n}\" \
       '${DEST}/pipeline/jobs/shared_contract_measured.job")"
  echo "${out}"
  echo "${out}" | awk '{print $4}'
}

N1_ID="$(submit_n 1 08:00:00 "afterok:${SMOKE_ID},afterany:${W13_JOB}")"
echo "N1_ID=${N1_ID}"
N5_ID="$(submit_n 5 24:00:00 "afterok:${SMOKE_ID},afterok:${N1_ID},afterany:${W13_JOB}")"
echo "N5_ID=${N5_ID}"
N20_ID="$(submit_n 20 72:00:00 "afterok:${SMOKE_ID},afterok:${N1_ID},afterany:${W13_JOB}")"
echo "N20_ID=${N20_ID}"

echo "SUBMITTED smoke=${SMOKE_ID} measured_N1=${N1_ID} measured_N5=${N5_ID} measured_N20=${N20_ID}"
printf '%s\n' "smoke=${SMOKE_ID}" "N1=${N1_ID}" "N5=${N5_ID}" "N20=${N20_ID}" "git=${GIT_HEAD}" \
  | ssh -o BatchMode=yes discovery "cat > '${DEST}/SUBMITTED_JOBS.txt'"
