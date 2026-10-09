#!/usr/bin/env python3
"""Compute cumulative savings using measured stock wall for every genome."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from acts.provenance import provenance  # noqa: E402
from acts.savings_analysis import fully_measured  # noqa: E402
from savings_job_load import load_savings_job  # noqa: E402

KIND = {
    "hmmsearch": "hmmsearch_stock_completion",
    "hmmscan": "hmmscan_stock_completion",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", nargs="+", required=True, type=Path)
    parser.add_argument("--stock-dir", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args(argv)


def load_completions(path: Path, kind: str) -> list[dict]:
    completions = []
    for candidate in sorted(path.glob("*.json")):
        raw = json.loads(candidate.read_text())
        if raw.get("kind") == kind:
            completions.append(raw)
    return completions


def default_out(mode: str) -> Path:
    name = (
        "savings_measured_summary.json"
        if mode == "hmmsearch"
        else "savings_measured_summary_hmmscan.json"
    )
    return ROOT / "results" / name


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    jobs = [load_savings_job(path) for path in args.jobs]
    modes = {job["mode"] for job in jobs}
    if len(modes) != 1:
        raise SystemExit("pass jobs from one mode per measured summary")
    mode = modes.pop()
    completions = load_completions(args.stock_dir, KIND[mode])
    by_collection = {
        collection: [row for row in completions if row.get("collection") == collection]
        for collection in ("A", "B")
    }
    rows = []
    for job in jobs:
        row = fully_measured(job, by_collection[job["collection"]])
        row["mode"] = mode
        row["post_hoc"] = mode == "hmmscan"
        rows.append(row)
    versions = {
        f"{job['collection']}_{mode}": str(job.get("hmmer", "unknown")) for job in jobs
    }
    payload = {
        "label": "PRE-REGISTERED fully measured cumulative savings",
        "mode": mode,
        "post_hoc": mode == "hmmscan",
        "inputs": {
            "jobs": [str(path) for path in args.jobs],
            "stock_dir": str(args.stock_dir),
            "kind": KIND[mode],
            "n_stock_files": len(completions),
        },
        "collections": {row["collection"]: row for row in rows},
        "provenance": provenance(versions=versions),
    }
    if mode == "hmmscan":
        payload["label"] = (
            "PRE-REGISTERED fully measured cumulative savings. "
            "hmmscan is a post-hoc mode and is not paper_uses."
        )
    out = args.out or default_out(mode)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
