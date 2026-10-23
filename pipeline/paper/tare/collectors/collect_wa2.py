#!/usr/bin/env python3
"""Validate committed WA2 measured_v2; optional timing_v2 if present."""
from __future__ import annotations

import sys
from pathlib import Path

from common import REPO, load_json, rsync_from_carc, status_line, write_json

V2 = REPO / "pipeline/results/unrelated_ship/measured_v2.json"
TIMING = REPO / "pipeline/results/unrelated_ship/timing_v2.json"
REMOTE_T = "tare-exp-a/pipeline/results/unrelated_ship/timing_v2.json"


def main() -> int:
    if not V2.is_file():
        status_line("WA2", "FAILED", "measured_v2.json not committed")
        return 1
    d = load_json(V2)
    outcome = d.get("outcome")
    status_line("WA2-correctness", "COLLECTED", f"outcome={outcome}")
    if outcome != "PASS":
        status_line("WA2-timing", "FAILED", "not eligible (correctness not PASS)")
        return 0  # correctness collected; timing correctly absent
    try:
        rsync_from_carc(REMOTE_T, TIMING)
    except SystemExit:
        status_line("WA2-timing", "STILL RUNNING", "no timing_v2.json")
        return 2
    status_line("WA2-timing", "COLLECTED", str(TIMING.relative_to(REPO)))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
