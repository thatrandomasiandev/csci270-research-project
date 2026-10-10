#!/usr/bin/env python3
"""Small probe-eval grid. Each cell must match the committed audit JSON.

Expected values are the rows in pipeline/results/probe_eval_audit.json
for the same (kind, class, p, probe_n). The full 4/224 count is not
recomputed here; check_paper_sources.py checks that count against the
committed writeup. This script does not write into pipeline/results/.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PIPE = REPO / "pipeline"
AUDIT = PIPE / "results" / "probe_eval_audit.json"

# One control, one determinism refuse, the canonical in-scope miss,
# and the stated F6-env limitation. probe_n=50 is the smallest size
# in the committed grid.
CELLS = (
    ("vcf", "C1", 0.0, 50),
    ("vcf", "F1", 1.0, 50),
    ("vcf", "F4", 0.01, 50),
    ("fasta", "F6-env", 1.0, 50),
    ("fasta", "C4", 0.0, 50),
)


def _load_runner():
    path = PIPE / "scripts" / "run_probe_eval.py"
    spec = importlib.util.spec_from_file_location("artifact_probe_eval", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"FAIL cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expected(rows: list[dict], kind: str, cls: str, p: float, probe_n: int) -> dict:
    matches = [
        row
        for row in rows
        if row["kind"] == kind
        and row["class"] == cls
        and row["p"] == p
        and row["probe_n"] == probe_n
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"FAIL committed grid has {len(matches)} rows for {kind} {cls} p={p} n={probe_n}"
        )
    return matches[0]


def main() -> int:
    started = time.perf_counter()
    payload = json.loads(AUDIT.read_text())
    runner = _load_runner()
    work = Path(tempfile.mkdtemp(prefix="acts_artifact_probe_"))
    failures = 0
    for kind, cls, p, probe_n in CELLS:
        expected = _expected(payload["rows"], kind, cls, p, probe_n)
        got = runner.run_cell(work, kind, cls, p, probe_n)
        fields = ("input1_decision", "unsafe_ship", "false_refuse")
        actual = {
            "input1_decision": got["input1"]["decision"],
            "unsafe_ship": got["unsafe_ship"],
            "false_refuse": got["false_refuse"],
        }
        want = {
            "input1_decision": expected["input1"]["decision"],
            "unsafe_ship": expected["unsafe_ship"],
            "false_refuse": expected["false_refuse"],
        }
        ok = actual == want
        print(
            f"{'PASS' if ok else 'FAIL'} probe {kind} {cls} p={p} n={probe_n}: "
            + " ".join(f"{name}={actual[name]} expected={want[name]}" for name in fields)
        )
        if not ok:
            failures += 1
    elapsed = time.perf_counter() - started
    print(f"wall_s={elapsed:.3f} failures={failures}")
    print(f"expected_source={AUDIT.relative_to(REPO)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
