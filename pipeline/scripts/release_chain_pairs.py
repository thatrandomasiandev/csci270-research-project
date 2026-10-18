#!/usr/bin/env python3
"""Strict-hash diffs for consecutive Pfam releases.

The counts use the same functions as ``reference_kill_tests.py`` r1:
``iter_models`` and ``model_hashes``. An accession stem is the ACC token
with the version suffix removed. A repeated stem keeps the last block.
The strict hash is ``entry_content_hash(block, PROFILE_VOLATILE_TAGS)``.

``f_delta`` is ``(z_new - unchanged_strict) / z_new``, the fraction of the
new release that is new or edited. That is the quantity behind
``reference_kill_r1.json`` and Figure 5.

This script only reads paths it is given. It does not download.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import socket
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from acts.entry_hash import entry_content_hash  # noqa: E402
from acts.reference_formats import (  # noqa: E402
    PROFILE_VOLATILE_TAGS,
    iter_profile_raw,
)
from reference_kill_tests import iter_models, model_hashes  # noqa: E402

ORDER = ("37.0", "37.1", "37.2", "37.3", "37.4", "38.0", "38.1", "38.2")
PAIRS = tuple(zip(ORDER, ORDER[1:]))
CONTROL_KEYS = (
    "z_old",
    "z_new",
    "added",
    "removed",
    "shared",
    "unchanged_strict",
    "unchanged_body",
    "frac_new_unchanged_strict",
    "frac_new_unchanged_body",
)


def git_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def index_release(path: Path) -> dict:
    """Last-write-wins accession index, plus the collisions r1's dict hides."""
    strict: dict[str, str] = {}
    body: dict[str, str] = {}
    n_blocks = 0
    overwrites = 0
    empty_acc = 0
    magics: Counter[str] = Counter()
    hash_counts: Counter[str] = Counter()
    for acc, block in iter_models(path):
        n_blocks += 1
        magics[block[0].split(None, 1)[0] if block and block[0].strip() else ""] += 1
        if acc == "":
            empty_acc += 1
        digest, body_digest = model_hashes(block)
        if acc in strict:
            overwrites += 1
        strict[acc] = digest
        body[acc] = body_digest
        hash_counts[digest] += 1
    return {
        "strict": strict,
        "body": body,
        "n_blocks": n_blocks,
        "z": len(strict),
        "overwrites": overwrites,
        "empty_acc": empty_acc,
        "magics": dict(magics),
        "duplicate_hashes": sum(1 for count in hash_counts.values() if count > 1),
    }


def parser_entry_count(path: Path) -> dict:
    """Shipped parser count. Adjacent same-record blocks are one entry."""
    n = 0
    hashes: Counter[str] = Counter()
    for raw in iter_profile_raw(path):
        n += 1
        hashes[entry_content_hash(raw, PROFILE_VOLATILE_TAGS)] += 1
    return {
        "parser_entries": n,
        "parser_duplicate_hashes": sum(1 for count in hashes.values() if count > 1),
    }


def compare(old_name: str, new_name: str, old: dict, new: dict) -> dict:
    shared = set(old["strict"]) & set(new["strict"])
    unchanged = sum(1 for acc in shared if old["strict"][acc] == new["strict"][acc])
    body_same = sum(1 for acc in shared if old["body"][acc] == new["body"][acc])
    added = len(set(new["strict"]) - set(old["strict"]))
    removed = len(set(old["strict"]) - set(new["strict"]))
    old_hashset = set(old["strict"].values())
    hashset_fresh = sum(1 for digest in new["strict"].values() if digest not in old_hashset)
    z_new = new["z"]
    if z_new == 0:
        raise SystemExit(f"{new_name} has no models")
    edited = len(shared) - unchanged
    return {
        "old_release": old_name,
        "new_release": new_name,
        "z_old": old["z"],
        "z_new": z_new,
        "n_blocks_old": old["n_blocks"],
        "n_blocks_new": new["n_blocks"],
        "added": added,
        "removed": removed,
        "shared": len(shared),
        "unchanged_strict": unchanged,
        "edited": edited,
        "unchanged_body": body_same,
        "frac_new_unchanged_strict": unchanged / z_new,
        "frac_new_unchanged_body": body_same / z_new,
        "f_delta": (z_new - unchanged) / z_new,
        "hashset_fresh": hashset_fresh,
        "hashset_f_delta": hashset_fresh / z_new,
        "duplicate_acc_stems_old": old["overwrites"],
        "duplicate_acc_stems_new": new["overwrites"],
        "empty_acc_old": old["empty_acc"],
        "empty_acc_new": new["empty_acc"],
        "duplicate_hashes_old": old["duplicate_hashes"],
        "duplicate_hashes_new": new["duplicate_hashes"],
        "magics_old": old["magics"],
        "magics_new": new["magics"],
    }


def control_mismatches(pair: dict, expected: dict) -> list[str]:
    bad: list[str] = []
    for key in CONTROL_KEYS:
        if pair[key] != expected[key]:
            bad.append(f"{key}: measured {pair[key]!r} != reference_kill_r1 {expected[key]!r}")
    return bad


def self_test() -> None:
    """Known-good and known-bad blocks. No release file is read."""
    def block(name: str, acc: str, date: str, extra: str = "") -> str:
        return (
            "HMMER3/f [3.3 | Nov 2019]\n"
            f"NAME  {name}\n"
            f"ACC   {acc}\n"
            f"DATE  {date}\n"
            "BM    hmmbuild\n"
            "SM    hmmsearch -Z 1\n"
            f"{extra}"
            "GA    25 25;\n"
            "HMM   A\n"
            "      1.0\n"
            "//\n"
        )

    unchanged = block("A", "PF00001.1", "yesterday")
    date_only = block("A", "PF00001.1", "today")
    renamed = block("A2", "PF00001.2", "yesterday")
    if entry_content_hash(unchanged, PROFILE_VOLATILE_TAGS) != entry_content_hash(
        date_only, PROFILE_VOLATILE_TAGS
    ):
        raise SystemExit("self-test: a DATE/BM/SM-only edit was not unchanged")
    if entry_content_hash(unchanged, PROFILE_VOLATILE_TAGS) == entry_content_hash(
        renamed, PROFILE_VOLATILE_TAGS
    ):
        raise SystemExit("self-test: a NAME edit hashed as unchanged")
    strict_u, _ = model_hashes(unchanged.splitlines(keepends=True))
    if strict_u != entry_content_hash(unchanged, PROFILE_VOLATILE_TAGS):
        raise SystemExit("self-test: model_hashes diverges from entry_content_hash")
    print("self-test pass")


def parse_release(item: str) -> tuple[str, Path]:
    if "=" not in item:
        raise SystemExit(f"expected VERSION=PATH, got {item}")
    version, raw = item.split("=", 1)
    if version not in ORDER:
        raise SystemExit(f"version {version} is not in {ORDER}")
    path = Path(raw)
    if not path.is_file():
        raise SystemExit(f"missing {path}")
    return version, path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--release", action="append", default=[], metavar="VER=PATH")
    parser.add_argument("--out", type=Path, required=False)
    parser.add_argument(
        "--control",
        type=Path,
        default=ROOT / "results" / "reference_kill_r1.json",
        help="reference_kill_r1.json. The 38.1→38.2 pair must match it.",
    )
    args = parser.parse_args()
    if args.self_test:
        self_test()
        if not args.release:
            return
    if not args.release or args.out is None:
        raise SystemExit("need --release VER=PATH (repeatable) and --out")

    releases = dict(parse_release(item) for item in args.release)
    present = [version for version in ORDER if version in releases]
    wanted = [(a, b) for a, b in PAIRS if a in releases and b in releases]
    if not wanted:
        raise SystemExit(f"no consecutive pair in {present}")

    started = time.perf_counter()
    indexed: dict[str, dict] = {}
    file_meta: dict[str, dict] = {}
    for version in present:
        path = releases[version]
        t0 = time.perf_counter()
        indexed[version] = index_release(path)
        parser_meta = parser_entry_count(path)
        indexed[version].update(parser_meta)
        file_meta[version] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "md5": md5_file(path),
            "index_wall_s": time.perf_counter() - t0,
        }

    expected = json.loads(args.control.read_text())
    pairs = []
    control_ok = None
    for old_name, new_name in wanted:
        pair = compare(old_name, new_name, indexed[old_name], indexed[new_name])
        pair["old_file"] = file_meta[old_name]
        pair["new_file"] = file_meta[new_name]
        pair["parser_entries_old"] = indexed[old_name]["parser_entries"]
        pair["parser_entries_new"] = indexed[new_name]["parser_entries"]
        pair["parser_duplicate_hashes_old"] = indexed[old_name]["parser_duplicate_hashes"]
        pair["parser_duplicate_hashes_new"] = indexed[new_name]["parser_duplicate_hashes"]
        pair["parser_matches_r1_z"] = (
            pair["parser_entries_old"] == pair["z_old"] and pair["parser_entries_new"] == pair["z_new"]
        )
        if (old_name, new_name) == ("38.1", "38.2"):
            mismatches = control_mismatches(pair, expected)
            pair["control"] = "reference_kill_r1.json"
            pair["control_pass"] = not mismatches
            pair["control_mismatches"] = mismatches
            control_ok = pair["control_pass"]
        pairs.append(pair)

    payload = {
        "protocol": "pipeline/docs/RELEASE_CHAIN_PROTOCOL.md",
        "definition": "reference_kill_tests.iter_models + model_hashes; last ACC stem wins",
        "git_head": git_head(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "argv": sys.argv,
        "wall_s": time.perf_counter() - started,
        "threads": 1,
        "releases_present": present,
        "complete": present == list(ORDER) and len(pairs) == len(PAIRS),
        "pairs": pairs,
        "control_38_1_38_2_pass": control_ok,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {args.out} pairs={len(pairs)} control={control_ok}")
    if control_ok is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
