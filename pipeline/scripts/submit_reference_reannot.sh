#!/usr/bin/env bash
# Stage this session's tree to its own CARC directory and sbatch.
#   submit_reference_reannot.sh churn
#   submit_reference_reannot.sh timed
# Does not write pipeline/results/savings or the shared pipeline tree.
set -euo pipefail

MODE="${1:?churn or timed}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REMOTE=/project2/biyik_1165/jjt_373/csci270-star/reference_reannot
HASH="$(git -C "$ROOT" rev-parse HEAD)"

if [[ -n "$(git -C "$ROOT" status --porcelain -- pipeline/acts/reference_run.py pipeline/acts/reference_formats.py pipeline/scripts/run_reference_reannot.py pipeline/scripts/reference_reannot_churn.py pipeline/jobs/reference_reannot.job pipeline/jobs/reference_reannot_churn.job)" ]]; then
  echo "reference-reannot files are dirty; commit before staging" >&2
  exit 2
fi

ssh carc-transfer "mkdir -p '${REMOTE}'/{scripts,jobs,acts,logs,results,work,data/pfam38.1,data/genomes}"
git -C "$ROOT" archive HEAD \
  pipeline/acts \
  pipeline/scripts/reference_reannot_churn.py \
  pipeline/scripts/run_reference_reannot.py \
  pipeline/jobs/reference_reannot_churn.job \
  pipeline/jobs/reference_reannot.job \
  | ssh carc-transfer "tar -x --strip-components=1 -C '${REMOTE}'"
printf '%s\n' "$HASH" | ssh carc-transfer "cat > '${REMOTE}/GIT_HASH'"
rsync -avz \
  "${ROOT}/pipeline/data/hmmer/pfam38.1/Pfam-A.hmm.gz" \
  "${ROOT}/pipeline/data/hmmer/pfam38.1/Pfam.version.gz" \
  "carc-transfer:${REMOTE}/data/pfam38.1/"
for acc in GCF_002853805.1 GCF_002090355.1 GCF_001650275.1 GCF_052050745.1 GCF_016659085.1; do
  rsync -avz "${ROOT}/pipeline/data/recurrence/A/${acc}_protein.faa.gz" \
    "carc-transfer:${REMOTE}/data/genomes/"
done

if [[ "$MODE" == "churn" ]]; then
  ssh discovery "sbatch --export=ALL,ACTS_GIT_HASH=${HASH} '${REMOTE}/jobs/reference_reannot_churn.job'"
elif [[ "$MODE" == "timed" ]]; then
  test -f "${ROOT}/pipeline/results/reference_reannot_predictions.json"
  test -f "${ROOT}/pipeline/results/reference_reannot_churn.json"
  rsync -avz \
    "${ROOT}/pipeline/results/reference_reannot_predictions.json" \
    "${ROOT}/pipeline/results/reference_reannot_churn.json" \
    "carc-transfer:${REMOTE}/results/"
  ssh discovery "sbatch --export=ALL,ACTS_GIT_HASH=${HASH} '${REMOTE}/jobs/reference_reannot.job'"
else
  echo "unknown mode ${MODE}" >&2
  exit 2
fi
