#!/usr/bin/env python3
"""Stacked changed fraction for each consecutive Pfam release pair.

Source: pipeline/results/release_chain/pairs.json
Written only when that file has all seven pairs and the 38.1→38.2
control matched reference_kill_r1.json. Blue is what TARE reruns
(edited and new). Gray is unchanged.

Run from this directory: python3 make_churn_pairs.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
PAIRS_JSON = HERE.parents[2] / "results" / "release_chain" / "pairs.json"
EXPECTED = (
    ("37.0", "37.1"),
    ("37.1", "37.2"),
    ("37.2", "37.3"),
    ("37.3", "37.4"),
    ("37.4", "38.0"),
    ("38.0", "38.1"),
    ("38.1", "38.2"),
)

plt.rcParams.update({
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 7.5,
    "axes.titlesize": 7.5,
    "axes.labelsize": 7.5,
    "legend.fontsize": 6.8,
    "xtick.labelsize": 6.8,
    "ytick.labelsize": 6.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "grid.linewidth": 0.4,
    "grid.alpha": 0.35,
})

SYS_NAME = os.environ.get("TARE_SYS_NAME", "PARE")
SYS_BLUE = "#2171b5"
SYS_LIGHT = "#9ecae1"
GRAY = "#bdbdbd"
INK = "#252525"
WIDTH_IN = 7.0


def load_pairs(path: Path) -> list[dict]:
    if not path.is_file():
        raise SystemExit(f"missing {path}; the seven-pair measurement has not been written")
    payload = json.loads(path.read_text())
    if not payload.get("complete"):
        raise SystemExit(f"{path} is not a complete seven-pair measurement")
    if payload.get("control_38_1_38_2_pass") is not True:
        raise SystemExit(f"{path} did not pass the 38.1→38.2 control")
    rows = payload["pairs"]
    got = [(row["old_release"], row["new_release"]) for row in rows]
    if got != list(EXPECTED):
        raise SystemExit(f"pair order {got} != {list(EXPECTED)}")
    return rows


def main() -> None:
    rows = load_pairs(PAIRS_JSON)
    labels = []
    unchanged, edited, new, removed, f_delta = [], [], [], [], []
    for row in rows:
        z_new = row["z_new"]
        parts = row["unchanged_strict"] + row["edited"] + row["added"]
        if parts != z_new:
            raise SystemExit(
                f"{row['old_release']}→{row['new_release']}: "
                f"unchanged+edited+new = {parts} != z_new {z_new}"
            )
        labels.append(f"{row['old_release']}\u2192{row['new_release']}")
        unchanged.append(row["unchanged_strict"] / z_new)
        edited.append(row["edited"] / z_new)
        new.append(row["added"] / z_new)
        removed.append(row["removed"])
        f_delta.append(row["f_delta"])

    fig, ax = plt.subplots(figsize=(WIDTH_IN, 2.15))
    x = list(range(len(rows)))
    ax.bar(x, unchanged, color=GRAY, width=0.72, label="unchanged")
    ax.bar(x, edited, bottom=unchanged, color=SYS_LIGHT, width=0.72, label=f"edited ({SYS_NAME} reruns)")
    bottom_new = [u + e for u, e in zip(unchanged, edited)]
    ax.bar(x, new, bottom=bottom_new, color=SYS_BLUE, width=0.72, label=f"new ({SYS_NAME} reruns)")
    for i, frac in enumerate(f_delta):
        ax.text(i, 1.02, f"{100 * frac:.1f}%", ha="center", va="bottom", fontsize=6.8, color=SYS_BLUE)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{lab}\n\u2212{removed[i]} removed" for i, lab in enumerate(labels)])
    ax.set_xlim(-0.6, len(rows) - 0.4)
    ax.set_ylim(0, 1.14)
    ax.set_ylabel("fraction of the new release")
    
    ax.grid(axis="y")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.08), ncol=3, frameon=False)
    ax.text(
        0.0,
        -0.42,
        "Percentages are f\u0394 = (edited + new) / models in the new release; removed families are not in that denominator.",
        transform=ax.transAxes,
        fontsize=6.8,
        color=INK,
    )
    fig.tight_layout()
    for suffix, extra in (("pdf", {}), ("png", {"dpi": 220})):
        dest = HERE / f"churn_pairs.{suffix}"
        fig.savefig(dest, bbox_inches="tight", pad_inches=0.02, **extra)
        print("wrote", dest)
    plt.close(fig)


if __name__ == "__main__":
    main()
