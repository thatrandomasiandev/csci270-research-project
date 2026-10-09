#!/usr/bin/env python3
"""Compute cumulative savings using measured stock wall for every genome."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.provenance import provenance  # noqa: E402
from acts.savings_analysis import fully_measured, load_job  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", nargs=2, required=True, type=Path)
    parser.add_argument("--stock-dir", required=True, type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "results" / "savings_measured_summary.json",
    )
    return parser.parse_args(argv)


def load_completions(path: Path) -> list[dict]:
    completions = []
    for candidate in sorted(path.glob("*.json")):
        raw = json.loads(candidate.read_text())
        if raw.get("kind") == "hmmsearch_stock_completion":
            completions.append(raw)
    return completions


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    jobs = [load_job(path) for path in args.jobs]
    completions = load_completions(args.stock_dir)
    by_collection = {
        collection: [
            row for row in completions if row.get("collection") == collection
        ]
        for collection in ("A", "B")
    }
    rows = [
        fully_measured(job, by_collection[job["collection"]]) for job in jobs
    ]
    versions = {
        f"{job['collection']}_hmmer": str(job.get("hmmer", "unknown"))
        for job in jobs
    }
    payload = {
        "label": "PRE-REGISTERED fully measured cumulative savings",
        "inputs": {
            "jobs": [str(path) for path in args.jobs],
            "stock_dir": str(args.stock_dir),
            "n_stock_files": len(completions),
        },
        "collections": {row["collection"]: row for row in rows},
        "provenance": provenance(versions=versions),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
