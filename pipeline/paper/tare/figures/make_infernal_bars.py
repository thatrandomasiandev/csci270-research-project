"""Simple bar chart of Infernal speedup over stock, read from committed JSON.

Source: pipeline/results/infernal/measured2.json (median of ten genomes, 95% bootstrap CI).
Before bar: INFERNAL_PROTOCOL.md "Measured 2026-10-14", stock 328.4 s / update 666.0 s.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
matplotlib.rcParams["font.family"] = "serif"
matplotlib.rcParams["font.size"] = 9
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
s = json.loads((HERE.parents[2] / "results" / "infernal" / "measured2.json").read_text())["summary"]

bars = [
    ("Stock Infernal\n(rerun everything)", 1.0, None, "#888888"),
    ("TARE, first version\n(check too costly)", 328.4 / 666.0, None, "#c0392b"),
    ("TARE\n(no clans)", s["noclan"]["median_s_g"], s["noclan"]["bootstrap_median"], "#2b6cb0"),
    ("TARE\n(with clans)", s["clan"]["median_s_g"], s["clan"]["bootstrap_median"], "#2b6cb0"),
]

fig, ax = plt.subplots(figsize=(5.0, 3.4))
for i, (label, v, ci, col) in enumerate(bars):
    err = None if ci is None else [[v - ci["p2.5"]], [ci["p97.5"] - v]]
    ax.bar(i, v, color=col, width=0.62, yerr=err, capsize=4, error_kw={"lw": 0.9})
    top = v if ci is None else ci["p97.5"]
    ax.text(i, top + 0.06, f"{v:.2f}$\\times$", ha="center", va="bottom", fontsize=10, fontweight="bold")
ax.axhline(1.0, color="black", lw=0.8, ls="--")
ax.set_xticks(range(len(bars)))
ax.set_xticklabels([b[0] for b in bars], fontsize=8)
ax.set_ylabel("speedup over stock (higher is faster)")
ax.set_ylim(0, 2.75)
ax.set_title("Updating Infernal results after a database release\n"
             "(median of 10 genomes; error bars = 95% CI; all outputs byte-identical)", fontsize=8.5)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(HERE / "infernal_bars.pdf")
fig.savefig(HERE / "infernal_bars.png", dpi=220)
print("wrote", HERE / "infernal_bars.pdf")
