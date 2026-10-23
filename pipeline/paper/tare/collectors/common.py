"""Shared helpers for finalize collectors. Read-only on CARC staged trees."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# collectors/ → tare/ → paper/ → pipeline/ → repo root
REPO = Path(__file__).resolve().parents[4]
CARC_ROOT = Path(
    os.environ.get(
        "TARE_CARC_ROOT",
        "/project2/biyik_1165/jjt_373/csci270-star",
    )
)


def die(msg: str, code: int = 1) -> None:
    print(f"COLLECTOR FAIL: {msg}", file=sys.stderr)
    raise SystemExit(code)


def load_json(path: Path) -> dict:
    if not path.is_file():
        die(f"missing {path}")
    return json.loads(path.read_text())


def rsync_from_carc(remote_rel: str, dest: Path, timeout_s: int = 90) -> None:
    """Pull a file or directory from discovery. Never writes under CARC.

    Uses a bounded SSH connect/timeout so finalize cannot hang when the
    login node is unreachable. Failure → die() (collectors map to STILL RUNNING).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    remote = f"discovery:{CARC_ROOT / remote_rel}"
    # Alias `discovery` only; add ConnectTimeout without disabling ControlMaster.
    ssh = (
        "ssh -o ConnectTimeout=20 -o ServerAliveInterval=15 "
        "-o ServerAliveCountMax=3"
    )
    cmd = ["rsync", "-e", ssh, "-az", "--timeout", str(timeout_s), remote, str(dest)]
    try:
        proc = subprocess.run(
            cmd, check=False, capture_output=True, text=True, timeout=timeout_s + 30
        )
    except subprocess.TimeoutExpired:
        die(f"rsync timed out after {timeout_s}s pulling {remote_rel}", code=2)
    if proc.returncode != 0:
        # Unreachable / missing path → still running, not a hard fail.
        die(
            f"rsync failed ({proc.returncode}): {(proc.stderr or '')[-500:]}",
            code=2,
        )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def status_line(name: str, status: str, detail: str = "") -> None:
    extra = f" {detail}" if detail else ""
    print(f"{name:24s} {status}{extra}")
