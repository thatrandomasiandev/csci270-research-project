"""Summarize the Infernal cache-fill cost and payback from measured2.json.

Reads  pipeline/results/infernal/measured2.json (seed 20261047, ten genomes).
Writes pipeline/results/infernal/fill_summary.json.

fill_over_stock[g] = fill wall / median stock wall for genome g (one fill per genome and variant).
payback_releases   = (F/T - 1) / (1 - 1/S): updates after which fill plus updates cost less than
                     repeated full runs, from the paper's n >= (F - T)/(T - U) with U = T/S,
                     evaluated at the median fill ratio and the median S_g.
"""
import json
import statistics
from pathlib import Path

RES = Path(__file__).resolve().parents[1] / "results" / "infernal"
d = json.loads((RES / "measured2.json").read_text())
out = {"source": "pipeline/results/infernal/measured2.json", "seed": d["seed"], "variants": {}}
for var in ("noclan", "clan"):
    ratios = {g: d["genomes"][g][var]["fill"]["wall_s"] / d["genomes"][g][var]["median_stock_s"] for g in d["order"]}
    med = statistics.median(ratios.values())
    s = d["summary"][var]["median_s_g"]
    out["variants"][var] = {
        "fill_over_stock": ratios,
        "median_fill_over_stock": med,
        "min_fill_over_stock": min(ratios.values()),
        "max_fill_over_stock": max(ratios.values()),
        "median_s_g": s,
        "payback_releases": (med - 1) / (1 - 1 / s),
    }
(RES / "fill_summary.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps({k: {kk: v[kk] for kk in ("median_fill_over_stock", "min_fill_over_stock", "max_fill_over_stock", "payback_releases")} for k, v in out["variants"].items()}, indent=1))
