#!/usr/bin/env python3
"""Compare baseline vs optimized timing CSVs; print speedup."""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from statistics import mean, stdev


def load_times(path: Path) -> list[float]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    return [float(r["wall_sec"]) for r in rows]


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "results"
    base = root / "baseline_timings.csv"
    opt = root / "optimized_timings.csv"
    if len(sys.argv) >= 3:
        base, opt = Path(sys.argv[1]), Path(sys.argv[2])
    if not base.exists() or not opt.exists():
        print(f"Missing CSVs.\n  baseline: {base}\n  optimized: {opt}", file=sys.stderr)
        sys.exit(1)
    bt, ot = load_times(base), load_times(opt)
    bm, om = mean(bt), mean(ot)
    speedup = bm / om if om > 0 else float("inf")
    print(f"baseline  n={len(bt)} mean={bm:.3f}s std={stdev(bt) if len(bt)>1 else 0:.3f}")
    print(f"optimized n={len(ot)} mean={om:.3f}s std={stdev(ot) if len(ot)>1 else 0:.3f}")
    print(f"speedup   {speedup:.2f}x  ({'PASS ≥2x' if speedup >= 2.0 else 'FAIL <2x'})")


if __name__ == "__main__":
    main()
