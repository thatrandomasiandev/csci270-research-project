#!/usr/bin/env bash
# From the Mac: rsync via carc-transfer, then `ssh discovery sbatch`.
# Nothing compute-heavy on login nodes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REMOTE=/project2/biyik_1165/jjt_373/csci270-star/pipeline

ssh carc-transfer "mkdir -p '${REMOTE}'/{scripts,jobs,results,data/kprot,data/hmmer}"
rsync -avz \
  "${ROOT}/pipeline/scripts/run_headline_screen.py" \
  "${ROOT}/pipeline/scripts/submit_headline_hmmer.sh" \
  "carc-transfer:${REMOTE}/scripts/"
rsync -avz \
  "${ROOT}/pipeline/jobs/headline_hmmer_carc.job" \
  "carc-transfer:${REMOTE}/jobs/"
rsync -avz \
  "${ROOT}/pipeline/results/kprot_overlap.json" \
  "carc-transfer:${REMOTE}/results/"
rsync -avz \
  "${ROOT}/pipeline/data/kprot/BW25113.faa.gz" \
  "carc-transfer:${REMOTE}/data/kprot/"
if [[ -f "${ROOT}/pipeline/data/hmmer/Pfam-A.hmm.gz" ]]; then
  rsync -avz "${ROOT}/pipeline/data/hmmer/Pfam-A.hmm.gz" \
    "carc-transfer:${REMOTE}/data/hmmer/"
fi
if [[ -f "${ROOT}/pipeline/data/hmmer/Pfam.version.gz" ]]; then
  rsync -avz "${ROOT}/pipeline/data/hmmer/Pfam.version.gz" \
    "carc-transfer:${REMOTE}/data/hmmer/"
fi

ssh discovery "sbatch '${REMOTE}/jobs/headline_hmmer_carc.job'"
