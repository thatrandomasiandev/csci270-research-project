#!/usr/bin/env python3
"""Part A: fit t = a + b*n on nested HG00099 subsets. No cached-path comparison."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from oracle_snpeff_ann import run_snpeff
from acts.vcf import body_lines, is_header, read_maybe_gz, variant_key

S99 = ROOT / "data" / "vep_chr22" / "HG00099.c1.vcf.gz"
S96 = ROOT / "data" / "vep_chr22" / "HG00096.c1.vcf.gz"
S97 = ROOT / "data" / "vep_chr22" / "HG00097.c1.vcf.gz"
SUB = ROOT / "data" / "vep_chr22" / "subsets"
OUT = ROOT / "results" / "snpeff_timing_fit.json"
SIZES = (1, 1000, 5000, 20000, None)  # None = full
RUNS = 3


def vcf_parts(path: Path) -> tuple[list[str], list[str]]:
    text = read_maybe_gz(path)
    header = [ln for ln in text.splitlines() if is_header(ln)]
    return header, body_lines(text)


def write_subset(header: list[str], body: list[str], n: int, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    take = body[:n]
    dest.write_text("\n".join(header + take) + "\n")
    return len(take)


def keys(path: Path) -> set[str]:
    return {variant_key(ln) for ln in body_lines(read_maybe_gz(path))}


def fit_ab(ns: list[int], ts: list[float]) -> tuple[float, float]:
    n_bar = statistics.fmean(ns)
    t_bar = statistics.fmean(ts)
    var_n = sum((n - n_bar) ** 2 for n in ns)
    if var_n == 0:
        return t_bar, 0.0
    cov = sum((n - n_bar) * (t - t_bar) for n, t in zip(ns, ts))
    b = cov / var_n
    a = t_bar - b * n_bar
    return a, b


def measure_wrapper_w(header: list[str], body: list[str], prev: set[str], tmp: Path) -> dict:
    """Split/lookup/reassemble with `cat` instead of SnpEff, same HG00099 input."""
    tmp.mkdir(parents=True, exist_ok=True)
    times = []
    for i in range(RUNS):
        t0 = time.perf_counter()
        misses = [ln for ln in body if variant_key(ln) not in prev]
        miss_vcf = tmp / f"miss_cat_{i}.vcf"
        miss_vcf.write_text("\n".join(header + misses) + "\n")
        cat_out = tmp / f"miss_cat_{i}.out"
        cat_out.write_text(miss_vcf.read_text())
        rebuilt = []
        miss_i = 0
        cat_body = body_lines(cat_out.read_text())
        for ln in body:
            if variant_key(ln) in prev:
                rebuilt.append(ln)
            else:
                rebuilt.append(cat_body[miss_i])
                miss_i += 1
        (tmp / f"reassembled_cat_{i}.vcf").write_text("\n".join(header + rebuilt) + "\n")
        times.append(time.perf_counter() - t0)
    return {
        "n_miss": len([ln for ln in body if variant_key(ln) not in prev]),
        "runs_s": times,
        "mean_s": statistics.fmean(times),
    }


def main() -> int:
    if not S99.is_file():
        print("INCOMPLETE: missing HG00099 -c1", file=sys.stderr)
        return 2
    header, body = vcf_parts(S99)
    n_full = len(body)
    prev = keys(S96) | keys(S97)
    miss_n = sum(1 for ln in body if variant_key(ln) not in prev)

    raw = []
    means = []
    for size in SIZES:
        n = n_full if size is None else size
        dest = SUB / f"HG00099.n{n}.vcf"
        wrote = write_subset(header, body, n, dest)
        runs = []
        load_logged = []
        for i in range(RUNS):
            _out, err, wall = run_snpeff(dest)
            runs.append(wall)
            load_logged.append(err.strip() if err.strip() else None)
            print(f"n={wrote} run={i+1} wall_s={wall:.4f}", flush=True)
        raw.append(
            {
                "n": wrote,
                "runs_s": runs,
                "mean_s": statistics.fmean(runs),
                "stdev_s": statistics.stdev(runs) if len(runs) > 1 else 0.0,
                "snpeff_stderr": load_logged,
            }
        )
        means.append((wrote, statistics.fmean(runs)))

    a, b = fit_ab([n for n, _ in means], [t for _, t in means])
    w = measure_wrapper_w(header, body, prev, SUB / "wrapper")
    pred_full = a + b * n_full
    pred_cached = a + b * miss_n + w["mean_s"]
    pred_x = pred_full / pred_cached if pred_cached else None

    payload = {
        "tool": "SnpEff 5.4c GRCh38.86",
        "flags": ["-noStats", "-noLog"],
        "sample": "HG00099",
        "extract": "chr22 joint_called_c1",
        "n_full": n_full,
        "miss_n": miss_n,
        "miss_frac": miss_n / n_full if n_full else None,
        "prev": "HG00096∪HG00097",
        "runs_per_size": RUNS,
        "raw": raw,
        "fit": {
            "model": "t = a + b*n",
            "a_s": a,
            "b_s_per_record": b,
            "note": "OLS on per-size mean wall times",
        },
        "wrapper_cat": w,
        "prediction": {
            "t_stock_s": pred_full,
            "t_cached_s": pred_cached,
            "speedup": pred_x,
            "formula": "(a + b*N) / (a + b*miss_n + w)",
            "amdahl_note": "if a dominates, measured ~1x means startup, not fake overlap",
        },
        "jvm_or_db_load_s": None,
        "jvm_or_db_load_note": "-noLog: SnpEff did not print load time",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
