#!/usr/bin/env python3
"""Collect W13 headline_bounded measured results (STILL RUNNING until array done)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from common import REPO, die, load_json, rsync_from_carc, status_line, write_json

OUT = REPO / "pipeline/results/exact_replay/headline_bounded.json"
REMOTE_DIR = "headline_bounded/results"
N_TASKS = 9


def main() -> int:
    staging = REPO / "pipeline/results/exact_replay/_w13_staging"
    staging.mkdir(parents=True, exist_ok=True)
    try:
        rsync_from_carc(f"{REMOTE_DIR}/", staging)
    except SystemExit:
        status_line("W13", "STILL RUNNING", "rsync/missing results")
        return 2
    files = sorted(staging.glob("headline_bounded_*.json"))
    # exclude pilot
    measured = [p for p in files if "pilot" not in p.name]
    if len(measured) < N_TASKS:
        status_line("W13", "STILL RUNNING", f"{len(measured)}/{N_TASKS} tasks")
        return 2
    genomes = []
    for path in measured:
        row = load_json(path)
        if row.get("outcome") != "EXACT":
            die(f"{path.name} outcome={row.get('outcome')}")
        genomes.append(row)
    # Prefer a scored aggregate if present; else write provenance stub for analysis.
    agg = staging / "headline_bounded.json"
    if agg.is_file():
        payload = load_json(agg)
    else:
        payload = {
            "test": "headline-bounded",
            "n_genomes": len(genomes),
            "genomes": [
                {
                    "proteome": g.get("proteome"),
                    "outcome": g.get("outcome"),
                    "S_g": g.get("S_g"),
                    "task": g.get("task"),
                }
                for g in genomes
            ],
            "needs_headline_analysis": True,
        }
    write_json(OUT, payload)
    status_line("W13", "COLLECTED", str(OUT.relative_to(REPO)))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
