#!/usr/bin/env python3
"""POST-HOC sensitivity analysis for biased savings stock imputation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from acts.provenance import provenance  # noqa: E402
from acts.savings_analysis import sensitivity  # noqa: E402
from savings_job_load import load_savings_job  # noqa: E402

FORMULA = (
    "r = sum(sampled measured stock) / sum(sampled fitted stock); "
    "unsampled corrected stock_i = r * fitted stock_i; sampled stock "
    "remains measured"
)
ASSUMPTIONS = [
    "The sampled measured/predicted ratio is representative of unsampled genomes.",
    "Cached wall and singleton_8 probe cost P are unchanged.",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", nargs="+", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args(argv)


def default_out(mode: str) -> Path:
    name = (
        "savings_sensitivity.json"
        if mode == "hmmsearch"
        else "savings_sensitivity_hmmscan.json"
    )
    return ROOT / "results" / name


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    jobs = [load_savings_job(path) for path in args.jobs]
    modes = {job["mode"] for job in jobs}
    if len(modes) != 1:
        raise SystemExit("pass jobs from one mode; hmmscan stays a separate POST-HOC file")
    mode = modes.pop()
    rows = []
    for job in jobs:
        row = sensitivity(job)
        if mode == "hmmscan":
            row["mode"] = "hmmscan"
            row["post_hoc"] = True
        rows.append(row)
    label = "POST-HOC sensitivity; not the pre-registered analysis"
    payload = {
        "label": label,
        "inputs": [str(path) for path in args.jobs],
        "formula": FORMULA,
        "assumptions": list(ASSUMPTIONS),
        "collections": {row["collection"]: row for row in rows},
        "provenance": provenance(),
    }
    if mode == "hmmscan":
        payload["label"] = (
            label + ". hmmscan is a post-hoc mode and is not paper_uses."
        )
        payload["mode"] = "hmmscan"
        payload["post_hoc"] = True
    out = args.out or default_out(mode)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
