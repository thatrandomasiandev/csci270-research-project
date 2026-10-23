#!/usr/bin/env python3
"""Collect W5x Table 4 x86 measured.json."""
from __future__ import annotations

import sys
from pathlib import Path

from common import REPO, die, load_json, rsync_from_carc, status_line, write_json

OUT = REPO / "pipeline/results/baselines_x86/measured.json"
REMOTE = "tare-w5x/results/measured.json"


def main() -> int:
    dest = REPO / "pipeline/results/baselines_x86/_staging_measured.json"
    try:
        rsync_from_carc(REMOTE, dest)
    except SystemExit:
        status_line("W5x", "STILL RUNNING", "no measured.json yet")
        return 2
    payload = load_json(dest)
    if payload.get("label") != "MEASURED" and payload.get("phase") != "measured":
        # partial file while job runs
        if payload.get("label") == "PARTIAL":
            status_line("W5x", "STILL RUNNING", "PARTIAL")
            return 2
    write_json(OUT, payload)
    status_line("W5x", "COLLECTED", str(OUT.relative_to(REPO)))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
