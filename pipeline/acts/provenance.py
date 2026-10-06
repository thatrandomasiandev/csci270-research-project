"""Provenance block for result JSON. Every measured file should embed this."""

from __future__ import annotations

import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def provenance() -> dict:
    git = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "git": git,
        "git_dirty": bool(dirty),
        "host": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
    }
