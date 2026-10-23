#!/usr/bin/env python3
"""Collect W8 release-chain measured results."""
from __future__ import annotations

import sys
from pathlib import Path

from common import REPO, die, load_json, rsync_from_carc, status_line, write_json

OUT = REPO / "pipeline/results/release_chain/measured.json"
REMOTE = "tare-w8/results"
N_GENOMES = 3


def main() -> int:
    staging = REPO / "pipeline/results/release_chain/_w8_staging"
    staging.mkdir(parents=True, exist_ok=True)
    try:
        rsync_from_carc(f"{REMOTE}/", staging)
    except SystemExit:
        status_line("W8", "STILL RUNNING", "rsync/missing")
        return 2
    parts = sorted(staging.glob("measured_20261222_*.json"))
    if len(parts) < N_GENOMES:
        status_line("W8", "STILL RUNNING", f"{len(parts)}/{N_GENOMES}")
        return 2
    genomes = [load_json(p) for p in parts]
    # RELEASE_CHAIN_PROTOCOL.md: "If B1 fails, that genome stops. Later steps are
    # not imputed ... A FAIL stays in the median." So a scored FAIL is a result,
    # not a collector error. Anything other than PASS or a scored FAIL is.
    for g in genomes:
        if g.get("outcome") not in ("PASS", "FAIL"):
            die(f"unexpected outcome {g.get('outcome')!r} in {g.get('proteome')}")
    payload = {
        "test": "release-chain-measured",
        "seed": 20261222,
        "n_genomes": len(genomes),
        "genomes": genomes,
        "source_files": [p.name for p in parts],
        "n_pass": sum(g.get("outcome") == "PASS" for g in genomes),
        "failed": [
            {
                "proteome": g.get("proteome"),
                "step": (g.get("current_step") or {}).get("kind"),
                "release": (g.get("current_step") or {}).get("release"),
                "decision": (g.get("current_step") or {}).get("decision"),
            }
            for g in genomes
            if g.get("outcome") == "FAIL"
        ],
    }
    # merge if aggregate exists
    if (staging / "measured.json").is_file():
        payload = load_json(staging / "measured.json")
    write_json(OUT, payload)
    status_line("W8", "COLLECTED", str(OUT.relative_to(REPO)))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
