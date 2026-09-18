#!/usr/bin/env bash
# Time stock STAR (or STAR_BIN) on a fixed FASTQ pair.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAR_BIN="${STAR_BIN:-${ROOT}/upstream/bin/Linux_x86_64_static/STAR}"
GENOME_DIR="${GENOME_DIR:-${ROOT}/bench/datasets/genome}"
READ1="${READ1:-${ROOT}/bench/datasets/reads_1.fastq.gz}"
READ2="${READ2:-${ROOT}/bench/datasets/reads_2.fastq.gz}"
# IMPORTANT: OUT_PREFIX must NOT be a prefix of the CSV filename
OUT_DIR="${OUT_DIR:-${ROOT}/bench/results/stock_align}"
OUT_PREFIX="${OUT_PREFIX:-${OUT_DIR}/run_}"
THREADS="${THREADS:-1}"
RUNS="${RUNS:-3}"
CSV="${CSV:-${ROOT}/bench/results/baseline_timings.csv}"
if command -v gzcat >/dev/null 2>&1; then
  READCMD="${READCMD:-gzcat}"
else
  READCMD="${READCMD:-zcat}"
fi

if [[ ! -x "${STAR_BIN}" && ! -f "${STAR_BIN}" ]]; then
  echo "STAR binary not found at ${STAR_BIN}" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}" "$(dirname "${CSV}")"
echo "run,wall_sec,threads,star_bin" > "${CSV}"

for i in $(seq 1 "${RUNS}"); do
  rm -rf "${OUT_DIR:?}/"*
  START=$(python3 -c 'import time; print(time.time())')
  "${STAR_BIN}" \
    --runThreadN "${THREADS}" \
    --genomeDir "${GENOME_DIR}" \
    --readFilesIn "${READ1}" "${READ2}" \
    --readFilesCommand "${READCMD}" \
    --outFileNamePrefix "${OUT_PREFIX}" \
    --outSAMtype BAM SortedByCoordinate \
    --limitBAMsortRAM 4000000000
  END=$(python3 -c 'import time; print(time.time())')
  WALL=$(python3 -c "print(${END}-${START})")
  echo "${i},${WALL},${THREADS},${STAR_BIN}" | tee -a "${CSV}"
done

# Preserve mapping stats from last run
if [[ -f "${OUT_PREFIX}Log.final.out" ]]; then
  cp -f "${OUT_PREFIX}Log.final.out" "${ROOT}/bench/results/baseline_Log.final.out"
fi

echo "Wrote ${CSV}"
