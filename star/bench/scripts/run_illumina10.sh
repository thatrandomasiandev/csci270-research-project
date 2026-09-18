#!/usr/bin/env bash
# Fair 1-thread bake-off across Suite A (or Suite B paths).
# Usage: THREADS=1 ./run_illumina10.sh [suite_dir]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SUITE="${1:-${ROOT}/bench/datasets/illumina10}"
THREADS="${THREADS:-1}"
RUNS="${RUNS:-3}"
STOCK="${STOCK_BIN:-${ROOT}/upstream/bin/Linux_x86_64_static/STAR}"
OPT="${OPT_BIN:-${ROOT}/src/STAR_optimized}"
OUT_CSV="${ROOT}/bench/results/illumina10_timings.csv"
GENOME_DIR="${GENOME_DIR:-${SUITE}/genome}"

echo "dataset,variant,run,wall_sec,threads" > "${OUT_CSV}"

if [[ ! -f "${GENOME_DIR}/Genome" ]]; then
  echo "Missing genome index at ${GENOME_DIR}. Build once from shared/raw." >&2
  exit 1
fi

for d in $(ls -d "${SUITE}"/d[0-9][0-9] 2>/dev/null); do
  id="$(basename "$d")"
  R1="$d/reads_1.fastq.gz"
  R2="$d/reads_2.fastq.gz"
  [[ -f "$R1" && -f "$R2" ]] || continue
  for variant in stock opt; do
    if [[ "$variant" == stock ]]; then BIN="$STOCK"; else BIN="$OPT"; fi
    [[ -x "$BIN" || -f "$BIN" ]] || { echo "missing $BIN" >&2; exit 1; }
    odir="${ROOT}/bench/results/illumina10_${id}_${variant}"
    mkdir -p "$odir"
    for i in $(seq 1 "$RUNS"); do
      rm -rf "${odir:?}/"*
      START=$(python3 -c 'import time; print(time.time())')
      "$BIN" \
        --runThreadN "$THREADS" \
        --genomeDir "$GENOME_DIR" \
        --readFilesIn "$R1" "$R2" \
        --readFilesCommand zcat \
        --outFileNamePrefix "${odir}/run_" \
        --outSAMtype BAM SortedByCoordinate \
        --limitBAMsortRAM 4000000000
      END=$(python3 -c 'import time; print(time.time())')
      WALL=$(python3 -c "print(${END}-${START})")
      echo "${id},${variant},${i},${WALL},${THREADS}" | tee -a "${OUT_CSV}"
    done
  done
done
echo "Wrote ${OUT_CSV}"
