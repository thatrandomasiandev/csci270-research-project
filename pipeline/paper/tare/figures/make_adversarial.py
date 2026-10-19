"""Detection of injected couplings by TARE's shipped check.

Run from this directory:  python3 make_adversarial.py

Source: pipeline/results/adversarial/measured.json
The dashed curve is Eq. 4 (random pads only) at the measured q.
Laptop timings are not plotted.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
RES = HERE.parents[2] / "results" / "adversarial" / "measured.json"

plt.rcParams.update({
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 7.5,
    "axes.titlesize": 7.5,
    "axes.labelsize": 7.5,
    "legend.fontsize": 6.2,
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

C = {
    "tare": "#2171b5",
    "tare_light": "#9ecae1",
    "stock": "#636363",
    "bad": "#cb181d",
    "n1": "#d9d9d9",
    "n2": "#bdbdbd",
    "n3": "#969696",
    "ink": "#252525",
}
ONE = 3.35

# Empirical series. Eq. 4 is one dashed stock-gray curve per single-entry form.
SERIES = (
    # C4 is drawn before C1. Both sit at detection 1, and the darker
    # circles stay visible on top of the squares.
    ("C4/k{k}", "C4 whole file", C["tare_light"], "s", False),
    ("C1/k{k}", "C1 residues", C["tare"], "o", False),
    ("C2/k{k}", "C2 hidden entry", C["bad"], "^", True),
    ("C3/d2/k{k}", "C3 distance 2", C["stock"], "D", True),
    ("C3/d5/k{k}", "C3 distance 5", C["n3"], "v", True),
    ("C3/d20/k{k}", "C3 distance 20", C["n2"], "P", True),
)
KS = (1, 5, 22, 100)


def main() -> None:
    payload = json.loads(RES.read_text())
    cells = payload["cells"]
    fig, ax = plt.subplots(figsize=(ONE, 2.55))
    for template, label, color, marker, show_eq in SERIES:
        xs, ys, lo, hi = [], [], [], []
        eq = []
        for k in KS:
            cell = cells[template.format(k=k)]
            rate = cell["detection_rate"]
            if rate is None:
                continue
            xs.append(k)
            ys.append(rate)
            band = cell["detection_wilson95"] or [rate, rate]
            lo.append(max(0.0, rate - band[0]))
            hi.append(max(0.0, band[1] - rate))
            if show_eq and cell.get("eq4_detection") is not None:
                eq.append(cell["eq4_detection"])
            else:
                eq.append(None)
        # C1 and C4 are both detection 1. An open square behind the
        # circle keeps both markers on the true k.
        open_square = label.startswith("C4")
        ax.errorbar(
            xs, ys, yerr=[lo, hi], fmt=marker, color=color,
            ms=5.4 if open_square else 3.2,
            lw=0.8, capsize=1.6, label=label,
            markerfacecolor="none" if open_square else color,
            markeredgewidth=0.9,
            zorder=2 if open_square else 4,
        )
        if show_eq and any(value is not None for value in eq):
            ax.plot(
                [x for x, value in zip(xs, eq) if value is not None],
                [value for value in eq if value is not None],
                ls="--", color=color, lw=0.7, alpha=0.9, zorder=2,
            )
    c0_needless = [
        cells[f"C0/k{k}"]["needless_refusal"] for k in KS if f"C0/k{k}" in cells
    ]
    c0_n = [cells[f"C0/k{k}"]["n_trials"] for k in KS if f"C0/k{k}" in cells]
    if c0_n:
        ax.set_title(
            f"C0 needless refusals {sum(c0_needless)}/{sum(c0_n)}",
            loc="left", color=C["stock"], pad=2,
        )
    ax.set_xscale("log")
    ax.set_xticks(list(KS))
    ax.set_xticklabels([str(k) for k in KS])
    ax.set_xlim(0.7, 140)
    ax.set_ylim(-0.05, 1.08)
    ax.set_xlabel("Affected records k  (n = 2,000)")
    ax.set_ylabel("Detection rate")
    ax.grid(axis="y")
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0.12, 0.78), borderaxespad=0.0)
    fig.tight_layout(pad=0.3)
    fig.savefig(HERE / "adversarial.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(HERE / "adversarial.png", dpi=220, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print("wrote adversarial.pdf and adversarial.png")


if __name__ == "__main__":
    main()
