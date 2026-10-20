"""Totals for the W10 grid with the audit active (both arms), for the paper.

Reads pipeline/results/adversarial/measured_v2.json; writes pipeline/results/adversarial/v2_summary.json.
Hidden forms are C2 and C3 (16 cells x 50 trials). "covered" is k in {22, 100}, where k/n >= 0.01 at n = 2000,
the region the bounded audit's guarantee covers; "below" is k in {1, 5}.
"""
import json
from pathlib import Path

RES = Path(__file__).resolve().parents[1] / "results" / "adversarial"
d = json.loads((RES / "measured_v2.json").read_text())
out = {"source": "pipeline/results/adversarial/measured_v2.json", "code_commit": d["code_commit"], "arms": {}}
for arm in ("shipped", "bounded"):
    cells = d[arm]["cells"]
    hidden = {k: v for k, v in cells.items() if k.startswith(("C2/", "C3/"))}
    def tot(sel, key):
        return sum(v[key] for k, v in hidden.items() if sel(int(k.rsplit("/k", 1)[1])))
    out["arms"][arm] = {
        "hidden_trials": sum(v["n_trials"] for v in hidden.values()),
        "hidden_unsafe": sum(v["UNSAFE"] for v in hidden.values()),
        "hidden_detected": sum(v["true_refusal"] for v in hidden.values()),
        "covered_trials": tot(lambda k: k >= 22, "n_trials"),
        "covered_unsafe": tot(lambda k: k >= 22, "UNSAFE"),
        "below_trials": tot(lambda k: k < 22, "n_trials"),
        "below_unsafe": tot(lambda k: k < 22, "UNSAFE"),
        "c0_needless": sum(v["needless_refusal"] for k, v in cells.items() if k.startswith("C0/")),
        "c0_trials": sum(v["n_trials"] for k, v in cells.items() if k.startswith("C0/")),
    }
out["bounded_audit_fraction_of_stock"] = d["server_audit_cost"]["bounded_fraction_of_stock_median"]
out["shipped_audit_fraction_of_stock"] = d["server_audit_cost"]["shipped_fraction_of_stock_median"]
(RES / "v2_summary.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out, indent=1))
