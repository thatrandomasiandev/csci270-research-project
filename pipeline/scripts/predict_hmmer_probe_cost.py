#!/usr/bin/env python3
"""Add inference probe cost P to the HMMER cumulative speedup model.

Does not overwrite results/hmmer_predicted_speedup.json.
Reads predict_hmmer_speedup.py; does not edit it.

    P = Σ_i (a + b · n_i)

over the inference tool-call schedule. FASTA→table (HMMER tblout is
tab-delimited, so the alignment extra calls do not run).

Batched subset-invariance (INFERENCE_PROTOCOL addendum 2026-09-27):
4 full-probe calls (trace, determinism, perturbation, shuffle)
+ 2 halves + 4 quarters + 8 singletons.
Call count is independent of probe_n (for n ≥ 8).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import predict_hmmer_speedup as pred  # noqa: E402

RES = pred.RES
FIG = pred.FIG
STOCK = pred.STOCK
SCAN = pred.SCAN
SEARCH = pred.SEARCH

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


def batch_sizes_batched(k: int) -> list[int]:
    """Record counts for the FASTA→table batched inference schedule."""
    if k <= 0:
        return []
    sizes = [k, k, k, k]  # trace, determinism, pert, shuffle
    h, r = divmod(k, 2)
    sizes.extend([h + (1 if i < r else 0) for i in range(2)])
    q, r4 = divmod(k, 4)
    sizes.extend([q + (1 if i < r4 else 0) for i in range(4)])
    sizes.extend([1] * min(8, k))
    return [n for n in sizes if n > 0]


def batch_sizes_singleton(k: int) -> list[int]:
    if k <= 0:
        return []
    return [k, k, k, k] + [1] * k


def probe_cost(a: float, b: float, sizes: list[int]) -> dict:
    parts = [a + b * n for n in sizes]
    return {
        "n_calls": len(sizes),
        "sizes": sizes,
        "P_s": sum(parts),
        "P_h": pred.hours(sum(parts)),
    }


def add_probe(cum: list[dict], P: float) -> list[dict]:
    out = []
    for row in cum:
        cached = row["cum_cached_s"] + P
        cached_lo = row["cum_cached_s_lo"] + P
        cached_hi = row["cum_cached_s_hi"] + P
        item = dict(row)
        item["probe_cost_s"] = P
        item["cum_cached_s"] = cached
        item["cum_cached_s_lo"] = cached_lo
        item["cum_cached_s_hi"] = cached_hi
        item["cum_speedup"] = row["cum_stock_s"] / cached if cached else None
        item["cum_speedup_lo"] = row["cum_stock_s"] / cached_hi if cached_hi else None
        item["cum_speedup_hi"] = row["cum_stock_s"] / cached_lo if cached_lo else None
        out.append(item)
    return out


def write_figure(payload: dict, dest: Path) -> None:
    collections = ["A", "B", "C"]
    titles = {
        "A": "A · diverse E. coli",
        "B": "B · O157:H7",
        "C": "C · S. aureus",
    }
    modes = (("hmmscan", SCAN), ("hmmsearch", SEARCH))
    fig, axes = plt.subplots(2, 3, figsize=(11.4, 6.4), sharex=False, sharey=False)
    for row, (mode, color) in enumerate(modes):
        for col, cid in enumerate(collections):
            ax = axes[row][col]
            block = payload["collections"][cid]["modes"][mode]["batched_500"]
            xs = [r["genome"] for r in block["cumulative"]]
            ys = [r["cum_speedup"] for r in block["cumulative"]]
            ax.plot(xs, ys, color=color, lw=1.8, label="median + P")
            ax.axhline(3.0, color=STOCK, ls="--", lw=1.1, label="3×")
            ax.set_xlim(1, xs[-1])
            ax.set_ylim(bottom=0)
            if row == 0:
                ax.set_title(titles[cid])
            if row == 1:
                ax.set_xlabel("genomes (cumulative)")
            if col == 0:
                ax.set_ylabel(f"{mode} cum. speedup")
            if col == 2:
                ax.legend(fontsize=8, loc="upper left")
    fig.suptitle(
        "Predicted HMMER cumulative speedup with batched probe cost P  ·  probe_n=500",
        fontsize=12,
    )
    fig.tight_layout()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest)
    plt.close(fig)


def main() -> int:
    screen = pred.load_json("headline_screen.json")
    curves = pred.load_json("recurrence_curves.json")
    n = float(screen["N"])
    params = pred.mode_params(screen)

    scenarios = {
        "batched_8": ("batched", 8),
        "batched_500": ("batched", 500),
        "singleton_8": ("singleton", 8),
        "singleton_500": ("singleton", 500),
    }
    size_fn = {"batched": batch_sizes_batched, "singleton": batch_sizes_singleton}

    P_by_mode: dict[str, dict] = {}
    for name, p in params.items():
        per = {}
        for tag, (kind, k) in scenarios.items():
            sizes = size_fn[kind](k)
            rec = probe_cost(p["a"], p["b"], sizes)
            rec["subset_mode"] = kind
            rec["probe_n"] = k
            per[tag] = rec
        P_by_mode[name] = per

    collections = {}
    for cid, raw in curves["collections"].items():
        ks = list(raw["k"])
        m_med = list(raw["m_median"])
        m_lo = list(raw["m_p10"])
        m_hi = list(raw["m_p90"])
        modes = {}
        for name, p in params.items():
            per_k = pred.series_for_mode(p, n, ks, m_med, m_lo, m_hi)
            cum0 = pred.cumulative_for_mode(p, n, ks, m_med, m_lo, m_hi)
            tagged = {}
            for tag, rec in P_by_mode[name].items():
                cum = add_probe(cum0, rec["P_s"])
                last = cum[-1]
                tagged[tag] = {
                    "P_s": rec["P_s"],
                    "n_calls": rec["n_calls"],
                    "cumulative": cum,
                    "cum_stock_s": last["cum_stock_s"],
                    "cum_cached_s": last["cum_cached_s"],
                    "cum_speedup": last["cum_speedup"],
                }
            modes[name] = {
                "a": p["a"],
                "b": p["b"],
                "w": p["w"],
                "stock_per_genome_s": pred.stock_wall(p["a"], p["b"], n),
                "per_k": per_k,
                **tagged,
            }
        collections[cid] = {
            "id": raw["id"],
            "K": raw["K"],
            "n_orderings": raw["n_orderings"],
            "modes": modes,
        }

    fig_path = FIG / "21_hmmer_predicted_speedup_with_probe.png"
    payload = {
        "protocol": "pipeline/docs/INFERENCE_PROTOCOL.md",
        "screen": "results/headline_screen.json",
        "curves": "results/recurrence_curves.json",
        "baseline_predictions": "results/hmmer_predicted_speedup.json",
        "formula_P": "P = sum_i (a + b * n_i) over inference tool calls",
        "cumulative": "cum_cached = P + sum of per-genome cached times",
        "schedule_note": (
            "FASTA→table HMMER tblout is tab-delimited, so infer_alignment "
            "is a no-op. Batched subset uses seed family 20260927: 2 halves, "
            "4 quarters, 8 singletons. Not a novelty claim (Chen/Segura MR cost cut)."
        ),
        "N": n,
        "modes": {name: {"a": p["a"], "b": p["b"], "w": p["w"]} for name, p in params.items()},
        "P": P_by_mode,
        "collections": collections,
        "figure": str(fig_path.relative_to(ROOT)),
    }
    dest = RES / "hmmer_predicted_speedup_with_probe.json"
    dest.write_text(json.dumps(payload, indent=2) + "\n")
    write_figure(payload, fig_path)
    print(f"wrote {dest}")
    print(f"wrote {fig_path}")
    for mode in ("hmmscan", "hmmsearch"):
        for tag in ("batched_8", "batched_500", "singleton_8", "singleton_500"):
            rec = P_by_mode[mode][tag]
            print(
                f"  {mode} {tag}: calls={rec['n_calls']} "
                f"P={rec['P_s']:.1f}s ({rec['P_h']:.2f}h)"
            )
    for cid in ("A", "B"):
        for mode in ("hmmscan", "hmmsearch"):
            last = collections[cid]["modes"][mode]["batched_500"]
            print(
                f"  {cid} {mode} batched_500 cum_speedup="
                f"{last['cum_speedup']:.3f}×  (P={last['P_s']:.0f}s)"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
