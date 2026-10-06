#!/usr/bin/env python3
"""Verdict for the timed 38.1 → 38.2 re-annotation.

Reads result JSON only. The constants below are the pre-registered
predictions. They are not fitted from the result file. CONFIRMED means
the unweighted mean of per-genome speedups, probe excluded, is within
±25% of the unweighted mean of the primary predictions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Locked with the 2026-10-06 timed-reannotation addendum.
# a, b: results/headline_screen.json. c_count: 4052/30134 from R1.
A_S = 31.959641573764316
B_S = 0.7228553909794854
C_COUNT_NUM = 4052
C_COUNT_DEN = 30134
C_COUNT = C_COUNT_NUM / C_COUNT_DEN
TOLERANCE = 0.25
PRIMARY_AT_4192 = (A_S + B_S * 4192) / (A_S + C_COUNT * B_S * 4192)
# Model files only, results/reference_reannot_churn.json, before any timed arm.
# c_length = 600557 / 4754065.
C_LENGTH = 600557 / 4754065
LENGTH_NEW = 4754065
LENGTH_CHANGED_AND_NEW = 600557
GENOMES = (
    {"position": 1, "index": 9, "accession": "GCF_002853805.1", "n_proteins": 5117},
    {"position": 2, "index": 5, "accession": "GCF_002090355.1", "n_proteins": 4091},
    {"position": 3, "index": 2, "accession": "GCF_001650275.1", "n_proteins": 5176},
    {"position": 4, "index": 75, "accession": "GCF_052050745.1", "n_proteins": 4197},
    {"position": 5, "index": 29, "accession": "GCF_016659085.1", "n_proteins": 4191},
)


def primary(n: float, c: float = C_COUNT) -> float:
    return (A_S + B_S * n) / (A_S + c * B_S * n)


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("empty")
    return sum(values) / len(values)


def amdahl(run: dict) -> dict:
    """Measured split of one arm-(ii) wall. a is the headline intercept."""
    phases = run.get("phases") or {}
    prep = float(phases.get("prep_s") or 0.0)
    tool = float(phases.get("tool_s") or 0.0)
    merge = float(phases.get("merge_rescale_s") or 0.0) + float(phases.get("render_s") or 0.0)
    wall = float(run["wall_s"])
    return {
        "w_s": wall - prep - tool - merge,
        "a_s": A_S,
        "a_note": "headline intercept, assumed not to shrink on the sub-reference",
        "tool_s": tool,
        "b_n_changed_s": tool - A_S,
        "prep_s": prep,
        "merge_s": merge,
    }


def _walls(runs: list[dict], accession: str, arm: str) -> list[float]:
    return [
        float(row["wall_s"])
        for row in runs
        if row.get("timed") and row.get("accession") == accession and row.get("arm") == arm
    ]


def _prediction_mismatch(payload: dict) -> str:
    recorded = payload.get("predictions")
    if not recorded:
        return ""
    if "c_count" in recorded and abs(float(recorded["c_count"]) - C_COUNT) > 1e-12:
        return "recorded c_count does not match the locked count fraction"
    if "c_length" in recorded and abs(float(recorded["c_length"]) - C_LENGTH) > 1e-12:
        return "recorded c_length does not match the locked length fraction"
    locked = {genome["accession"]: genome["n_proteins"] for genome in GENOMES}
    for genome in recorded.get("genomes") or []:
        accession = genome.get("accession")
        if accession in locked and int(genome["n_proteins"]) != locked[accession]:
            return f"recorded protein count for {accession} does not match the lock"
    return ""


def judge(payload: dict) -> dict:
    mismatch = _prediction_mismatch(payload)
    if mismatch:
        return {
            "verdict": "PROTOCOL_MISMATCH",
            "speedup": None,
            "why": mismatch,
            "no_speedup": True,
        }
    stop = payload.get("stop")
    if stop and stop.get("kind") == "STOP_MATCH":
        return {
            "verdict": "STOP_MATCH",
            "speedup": None,
            "why": stop.get("why") or "ref-merge mismatch",
            "no_speedup": True,
        }
    if stop:
        return {
            "verdict": stop.get("kind") or "STOP",
            "speedup": None,
            "why": stop.get("why") or "",
            "no_speedup": True,
        }
    runs = list(payload.get("runs") or [])
    per_genome = []
    for genome in GENOMES:
        stock = _walls(runs, genome["accession"], "stock")
        acts = _walls(runs, genome["accession"], "acts")
        if len(stock) < 3 or len(acts) < 3:
            return {
                "verdict": "INCOMPLETE",
                "speedup": None,
                "why": f"{genome['accession']} has stock={len(stock)} acts={len(acts)}",
                "no_speedup": True,
            }
        measured = mean(stock) / mean(acts)
        predicted = primary(genome["n_proteins"])
        per_genome.append(
            {
                "accession": genome["accession"],
                "n_proteins": genome["n_proteins"],
                "mean_stock_s": mean(stock),
                "mean_acts_s": mean(acts),
                "measured_speedup": measured,
                "primary_speedup": predicted,
                "secondary_speedup": (
                    primary(genome["n_proteins"], C_LENGTH) if C_LENGTH is not None else None
                ),
            }
        )
    measured_mean = mean([row["measured_speedup"] for row in per_genome])
    primary_mean = mean([row["primary_speedup"] for row in per_genome])
    relative = abs(measured_mean - primary_mean) / primary_mean
    confirmed = relative <= TOLERANCE
    probe = float((payload.get("setup") or {}).get("probe_wall_s") or 0.0)
    mean_stock = mean([row["mean_stock_s"] for row in per_genome])
    mean_acts = mean([row["mean_acts_s"] for row in per_genome])
    acts_runs = [
        row for row in runs if row.get("timed") and row.get("arm") == "acts"
    ]
    splits = [amdahl(row) for row in acts_runs]
    def avg(key: str) -> float:
        return mean([row[key] for row in splits]) if splits else 0.0

    return {
        "verdict": "CONFIRMED" if confirmed else "REFUTED",
        "no_speedup": False,
        "measured_mean_speedup": measured_mean,
        "primary_mean_speedup": primary_mean,
        "primary_at_n_4192": PRIMARY_AT_4192,
        "relative_error": relative,
        "tolerance": TOLERANCE,
        "c_count": C_COUNT,
        "c_length": C_LENGTH,
        "secondary_mean_speedup": (
            mean([row["secondary_speedup"] for row in per_genome]) if C_LENGTH is not None else None
        ),
        "probe_wall_s": probe,
        "speedup_with_P_over_1": mean_stock / (mean_acts + probe) if probe else None,
        "speedup_with_P_over_5": (5 * mean_stock) / (5 * mean_acts + probe) if probe else None,
        "amdahl_mean": {
            "w_s": avg("w_s"),
            "a_s": A_S,
            "b_n_changed_s": avg("b_n_changed_s"),
            "prep_s": avg("prep_s"),
            "merge_s": avg("merge_s"),
            "tool_s": avg("tool_s"),
        },
        "per_genome": per_genome,
        "why": (
            f"mean measured {measured_mean:.4f}× vs primary mean {primary_mean:.4f}× "
            f"(relative {relative:.3f}, tolerance {TOLERANCE})"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.result.read_text())
    report = judge(payload)
    print(json.dumps(report, indent=2))
    print(f"verdict: {report['verdict']}")
    if report.get("no_speedup"):
        print("no speedup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
