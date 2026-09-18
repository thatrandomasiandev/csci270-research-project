"""Aggregate summaries and evaluate Decay vs Overopt diagnostic (AUROC)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

FEATURE_NAMES = [
    "ensemble_disagreement",
    "support_novelty",
    "heldout_acc",
    "onpolicy_acc",
    "fixed_ref_acc",
    "action_entropy",
    "kl_to_init",
]


def load_summaries(root: Path) -> List[Dict]:
    rows = []
    for p in sorted(root.glob("**/summary.json")):
        with open(p) as f:
            d = json.load(f)
        d["_path"] = str(p)
        rows.append(d)
    return rows


def auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    """labels: 1 = positive class (decay)."""
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int64)
    if len(np.unique(labels)) < 2:
        return float("nan")
    order = np.argsort(-scores)
    labels = labels[order]
    pos = labels.sum()
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return float("nan")
    tps = np.cumsum(labels)
    fps = np.cumsum(1 - labels)
    tpr = tps / pos
    fpr = fps / neg
    # trapezoid
    return float(np.trapz(tpr, fpr))


def logistic_fit(X: np.ndarray, y: np.ndarray, lr=0.2, steps=800, l2=1e-2):
    n, d = X.shape
    w = np.zeros(d)
    b = 0.0
    for _ in range(steps):
        z = X @ w + b
        p = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        grad_w = X.T @ (p - y) / n + l2 * w
        grad_b = float(np.mean(p - y))
        w -= lr * grad_w
        b -= lr * grad_b
    return w, b


def standardize(X: np.ndarray, mean=None, std=None):
    if mean is None:
        mean = np.nanmean(X, axis=0)
        std = np.nanstd(X, axis=0) + 1e-8
    Xs = (X - mean) / std
    Xs = np.nan_to_num(Xs, nan=0.0)
    return Xs, mean, std


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=str, default="results/raw")
    ap.add_argument("--out", type=str, default="results/summary.json")
    args = ap.parse_args()

    rows = load_summaries(Path(args.root))
    # Primary labeled set: decay vs overopt (+ shared_blindspot as overopt)
    labeled = [
        r
        for r in rows
        if r.get("protocol") in ("decay", "overopt", "shared_blindspot")
        and r.get("mitigation", "none") == "none"
        or (
            r.get("protocol") in ("decay", "overopt", "shared_blindspot")
            and r.get("uncertainty_penalty", 0) == 0
            and r.get("kl_coef", 0) == 0
            and not r.get("more_prefs", False)
        )
    ]
    # Deduplicate filter more carefully
    labeled = []
    for r in rows:
        if r.get("protocol") not in ("decay", "overopt", "shared_blindspot"):
            continue
        if float(r.get("uncertainty_penalty") or 0) != 0:
            continue
        if float(r.get("kl_coef") or 0) != 0:
            continue
        if r.get("more_prefs"):
            continue
        labeled.append(r)

    X, y, meta = [], [], []
    for r in labeled:
        vec = [float(r.get(n, np.nan)) for n in FEATURE_NAMES]
        X.append(vec)
        # decay = 1, overopt/shared = 0
        y.append(1 if r["protocol"] == "decay" else 0)
        meta.append(r)

    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    report: Dict = {
        "n_runs_total": len(rows),
        "n_labeled": len(labeled),
        "protocol_counts": {},
        "means_by_protocol": {},
        "auroc": {},
        "ablations": {},
    }

    for r in rows:
        report["protocol_counts"][r["protocol"]] = (
            report["protocol_counts"].get(r["protocol"], 0) + 1
        )

    protocols = sorted(set(r["protocol"] for r in rows))
    for prot in protocols:
        subset = [r for r in rows if r["protocol"] == prot]
        keys = FEATURE_NAMES + [
            "final_proxy_mean20",
            "final_true_mean20",
            "hack_mass",
            "ood_mass",
            "heldout_acc",
        ]
        report["means_by_protocol"][prot] = {
            k: float(np.nanmean([r.get(k, np.nan) for r in subset])) for k in keys
        }

    if len(labeled) >= 4 and len(np.unique(y)) > 1:
        # Leave-one-seed-out style: split by seed
        seeds = sorted(set(int(r["seed"]) for r in meta))
        scores_all = np.zeros(len(meta))
        for hold in seeds:
            train_idx = [i for i, r in enumerate(meta) if int(r["seed"]) != hold]
            test_idx = [i for i, r in enumerate(meta) if int(r["seed"]) == hold]
            if not train_idx or not test_idx:
                continue
            Xtr, mean, std = standardize(X[train_idx])
            Xte, _, _ = standardize(X[test_idx], mean, std)
            w, b = logistic_fit(Xtr, y[train_idx])
            z = Xte @ w + b
            for i, s in zip(test_idx, z):
                scores_all[i] = s
        report["auroc"]["full"] = auroc(scores_all, y.astype(int))

        # Single-feature AUROC (direction chosen to maximize)
        for j, name in enumerate(FEATURE_NAMES):
            s = X[:, j]
            a1 = auroc(s, y.astype(int))
            a2 = auroc(-s, y.astype(int))
            report["auroc"][name] = float(np.nanmax([a1, a2]))

        # Ablations: drop one feature family
        families = {
            "no_disagreement": [0],
            "no_novelty": [1],
            "no_accuracy": [2, 3, 4],
            "no_policy_geometry": [5, 6],
        }
        for fam, drop in families.items():
            keep = [i for i in range(X.shape[1]) if i not in drop]
            scores = np.zeros(len(meta))
            for hold in seeds:
                train_idx = [i for i, r in enumerate(meta) if int(r["seed"]) != hold]
                test_idx = [i for i, r in enumerate(meta) if int(r["seed"]) == hold]
                if not train_idx or not test_idx:
                    continue
                Xtr, mean, std = standardize(X[train_idx][:, keep])
                Xte, _, _ = standardize(X[test_idx][:, keep], mean, std)
                w, b = logistic_fit(Xtr, y[train_idx])
                z = Xte @ w + b
                for i, s in zip(test_idx, z):
                    scores[i] = s
            report["ablations"][fam] = auroc(scores, y.astype(int))

    # Mitigation deltas
    report["mitigations"] = {}
    for prot in ("decay", "overopt"):
        base = [
            r
            for r in rows
            if r["protocol"] == prot
            and float(r.get("uncertainty_penalty") or 0) == 0
            and float(r.get("kl_coef") or 0) == 0
            and not r.get("more_prefs")
        ]
        report["mitigations"][prot] = {}
        base_true = float(np.nanmean([r.get("final_true_mean20", np.nan) for r in base])) if base else None
        report["mitigations"][prot]["none_true"] = base_true
        for tag, pred in (
            ("uncertainty_penalty", lambda r: float(r.get("uncertainty_penalty") or 0) > 0),
            ("kl", lambda r: float(r.get("kl_coef") or 0) > 0),
            ("more_prefs", lambda r: bool(r.get("more_prefs"))),
        ):
            subset = [r for r in rows if r["protocol"] == prot and pred(r)]
            if subset:
                report["mitigations"][prot][tag + "_true"] = float(
                    np.nanmean([r.get("final_true_mean20", np.nan) for r in subset])
                )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
