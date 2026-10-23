#!/usr/bin/env python3
"""Collect W12a server.json (expert-script measured)."""
from __future__ import annotations

import sys
from pathlib import Path

from common import REPO, load_json, rsync_from_carc, status_line, write_json

OUT = REPO / "pipeline/results/baselines_exact/server.json"
REMOTE = "tare-w12a/checkout/pipeline/results/baselines_exact/server.json"


def main() -> int:
    dest = REPO / "pipeline/results/baselines_exact/_staging_server.json"
    try:
        rsync_from_carc(REMOTE, dest)
    except SystemExit:
        status_line("W12a", "STILL RUNNING", "no server.json")
        return 2
    payload = load_json(dest)
    if payload.get("status") != "measured":
        status_line("W12a", "STILL RUNNING", f"status={payload.get('status')}")
        return 2
    write_json(OUT, payload)
    status_line("W12a", "COLLECTED", str(OUT.relative_to(REPO)))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
