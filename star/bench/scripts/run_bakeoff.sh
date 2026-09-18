#!/usr/bin/env bash
# Fair bake-off: stock vs opt on one dataset, MATCH-gated.
# Usage: run_bakeoff.sh [dataset_id]
# Env: STOCK_BIN OPT_BIN GENOME_DIR READ1 READ2 RUNS THREADS
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DS="${1:-i01}"
STOCK_BIN="${STOCK_BIN:-${ROOT}/src/STAR_stock_mac}"
OPT_BIN="${OPT_BIN:-${ROOT}/src/STAR_opt_mac_s123}"
GENOME_DIR="${GENOME_DIR:-${ROOT}/bench/datasets/suiteB/${DS}/genome_nb10}"
# Default FASTQs for suite B i01–i04
case "${DS}" in
  i01) R1n=SRR1039508; ;;
  i02) R1n=SRR1039509; ;;
  i03) R1n=SRR1039512; ;;
  i04) R1n=SRR1039513; ;;
  *) R1n=""; ;;
esac
READ1="${READ1:-${ROOT}/bench/datasets/suiteB/${DS}/fastq/${R1n}_R1.fastq.gz}"
READ2="${READ2:-${ROOT}/bench/datasets/suiteB/${DS}/fastq/${R1n}_R2.fastq.gz}"
OUT_ROOT="${OUT_ROOT:-${ROOT}/bench/results/bakeoff_s123_${DS}}"
THREADS="${THREADS:-1}"
RUNS="${RUNS:-3}"
WARMUP="${WARMUP:-1}"
if command -v gzcat >/dev/null 2>&1; then READCMD="${READCMD:-gzcat}"; else READCMD="${READCMD:-zcat}"; fi
LIMIT_BAM_SORT_RAM="${LIMIT_BAM_SORT_RAM:-4000000000}"

CMP="${ROOT}/bench/scripts/compare_outputs.sh"
CSV="${OUT_ROOT}/timings.csv"
mkdir -p "${OUT_ROOT}"
echo "run,label,wall_sec,output,threads,star_bin" > "${CSV}"

run_star() {
  local bin="$1" label="$2" tag="$3" outdir="$4"
  rm -rf "${outdir}"
  mkdir -p "${outdir}"
  local prefix="${outdir}/run_"
  local start end wall
  start=$(python3 -c 'import time; print(time.time())')
  # EXTRA_STAR_ARGS: identical on both sides (e.g. --outBAMcompression 0).
  # shellcheck disable=SC2086
  "${bin}" \
    --runThreadN "${THREADS}" \
    --genomeDir "${GENOME_DIR}" \
    --readFilesIn "${READ1}" "${READ2}" \
    --readFilesCommand "${READCMD}" \
    --outFileNamePrefix "${prefix}" \
    --outSAMtype BAM SortedByCoordinate \
    --limitBAMsortRAM "${LIMIT_BAM_SORT_RAM}" \
    ${EXTRA_STAR_ARGS:-} \
    >/dev/null
  end=$(python3 -c 'import time; print(time.time())')
  wall=$(python3 -c "print(f'{${end}-${start}:.6f}')")
  echo "${wall}"
}

echo "=== bakeoff ${DS}: threads=${THREADS} genome=${GENOME_DIR} ==="
echo "stock=${STOCK_BIN}"
echo "opt=${OPT_BIN}"
[[ -f "${GENOME_DIR}/Genome" ]] || { echo "missing genome ${GENOME_DIR}" >&2; exit 1; }
[[ -f "${READ1}" && -f "${READ2}" ]] || { echo "missing FASTQs" >&2; exit 1; }

if [[ "${WARMUP}" -gt 0 ]]; then
  echo "--- warmup stock ---"
  run_star "${STOCK_BIN}" stock warmup "${OUT_ROOT}/_warmup_stock" >/dev/null
  echo "--- warmup opt ---"
  run_star "${OPT_BIN}" opt warmup "${OUT_ROOT}/_warmup_opt" >/dev/null
fi

declare -a stock_times=() opt_times=()
for i in $(seq 1 "${RUNS}"); do
  echo "--- timed ${i} stock ---"
  sw=$(run_star "${STOCK_BIN}" stock "r${i}" "${OUT_ROOT}/stock_${i}")
  stock_bam="${OUT_ROOT}/stock_${i}/run_Aligned.sortedByCoord.out.bam"
  echo "--- timed ${i} opt ---"
  ow=$(run_star "${OPT_BIN}" opt "r${i}" "${OUT_ROOT}/opt_${i}")
  opt_bam="${OUT_ROOT}/opt_${i}/run_Aligned.sortedByCoord.out.bam"
  verdict="FAIL"
  if "${CMP}" "${stock_bam}" "${opt_bam}"; then
    verdict="MATCH"
  else
    verdict="DIFF"
  fi
  # Also compare SJ.out.tab if present
  if [[ -f "${OUT_ROOT}/stock_${i}/run_SJ.out.tab" && -f "${OUT_ROOT}/opt_${i}/run_SJ.out.tab" ]]; then
    if ! cmp -s "${OUT_ROOT}/stock_${i}/run_SJ.out.tab" "${OUT_ROOT}/opt_${i}/run_SJ.out.tab"; then
      verdict="DIFF_SJ"
    fi
  fi
  echo "${i},stock,${sw},${verdict},${THREADS},${STOCK_BIN}" >> "${CSV}"
  echo "${i},opt,${ow},${verdict},${THREADS},${OPT_BIN}" >> "${CSV}"
  stock_times+=("${sw}")
  opt_times+=("${ow}")
  echo "run ${i}: stock=${sw}s opt=${ow}s ${verdict}"
  if [[ "${verdict}" != "MATCH" ]]; then
    echo "OUTPUT MISMATCH — aborting further timing" >&2
    exit 1
  fi
done

python3 - "${CSV}" <<'PY'
import csv, statistics, sys
path = sys.argv[1]
stock, opt = [], []
verdicts = set()
with open(path) as f:
    for row in csv.DictReader(f):
        verdicts.add(row["output"])
        (stock if row["label"]=="stock" else opt).append(float(row["wall_sec"]))
sm, om = statistics.mean(stock), statistics.mean(opt)
ss = statistics.stdev(stock) if len(stock)>1 else 0.0
os_ = statistics.stdev(opt) if len(opt)>1 else 0.0
spd = sm/om if om else float("inf")
print(f"stock mean±std: {sm:.4f}±{ss:.4f} s (n={len(stock)})")
print(f"opt   mean±std: {om:.4f}±{os_:.4f} s (n={len(opt)})")
print(f"speedup: {spd:.3f}×")
print(f"output: {','.join(sorted(verdicts))}")
print(f"min_pair_speedup: {min(s/o for s,o in zip(stock,opt)):.3f}×")
PY
