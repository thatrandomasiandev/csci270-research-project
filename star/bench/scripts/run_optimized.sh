#!/usr/bin/env bash
# Optimized runner: pigz decompression + optional patched STAR binary.
# Same mapping flags as baseline except readFilesCommand.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Prefer patched build; fall back to stock static
STAR_BIN="${STAR_BIN:-}"
if [[ -z "${STAR_BIN}" ]]; then
  if [[ -x "${ROOT}/src/STAR_optimized" ]]; then
    STAR_BIN="${ROOT}/src/STAR_optimized"
  else
    STAR_BIN="${ROOT}/upstream/bin/Linux_x86_64_static/STAR"
  fi
fi
GENOME_DIR="${GENOME_DIR:-${ROOT}/bench/datasets/genome}"
READ1="${READ1:-${ROOT}/bench/datasets/reads_1.fastq.gz}"
READ2="${READ2:-${ROOT}/bench/datasets/reads_2.fastq.gz}"
OUT_DIR="${OUT_DIR:-${ROOT}/bench/results/opt_align}"
OUT_PREFIX="${OUT_PREFIX:-${OUT_DIR}/run_}"
THREADS="${THREADS:-1}"
RUNS="${RUNS:-3}"
CSV="${CSV:-${ROOT}/bench/results/optimized_timings.csv}"
# Must match baseline for Zhang fairness (same CLI); override only if both sides set it.
if command -v gzcat >/dev/null 2>&1; then
  READCMD="${READCMD:-gzcat}"
else
  READCMD="${READCMD:-zcat}"
fi

mkdir -p "${OUT_DIR}" "$(dirname "${CSV}")"
echo "run,wall_sec,threads,star_bin,readcmd" > "${CSV}"

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
    --limitBAMsortRAM 4000000000 \
    ${OUTBAMCOMPRESSION:+--outBAMcompression "${OUTBAMCOMPRESSION}"}
  END=$(python3 -c 'import time; print(time.time())')
  WALL=$(python3 -c "print(${END}-${START})")
  echo "${i},${WALL},${THREADS},${STAR_BIN},${READCMD}" | tee -a "${CSV}"
done

if [[ -f "${OUT_PREFIX}Log.final.out" ]]; then
  cp -f "${OUT_PREFIX}Log.final.out" "${ROOT}/bench/results/optimized_Log.final.out"
fi
echo "Wrote ${CSV}"
