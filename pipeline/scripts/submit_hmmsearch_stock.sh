#!/usr/bin/env bash
# Stage this commit on its own CARC tree, then submit the pre-registered
# HMMER build and one-genome stock array. Does not read or write
# results/savings/GIT_HASH.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PIPE="${ROOT}/pipeline"
HASH="$(git -C "${ROOT}" rev-parse HEAD)"
REMOTE_BASE=/project2/biyik_1165/jjt_373/csci270-star
REMOTE="${REMOTE_BASE}/acts-hmmsearch-stock-20261008"
DATA="${REMOTE_BASE}/pipeline"
MANIFEST="${PIPE}/results/hmmsearch_stock_tasks.json"

python3 - "${PIPE}" "${MANIFEST}" <<'PY'
import json
import sys
from pathlib import Path

pipe = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
sys.path.insert(0, str(pipe))
sys.path.insert(0, str(pipe / "scripts"))
from hmmsearch_stock import task_manifest
from acts.savings_analysis import load_job, stock_tasks

jobs = [
    load_job(pipe / "results/savings_20261006/A_hmmsearch.json"),
    load_job(pipe / "results/savings_20261006/B_hmmsearch.json"),
]
expected = task_manifest(stock_tasks(jobs))
actual = json.loads(manifest_path.read_text())
if actual != expected:
    raise SystemExit("hmmsearch_stock_tasks.json does not match the savings dumps")
if expected["n_tasks"] != 58:
    raise SystemExit(f"expected 58 stock tasks, found {expected['n_tasks']}")
PY

ssh carc-transfer "mkdir -p '${REMOTE}/results/hmmsearch_stock/logs'"
tar --exclude '__pycache__' --exclude '*.pyc' -C "${PIPE}" -cf - \
  acts scripts/hmmsearch_stock.py scripts/run_hmmsearch_stock.py \
  jobs/hmmsearch_stock_completion.job \
  results/hmmsearch_stock_tasks.json \
  | ssh carc-transfer "tar -x -C '${REMOTE}'"
printf '%s\n' "${HASH}" | ssh carc-transfer "cat > '${REMOTE}/GIT_HASH'"
ssh carc-transfer "mv '${REMOTE}/results/hmmsearch_stock_tasks.json' '${REMOTE}/hmmsearch_stock_tasks.json'"

BUILD_LINE="$(ssh discovery "sbatch --job-name=stock_hmm_build --time=01:00:00 \
  --output='${REMOTE}/results/hmmsearch_stock/logs/%x-%j.out' \
  --error='${REMOTE}/results/hmmsearch_stock/logs/%x-%j.err' \
  --export=ALL,ACTS_CODE_ROOT='${REMOTE}',ACTS_DATA_ROOT='${DATA}',ACTS_STOCK_PHASE=build,ACTS_GIT_HASH_FILE='${REMOTE}/GIT_HASH' \
  '${REMOTE}/jobs/hmmsearch_stock_completion.job'")"
echo "${BUILD_LINE}"
BUILD_ID="${BUILD_LINE##* }"

ssh discovery "sbatch --job-name=stock_hmm_measure --time=00:45:00 \
  --array=0-57 --dependency=afterok:${BUILD_ID} \
  --output='${REMOTE}/results/hmmsearch_stock/logs/%x-%A_%a.out' \
  --error='${REMOTE}/results/hmmsearch_stock/logs/%x-%A_%a.err' \
  --export=ALL,ACTS_CODE_ROOT='${REMOTE}',ACTS_DATA_ROOT='${DATA}',ACTS_STOCK_PHASE=measure,ACTS_GIT_HASH_FILE='${REMOTE}/GIT_HASH' \
  '${REMOTE}/jobs/hmmsearch_stock_completion.job'"
