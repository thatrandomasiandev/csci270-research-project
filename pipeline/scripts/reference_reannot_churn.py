#!/usr/bin/env python3
"""Length-weighted reference churn from the two model files. No tool is timed.

Writes the integers the secondary prediction needs:
c_length = (length of changed and new entries) / (length of the new release).
An entry is unchanged when its content hash occurs in the old release.
"""

from __future__ import annotations

import argparse
import gc
import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.provenance import provenance  # noqa: E402
from acts.reference_formats import (  # noqa: E402
    length_weighted_churn_hashes,
    parse_reference,
)

# R1, results/reference_kill_r1.json. A mismatch means these are not the
# files that measurement used, and the timed job must not start.
R1_Z_NEW = 30134
R1_UNCHANGED_STRICT = 26082


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    raw = path.read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    return raw.decode().strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--old-version", type=Path)
    parser.add_argument("--new-version", type=Path)
    parser.add_argument("-o", "--out", type=Path, required=True)
    args = parser.parse_args()

    old_sha = sha256(args.old)
    new_sha = sha256(args.new)
    old_entries = parse_reference(args.old)
    old_hashes = {entry.content_hash for entry in old_entries}
    n_old = len(old_entries)
    del old_entries
    gc.collect()
    new_entries = parse_reference(args.new)
    report = length_weighted_churn_hashes(old_hashes, new_entries, n_old=n_old)
    matches = (
        report["n_new"] == R1_Z_NEW and report["n_unchanged_hash"] == R1_UNCHANGED_STRICT
    )
    payload = {
        "measurement": "length-weighted churn from model files only",
        "timed": False,
        "old_path": str(args.old),
        "new_path": str(args.new),
        "old_sha256": old_sha,
        "new_sha256": new_sha,
        "old_bytes": args.old.stat().st_size,
        "new_bytes": args.new.stat().st_size,
        "old_version": version_text(args.old_version),
        "new_version": version_text(args.new_version),
        "r1_z_new": R1_Z_NEW,
        "r1_unchanged_strict": R1_UNCHANGED_STRICT,
        "r1_crosscheck": "ok" if matches else "MISMATCH",
        **report,
        "provenance": provenance(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({k: payload[k] for k in (
        "n_old", "n_new", "n_unchanged_hash", "n_changed_and_new",
        "length_new", "length_changed_and_new", "c_length", "r1_crosscheck",
    )}, indent=2))
    return 0 if matches else 2


if __name__ == "__main__":
    sys.exit(main())
