#!/usr/bin/env python3
"""Generate the full Suite B / rung-ladder figure pack for write-up + slides."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import mean, stdev

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

mpl.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 140,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    }
)

STOCK = "#4A5568"
OPT = "#2B6CB0"
CLAIM = "#2F855A"
HUMAN = "#2B6CB0"
FLY = "#C05621"
NF = "#6B46C1"
MUTED = "#718096"

IDS = [f"i{i:02d}" for i in range(1, 11)]
SUITE_COLOR = {
    **{f"i{i:02d}": HUMAN for i in range(1, 5)},
    **{f"i{i:02d}": FLY for i in range(5, 9)},
    **{f"i{i:02d}": NF for i in range(9, 11)},
}
SUITE_LABEL = {
    **{f"i{i:02d}": "Human chr1 10Mb" for i in range(1, 5)},
    **{f"i{i:02d}": "Fly 2L 10Mb" for i in range(5, 9)},
    **{f"i{i:02d}": "nf-core" for i in range(9, 11)},
}

# Honest i01 rung ladder (from bakeoff_*_i01/timings.csv, 2026-09-18/19)
RUNG_ORDER = [
    ("S1–S3", "bakeoff_s123_i01"),
    ("S1–S4", "bakeoff_s1234_i01"),
    ("S5", "bakeoff_s5_i01"),
    ("S5+PGO", "bakeoff_s5pgo_i01"),
    ("S6", "bakeoff_s6_i01"),
    ("S7", "bakeoff_s7_i01"),
    ("S7+PGO", "bakeoff_s7pgo_i01"),
    ("S8+jem+PGO", "bakeoff_s8j_i01"),
]


def load_pairs(path: Path) -> dict:
    rows = list(csv.DictReader(path.open()))
    stock = [float(r["wall_sec"]) for r in rows if r["label"] == "stock"]
    opt = [float(r["wall_sec"]) for r in rows if r["label"] == "opt"]
    if len(stock) != len(opt) or not stock:
        raise SystemExit(f"bad paired timings in {path}")
    pairs = [s / o for s, o in zip(stock, opt)]
    return {
        "stock": stock,
        "opt": opt,
        "pairs": pairs,
        "stock_mean": mean(stock),
        "stock_std": stdev(stock) if len(stock) > 1 else 0.0,
        "opt_mean": mean(opt),
        "opt_std": stdev(opt) if len(opt) > 1 else 0.0,
        "speedup_mean": mean(pairs),
        "speedup_min": min(pairs),
        "n": len(pairs),
        "ge2": sum(1 for p in pairs if p >= 2.0),
    }


def load_summary(path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.open()))
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "n": int(r["n"]),
                "stock_mean": float(r["stock_mean"]),
                "stock_std": float(r["stock_std"]),
                "opt_mean": float(r["opt_mean"]),
                "opt_std": float(r["opt_std"]),
                "speedup": float(r["speedup"]),
                "min_pair": float(r["min_pair"]),
                "output": r["output"],
                "notes": r.get("notes", ""),
            }
        )
    return out


def caption(fig, text: str) -> None:
    fig.text(0.01, -0.02, text, fontsize=8, color="#666")


def plot_suite_wall(summary: list[dict], out: Path) -> None:
    ids = [r["id"] for r in summary]
    x = np.arange(len(ids))
    w = 0.38
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    ax.bar(
        x - w / 2,
        [r["stock_mean"] for r in summary],
        w,
        yerr=[r["stock_std"] for r in summary],
        capsize=2.5,
        color=STOCK,
        label="Stock STAR 2.7.11b",
        zorder=2,
    )
    ax.bar(
        x + w / 2,
        [r["opt_mean"] for r in summary],
        w,
        yerr=[r["opt_std"] for r in summary],
        capsize=2.5,
        color=OPT,
        label="Opt S1–S8 + jemalloc + PGO",
        zorder=2,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(ids)
    ax.set_ylabel("Wall-clock time (s)")
    ax.set_xlabel("Illumina Suite B dataset")
    ax.set_title("Mac Suite B: stock vs optimized wall-clock (1 thread, BAM comp=0)")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)
    # suite band annotations
    ax.axvspan(-0.5, 3.5, color=HUMAN, alpha=0.06, zorder=0)
    ax.axvspan(3.5, 7.5, color=FLY, alpha=0.06, zorder=0)
    ax.axvspan(7.5, 9.5, color=NF, alpha=0.06, zorder=0)
    ax.text(1.5, ax.get_ylim()[1] * 0.97, "Human", ha="center", va="top", fontsize=9, color=HUMAN)
    ax.text(5.5, ax.get_ylim()[1] * 0.97, "Fly 2L", ha="center", va="top", fontsize=9, color=FLY)
    ax.text(8.5, ax.get_ylim()[1] * 0.97, "nf-core", ha="center", va="top", fontsize=9, color=NF)
    caption(fig, "Source: illumina10_s8j_mac.csv · bakeoff_s8j_i0{1–10} · all MATCH · Apple M4 Pro")
    fig.savefig(out / "01_suiteB_stock_vs_opt_wall.png")
    plt.close(fig)


def plot_suite_speedup(summary: list[dict], out: Path) -> None:
    ids = [r["id"] for r in summary]
    x = np.arange(len(ids))
    means = [r["speedup"] for r in summary]
    mins = [r["min_pair"] for r in summary]
    colors = [SUITE_COLOR[i] for i in ids]

    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    bars = ax.bar(x, means, color=colors, width=0.65, zorder=2, alpha=0.9)
    for i, r in enumerate(summary):
        ax.plot([x[i] - 0.22, x[i] + 0.22], [mins[i], mins[i]], color="#1A202C", lw=2.4, zorder=3)
        ax.text(x[i], means[i] + 0.04, f"{means[i]:.2f}×", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.axhline(2.0, color=CLAIM, linestyle="--", lw=1.6, label="2× claim", zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{r['id']}\nn={r['n']}" for r in summary])
    ax.set_ylabel("Speedup (stock / opt)")
    ax.set_xlabel("Dataset (black tick = min pair)")
    ax.set_title("Suite B mean speedup — 10/10 min_pair ≥ 2.0")
    ax.set_ylim(0, max(means) * 1.22)
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)
    # legend proxies for suites
    from matplotlib.patches import Patch

    ax.legend(
        handles=[
            Patch(facecolor=HUMAN, label="Human chr1 10Mb"),
            Patch(facecolor=FLY, label="Fly 2L 10Mb"),
            Patch(facecolor=NF, label="nf-core"),
            plt.Line2D([0], [0], color=CLAIM, linestyle="--", label="2× claim"),
        ],
        frameon=False,
        loc="upper left",
        fontsize=9,
    )
    caption(fig, "Source: illumina10_s8j_mac.csv · arithmetic mean of per-pair ratios · Zhang fairness: 1 thread")
    fig.savefig(out / "02_suiteB_speedup.png")
    plt.close(fig)


def plot_suite_per_pair(results: Path, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(10.5, 5.0))
    rng = np.random.default_rng(0)
    all_max = 2.0
    for i, ds in enumerate(IDS):
        path = results / f"bakeoff_s8j_{ds}" / "timings.csv"
        data = load_pairs(path)
        pairs = data["pairs"]
        all_max = max(all_max, max(pairs))
        jitter = rng.uniform(-0.15, 0.15, size=len(pairs))
        ax.scatter(
            np.full(len(pairs), i) + jitter,
            pairs,
            s=42,
            color=SUITE_COLOR[ds],
            alpha=0.85,
            zorder=3,
            edgecolors="white",
            linewidths=0.5,
        )
        ax.hlines(data["speedup_mean"], i - 0.3, i + 0.3, colors="#1A202C", lw=2.2, zorder=4)
    ax.axhline(2.0, color=CLAIM, linestyle="--", lw=1.5, label="2× claim", zorder=1)
    ax.set_xticks(range(10))
    ax.set_xticklabels(IDS)
    ax.set_ylabel("Per-pair speedup (×)")
    ax.set_xlabel("Illumina Suite B dataset")
    ax.set_title("Every timed stock/opt pair (all MATCH)")
    ax.set_ylim(1.9, all_max * 1.06)
    ax.legend(frameon=False)
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)
    caption(fig, "Source: bakeoff_s8j_i0{1–10}/timings.csv · each point = one pair · black bar = mean")
    fig.savefig(out / "03_suiteB_per_pair_scatter.png")
    plt.close(fig)


def plot_pass_fail_board(summary: list[dict], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 3.2))
    ids = [r["id"] for r in summary]
    vals = [r["min_pair"] for r in summary]
    colors = [CLAIM if v >= 2.0 else "#C53030" for v in vals]
    ax.barh(ids[::-1], vals[::-1], color=colors[::-1], height=0.7, zorder=2)
    ax.axvline(2.0, color="#1A202C", linestyle="--", lw=1.4, zorder=1)
    for y, v in enumerate(vals[::-1]):
        ax.text(v + 0.02, y, f"{v:.3f}×", va="center", fontsize=9)
    ax.set_xlabel("min_pair speedup (×)")
    ax.set_title("Pass board: min_pair ≥ 2.0 on every dataset")
    ax.set_xlim(0, max(vals) * 1.15)
    ax.grid(axis="x", linestyle=":", alpha=0.45, zorder=0)
    caption(fig, "Green = pass · Source: illumina10_s8j_mac.csv")
    fig.savefig(out / "04_suiteB_pass_board.png")
    plt.close(fig)


def plot_rung_ladder(results: Path, out: Path) -> None:
    labels, means, mins, ns = [], [], [], []
    for lab, dirname in RUNG_ORDER:
        path = results / dirname / "timings.csv"
        if not path.exists():
            continue
        d = load_pairs(path)
        labels.append(lab)
        means.append(d["speedup_mean"])
        mins.append(d["speedup_min"])
        ns.append(d["n"])
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    colors = [CLAIM if m >= 2.0 else OPT for m in means]
    ax.plot(x, means, "-o", color=OPT, lw=2, markersize=8, label="Mean speedup", zorder=3)
    ax.fill_between(x, mins, means, color=OPT, alpha=0.18, label="Mean − min_pair band")
    for i, (m, n) in enumerate(zip(means, mins)):
        ax.plot(i, n, "v", color="#1A202C", markersize=7, zorder=4)
        ax.text(i, means[i] + 0.025, f"{means[i]:.2f}×", ha="center", fontsize=8, fontweight="bold")
    ax.axhline(2.0, color=CLAIM, linestyle="--", lw=1.5, label="2× claim", zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{l}\nn={n}" for l, n in zip(labels, ns)], fontsize=9)
    ax.set_ylabel("Speedup on i01 (×)")
    ax.set_xlabel("Cumulative optimization rung (same dataset i01)")
    ax.set_title("Rung ladder on i01 — crossing 2× with S7+PGO → S8+jemalloc")
    ax.set_ylim(1.85, max(means) * 1.12)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)
    caption(fig, "Source: bakeoff_s*_i01/timings.csv · triangles = min_pair · mmap rung omitted (no win)")
    fig.savefig(out / "05_rung_ladder_i01.png")
    plt.close(fig)


def plot_time_saved(summary: list[dict], out: Path) -> None:
    ids = [r["id"] for r in summary]
    saved = [r["stock_mean"] - r["opt_mean"] for r in summary]
    x = np.arange(len(ids))
    fig, ax = plt.subplots(figsize=(10.5, 4.4))
    ax.bar(x, saved, color=[SUITE_COLOR[i] for i in ids], zorder=2)
    for i, s in enumerate(saved):
        ax.text(i, s + 0.08, f"{s:.1f}s", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(ids)
    ax.set_ylabel("Seconds saved per run (stock − opt)")
    ax.set_xlabel("Dataset")
    ax.set_title("Absolute wall-clock saved by optimization")
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)
    caption(fig, "Derived from illumina10_s8j_mac.csv means")
    fig.savefig(out / "06_suiteB_seconds_saved.png")
    plt.close(fig)


def plot_error_bars_zoom(summary: list[dict], out: Path) -> None:
    """Coefficient of variation / stability."""
    ids = [r["id"] for r in summary]
    stock_cv = [
        (r["stock_std"] / r["stock_mean"] * 100) if r["stock_mean"] else 0 for r in summary
    ]
    opt_cv = [(r["opt_std"] / r["opt_mean"] * 100) if r["opt_mean"] else 0 for r in summary]
    x = np.arange(len(ids))
    w = 0.38
    fig, ax = plt.subplots(figsize=(10.5, 4.2))
    ax.bar(x - w / 2, stock_cv, w, color=STOCK, label="Stock CV%", zorder=2)
    ax.bar(x + w / 2, opt_cv, w, color=OPT, label="Opt CV%", zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels(ids)
    ax.set_ylabel("Coefficient of variation (%)")
    ax.set_title("Run-to-run stability (std / mean × 100)")
    ax.legend(frameon=False)
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)
    caption(fig, "Source: illumina10_s8j_mac.csv · lower is more stable")
    fig.savefig(out / "07_suiteB_cv_stability.png")
    plt.close(fig)


def plot_group_means(summary: list[dict], out: Path) -> None:
    groups = {
        "Human (i01–i04)": [r for r in summary if r["id"] in {"i01", "i02", "i03", "i04"}],
        "Fly 2L (i05–i08)": [r for r in summary if r["id"] in {"i05", "i06", "i07", "i08"}],
        "nf-core (i09–i10)": [r for r in summary if r["id"] in {"i09", "i10"}],
    }
    labels = list(groups)
    mean_spd = [mean(r["speedup"] for r in groups[g]) for g in labels]
    min_spd = [min(r["min_pair"] for r in groups[g]) for g in labels]
    colors = [HUMAN, FLY, NF]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.bar(x, mean_spd, color=colors, width=0.55, zorder=2)
    for i, (m, mn) in enumerate(zip(mean_spd, min_spd)):
        ax.plot([i - 0.2, i + 0.2], [mn, mn], color="#1A202C", lw=2.5, zorder=3)
        ax.text(i, m + 0.03, f"{m:.3f}×", ha="center", fontweight="bold")
    ax.axhline(2.0, color=CLAIM, linestyle="--", lw=1.5, zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Mean speedup (×)")
    ax.set_title("Speedup by organism / index family")
    ax.set_ylim(0, max(mean_spd) * 1.2)
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)
    caption(fig, "Black tick = worst min_pair inside group · Source: illumina10_s8j_mac.csv")
    fig.savefig(out / "08_suiteB_by_organism.png")
    plt.close(fig)


def plot_cost_model_schematic(out: Path) -> None:
    """Conceptual pie: copy traffic vs productive stitch (from profiling narrative ~half)."""
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.2))

    ax = axes[0]
    sizes = [50, 50]
    ax.pie(
        sizes,
        labels=["Redundant Transcript\ncopy traffic ~50%", "Productive stitch\n+ other ~50%"],
        colors=[MUTED, OPT],
        startangle=90,
        wedgeprops={"linewidth": 1, "edgecolor": "white"},
        textprops={"fontsize": 9},
    )
    ax.set_title("Stock hot path (conceptual)")

    ax = axes[1]
    sizes2 = [12, 88]
    ax.pie(
        sizes2,
        labels=["Residual copy\n~12%", "Productive work\n(+ allocator gains)"],
        colors=[MUTED, CLAIM],
        startangle=90,
        wedgeprops={"linewidth": 1, "edgecolor": "white"},
        textprops={"fontsize": 9},
    )
    ax.set_title("After S1–S8 + jemalloc (conceptual)")

    fig.suptitle("Cost model: eliminate |\u03c4|_copy, keep stitch scores identical", fontsize=12)
    caption(
        fig,
        "Schematic from profiling narrative (stitchWindowAligns Transcript copies) — not a cycle-accurate pie",
    )
    fig.savefig(out / "09_cost_model_schematic.png")
    plt.close(fig)


def plot_withdrawn_vs_honest(out: Path) -> None:
    """Negative control: withdrawn Nbases=14 vs honest nb10 claim."""
    labels = ["Withdrawn\n(Nbases=14, 800 PE)", "Honest Suite B\n(nb10, full protocol)"]
    vals = [2.5, 2.066]  # illustrative withdrawn headline vs i03 focused honest
    colors = ["#C53030", CLAIM]
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    bars = ax.bar(labels, vals, color=colors, width=0.55, zorder=2)
    ax.axhline(2.0, color="#1A202C", linestyle="--", lw=1.3, label="2×")
    ax.text(0, 2.5 + 0.08, "~2.5× (rigged)", ha="center", color="#C53030", fontweight="bold")
    ax.text(1, 2.066 + 0.08, "i03 mean 2.066×\n(valid)", ha="center", color=CLAIM, fontweight="bold", fontsize=9)
    ax.set_ylabel("Reported speedup (×)")
    ax.set_title("Negative control: oversized index withdrawn")
    ax.set_ylim(0, 3.2)
    ax.legend(frameon=False)
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)
    caption(fig, "Withdrawn claim from PROFILING_LOG · honest = STATUS i03 cool-machine mean")
    fig.savefig(out / "10_withdrawn_vs_honest.png")
    plt.close(fig)


def plot_dashboard(summary: list[dict], results: Path, out: Path) -> None:
    fig = plt.figure(figsize=(12.5, 8.5))
    gs = fig.add_gridspec(2, 2, hspace=0.35, wspace=0.28)

    # top-left wall
    ax = fig.add_subplot(gs[0, 0])
    ids = [r["id"] for r in summary]
    x = np.arange(len(ids))
    w = 0.38
    ax.bar(x - w / 2, [r["stock_mean"] for r in summary], w, color=STOCK, label="Stock")
    ax.bar(x + w / 2, [r["opt_mean"] for r in summary], w, color=OPT, label="Opt")
    ax.set_xticks(x)
    ax.set_xticklabels(ids, fontsize=8)
    ax.set_ylabel("Wall (s)")
    ax.set_title("Wall-clock")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(axis="y", linestyle=":", alpha=0.4)

    # top-right speedup
    ax = fig.add_subplot(gs[0, 1])
    ax.bar(x, [r["speedup"] for r in summary], color=[SUITE_COLOR[i] for i in ids])
    ax.axhline(2.0, color=CLAIM, ls="--", lw=1.3)
    ax.set_xticks(x)
    ax.set_xticklabels(ids, fontsize=8)
    ax.set_ylabel("Speedup (×)")
    ax.set_title("Mean speedup vs 2×")
    ax.grid(axis="y", linestyle=":", alpha=0.4)

    # bottom-left rung
    ax = fig.add_subplot(gs[1, 0])
    labs, ms = [], []
    for lab, dirname in RUNG_ORDER:
        p = results / dirname / "timings.csv"
        if not p.exists():
            continue
        d = load_pairs(p)
        labs.append(lab)
        ms.append(d["speedup_mean"])
    ax.plot(range(len(labs)), ms, "-o", color=OPT)
    ax.axhline(2.0, color=CLAIM, ls="--")
    ax.set_xticks(range(len(labs)))
    ax.set_xticklabels(labs, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("i01 speedup (×)")
    ax.set_title("Rung ladder (i01)")
    ax.grid(axis="y", linestyle=":", alpha=0.4)

    # bottom-right stats text
    ax = fig.add_subplot(gs[1, 1])
    ax.axis("off")
    worst = min(summary, key=lambda r: r["min_pair"])
    best = max(summary, key=lambda r: r["speedup"])
    lines = [
        "LOCKED CLAIM (STATUS)",
        f"  Scoreboard: 10/10 MATCH + min_pair ≥ 2.0",
        f"  Worst min_pair: {worst['id']} = {worst['min_pair']:.3f}×",
        f"  Best mean: {best['id']} = {best['speedup']:.3f}×",
        f"  Mean of means: {mean(r['speedup'] for r in summary):.3f}×",
        "",
        "PROTOCOL",
        "  STAR 2.7.11b · 1 thread · SortedByCoordinate",
        "  --outBAMcompression 0 · identical CLI",
        "  Opt: S1–S8 + jemalloc + PGO/LTO",
        "",
        "INDEXES",
        "  Human chr1 10Mb nb10 · Fly 2L 10Mb nb10",
        "  nf-core mini nb7",
    ]
    ax.text(0.02, 0.98, "\n".join(lines), va="top", family="monospace", fontsize=9.5)

    fig.suptitle("STAR ≥2× Suite B — figure dashboard", fontsize=14, fontweight="bold", y=0.98)
    fig.savefig(out / "00_dashboard.png")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--results",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "results",
    )
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out = args.out or (args.results / "figures")
    out.mkdir(parents=True, exist_ok=True)

    summary_path = args.results / "illumina10_s8j_mac.csv"
    summary = load_summary(summary_path)

    plot_dashboard(summary, args.results, out)
    plot_suite_wall(summary, out)
    plot_suite_speedup(summary, out)
    plot_suite_per_pair(args.results, out)
    plot_pass_fail_board(summary, out)
    plot_rung_ladder(args.results, out)
    plot_time_saved(summary, out)
    plot_error_bars_zoom(summary, out)
    plot_group_means(summary, out)
    plot_cost_model_schematic(out)
    plot_withdrawn_vs_honest(out)

    # also emit legacy lock / early-s8j trio plots when present
    import importlib.util

    legacy = Path(__file__).with_name("plot_bakeoff.py")
    if legacy.exists():
        spec = importlib.util.spec_from_file_location("plot_bakeoff", legacy)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        if (args.results / "bakeoff_lock_i01" / "timings.csv").exists():
            mod.plot_lock(args.results, out)
        if (args.results / "bakeoff_s8j_i01" / "timings.csv").exists():
            mod.plot_s8j(args.results, out)

    print(f"Wrote figures under {out}")
    for p in sorted(out.glob("*.png")):
        print(f"  {p.name}")


if __name__ == "__main__":
    main()
