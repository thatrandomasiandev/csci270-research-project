#!/usr/bin/env python3
"""Score headline timing results. Reads result JSON only.

Locked with the measured-run pre-registration. CV above 5% is a flag.
It is not a reason to drop a genome or to call the genome FAIL.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

F_DELTA = 4052 / 30134
# Arithmetic means over the three paired B runs of job 13138266.
# a_i = discovery_s / (f * paired stock wall)
# c_i = (TARE wall - discovery_s) / paired stock wall
A_COEF = 1.0146410126797523
C_COEF = 0.10846594102974193
S_PRED = 1.0 / (A_COEF * F_DELTA + C_COEF)
BOOT_SEED = 20261047
BOOT_N = 10_000
CV_FLAG = 0.05
R = 3


def _arm_rows(payload: dict, arm: str) -> list[dict]:
    return [row for row in payload.get("repeats") or [] if row.get("arm") == arm]


def _walls(rows: list[dict]) -> list[float]:
    return [float(row["wall_s"]) for row in rows]


def _cpus(rows: list[dict]) -> list[float] | None:
    if not rows or any("cpu_s" not in row for row in rows):
        return None
    return [float(row["cpu_s"]) for row in rows]


def coefficient_of_variation(values: list[float]) -> float:
    if len(values) < 2:
        return float("inf")
    mean = statistics.fmean(values)
    if mean <= 0:
        return float("inf")
    return statistics.stdev(values) / mean


def empirical_quantile(ordered: list[float], probability: float) -> float:
    """Smallest order statistic whose 1-based rank / n is at least probability."""
    n = len(ordered)
    if n == 0:
        raise ValueError("empty sample")
    index = math.ceil(probability * n) - 1
    index = min(max(index, 0), n - 1)
    return ordered[index]


def bootstrap_median_ci(
    values: list[float],
    *,
    seed: int = BOOT_SEED,
    resamples: int = BOOT_N,
) -> dict:
    if not values:
        raise ValueError("no speedups")
    rng = random.Random(seed)
    n = len(values)
    medians = [
        statistics.median([values[rng.randrange(n)] for _ in range(n)])
        for _ in range(resamples)
    ]
    ordered = sorted(medians)
    return {
        "seed": seed,
        "resamples": resamples,
        "quantile": "empirical cdf, ceil(p*n)-1",
        "low": empirical_quantile(ordered, 0.025),
        "high": empirical_quantile(ordered, 0.975),
    }


def score_genome(payload: dict) -> dict:
    """One genome. FAIL is reported. CV and phase shape are flags only."""
    reasons: list[str] = []
    stock = _arm_rows(payload, "A")
    tare = _arm_rows(payload, "B")
    if len(stock) != R or len(tare) != R:
        reasons.append(f"expected {R} runs per arm, found A={len(stock)} B={len(tare)}")
    for row in tare:
        compared = row.get("compare") or {}
        if row.get("decision") != "SHIP" or not compared.get("byte_equal"):
            reasons.append(
                f"B{row.get('repeat')} is not byte-identical ({row.get('decision')})"
            )
    if not payload.get("stock_vs_stock_byte_equal"):
        reasons.append("stock 38.2 repeats are not byte-identical")
    unpinned = payload.get("unpinned") or {}
    if not unpinned.get("differs"):
        reasons.append("unpinned control does not differ")
    walls_a = _walls(stock)
    walls_b = _walls(tare)
    cv_a = coefficient_of_variation(walls_a) if len(walls_a) >= 2 else None
    cv_b = coefficient_of_variation(walls_b) if len(walls_b) >= 2 else None
    flags: list[str] = []
    if cv_a is not None and cv_a > CV_FLAG:
        flags.append(f"CV A {cv_a:.4f}")
    if cv_b is not None and cv_b > CV_FLAG:
        flags.append(f"CV B {cv_b:.4f}")
    for row in tare:
        if row.get("shape_ok") is False:
            flags.append(f"B{row.get('repeat')} phase shape: {row.get('shape_why')}")
    median_a = statistics.median(walls_a) if walls_a else None
    median_b = statistics.median(walls_b) if walls_b else None
    speedup = None
    if median_a and median_b:
        speedup = median_a / median_b
    cpu_a = _cpus(stock)
    cpu_b = _cpus(tare)
    cpu_ratio = None
    if cpu_a and cpu_b:
        med_cpu_a = statistics.median(cpu_a)
        med_cpu_b = statistics.median(cpu_b)
        if med_cpu_b:
            cpu_ratio = med_cpu_a / med_cpu_b
    fill = (payload.get("fill") or {}).get("wall_s")
    stock_old = (payload.get("stock_38_1") or {}).get("wall_s")
    overhead = None
    if fill and stock_old:
        overhead = float(fill) / float(stock_old)
    break_even = None
    if fill is not None and median_a and median_b and median_a > median_b:
        break_even = (float(fill) - median_a) / (median_a - median_b)
    prediction_error = None
    if speedup:
        prediction_error = abs(S_PRED - speedup) / speedup
    completed = len(stock) == R and len(tare) == R and median_a is not None
    return {
        "proteome": payload.get("proteome"),
        "task": payload.get("task"),
        "job_id": payload.get("job_id"),
        "outcome": "FAIL" if reasons or not completed else "EXACT",
        "fail_reasons": reasons,
        "flags": flags,
        "completed": completed and not payload.get("stopped"),
        "stopped": payload.get("stopped"),
        "stock_median_s": median_a,
        "tare_median_s": median_b,
        "stock_walls_s": walls_a,
        "tare_walls_s": walls_b,
        "S_g": speedup,
        "cv_A": cv_a,
        "cv_B": cv_b,
        "cv_flag_A": bool(cv_a is not None and cv_a > CV_FLAG),
        "cv_flag_B": bool(cv_b is not None and cv_b > CV_FLAG),
        "cpu_ratio": cpu_ratio,
        "cpu_A_median_s": statistics.median(cpu_a) if cpu_a else None,
        "cpu_B_median_s": statistics.median(cpu_b) if cpu_b else None,
        "first_run_overhead": overhead,
        "break_even_n": break_even,
        "S_pred": S_PRED,
        "prediction_error": prediction_error,
        "shape_ok": all(row.get("shape_ok") for row in tare) if tare else False,
    }


def summarize(records: list[dict]) -> dict:
    usable = [row for row in records if row.get("S_g") is not None and not row.get("stopped")]
    speedups = [float(row["S_g"]) for row in usable]
    out: dict = {
        "n_files": len(records),
        "n_speedups": len(speedups),
        "dropped": 0,
        "a": A_COEF,
        "c": C_COEF,
        "f": F_DELTA,
        "S_pred": S_PRED,
        "genomes": records,
    }
    if not speedups:
        out["headline_median"] = None
        return out
    out["headline_median"] = statistics.median(speedups)
    out["geometric_mean"] = statistics.geometric_mean(speedups)
    out["range"] = [min(speedups), max(speedups)]
    out["bootstrap_ci95"] = bootstrap_median_ci(speedups)
    errors = [row["prediction_error"] for row in usable if row.get("prediction_error") is not None]
    out["max_prediction_error"] = max(errors) if errors else None
    overheads = [row["first_run_overhead"] for row in usable if row.get("first_run_overhead") is not None]
    evens = [row["break_even_n"] for row in usable if row.get("break_even_n") is not None]
    out["first_run_overhead_median"] = statistics.median(overheads) if overheads else None
    out["break_even_n_median"] = statistics.median(evens) if evens else None
    out["any_fail"] = any(row["outcome"] == "FAIL" for row in records)
    out["any_cv_flag"] = any(row["cv_flag_A"] or row["cv_flag_B"] for row in records)
    return out


def load_records(paths: list[Path]) -> list[dict]:
    records = []
    for path in paths:
        payload = json.loads(path.read_text())
        row = score_genome(payload)
        row["path"] = str(path)
        records.append(row)
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score headline result JSON files.")
    parser.add_argument("json", nargs="+", type=Path)
    parser.add_argument("--pilot-check", action="store_true")
    args = parser.parse_args(argv)
    records = load_records(args.json)
    summary = summarize(records)
    if args.pilot_check:
        if len(records) != 1:
            print("pilot check expects one JSON", file=sys.stderr)
            return 2
        row = records[0]
        if row["outcome"] != "EXACT":
            print(f"pilot rescore is {row['outcome']}: {row['fail_reasons']}", file=sys.stderr)
            return 1
        if not row["cv_flag_B"] or row["cv_flag_A"]:
            print(f"pilot CV flags A={row['cv_flag_A']} B={row['cv_flag_B']}", file=sys.stderr)
            return 1
        if row["S_g"] is None or abs(row["S_g"] - (2053.695990220178 / 501.117714765016)) > 1e-9:
            print(f"pilot S_g {row['S_g']}", file=sys.stderr)
            return 1
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
