"""Infernal speedup per genome after sizing the check by work, read from committed JSON.

Source: pipeline/results/infernal/measured2.json (seed 20261047, ten genomes, three
alternating stock/TARE runs per genome and mode). Before point: INFERNAL_PROTOCOL.md
"Measured 2026-10-14", update 666.0 s vs stock 328.4 s.
"""
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
matplotlib.rcParams["font.family"] = "serif"
matplotlib.rcParams["font.size"] = 8
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
d = json.loads((HERE.parents[2] / "results" / "infernal" / "measured2.json").read_text())
BEFORE = 328.4 / 666.0
MODES = [("noclan", "without clans", "#2b6cb0", "o", -0.17), ("clan", "with clans", "#d9822b", "s", 0.17)]

order = sorted(d["order"], key=lambda g: d["genomes"][g]["noclan"]["s_g"])
fig, (ax, bx) = plt.subplots(1, 2, figsize=(7.0, 3.3), gridspec_kw={"width_ratios": [1.45, 1]})

# (a) per-genome speedup with every run
for mode, label, col, mk, dy in MODES:
    s = d["summary"][mode]
    lo, hi = s["bootstrap_median"]["p2.5"], s["bootstrap_median"]["p97.5"]
    ax.axvspan(lo, hi, color=col, alpha=0.12, lw=0)
    ax.axvline(s["median_s_g"], color=col, lw=1.0, ls="-")
    ax.axvline(s["predicted_s"], color=col, lw=0.8, ls=":")
    for i, g in enumerate(order):
        m = d["genomes"][g][mode]
        runs = [r["stock"]["wall_s"] / r["tare"]["wall_s"] for r in m["runs"]]
        ax.scatter(runs, [i + dy] * len(runs), s=6, color=col, alpha=0.45, lw=0)
        ax.scatter([m["s_g"]], [i + dy], s=22, color=col, marker=mk, edgecolor="white", lw=0.5,
                   zorder=4, label=f"{label}: median {s['median_s_g']:.2f}$\\times$" if i == 0 else None)
ax.axvline(1.0, color="black", lw=0.8)
ax.text(1.0, len(order) - 0.35, " break-even", fontsize=6.5, va="bottom")
ax.axvline(BEFORE, color="#c0392b", lw=1.0, ls="--")
ax.text(BEFORE, len(order) - 0.35, f"before\n{BEFORE:.2f}$\\times$ ", fontsize=6.5, va="bottom", ha="right",
        color="#c0392b")
ax.set_yticks(range(len(order)))
ax.set_yticklabels([f"{g}  ({d['genomes'][g]['residues'] / 1e6:.1f} Mb)" for g in order], fontsize=6)
ax.set_xlim(0.3, 2.75)
ax.set_ylim(-0.6, len(order) + 0.6)
ax.set_xlabel("speedup $S_g$ = median stock wall / median TARE wall", fontsize=7)
ax.set_title("(a) Speedup per genome (small dots = individual runs;\nband = 95% bootstrap CI of the median; dotted = model)",
             fontsize=7)
ax.legend(fontsize=6.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2)
ax.spines[["top", "right"]].set_visible(False)

# (b) wall time, stock vs TARE, per genome (without clans)
stock = [d["genomes"][g]["noclan"]["median_stock_s"] for g in order]
tare = [d["genomes"][g]["noclan"]["median_tare_s"] for g in order]
for i in range(len(order)):
    bx.plot([tare[i], stock[i]], [i, i], color="#999999", lw=1.0, zorder=1)
bx.scatter(stock, range(len(order)), color="#555555", s=20, label="stock Infernal (full rerun)", zorder=3)
bx.scatter(tare, range(len(order)), color="#2b6cb0", s=20, label="TARE update", zorder=3)
bx.set_yticks(range(len(order)))
bx.set_yticklabels([])
bx.set_ylim(-0.6, len(order) + 0.6)
bx.set_xlim(0, max(stock) * 1.12)
bx.set_xlabel("wall seconds (median of 3 runs, without clans)", fontsize=7)
tot_s, tot_t = sum(stock), sum(tare)
bx.set_title(f"(b) Time per genome: {statistics.median(stock):.0f} s $\\rightarrow$ {statistics.median(tare):.0f} s median\n"
             f"(all ten: {tot_s / 60:.0f} $\\rightarrow$ {tot_t / 60:.0f} min; outputs byte-identical)", fontsize=7)
bx.legend(fontsize=6.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2)
bx.spines[["top", "right"]].set_visible(False)

fig.tight_layout()
fig.savefig(HERE / "infernal_speedup.pdf")
fig.savefig(HERE / "infernal_speedup.png", dpi=220)
print("wrote", HERE / "infernal_speedup.pdf")
