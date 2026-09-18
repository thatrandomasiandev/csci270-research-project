"""Plot protocol comparisons and diagnostic separation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def load_rows(root: Path):
    rows = []
    for p in root.glob("**/summary.json"):
        with open(p) as f:
            rows.append(json.load(f))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="results/raw")
    ap.add_argument("--summary", default="results/summary.json")
    ap.add_argument("--figdir", default="results/figures")
    args = ap.parse_args()

    figdir = Path(args.figdir)
    figdir.mkdir(parents=True, exist_ok=True)
    rows = load_rows(Path(args.root))
    # baseline only
    base = [
        r
        for r in rows
        if float(r.get("uncertainty_penalty") or 0) == 0
        and float(r.get("kl_coef") or 0) == 0
        and not r.get("more_prefs")
    ]

    protocols = ["oracle", "decay", "overopt", "shared_blindspot"]
    metrics = [
        ("final_true_mean20", "True return"),
        ("final_proxy_mean20", "Proxy return"),
        ("ensemble_disagreement", "Ensemble disagreement"),
        ("support_novelty", "Support novelty"),
        ("onpolicy_acc", "On-policy pref acc"),
        ("hack_mass", "Hack-manifold mass"),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(12, 7))
    axes = axes.ravel()
    for ax, (key, title) in zip(axes, metrics):
        data, labels = [], []
        for prot in protocols:
            vals = [r.get(key, np.nan) for r in base if r["protocol"] == prot]
            vals = [v for v in vals if v == v]
            if vals:
                data.append(vals)
                labels.append(prot)
        if data:
            ax.boxplot(data, labels=labels, showmeans=True)
        ax.set_title(title)
        ax.tick_params(axis="x", rotation=30)
    fig.suptitle("Causal induction protocols (baseline mitigations=none)")
    fig.tight_layout()
    fig.savefig(figdir / "protocol_boxplots.png", dpi=160)
    plt.close(fig)

    # Scatter: novelty vs disagreement colored by protocol
    fig, ax = plt.subplots(figsize=(6, 5))
    colors = {
        "oracle": "#4C78A8",
        "decay": "#E45756",
        "overopt": "#72B7B2",
        "shared_blindspot": "#F58518",
    }
    for prot in protocols:
        pts = [r for r in base if r["protocol"] == prot]
        ax.scatter(
            [r.get("support_novelty", np.nan) for r in pts],
            [r.get("ensemble_disagreement", np.nan) for r in pts],
            label=prot,
            c=colors[prot],
            s=60,
            alpha=0.85,
        )
    ax.set_xlabel("Support novelty")
    ax.set_ylabel("Ensemble disagreement")
    ax.legend()
    ax.set_title("Diagnostic plane")
    fig.tight_layout()
    fig.savefig(figdir / "diagnostic_plane.png", dpi=160)
    plt.close(fig)

    # AUROC bars if summary exists
    summ_path = Path(args.summary)
    if summ_path.exists():
        with open(summ_path) as f:
            summ = json.load(f)
        auroc = summ.get("auroc", {})
        if auroc:
            keys = list(auroc.keys())
            vals = [auroc[k] for k in keys]
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.bar(keys, vals, color="#4C78A8")
            ax.axhline(0.5, color="gray", ls="--", lw=1)
            ax.set_ylim(0, 1.05)
            ax.set_ylabel("AUROC (Decay=positive)")
            ax.set_title("Diagnostic AUROC and single-feature scores")
            ax.tick_params(axis="x", rotation=40)
            fig.tight_layout()
            fig.savefig(figdir / "auroc.png", dpi=160)
            plt.close(fig)

        ab = summ.get("ablations", {})
        if ab:
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.bar(list(ab.keys()), list(ab.values()), color="#72B7B2")
            ax.axhline(auroc.get("full", 0.5), color="#E45756", ls="--", label="full")
            ax.set_ylim(0, 1.05)
            ax.set_ylabel("AUROC")
            ax.set_title("Feature-family ablations")
            ax.legend()
            ax.tick_params(axis="x", rotation=30)
            fig.tight_layout()
            fig.savefig(figdir / "ablations.png", dpi=160)
            plt.close(fig)

    print(f"Wrote figures to {figdir}")


if __name__ == "__main__":
    main()
