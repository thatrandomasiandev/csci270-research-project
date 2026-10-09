#!/usr/bin/env bash
# Stage this commit on its own CARC tree via discovery, then submit the
# pre-registered HMMER build and one-genome hmmscan stock array.
# Does not read or write results/savings/GIT_HASH. Does not use
# carc-transfer. Both sbatch calls pass --nice=10000.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PIPE="${ROOT}/pipeline"
HASH="$(git -C "${ROOT}" rev-parse HEAD)"
git -C "${ROOT}" diff --exit-code -- \
  pipeline/results/hmmscan_stock_tasks.json \
  pipeline/results/savings_20261006/A_hmmscan.json \
  pipeline/results/savings_20261006/B_hmmscan.json \
  pipeline/scripts/hmmscan_stock.py \
  pipeline/scripts/run_hmmscan_stock.py \
  pipeline/jobs/hmmscan_stock_completion.job \
  pipeline/docs/SAVINGS_PROTOCOL.md
REMOTE_BASE=/project2/biyik_1165/jjt_373/csci270-star
REMOTE="${REMOTE_BASE}/acts-hmmscan-stock-20261009"
DATA="${REMOTE_BASE}/pipeline"
MANIFEST="${PIPE}/results/hmmscan_stock_tasks.json"

python3 - "${PIPE}" "${MANIFEST}" <<'PY'
import json
import sys
from pathlib import Path

pipe = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
sys.path.insert(0, str(pipe))
sys.path.insert(0, str(pipe / "scripts"))
from hmmscan_stock import task_manifest
from acts.savings_analysis import stock_tasks
from savings_job_load import load_savings_job

jobs = [
    load_savings_job(pipe / "results/savings_20261006/A_hmmscan.json"),
    load_savings_job(pipe / "results/savings_20261006/B_hmmscan.json"),
]
expected = task_manifest(stock_tasks(jobs))
actual = json.loads(manifest_path.read_text())
if actual != expected:
    raise SystemExit("hmmscan_stock_tasks.json does not match the savings dumps")
if expected["n_tasks"] != 58:
    raise SystemExit(f"expected 58 stock tasks, found {expected['n_tasks']}")
PY

STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT
git -C "${ROOT}" archive HEAD \
  pipeline/acts \
  pipeline/scripts/hmmscan_stock.py \
  pipeline/scripts/run_hmmscan_stock.py \
  pipeline/jobs/hmmscan_stock_completion.job \
  pipeline/results/hmmscan_stock_tasks.json \
  | tar -x -C "${STAGE}"
ssh discovery "mkdir -p '${REMOTE}/results/hmmscan_stock/logs'"
rsync -a --exclude '__pycache__' --exclude '*.pyc' \
  "${STAGE}/pipeline/acts/" "discovery:${REMOTE}/acts/"
rsync -a "${STAGE}/pipeline/scripts/" "discovery:${REMOTE}/scripts/"
rsync -a "${STAGE}/pipeline/jobs/" "discovery:${REMOTE}/jobs/"
rsync -a "${STAGE}/pipeline/results/hmmscan_stock_tasks.json" \
  "discovery:${REMOTE}/hmmscan_stock_tasks.json"
printf '%s\n' "${HASH}" | ssh discovery "cat > '${REMOTE}/GIT_HASH'"

BUILD_LINE="$(ssh discovery "sbatch --nice=10000 --job-name=scan_stock_build --time=01:00:00 \
  --output='${REMOTE}/results/hmmscan_stock/logs/%x-%j.out' \
  --error='${REMOTE}/results/hmmscan_stock/logs/%x-%j.err' \
  --export=ALL,ACTS_CODE_ROOT='${REMOTE}',ACTS_DATA_ROOT='${DATA}',ACTS_STOCK_PHASE=build,ACTS_GIT_HASH_FILE='${REMOTE}/GIT_HASH' \
  '${REMOTE}/jobs/hmmscan_stock_completion.job'")"
echo "${BUILD_LINE}"
BUILD_ID="${BUILD_LINE##* }"

ssh discovery "sbatch --nice=10000 --job-name=scan_stock_measure --time=02:00:00 \
  --array=0-57 --dependency=afterok:${BUILD_ID} \
  --output='${REMOTE}/results/hmmscan_stock/logs/%x-%A_%a.out' \
  --error='${REMOTE}/results/hmmscan_stock/logs/%x-%A_%a.err' \
  --export=ALL,ACTS_CODE_ROOT='${REMOTE}',ACTS_DATA_ROOT='${DATA}',ACTS_STOCK_PHASE=measure,ACTS_GIT_HASH_FILE='${REMOTE}/GIT_HASH' \
  '${REMOTE}/jobs/hmmscan_stock_completion.job'"
