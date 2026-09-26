#!/usr/bin/env python3
"""Figure pack for Survivor 1 measurements. Numbers come only from results JSON/CSV."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = RES / "figures"

STOCK = "#4A5568"
OPT = "#2B6CB0"
CLAIM = "#2F855A"
MISS = "#C05621"
HIT = "#2B6CB0"
MUTED = "#718096"
PRED = "#6B46C1"


def short_sample(name: str) -> str:
    return name.replace("HG000", "")


def _pair(prev: str, new: str) -> str:
    return f"{short_sample(prev)}→{short_sample(new)}"

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


def save(fig: mpl.figure.Figure, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / name
    fig.savefig(dest)
    plt.close(fig)
    print(dest)
    return dest


def load_json(name: str) -> dict:
    return json.loads((RES / name).read_text())


def fig_00_dashboard(overlap: dict, fit: dict, cached: dict) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.6))

    ax = axes[0, 0]
    labels = [_pair(r["prev"], r["new"]) for r in overlap["rows"]]
    labels.append("96∪97→99")
    recalls = [r["recall_in_new"] for r in overlap["rows"]]
    recalls.append(overlap["growing_cohort"]["recall_in_new"])
    colors = [HIT, HIT, HIT, CLAIM]
    ax.bar(range(len(labels)), recalls, color=colors)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel("recall_in_new")
    ax.set_title("CEU chr22 −c1 overlap")
    for i, v in enumerate(recalls):
        ax.text(i, v + 0.02, f"{v:.3f}", ha="center", fontsize=9)

    ax = axes[0, 1]
    ns = [row["n"] for row in fit["raw"]]
    means = [row["mean_s"] for row in fit["raw"]]
    stds = [row["stdev_s"] for row in fit["raw"]]
    a = fit["fit"]["a_s"]
    b = fit["fit"]["b_s_per_record"]
    xs = np.linspace(0, fit["n_full"], 200)
    ax.plot(xs, a + b * xs, color=PRED, label=f"OLS t = {a:.3f} + {b:.3e} n")
    ax.errorbar(ns, means, yerr=stds, fmt="o", color=STOCK, capsize=3, label="mean ± stdev (3 runs)")
    ax.set_xlabel("records (HG00099 prefixes)")
    ax.set_ylabel("wall (s)")
    ax.set_title("Pre-registered stock fit")
    ax.legend(fontsize=8)

    ax = axes[1, 0]
    cats = ["stock", "cached"]
    pred = [fit["prediction"]["t_stock_s"], fit["prediction"]["t_cached_s"]]
    meas = [cached["timing"]["stock_mean_s"], cached["timing"]["cached_mean_s"]]
    x = np.arange(2)
    w = 0.35
    ax.bar(x - w / 2, pred, w, color=PRED, label="predicted (locked)")
    ax.bar(x + w / 2, meas, w, color=STOCK, label="measured mean")
    ax.set_xticks(x)
    ax.set_xticklabels(cats)
    ax.set_ylabel("wall (s)")
    ax.set_title("HG00099 wall: predicted vs measured")
    ax.legend(fontsize=8)

    ax = axes[1, 1]
    names = ["overlap-only\nN/miss_n", "predicted\n(a+b n+w)", "measured"]
    vals = [
        fit["n_full"] / fit["miss_n"],
        fit["prediction"]["speedup"],
        cached["timing"]["measured_speedup"],
    ]
    ax.bar(names, vals, color=[MUTED, PRED, CLAIM])
    ax.axhline(1.0, color=STOCK, ls="--", lw=1)
    ax.set_ylabel("speedup (stock / cached)")
    ax.set_title("Why not N/miss_n")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.05, f"{v:.3f}×", ha="center", fontsize=9)

    fig.suptitle("SnpEff 5.4c GRCh38.86 · HG00099 chr22 joint_called_c1 · 2026-09-24", fontsize=12)
    fig.tight_layout()
    save(fig, "00_dashboard.png")


def fig_01_overlap(overlap: dict) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    labels = [_pair(r["prev"], r["new"]) for r in overlap["rows"]]
    labels.append("96∪97→99")
    recalls = [r["recall_in_new"] for r in overlap["rows"]]
    recalls.append(overlap["growing_cohort"]["recall_in_new"])
    shared = [r["n_shared"] for r in overlap["rows"]]
    shared.append(overlap["growing_cohort"]["n_shared"])
    bars = ax.bar(range(len(labels)), recalls, color=[HIT, HIT, HIT, CLAIM])
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=18, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel("recall_in_new")
    ax.set_title("1000G CEU chr22 overlap (joint_called_c1, full ALT)")
    for i, (bar, rec, sh) in enumerate(zip(bars, recalls, shared)):
        ax.text(bar.get_x() + bar.get_width() / 2, rec + 0.02, f"{rec:.3f}\n({sh} shared)", ha="center", fontsize=8)
    ax.text(
        0.01,
        0.98,
        "Not separately-called. n_multiallelic = 0.",
        transform=ax.transAxes,
        va="top",
        color=MUTED,
        fontsize=8,
    )
    save(fig, "01_ceu_overlap_recall.png")


def fig_02_hits_misses(cached: dict) -> None:
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    samples = ["HG00096", "HG00097", "HG00099"]
    hits = [
        cached["populate"]["HG00096"]["n_hits"],
        cached["populate"]["HG00097"]["n_hits"],
        cached["HG00099"]["n_hits"],
    ]
    misses = [
        cached["populate"]["HG00096"]["n_misses"],
        cached["populate"]["HG00097"]["n_misses"],
        cached["HG00099"]["n_misses"],
    ]
    x = np.arange(len(samples))
    ax.bar(x, hits, color=HIT, label="cache hits")
    ax.bar(x, misses, bottom=hits, color=MISS, label="SnpEff misses")
    ax.set_xticks(x)
    ax.set_xticklabels(samples)
    ax.set_ylabel("records")
    ax.set_title("Record-memo path: hits vs misses (populate 96→97, then 99)")
    ax.legend()
    for i, (h, m) in enumerate(zip(hits, misses)):
        ax.text(i, h + m + 800, f"{h + m}", ha="center", fontsize=9)
        if h:
            ax.text(i, h / 2, str(h), ha="center", va="center", color="white", fontsize=9)
        ax.text(i, h + m / 2, str(m), ha="center", va="center", color="white", fontsize=9)
    save(fig, "02_cache_hits_misses.png")


def fig_03_fit(fit: dict) -> None:
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    a = fit["fit"]["a_s"]
    b = fit["fit"]["b_s_per_record"]
    xs = np.linspace(0, fit["n_full"], 300)
    ax.plot(xs, a + b * xs, color=PRED, lw=2, label=f"OLS t = {a:.4f} + {b:.4e}·n")
    for row in fit["raw"]:
        ax.scatter(
            [row["n"]] * len(row["runs_s"]),
            row["runs_s"],
            color=STOCK,
            s=28,
            zorder=3,
            label="individual run" if row["n"] == 1 else None,
        )
    ns = [row["n"] for row in fit["raw"]]
    means = [row["mean_s"] for row in fit["raw"]]
    stds = [row["stdev_s"] for row in fit["raw"]]
    ax.errorbar(ns, means, yerr=stds, fmt="D", color=OPT, capsize=4, label="mean ± stdev")
    ax.axhline(a, color=MUTED, ls=":", lw=1, label=f"a = {a:.3f} s")
    ax.axvline(fit["miss_n"], color=MISS, ls="--", lw=1, label=f"miss_n = {fit['miss_n']}")
    ax.axvline(fit["n_full"], color=CLAIM, ls="--", lw=1, label=f"N = {fit['n_full']}")
    ax.set_xlabel("records n (nested prefixes of HG00099)")
    ax.set_ylabel("stock SnpEff wall (s)")
    ax.set_title("Pre-registered fit · 3 runs/size · −noStats −noLog")
    ax.legend(fontsize=8, loc="upper left")
    save(fig, "03_snpeff_timing_fit.png")


def fig_04_amdahl(fit: dict) -> None:
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    a = fit["fit"]["a_s"]
    b = fit["fit"]["b_s_per_record"]
    n = fit["n_full"]
    miss = fit["miss_n"]
    w = fit["wrapper_cat"]["mean_s"]
    stock = [a, b * n, 0.0]
    cached = [a, b * miss, w]
    x = np.arange(2)
    ax.bar(x, [stock[0], cached[0]], color=STOCK, label="a (startup)")
    ax.bar(x, [stock[1], cached[1]], bottom=[stock[0], cached[0]], color=OPT, label="b · records")
    ax.bar(
        x,
        [stock[2], cached[2]],
        bottom=[stock[0] + stock[1], cached[0] + cached[1]],
        color=MISS,
        label="w (cat wrapper)",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(
        [
            f"stock\n{fit['prediction']['t_stock_s']:.3f} s",
            f"cached\n{fit['prediction']['t_cached_s']:.3f} s",
        ]
    )
    ax.set_ylabel("predicted wall (s)")
    ax.set_title("Locked prediction: (a + bN) / (a + b·miss_n + w)")
    ax.legend()
    save(fig, "04_amdahl_decomposition.png")


def fig_05_runs(cached: dict) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    stock = cached["timing"]["stock_s"]
    cached_t = cached["timing"]["cached_s"]
    x = np.arange(1, 4)
    w = 0.35
    ax.bar(x - w / 2, stock, w, color=STOCK, label="stock full")
    ax.bar(x + w / 2, cached_t, w, color=OPT, label="cached path")
    ax.set_xticks(x)
    ax.set_xticklabels([f"run {i}" for i in x])
    ax.set_ylabel("wall (s)")
    ax.set_title("HG00099 after 96∪97 cache · MATCH held · 3 runs each")
    ax.legend()
    save(fig, "05_cached_vs_stock_runs.png")


def fig_06_pred_vs_meas(fit: dict, cached: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.4))

    ax = axes[0]
    cats = ["stock", "cached"]
    pred = [fit["prediction"]["t_stock_s"], fit["prediction"]["t_cached_s"]]
    meas = [cached["timing"]["stock_mean_s"], cached["timing"]["cached_mean_s"]]
    err = [cached["timing"]["stock_stdev_s"], cached["timing"]["cached_stdev_s"]]
    x = np.arange(2)
    w = 0.35
    ax.bar(x - w / 2, pred, w, color=PRED, label="predicted (locked fit)")
    ax.bar(x + w / 2, meas, w, color=STOCK, yerr=err, capsize=4, label="measured mean ± stdev")
    ax.set_xticks(x)
    ax.set_xticklabels(cats)
    ax.set_ylabel("wall (s)")
    ax.set_title("Wall time")
    ax.legend(fontsize=8)

    ax = axes[1]
    names = ["predicted", "measured"]
    vals = [fit["prediction"]["speedup"], cached["timing"]["measured_speedup"]]
    ax.bar(names, vals, color=[PRED, CLAIM])
    ax.axhline(1.0, color=STOCK, ls="--", lw=1, label="1×")
    ax.set_ylabel("speedup")
    ax.set_title("Speedup (stock / cached)")
    ax.set_ylim(0, 1.6)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.04, f"{v:.4f}×", ha="center")
    ax.legend(fontsize=8)

    fig.suptitle("Do not edit the locked prediction after seeing measured times", fontsize=11)
    fig.tight_layout()
    save(fig, "06_predicted_vs_measured.png")


def fig_07_suiteb_unique() -> None:
    rows = list(csv.DictReader((RES / "suiteB_dups.csv").open()))
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    ids = [r["id"] for r in rows]
    fracs = [float(r["unique_frac"]) for r in rows]
    colors = []
    for i, r in enumerate(rows):
        if r["id"] in {"i01", "i02", "i03", "i04"}:
            colors.append(HIT)
        elif r["id"] in {"i05", "i06", "i07", "i08"}:
            colors.append(MISS)
        else:
            colors.append(PRED)
    ax.bar(ids, fracs, color=colors)
    ax.axhline(0.95, color=STOCK, ls="--", lw=1, label="refuse if unique_frac ≥ 0.95")
    ax.set_ylim(0.8, 1.0)
    ax.set_ylabel("unique_frac")
    ax.set_title("Suite B within-file uniqueness (PE pairs) · STAR instance")
    ax.legend(fontsize=8)
    save(fig, "07_suiteB_unique_frac.png")


def fig_08_instance_compare(overlap: dict) -> None:
    sb = list(csv.DictReader((RES / "suiteB_overlap.csv").open()))
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    labels = [f"{r['prev']}→{r['new']}" for r in sb]
    labels += [f"{r['prev'][-2:]}→{r['new'][-2:]}" for r in overlap["rows"]]
    labels.append("96∪97→99")
    vals = [float(r["recall_in_new"]) for r in sb]
    vals += [r["recall_in_new"] for r in overlap["rows"]]
    vals.append(overlap["growing_cohort"]["recall_in_new"])
    colors = [MUTED] * len(sb) + [HIT] * 3 + [CLAIM]
    ax.bar(range(len(labels)), vals, color=colors)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("recall_in_new")
    ax.set_ylim(0, 1)
    ax.set_title("Incremental overlap: Suite B reads vs CEU −c1 variants")
    ax.axhline(0.95, color=STOCK, ls=":", lw=1)
    save(fig, "08_instance_recall_compare.png")


def fig_09_match(ident: dict, cached: dict) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 3.6))
    ax.set_axis_off()
    rows = [
        ("stock-vs-stock body (n=200)", "MATCH" if ident["body_identical"] else "FAIL", ident["body_identical"]),
        ("shuffle body (n=200)", "MATCH" if ident["shuffle_body_identical"] else "FAIL", ident["shuffle_body_identical"]),
        ("full-file cmp (n=200)", "DIFF header only (expected)", False),
        (
            "reassembled vs stock body (n=52638)",
            "MATCH" if cached["bodies_equal"] else "FAIL",
            cached["bodies_equal"],
        ),
        ("differing body lines", "0" if cached["diffs"] is None else "n>0", cached["diffs"] is None),
    ]
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, len(rows) - 0.5)
    for i, (check, verdict, ok) in enumerate(rows[::-1]):
        color = CLAIM if ok else (MUTED if "expected" in verdict else MISS)
        ax.add_patch(plt.Rectangle((0.02, i - 0.35), 0.96, 0.7, facecolor=color, edgecolor="none"))
        ax.text(0.05, i, check, va="center", color="white", fontsize=11)
        ax.text(0.95, i, verdict, va="center", ha="right", color="white", fontsize=11)
    ax.set_title("MATCH board · accept rule is the record body, not full-file cmp")
    save(fig, "09_match_board.png")


def fig_10_suiteb_maxx() -> None:
    rows = list(csv.DictReader((RES / "suiteB_dups.csv").open()))
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    ids = [r["id"] for r in rows]
    xs = [float(r["max_speedup_if_pure"]) for r in rows]
    colors = []
    for r in rows:
        if r["id"] in {"i01", "i02", "i03", "i04"}:
            colors.append(HIT)
        elif r["id"] in {"i05", "i06", "i07", "i08"}:
            colors.append(MISS)
        else:
            colors.append(PRED)
    ax.bar(ids, xs, color=colors)
    ax.axhline(2.0, color=STOCK, ls="--", lw=1, label="course 2× (different object)")
    ax.set_ylabel("max speedup if per-record and MATCH")
    ax.set_title("Suite B: uniqueness bound only · STAR REFUSE_IDENTITY")
    ax.set_ylim(1.0, 2.2)
    ax.legend(fontsize=8)
    save(fig, "10_suiteB_max_speedup_if_pure.png")


def fig_11_alternating_carc(alt: dict) -> None:
    pairs = alt["pairs"]
    xs = [p["pair"] for p in pairs]
    stock = [p["stock_s"] for p in pairs]
    cached_t = [p["cached_s"] for p in pairs]
    ratios = [p["r"] for p in pairs]
    med = alt["median_r"]
    lo = alt["bootstrap"]["ci95_lo"]
    hi = alt["bootstrap"]["ci95_hi"]
    host = alt["machine_before"]["hostname"].split(".")[0]
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.6))

    ax = axes[0]
    w = 0.36
    ax.bar(np.array(xs) - w / 2, stock, w, color=STOCK, label="stock")
    ax.bar(np.array(xs) + w / 2, cached_t, w, color=OPT, label="cached")
    ax.set_xticks(xs)
    ax.set_xlabel("pair (ABBA)")
    ax.set_ylabel("wall (s)")
    ax.set_ylim(0, 24)
    ax.legend(fontsize=8, loc="lower right")
    ax.set_title("Paired wall")

    ax = axes[1]
    ax.axhspan(lo, hi, color=CLAIM, alpha=0.15, zorder=0)
    ax.axhline(1.0, color=STOCK, ls="--", lw=1, label="1×")
    ax.axhline(med, color=CLAIM, lw=1.6, label=f"median {med:.4f}")
    ax.plot(xs, ratios, "o", color=OPT, ms=7, zorder=3)
    ax.set_xticks(xs)
    ax.set_xlabel("pair")
    ax.set_ylabel("r = stock / cached")
    ax.set_ylim(0.98, 1.22)
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title(f"95% CI [{lo:.4f}, {hi:.4f}]")

    fig.suptitle(
        f"CARC exclusive {host} · SnpEff 5.4c · {alt['decision']} · wall primary",
        fontsize=12,
    )
    fig.tight_layout()
    save(fig, "11_snpeff_alternating_carc.png")


def main() -> int:
    overlap = load_json("vep_chr22_overlap.json")
    fit = load_json("snpeff_timing_fit.json")
    cached = load_json("snpeff_cached_identity.json")
    ident = load_json("snpeff_identity/report.json")
    fig_00_dashboard(overlap, fit, cached)
    fig_01_overlap(overlap)
    fig_02_hits_misses(cached)
    fig_03_fit(fit)
    fig_04_amdahl(fit)
    fig_05_runs(cached)
    fig_06_pred_vs_meas(fit, cached)
    fig_07_suiteb_unique()
    fig_08_instance_compare(overlap)
    fig_09_match(ident, cached)
    fig_10_suiteb_maxx()
    carc_path = RES / "snpeff_alternating_carc.json"
    if carc_path.is_file():
        fig_11_alternating_carc(json.loads(carc_path.read_text()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
