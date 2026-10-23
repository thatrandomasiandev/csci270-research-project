#!/usr/bin/env bash
# One-command finalize: collect CARC results, fill macros, rebuild paper, scan.
# Safe to re-run. Never writes under CARC staged trees (rsync pull only).
# Exit codes: 0 = all collected and paper clean; 2 = still running; 1 = hard fail.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "${ROOT}"
COLLECTORS="$(dirname "$0")/collectors"
export PYTHONPATH="${COLLECTORS}${PYTHONPATH:+:$PYTHONPATH}"

echo "=== TARE finalize ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="
echo "Repo: ${ROOT}"
echo

overall=0
still=0
failed=0

run_collector () {
  local name="$1"
  local script="$2"
  set +e
  python3 "${COLLECTORS}/${script}"
  local rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then
    :
  elif [[ $rc -eq 2 ]]; then
    still=$((still + 1))
    overall=2
  else
    failed=$((failed + 1))
    overall=1
  fi
}

run_collector W13 collect_w13.py
run_collector W8 collect_w8.py
run_collector W5x collect_w5x.py
run_collector W12a collect_w12a.py
run_collector W12b collect_w12b.py
run_collector WA2 collect_wa2.py

echo
echo "=== fill macros ==="
set +e
python3 pipeline/paper/tare/fill_macros.py
macro_rc=$?
set -e

echo
echo "=== figures ==="
# OSDI labels (anonymized system name); arXiv build uses build_arxiv.sh.
export TARE_SYS_NAME="${TARE_SYS_NAME:-PARE}"
python3 pipeline/paper/tare/figures/make_figures.py
python3 pipeline/paper/tare/figures/make_churn_pairs.py

echo
echo "=== build PDF ==="
(
  cd pipeline/paper/tare
  latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex >/tmp/tare_finalize_latex.log 2>&1 || {
    echo "LaTeX FAILED; see /tmp/tare_finalize_latex.log" >&2
    exit 1
  }
)

echo
echo "=== paper source checker ==="
set +e
python3 pipeline/artifact/check_paper_sources.py
check_rc=$?
set -e

echo
echo "=== anonymity scan ==="
set +e
python3 pipeline/artifact/anonymity_scan.py
anon_rc=$?
set -e

echo
echo "=== summary ==="
echo "collectors: still_running=${still} failed=${failed}"
echo "macros_pending_exit=${macro_rc} checker_exit=${check_rc} anonymity_exit=${anon_rc}"
if [[ ${still} -gt 0 ]]; then
  echo "STATUS: STILL RUNNING — re-run finalize.sh after CARC jobs finish"
  exit 2
fi
if [[ ${failed} -gt 0 || ${macro_rc} -ne 0 || ${check_rc} -ne 0 || ${anon_rc} -ne 0 ]]; then
  echo "STATUS: FAILED — see messages above"
  exit 1
fi
echo "STATUS: READY"
exit 0
