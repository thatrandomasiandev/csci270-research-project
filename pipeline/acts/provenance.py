"""Provenance block for result JSON. Every measured file should embed this."""

from __future__ import annotations

import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _git_hash(root: Path) -> str:
    explicit = os.environ.get("ACTS_GIT_HASH", "").strip()
    if explicit:
        return explicit
    sidecar_name = os.environ.get("ACTS_GIT_HASH_FILE", "").strip()
    if sidecar_name:
        sidecar = Path(sidecar_name)
        if sidecar.is_file():
            value = sidecar.read_text().strip()
            if value:
                return value
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
    ).stdout.strip() or "unknown"


def provenance(*, versions: dict[str, str] | None = None) -> dict:
    git = _git_hash(ROOT)
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
        "versions": dict(versions or {}),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
    }
