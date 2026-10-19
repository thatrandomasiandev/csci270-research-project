"""Compare measured random-pad detection with Equation 4 in every adversarial cell where it applies.

Reads pipeline/results/adversarial/measured.json; writes pipeline/results/adversarial/eq4_summary.json.
A cell is "below" when measured detection is under the Eq. 4 prediction, and "inside" when the
prediction lies within the measured 95% Wilson interval.
"""
import json
import math
from pathlib import Path

RES = Path(__file__).resolve().parents[1] / "results" / "adversarial"
d = json.loads((RES / "measured.json").read_text())


def wilson(k, n, z=1.959963984540054):
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


rows = []
for name, c in d["cells"].items():
    if not c.get("eq4_applies"):
        continue
    k = c["true_refusal"]
    n = c["n_trials"]
    lo, hi = wilson(k, n)
    rows.append({"cell": name, "detected": k, "trials": n, "measured": k / n, "eq4": c["eq4_detection"],
                 "wilson_lo": lo, "wilson_hi": hi, "below": k / n < c["eq4_detection"],
                 "inside": lo <= c["eq4_detection"] <= hi})
out = {
    "cells": rows,
    "n_cells": len(rows),
    "n_below": sum(r["below"] for r in rows),
    "n_outside_interval": sum(not r["inside"] for r in rows),
    "audit_ran_in_grid": False,
    "audit_note": "Each grid trial used a cold cache, so no cached rows were reused and the audit (R6) block was not entered; see audit_gate.json.",
}
(RES / "eq4_summary.json").write_text(json.dumps(out, indent=2) + "\n")
print({k: v for k, v in out.items() if k != "cells"})
