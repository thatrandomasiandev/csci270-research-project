#!/usr/bin/env bash
# Laptop path: four fixture smokes and the paper-number check.
# Exits non-zero on the first FAIL. Does not write pipeline/results/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${ROOT}"

python3 pipeline/artifact/laptop/t3_synthetic.py
python3 pipeline/artifact/laptop/record_reuse.py
python3 pipeline/artifact/laptop/ref_merge_smoke.py
python3 pipeline/artifact/laptop/probe_eval_smoke.py
python3 pipeline/artifact/check_paper_sources.py
