#!/usr/bin/env python3
"""Predict HMMER speedup from the headline screen and recurrence curves.

No timing. No CARC. Numbers come only from
``results/headline_screen.json`` and ``results/recurrence_curves.json``.

    speedup(k) = (a + b·N) / (a + b·m(k)·N + w)

``m(k)`` is the miss of genome *k*+1 given the first *k*
(``docs/RECURRENCE_PROTOCOL.md``). The first genome of a collection is
all misses: cached wall = stock wall = *a* + *b*·*N*.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
FIG = RES / "figures"

STOCK = "#4A5568"
SCAN = "#2B6CB0"
SEARCH = "#C05621"
CLAIM = "#2F855A"

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


def load_json(name: str) -> dict:
    return json.loads((RES / name).read_text())


def stock_wall(a: float, b: float, n: float) -> float:
    return a + b * n


def cached_wall(a: float, b: float, w: float, n: float, m: float) -> float:
    return a + b * m * n + w


def speedup(a: float, b: float, w: float, n: float, m: float) -> float:
    return stock_wall(a, b, n) / cached_wall(a, b, w, n, m)


def mode_params(screen: dict) -> dict[str, dict]:
    out = {}
    for mode in screen["modes"]:
        out[mode["mode"]] = {
            "a": mode["a_s"],
            "b": mode["b_s_per_record"],
            "w": mode["w"]["w_s"],
            "ceiling_k12": mode["ceiling"],
            "decision": mode["decision"],
        }
    return out


def series_for_mode(
    params: dict, n: float, ks: list[int], m_med: list[float], m_lo: list[float], m_hi: list[float]
) -> list[dict]:
    a, b, w = params["a"], params["b"], params["w"]
    rows = []
    for k, med, lo, hi in zip(ks, m_med, m_lo, m_hi):
        # Lower miss ⇒ higher speedup. Band is [speedup(m_p90), speedup(m_p10)].
        s_med = speedup(a, b, w, n, med)
        s_from_hi_m = speedup(a, b, w, n, hi)
        s_from_lo_m = speedup(a, b, w, n, lo)
        rows.append(
            {
                "k": k,
                "m_median": med,
                "m_p10": lo,
                "m_p90": hi,
                "speedup_median": s_med,
                "speedup_lo": min(s_from_hi_m, s_from_lo_m),
                "speedup_hi": max(s_from_hi_m, s_from_lo_m),
            }
        )
    return rows


def cumulative_for_mode(
    params: dict, n: float, ks: list[int], m_med: list[float], m_lo: list[float], m_hi: list[float]
) -> list[dict]:
    """Genome 1 is all misses. Genome *i*+1 uses *m(i)*."""
    a, b, w = params["a"], params["b"], params["w"]
    t_stock = stock_wall(a, b, n)
    k_to_m = {k: (med, lo, hi) for k, med, lo, hi in zip(ks, m_med, m_lo, m_hi)}
    n_genomes = max(ks) + 1
    rows = []
    cum_s = cum_c = cum_c_lo = cum_c_hi = 0.0
    for i in range(1, n_genomes + 1):
        if i == 1:
            c_med = c_lo = c_hi = t_stock
            m_used = None
        else:
            med, lo, hi = k_to_m[i - 1]
            c_med = cached_wall(a, b, w, n, med)
            c_lo = cached_wall(a, b, w, n, lo)
            c_hi = cached_wall(a, b, w, n, hi)
            m_used = med
        cum_s += t_stock
        cum_c += c_med
        cum_c_lo += c_lo
        cum_c_hi += c_hi
        rows.append(
            {
                "genome": i,
                "m_used": m_used,
                "stock_wall_s": t_stock,
                "cached_wall_s": c_med,
                "cached_wall_s_lo": min(c_lo, c_hi),
                "cached_wall_s_hi": max(c_lo, c_hi),
                "cum_stock_s": cum_s,
                "cum_cached_s": cum_c,
                "cum_cached_s_lo": min(cum_c_lo, cum_c_hi),
                "cum_cached_s_hi": max(cum_c_lo, cum_c_hi),
                "speedup_this_genome": t_stock / c_med,
                "cum_speedup": cum_s / cum_c,
            }
        )
    return rows


def snapshot(rows: list[dict], k: int) -> dict:
    for row in rows:
        if row["k"] == k:
            return {
                "k": k,
                "m_median": row["m_median"],
                "speedup_median": row["speedup_median"],
                "speedup_lo": row["speedup_lo"],
                "speedup_hi": row["speedup_hi"],
            }
    raise KeyError(k)


def hours(seconds: float) -> float:
    return seconds / 3600.0


def ceil_hours(seconds: float, pad: float = 1.5, extra_h: float = 1.0) -> int:
    """Exclusive-node --time request: 1.5× model wall + 1 h setup, snapped up."""
    raw = hours(seconds) * pad + extra_h
    for snap in (1, 2, 3, 4, 6, 8, 10, 12, 16, 18, 24, 36, 48):
        if raw <= snap:
            return snap
    return int(np.ceil(raw))


def write_figure(payload: dict, dest: Path) -> None:
    collections = ["A", "B", "C"]
    titles = {
        "A": "A · diverse E. coli",
        "B": "B · O157:H7",
        "C": "C · S. aureus",
    }
    modes = (
        ("hmmscan", SCAN),
        ("hmmsearch", SEARCH),
    )
    fig, axes = plt.subplots(2, 3, figsize=(11.4, 6.4), sharex=False, sharey=False)
    for row, (mode, color) in enumerate(modes):
        for col, cid in enumerate(collections):
            ax = axes[row][col]
            rows = payload["collections"][cid]["modes"][mode]["per_k"]
            xs = [r["k"] for r in rows]
            ys = [r["speedup_median"] for r in rows]
            lo = [r["speedup_lo"] for r in rows]
            hi = [r["speedup_hi"] for r in rows]
            ax.fill_between(xs, lo, hi, color=color, alpha=0.20, linewidth=0, label="10–90% m(k)")
            ax.plot(xs, ys, color=color, lw=1.8, label="median")
            ax.axhline(3.0, color=STOCK, ls="--", lw=1.1, label="3×")
            ax.set_xlim(1, xs[-1])
            ax.set_ylim(bottom=0)
            if row == 0:
                ax.set_title(titles[cid])
            if row == 1:
                ax.set_xlabel("k (genomes already seen)")
            if col == 0:
                ax.set_ylabel(f"{mode} speedup")
            if col == 2:
                ax.legend(fontsize=8, loc="upper left")
    fig.suptitle(
        "Predicted HMMER speedup vs recurrence  ·  N = 4,192 from the K-12 screen",
        fontsize=12,
    )
    fig.tight_layout()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest)
    plt.close(fig)


def main() -> int:
    screen = load_json("headline_screen.json")
    curves = load_json("recurrence_curves.json")
    n = float(screen["N"])
    params = mode_params(screen)

    collections = {}
    for cid, raw in curves["collections"].items():
        ks = list(raw["k"])
        m_med = list(raw["m_median"])
        m_lo = list(raw["m_p10"])
        m_hi = list(raw["m_p90"])
        modes = {}
        for name, p in params.items():
            per_k = series_for_mode(p, n, ks, m_med, m_lo, m_hi)
            cum = cumulative_for_mode(p, n, ks, m_med, m_lo, m_hi)
            last = cum[-1]
            modes[name] = {
                "a": p["a"],
                "b": p["b"],
                "w": p["w"],
                "stock_per_genome_s": stock_wall(p["a"], p["b"], n),
                "per_k": per_k,
                "cumulative": cum,
                "cum_stock_s": last["cum_stock_s"],
                "cum_cached_s": last["cum_cached_s"],
                "cum_speedup": last["cum_speedup"],
            }
        want_k = {"A": [10, 30], "B": [10, 39], "C": [10, 30]}.get(cid, [10])
        snapshots = {}
        for name in params:
            snapshots[name] = [snapshot(modes[name]["per_k"], k) for k in want_k if k in ks]
        collections[cid] = {
            "id": raw["id"],
            "K": raw["K"],
            "n_orderings": raw["n_orderings"],
            "modes": modes,
            "snapshots": snapshots,
        }

    # Budget for the pre-registered savings workloads (A first 30, B full 40).
    budget = {}
    stock_idx = {"A": [1, 2, 5, 10, 20, 30], "B": [1, 2, 5, 10, 20, 40]}
    workload_k = {"A": 30, "B": 40}
    for cid, n_keep in workload_k.items():
        per_mode = {}
        for name, block in collections[cid]["modes"].items():
            cum = [row for row in block["cumulative"] if row["genome"] <= n_keep]
            last = cum[-1]
            stock_sample_s = sum(
                row["stock_wall_s"] for row in cum if row["genome"] in stock_idx[cid]
            )
            per_mode[name] = {
                "n_genomes": n_keep,
                "cached_wall_s": last["cum_cached_s"],
                "cached_wall_h": hours(last["cum_cached_s"]),
                "stock_full_s": last["cum_stock_s"],
                "stock_full_h": hours(last["cum_stock_s"]),
                "stock_sampled_s": stock_sample_s,
                "stock_sampled_h": hours(stock_sample_s),
                "cum_speedup": last["cum_speedup"],
                "cached_time_request_h": ceil_hours(last["cum_cached_s"]),
                "stock_time_request_h": ceil_hours(stock_sample_s),
            }
        budget[cid] = per_mode

    requested_h = 0
    for cid in budget:
        for name in budget[cid]:
            requested_h += budget[cid][name]["cached_time_request_h"]
            requested_h += budget[cid][name]["stock_time_request_h"]

    payload = {
        "protocol": "pipeline/docs/RECURRENCE_PROTOCOL.md",
        "screen": "results/headline_screen.json",
        "curves": "results/recurrence_curves.json",
        "formula": "(a + b*N) / (a + b*m(k)*N + w)",
        "N": n,
        "m_gate_note": (
            "Screen m = 0.0019 is K-12 (best case). These curves use "
            "median m(k) and the 10–90% band over 20 orderings. "
            "N is locked to the screen proteome (4,192), not per-genome N_i."
        ),
        "pfam_scan": {
            "runs_hmmscan": True,
            "default_cut_ga": True,
            "source": "https://ftp.ebi.ac.uk/pub/databases/Pfam/Tools/PfamScan.tar.gz",
            "retrieved": "2026-09-27",
            "last_modified": "2017-03-01",
            "bytes": 28568,
            "files": {
                "hmmscan_binary": "PfamScan/Bio/Pfam/Scan/PfamScan.pm:78 ($self->{_HMMSCAN} = 'hmmscan')",
                "hmmscan_argv": "PfamScan.pm:138,145 (argv starts with 'hmmscan')",
                "cut_ga_default": "PfamScan.pm:428-429 (unless -e_seq/-e_dom/-b_seq/-b_dom)",
            },
            "finding": (
                "Official EBI PfamScan (pfam_scan.pl / PfamScan.pm) runs "
                "hmmscan, and pushes --cut_ga when the user does not set "
                "an E-value or bit-score cutoff."
            ),
        },
        "modes": {name: {"a": p["a"], "b": p["b"], "w": p["w"]} for name, p in params.items()},
        "collections": collections,
        "savings_budget": {
            "allocation": "biyik_1165",
            "node": "exclusive main, --cpus-per-task=32",
            "workloads": budget,
            "total_requested_node_hours": requested_h,
            "note": (
                "--time is 1.5× predicted exclusive-node wall + 1 h setup, "
                "snapped up. Four cached jobs + four stock jobs. "
                "Needs Josh approval before submit."
            ),
        },
        "figure": "results/figures/15_hmmer_predicted_speedup.png",
    }

    dest_json = RES / "hmmer_predicted_speedup.json"
    dest_json.write_text(json.dumps(payload, indent=2) + "\n")
    write_figure(payload, FIG / "15_hmmer_predicted_speedup.png")
    print(f"wrote {dest_json}")
    print(f"wrote {FIG / '15_hmmer_predicted_speedup.png'}")
    print(f"requested node-hours: {requested_h}")
    for cid in ("A", "B"):
        for mode in ("hmmscan", "hmmsearch"):
            snaps = collections[cid]["snapshots"][mode]
            bits = ", ".join(f"k={s['k']} → {s['speedup_median']:.2f}×" for s in snaps)
            print(f"  {cid} {mode}: {bits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
