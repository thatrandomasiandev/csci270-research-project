"""Phase breakdown before and after the cost pass, read from committed JSON.

Sources:
  pipeline/results/exact_replay/costpass_baseline.json  (replay_38.2.median_phases, stock.median_s)
  pipeline/results/exact_replay/costpass_measured.json  (proteomes[*].e2.phases, stock.wall_s)
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
matplotlib.rcParams["font.family"] = "serif"
matplotlib.rcParams["font.size"] = 8
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
RES = HERE.parents[2] / "results" / "exact_replay"

base = json.loads((RES / "costpass_baseline.json").read_text())
meas = json.loads((RES / "costpass_measured.json").read_text())

bp = base["replay_38.2"]["median_phases"]
before = {
    "diff": bp["diff_s"],
    "discovery": bp["discovery_s"],
    "replay": bp["replay_s"],
    "check": bp["ic2_s"],
    "verify": bp["verify_s"],
    "parse": bp["parse_s"],
}
before_stock = base["stock"]["median_s"]
before["other"] = base["replay_38.2"]["median_wall_s"] - sum(before.values())

rows = [("GCF_013315695.1\nbefore", before, before_stock)]
for p in meas["proteomes"]:
    ph = p["e2"]["phases"]
    check = ph["ic2_neighbor_s"] + sum(v for k, v in ph.items() if k.startswith("ic2_random_") and k.count("_") == 3)
    after = {
        "diff": ph["diff_s"],
        "discovery": ph["discovery_s"],
        "replay": ph["replay_s"],
        "check": check,
        "verify": ph["verify_s"],
        "parse": ph["parse_s"],
    }
    after["other"] = p["e2"]["wall_s"] - sum(after.values())
    rows.append((p["proteome"] + "\nafter", after, p["stock"]["wall_s"]))

order = ["diff", "discovery", "replay", "check", "verify", "parse", "other"]
colors = {
    "diff": "#bdbdbd",
    "discovery": "#2b6cb0",
    "replay": "#68a0d8",
    "check": "#d9822b",
    "verify": "#8c6bb1",
    "parse": "#7f7f7f",
    "other": "#dedede",
}

fig, ax = plt.subplots(figsize=(3.35, 2.2))
for i, (label, ph, stock) in enumerate(rows):
    left = 0.0
    for k in order:
        ax.barh(i, ph[k], left=left, color=colors[k], edgecolor="white", linewidth=0.4,
                label={"discovery":"selection"}.get(k,k) if i == 0 else None)
        left += ph[k]
    ax.plot([stock, stock], [i - 0.4, i + 0.4], color="black", linewidth=1.0)
    ax.text(left + 8, i, f"{stock / left:.2f}$\\times$", va="center", fontsize=7)
ax.set_yticks(range(len(rows)))
ax.set_yticklabels([r[0] for r in rows], fontsize=6.5)
ax.invert_yaxis()
ax.set_xlabel("wall seconds  (tick = stock run on Pfam 38.2)", fontsize=7)
ax.set_xlim(0, 1000)
ax.legend(ncol=4, fontsize=6, frameon=False, loc="lower center", bbox_to_anchor=(0.45, 1.0))
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(HERE / "phases.pdf")
fig.savefig(HERE / "phases.png", dpi=200)
print("wrote", HERE / "phases.pdf")
