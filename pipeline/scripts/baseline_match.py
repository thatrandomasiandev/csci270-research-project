"""Tblout MATCH for the locked baseline smoke.

Rules are the ones in pipeline/docs/BASELINES_PROTOCOL.md (locked
2026-09-27, a29c318): token identity, not bytes. hmmscan --cut_ga is
order plus split(). hmmsearch fixed-Z is multiset plus split().
"""

from __future__ import annotations

import os
import platform
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def body_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln and not ln.startswith("#")]


def ws(line: str) -> str:
    return " ".join(line.split())


def tables_match(got: str, stock: str, mode: str) -> bool:
    """Return True when tblout bodies match under the locked rule for mode."""
    left = [ws(ln) for ln in body_lines(got)]
    right = [ws(ln) for ln in body_lines(stock)]
    if mode == "hmmscan":
        return left == right
    if mode == "hmmsearch":
        return Counter(left) == Counter(right)
    raise ValueError(f"unknown mode {mode}")


def nonempty_body(text: str) -> bool:
    return any(body_lines(text))


def provenance(versions: dict[str, str] | None = None) -> dict:
    """Provenance for a result written on CARC.

    The ACTS tree is not checked out on the compute node. The git hash
    is the file named by ACTS_GIT_HASH_FILE, or ACTS_GIT_HASH.
    """
    git = (os.environ.get("ACTS_GIT_HASH") or "").strip()
    hash_file = (os.environ.get("ACTS_GIT_HASH_FILE") or "").strip()
    if not git and hash_file:
        path = Path(hash_file)
        if path.is_file():
            git = path.read_text().strip()
    uname = os.uname()
    return {
        "git": git or "unknown",
        "git_hash_file": hash_file or None,
        "git_dirty": None,
        "git_note": "hash is ACTS_GIT_HASH_FILE; this CARC path is not an ACTS checkout",
        "host": platform.node(),
        "platform": platform.platform(),
        "uname": f"{uname.sysname} {uname.release} {uname.machine}",
        "python": platform.python_version(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_nodelist": os.environ.get("SLURM_NODELIST"),
        "slurm_constraint": os.environ.get("SLURM_JOB_CONSTRAINT"),
        "slurm_cpus": os.environ.get("SLURM_CPUS_PER_TASK"),
        "versions": dict(versions or {}),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
    }


def _selfcheck() -> None:
    scan_a = "# meta\nA 1 x\nB  2   y\n"
    scan_b = "# other\nA 1 x\nB 2 y\n"
    scan_c = "# meta\nB 2 y\nA 1 x\n"
    if not tables_match(scan_a, scan_b, "hmmscan"):
        raise SystemExit("hmmscan whitespace order should match")
    if tables_match(scan_a, scan_c, "hmmscan"):
        raise SystemExit("hmmscan order should reject a swap")
    if not tables_match(scan_a, scan_c, "hmmsearch"):
        raise SystemExit("hmmsearch multiset should accept a swap")
    if nonempty_body("# only\n"):
        raise SystemExit("comments are not a body")
    if not nonempty_body("row\n"):
        raise SystemExit("a data row is a body")
    print("baseline_match selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
