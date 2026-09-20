#!/usr/bin/env python3
"""Plot honest bake-off wall times and speedups from timings.csv dirs."""
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
        "font.family": "sans-serif",
        "font.size": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 140,
        "savefig.dpi": 160,
        "savefig.bbox": "tight",
    }
)

STOCK = "#4A5568"
OPT = "#2B6CB0"
CLAIM = "#2F855A"


def load_bakeoff(path: Path) -> dict:
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


def plot_lock(results: Path, out: Path) -> None:
    ids = ["i01", "i02", "i03", "i04"]
    data = {d: load_bakeoff(results / f"bakeoff_lock_{d}" / "timings.csv") for d in ids}
    x = np.arange(len(ids))
    w = 0.36

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar(
        x - w / 2,
        [data[d]["stock_mean"] for d in ids],
        w,
        yerr=[data[d]["stock_std"] for d in ids],
        capsize=3,
        color=STOCK,
        label="Stock STAR 2.7.11b",
        zorder=2,
    )
    ax.bar(
        x + w / 2,
        [data[d]["opt_mean"] for d in ids],
        w,
        yerr=[data[d]["opt_std"] for d in ids],
        capsize=3,
        color=OPT,
        label="Optimized (S1–S7 + PGO)",
        zorder=2,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(ids)
    ax.set_ylabel("Wall-clock time (s)")
    ax.set_xlabel("Illumina dataset (full FASTQ)")
    ax.set_title("Honest bake-off: wall-clock (nb10, 1 thread, BAM comp=0)")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)
    fig.text(
        0.01,
        -0.02,
        "Source: bakeoff_lock_i0{1–4}/timings.csv · N=7 pairs/dataset · all MATCH",
        fontsize=8,
        color="#666",
    )
    fig.savefig(out / "honest_stock_vs_opt_wall.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    means = [data[d]["speedup_mean"] for d in ids]
    mins = [data[d]["speedup_min"] for d in ids]
    bars = ax.bar(x, means, color=CLAIM, zorder=2, width=0.55)
    for i, d in enumerate(ids):
        bars[i].set_color(CLAIM if means[i] >= 2.0 else "#C53030")
        ax.plot([x[i] - 0.18, x[i] + 0.18], [mins[i], mins[i]], color="#1A202C", lw=2, zorder=3)
        ax.text(
            x[i],
            means[i] + 0.04,
            f"{means[i]:.2f}×",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )
    ax.axhline(2.0, color=CLAIM, linestyle="--", lw=1.5, label="2× claim", zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{d}\n({data[d]['ge2']}/{data[d]['n']} ≥2×)" for d in ids])
    ax.set_ylabel("Speedup (stock / opt)")
    ax.set_xlabel("Dataset (tick = min pair)")
    ax.set_title("Mean per-pair speedup vs 2× claim line")
    ax.set_ylim(0, max(means) * 1.28)
    ax.legend(frameon=False, loc="upper right")
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)
    fig.text(
        0.01,
        -0.02,
        "Source: bakeoff_lock · arithmetic mean of per-pair ratios · horizontal tick = worst pair",
        fontsize=8,
        color="#666",
    )
    fig.savefig(out / "honest_speedup.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    rng = np.random.default_rng(0)
    for i, d in enumerate(ids):
        pairs = data[d]["pairs"]
        jitter = rng.uniform(-0.12, 0.12, size=len(pairs))
        ax.scatter(
            np.full(len(pairs), i) + jitter,
            pairs,
            s=36,
            color=OPT,
            alpha=0.85,
            zorder=3,
            edgecolors="white",
            linewidths=0.4,
        )
        ax.hlines(data[d]["speedup_mean"], i - 0.28, i + 0.28, colors="#1A202C", lw=2.2, zorder=4)
    ax.axhline(2.0, color=CLAIM, linestyle="--", lw=1.5, label="2× claim", zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels(ids)
    ax.set_ylabel("Per-pair speedup (×)")
    ax.set_xlabel("Illumina dataset")
    ax.set_title("Per-pair speedup ratios (all MATCH)")
    ax.set_ylim(1.6, max(max(data[d]["pairs"]) for d in ids) * 1.08)
    ax.legend(frameon=False)
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)
    fig.text(
        0.01,
        -0.02,
        "Source: bakeoff_lock · each point = one timed stock/opt pair · black bar = mean",
        fontsize=8,
        color="#666",
    )
    fig.savefig(out / "honest_per_pair_speedup.png")
    plt.close(fig)


def plot_s8j(results: Path, out: Path) -> None:
    ids = ["i01", "i02", "i03"]
    data = {d: load_bakeoff(results / f"bakeoff_s8j_{d}" / "timings.csv") for d in ids}
    x = np.arange(len(ids))
    w = 0.36

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.0), gridspec_kw={"width_ratios": [1.15, 1]})

    ax = axes[0]
    ax.bar(
        x - w / 2,
        [data[d]["stock_mean"] for d in ids],
        w,
        yerr=[data[d]["stock_std"] for d in ids],
        capsize=3,
        color=STOCK,
        label="Stock",
        zorder=2,
    )
    ax.bar(
        x + w / 2,
        [data[d]["opt_mean"] for d in ids],
        w,
        yerr=[data[d]["opt_std"] for d in ids],
        capsize=3,
        color=OPT,
        label="S8 + jemalloc + PGO",
        zorder=2,
    )
    ax.set_xticks(x)
    ax.set_xticklabels([f"{d}\n(n={data[d]['n']})" for d in ids])
    ax.set_ylabel("Wall-clock (s)")
    ax.set_title("S8+jemalloc wall time")
    ax.legend(frameon=False, fontsize=9)
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)
    ax.set_ylim(0, 8)

    ax = axes[1]
    means = [data[d]["speedup_mean"] for d in ids]
    mins = [data[d]["speedup_min"] for d in ids]
    ax.bar(x, means, color=CLAIM, width=0.55, zorder=2)
    for i, d in enumerate(ids):
        ax.plot([x[i] - 0.18, x[i] + 0.18], [mins[i], mins[i]], color="#1A202C", lw=2, zorder=3)
        ax.text(
            x[i],
            means[i] + 0.035,
            f"{means[i]:.3f}×",
            ha="center",
            fontsize=10,
            fontweight="bold",
        )
    ax.axhline(2.0, color="#1A202C", linestyle="--", lw=1.2, label="2×", zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{d}\n{data[d]['ge2']}/{data[d]['n']} ≥2×" for d in ids])
    ax.set_ylabel("Speedup (×)")
    ax.set_title("S8+jemalloc speedup (STATUS)")
    ax.set_ylim(0, 2.6)
    ax.legend(frameon=False, fontsize=9)
    ax.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)

    fig.suptitle("Focused cool-machine bake-off · S8 + jemalloc + PGO", fontsize=12, y=1.02)
    fig.text(
        0.01,
        -0.04,
        "Source: bakeoff_s8j_i0{1–3}/timings.csv · STATUS headline · all MATCH · i03 focused n=9",
        fontsize=8,
        color="#666",
    )
    fig.savefig(out / "honest_s8j_wall_and_speedup.png")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--results",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "results",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Figure output dir (default: <results>/figures)",
    )
    args = ap.parse_args()
    out = args.out or (args.results / "figures")
    out.mkdir(parents=True, exist_ok=True)
    plot_lock(args.results, out)
    plot_s8j(args.results, out)
    print(f"Wrote honest_*.png under {out}")


if __name__ == "__main__":
    main()
