#!/usr/bin/env python3
"""Locked confirmatory speedup formulas (docs/CONFIRM_PROTOCOL.md).

Imports scripts/predict_hmmer_speedup.py and
scripts/predict_hmmer_probe_cost.py. Does not edit them. Does not refit
a, b, w. hmmscan is PRIMARY; hmmsearch is secondary / not scored.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import predict_hmmer_probe_cost as probe  # noqa: E402
import predict_hmmer_speedup as pred  # noqa: E402
from confirm_select import N_GENOMES, PRIMARY_MODE, STOCK_POS  # noqa: E402

PROTOCOL = "pipeline/docs/CONFIRM_PROTOCOL.md"
REL_TOL = 0.20
CACHED_FRAC_MAX = 0.50
PROBE_ACCOUNT = "singleton_8"
PROBE_N = 8
SCREEN_N = 4192.0


def locked_params(screen: dict) -> dict[str, dict]:
    return pred.mode_params(screen)


def singleton_8_sizes() -> list[int]:
    return probe.batch_sizes_singleton(PROBE_N)


def probe_cost_P(a: float, b: float) -> dict:
    rec = probe.probe_cost(a, b, singleton_8_sizes())
    rec["subset_mode"] = "singleton"
    rec["probe_n"] = PROBE_N
    rec["account"] = PROBE_ACCOUNT
    return rec


def series_from_m(
    a: float,
    b: float,
    w: float,
    n_list: list[float],
    m_along: list[float],
) -> tuple[list[dict], list[dict]]:
    """Per-genome stock/cached and cumulative rows along one locked order.

    m_along[k-1] is the miss of genome k+1. Genome 1 is all misses.
    """
    k_genomes = len(n_list)
    if len(m_along) != k_genomes - 1:
        raise ValueError("m_along must have K-1 entries")
    per: list[dict] = []
    cum: list[dict] = []
    cum_s = cum_c = 0.0
    for i, n_i in enumerate(n_list, start=1):
        stock = pred.stock_wall(a, b, n_i)
        if i == 1:
            cached = stock
            m_used = None
        else:
            m_used = m_along[i - 2]
            cached = pred.cached_wall(a, b, w, n_i, m_used)
        cum_s += stock
        cum_c += cached
        per.append(
            {
                "k": i - 1 if i > 1 else None,
                "genome": i,
                "N_i": n_i,
                "m_used": m_used,
                "stock_wall_s": stock,
                "cached_wall_s": cached,
                "speedup_this_genome": stock / cached if cached else None,
            }
        )
        cum.append(
            {
                "genome": i,
                "m_used": m_used,
                "stock_wall_s": stock,
                "cached_wall_s": cached,
                "cum_stock_s": cum_s,
                "cum_cached_s": cum_c,
                "cum_cached_s_lo": cum_c,
                "cum_cached_s_hi": cum_c,
                "cum_speedup": cum_s / cum_c if cum_c else None,
            }
        )
    return per, cum


def with_probe(cum: list[dict], P: float) -> list[dict]:
    return probe.add_probe(cum, P)


def snapshot_cum(rows: list[dict], genomes: tuple[int, ...] = (1, 10, 30)) -> list[dict]:
    by_g = {row["genome"]: row for row in rows}
    out = []
    for g in genomes:
        if g not in by_g:
            continue
        row = by_g[g]
        out.append(
            {
                "genome": g,
                "m_used": row.get("m_used"),
                "cum_stock_s": row["cum_stock_s"],
                "cum_cached_s": row["cum_cached_s"],
                "cum_speedup": row["cum_speedup"],
            }
        )
    return out


def stock_sample_s(cum: list[dict], positions: tuple[int, ...] = STOCK_POS) -> float:
    want = set(positions)
    return sum(row["stock_wall_s"] for row in cum if row["genome"] in want)


def arm_prediction(
    *,
    mode: str,
    params: dict,
    n_list: list[float],
    m_along: list[float],
) -> dict:
    a, b, w = params["a"], params["b"], params["w"]
    per, cum0 = series_from_m(a, b, w, n_list, m_along)
    p_rec = probe_cost_P(a, b)
    cum_p = with_probe(cum0, p_rec["P_s"])
    last0 = cum0[-1]
    last_p = cum_p[-1]
    scored = mode == PRIMARY_MODE
    return {
        "mode": mode,
        "primary": scored,
        "scored": scored,
        "label": "PRIMARY" if scored else "secondary / not scored",
        "a": a,
        "b": b,
        "w": w,
        "P": p_rec,
        "per_genome": per,
        "cumulative": cum0,
        "cumulative_with_P": cum_p,
        "snapshots_m": [
            {"k": i, "m": m_along[i - 1]}
            for i in (1, 10, 29)
            if 1 <= i <= len(m_along)
        ],
        "snapshots_cum": snapshot_cum(cum0),
        "snapshots_cum_with_P": snapshot_cum(cum_p),
        "n_genomes": len(n_list),
        "cum_stock_s": last0["cum_stock_s"],
        "cum_cached_s": last0["cum_cached_s"],
        "cum_speedup": last0["cum_speedup"],
        "cum_cached_with_P_s": last_p["cum_cached_s"],
        "cum_speedup_with_P": last_p["cum_speedup"],
        "stock_sampled_s": stock_sample_s(cum0),
        "cached_frac_at_k30": (
            last0["cum_cached_s"] / last0["cum_stock_s"] if last0["cum_stock_s"] else None
        ),
        "time_request_h": pred.ceil_hours(last0["cum_cached_s"] + stock_sample_s(cum0)),
        "predicted_cached_h": pred.hours(last0["cum_cached_s"]),
        "predicted_stock_sample_h": pred.hours(stock_sample_s(cum0)),
        "predicted_combined_h": pred.hours(last0["cum_cached_s"] + stock_sample_s(cum0)),
    }


def within_band(measured: float, predicted: float, rel_tol: float = REL_TOL) -> bool:
    if predicted == 0:
        return False
    return abs(measured / predicted - 1.0) <= rel_tol


def confirmation_verdict(
    *,
    measured_speedup_with_P: float,
    predicted_speedup_with_P: float,
    cached_frac: float,
    rel_tol: float = REL_TOL,
    cached_frac_max: float = CACHED_FRAC_MAX,
) -> dict:
    """Criteria locked in CONFIRM_PROTOCOL.md, before seeing numbers."""
    band_ok = within_band(measured_speedup_with_P, predicted_speedup_with_P, rel_tol)
    frac_ok = cached_frac < cached_frac_max
    return {
        "criterion_1": (
            "cumulative measured speedup (with P) within ±20% of predicted"
        ),
        "criterion_1_holds": band_ok,
        "meas": measured_speedup_with_P,
        "pred": predicted_speedup_with_P,
        "rel_err": abs(measured_speedup_with_P / predicted_speedup_with_P - 1.0)
        if predicted_speedup_with_P
        else None,
        "rel_tol": rel_tol,
        "criterion_2": "cached below 50% of stock by k = 30",
        "criterion_2_holds": frac_ok,
        "cached_frac": cached_frac,
        "cached_frac_max": cached_frac_max,
        "confirmed": band_ok and frac_ok,
    }


def criteria_verbatim() -> list[str]:
    return [
        "Cumulative measured speedup (with P) is within ±20% of predicted: "
        "|meas / pred − 1| ≤ 0.20.",
        "Cached below 50% of stock by k = 30: cached_frac < 0.50.",
    ]
