#!/usr/bin/env bash
# One-shot: build (if needed) → fetch Suite B → bake-off all 10 → print scoreboard.
# Same protocol as STATUS.md / ILLUMINA10.md (MATCH-gated, 1 thread, outBAMcompression 0).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPTS="${ROOT}/bench/scripts"
RUNS="${RUNS:-3}"
THREADS="${THREADS:-1}"
DATASETS="${DATASETS:-i01 i02 i03 i04 i05 i06 i07 i08 i09 i10}"
OUT_CSV="${OUT_CSV:-${ROOT}/bench/results/illumina10_repro.csv}"
REF_CSV="${REF_CSV:-${ROOT}/bench/results/illumina10_s8j_mac.csv}"
SKIP_BUILD="${SKIP_BUILD:-0}"
SKIP_FETCH="${SKIP_FETCH:-0}"

mkdir -p "${ROOT}/bench/results"

if [[ "${SKIP_BUILD}" != "1" ]]; then
  # Fetch human i01 first so PGO train can run during opt build when possible
  if [[ "${SKIP_FETCH}" != "1" ]]; then
    # Minimal: ensure dirs; full fetch after stock exists
    true
  fi
  bash "${SCRIPTS}/build_stock_opt.sh"
fi

export STOCK_BIN="${STOCK_BIN:-${ROOT}/src/STAR_stock}"
export OPT_BIN="${OPT_BIN:-${ROOT}/src/STAR_opt}"
[[ -x "${STOCK_BIN}" ]] || STOCK_BIN="${ROOT}/src/STAR_stock_mac"
[[ -x "${OPT_BIN}" ]] || OPT_BIN="${ROOT}/src/STAR_opt_mac_s8_pgo"
[[ -x "${STOCK_BIN}" && -x "${OPT_BIN}" ]] || {
  echo "Missing binaries. Run build_stock_opt.sh or set STOCK_BIN/OPT_BIN." >&2
  exit 1
}

if [[ "${SKIP_FETCH}" != "1" ]]; then
  STOCK_BIN="${STOCK_BIN}" bash "${SCRIPTS}/fetch_suiteB.sh"
fi

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1 (required for BAM MATCH)" >&2; exit 1; }; }
need_cmd samtools
need_cmd python3

echo "id,n,stock_mean,stock_std,opt_mean,opt_std,speedup,min_pair,output,notes" > "${OUT_CSV}"

HOST="$(uname -srm)"
echo "=== reproduce Suite B on ${HOST} ==="
echo "stock=${STOCK_BIN}"
echo "opt=${OPT_BIN}"
echo "threads=${THREADS} runs=${RUNS}"

pass=0
fail=0
for ds in ${DATASETS}; do
  echo
  echo "######## ${ds} ########"
  OUT_ROOT="${ROOT}/bench/results/bakeoff_repro_${ds}"
  mkdir -p "${OUT_ROOT}"
  export STOCK_BIN OPT_BIN OUT_ROOT RUNS THREADS
  export EXTRA_STAR_ARGS="${EXTRA_STAR_ARGS:---outBAMcompression 0}"
  bash "${SCRIPTS}/run_bakeoff.sh" "${ds}" | tee "${OUT_ROOT}/console.txt"

  python3 - "${OUT_ROOT}/timings.csv" "${ds}" "${OUT_CSV}" <<'PY'
import csv, statistics, sys
path, ds, out_csv = sys.argv[1:4]
stock, opt, verdicts = [], [], set()
with open(path) as f:
    for row in csv.DictReader(f):
        verdicts.add(row["output"])
        (stock if row["label"] == "stock" else opt).append(float(row["wall_sec"]))
sm, om = statistics.mean(stock), statistics.mean(opt)
ss = statistics.stdev(stock) if len(stock) > 1 else 0.0
os_ = statistics.stdev(opt) if len(opt) > 1 else 0.0
spd = sm / om if om else float("inf")
mp = min(s / o for s, o in zip(stock, opt))
ver = ",".join(sorted(verdicts))
notes = "repro"
with open(out_csv, "a") as o:
    o.write(f"{ds},{len(stock)},{sm:.4f},{ss:.4f},{om:.4f},{os_:.4f},{spd:.3f},{mp:.3f},{ver},{notes}\n")
print(f"APPENDED {ds}: {spd:.3f}× min_pair={mp:.3f} {ver}")
PY
done

python3 - "${OUT_CSV}" "${REF_CSV}" <<'PY'
import csv, sys
from pathlib import Path
out_csv, ref_csv = sys.argv[1:3]

def load(p):
    rows = {}
    with open(p) as f:
        for r in csv.DictReader(f):
            rows[r["id"]] = r
    return rows

ours = load(out_csv)
print()
print("=" * 78)
print("REPRODUCTION SCOREBOARD (same columns as STATUS.md / illumina10_s8j_mac.csv)")
print("=" * 78)
print(f"{'ID':<4} {'stock mean±std':>18} {'opt mean±std':>18} {'mean':>8} {'min_pair':>8} {'≥2×':>5} {'out':>6}")
ok = 0
for i in range(1, 11):
    ds = f"i{i:02d}"
    r = ours.get(ds)
    if not r:
        print(f"{ds:<4} MISSING")
        continue
    ge2 = "yes" if float(r["min_pair"]) >= 2.0 and r["output"] == "MATCH" else "NO"
    if ge2 == "yes":
        ok += 1
    print(
        f"{ds:<4} {float(r['stock_mean']):7.3f}±{float(r['stock_std']):.3f}  "
        f"{float(r['opt_mean']):7.3f}±{float(r['opt_std']):.3f}  "
        f"{float(r['speedup']):7.3f}× {float(r['min_pair']):7.3f}× {ge2:>5} {r['output']:>6}"
    )
print("-" * 78)
print(f"Scoreboard: {ok}/10 datasets with MATCH and min_pair ≥ 2.0")
print()
print("NOTE: Absolute seconds will differ from Josh's Mac table on another CPU.")
print("      Graded claim is same-machine stock vs opt, MATCH output, and ≥2×.")
if Path(ref_csv).is_file():
    ref = load(ref_csv)
    print()
    print(f"Reference artifact (Josh Mac): {ref_csv}")
    print(f"{'ID':<4} {'your min_pair':>14} {'Josh min_pair':>14} {'delta':>10}")
    for i in range(1, 11):
        ds = f"i{i:02d}"
        if ds in ours and ds in ref:
            a, b = float(ours[ds]["min_pair"]), float(ref[ds]["min_pair"])
            print(f"{ds:<4} {a:14.3f} {b:14.3f} {a-b:+10.3f}")
print("=" * 78)
print(f"Wrote {out_csv}")
PY

echo "REPRODUCE_ALL_DONE"
