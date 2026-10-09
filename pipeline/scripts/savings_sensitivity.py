#!/usr/bin/env python3
"""POST-HOC sensitivity analysis for biased savings stock imputation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.provenance import provenance  # noqa: E402
from acts.savings_analysis import load_job, sensitivity  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", nargs=2, required=True, type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "results" / "savings_sensitivity.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    jobs = [load_job(path) for path in args.jobs]
    rows = [sensitivity(job) for job in jobs]
    payload = {
        "label": "POST-HOC sensitivity; not the pre-registered analysis",
        "inputs": [str(path) for path in args.jobs],
        "formula": (
            "r = sum(sampled measured stock) / sum(sampled fitted stock); "
            "unsampled corrected stock_i = r * fitted stock_i; sampled stock "
            "remains measured"
        ),
        "assumptions": [
            "The sampled measured/predicted ratio is representative of unsampled genomes.",
            "Cached wall and singleton_8 probe cost P are unchanged.",
        ],
        "collections": {row["collection"]: row for row in rows},
        "provenance": provenance(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
