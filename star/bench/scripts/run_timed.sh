#!/usr/bin/env bash
# Timed STAR run with phase logging. Fair: identical CLI; only STAR_BIN differs.
# Defaults: THREADS=1, warm-up discarded, then RUNS timed reps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAR_BIN="${STAR_BIN:-${ROOT}/src/STAR_stock_mac}"
GENOME_DIR="${GENOME_DIR:-${ROOT}/bench/datasets/suiteB/i01/genome}"
READ1="${READ1:-${ROOT}/bench/datasets/suiteB/i01/fastq/SRR1039508_R1.fastq.gz}"
READ2="${READ2:-${ROOT}/bench/datasets/suiteB/i01/fastq/SRR1039508_R2.fastq.gz}"
OUT_DIR="${OUT_DIR:-${ROOT}/bench/results/stock_suiteB_i01}"
OUT_PREFIX="${OUT_PREFIX:-${OUT_DIR}/run_}"
THREADS="${THREADS:-1}"
RUNS="${RUNS:-3}"
WARMUP="${WARMUP:-1}"
CSV="${CSV:-${ROOT}/bench/results/stock_suiteB_i01_timings.csv}"
PHASE_CSV="${PHASE_CSV:-${ROOT}/bench/results/stock_suiteB_i01_phases.csv}"
LABEL="${LABEL:-stock}"
# macOS: gzcat; Linux: zcat. Same command both sides.
if command -v gzcat >/dev/null 2>&1; then
  READCMD="${READCMD:-gzcat}"
else
  READCMD="${READCMD:-zcat}"
fi
LIMIT_BAM_SORT_RAM="${LIMIT_BAM_SORT_RAM:-4000000000}"

if [[ ! -x "${STAR_BIN}" && ! -f "${STAR_BIN}" ]]; then
  echo "STAR binary not found at ${STAR_BIN}" >&2
  exit 1
fi
if [[ ! -f "${GENOME_DIR}/Genome" ]]; then
  echo "Missing genome index at ${GENOME_DIR}" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}" "$(dirname "${CSV}")"
rm -f "${CSV}" "${PHASE_CSV}"
echo "run,wall_sec,threads,star_bin,readcmd,label" > "${CSV}"

run_once() {
  local tag="$1"
  rm -rf "${OUT_DIR:?}/"*
  local START END WALL
  START=$(python3 -c 'import time; print(time.time())')
  "${STAR_BIN}" \
    --runThreadN "${THREADS}" \
    --genomeDir "${GENOME_DIR}" \
    --readFilesIn "${READ1}" "${READ2}" \
    --readFilesCommand "${READCMD}" \
    --outFileNamePrefix "${OUT_PREFIX}" \
    --outSAMtype BAM SortedByCoordinate \
    --limitBAMsortRAM "${LIMIT_BAM_SORT_RAM}"
  END=$(python3 -c 'import time; print(time.time())')
  WALL=$(python3 -c "print(${END}-${START})")
  echo "${tag},${WALL},${THREADS},${STAR_BIN},${READCMD},${LABEL}"
  # Preserve log for phase parse
  if [[ -f "${OUT_PREFIX}Log.out" ]]; then
    cp -f "${OUT_PREFIX}Log.out" "${OUT_DIR}/${tag}_Log.out"
    python3 "${ROOT}/bench/scripts/phase_breakdown.py" \
      "${OUT_DIR}/${tag}_Log.out" \
      --label "${LABEL}_${tag}" \
      --wall "${WALL}" \
      --csv "${PHASE_CSV}"
  fi
  echo "${WALL}"
}

echo "=== ${LABEL}: warmup=${WARMUP} timed=${RUNS} threads=${THREADS} bin=${STAR_BIN} ==="
if [[ "${WARMUP}" -gt 0 ]]; then
  echo "--- warmup ---"
  run_once "warmup" >/dev/null
fi

for i in $(seq 1 "${RUNS}"); do
  echo "--- timed run ${i} ---"
  WALL=$(run_once "run${i}" | tee /dev/stderr | tail -1)
  echo "${i},${WALL},${THREADS},${STAR_BIN},${READCMD},${LABEL}" >> "${CSV}"
done

if [[ -f "${OUT_PREFIX}Log.final.out" ]]; then
  cp -f "${OUT_PREFIX}Log.final.out" "${OUT_DIR}/Log.final.out"
fi
echo "Wrote ${CSV} and ${PHASE_CSV}"
