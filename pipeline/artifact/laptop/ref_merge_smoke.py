#!/usr/bin/env python3
"""Laptop ref-merge MATCH on four committed toy profiles.

Pfam-A is not in the repository. This smoke builds four HMMER3 profiles
with hmmbuild from pipeline/artifact/fixtures/profiles/*.sto, presses them,
and runs the reference-side wrapper (`hmmscan --cut_ga`, `--verify full`).

Pinned expected values, HMMER 3.4, gathering threshold 15:
- base reference: SHIP, rows=2, reused_rows=0
  (ToyA and ToyC hit; ToyB and ToyD do not)
- release: DESC of ToyA edited and ToyD cloned: SHIP, rows=2, reused_rows=1
  SHIP under `--verify full` is ref-merge MATCH against a stock hmmscan.

This is not a Pfam 38.1 to 38.2 measurement and not a speedup.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PIPE = REPO / "pipeline"
sys.path.insert(0, str(PIPE))

from acts.reference_formats import parse_reference  # noqa: E402
from acts.reference_run import ReferenceIncremental  # noqa: E402

PROFILES = PIPE / "artifact" / "fixtures" / "profiles"
ORDER = ("ToyA", "ToyB", "ToyC", "ToyD")
# Queries are the consensus of ToyA, ToyB, and ToyC. ToyB scores under the
# gathering threshold, so the stock table has two rows.
QUERY_NAMES = ("ToyA", "ToyB", "ToyC")
EXPECT_BASE = {"decision": "SHIP", "rows": 2, "reused_rows": 0}
EXPECT_RELEASE = {"decision": "SHIP", "rows": 2, "reused_rows": 1}


def _consensus(sto: Path) -> str:
    seqs = [
        line.split(None, 1)[1].strip()
        for line in sto.read_text().splitlines()
        if line and not line.startswith("#") and not line.startswith("//")
    ]
    if len(set(seqs)) != 1:
        raise SystemExit(f"FAIL {sto.name}: alignment is not a single consensus")
    return seqs[0]


def _build(work: Path) -> Path:
    pieces: list[str] = []
    for name in ORDER:
        sto = PROFILES / f"{name}.sto"
        hmm = work / f"{name}.hmm"
        proc = subprocess.run(
            ["hmmbuild", "--amino", str(hmm), str(sto)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise SystemExit(f"FAIL hmmbuild {name}: {proc.stderr.strip()}")
        pieces.append(hmm.read_text())
    dest = work / "base.hmm"
    dest.write_text("".join(pieces))
    return dest


def _queries(dest: Path) -> None:
    lines: list[str] = []
    for name in QUERY_NAMES:
        lines.append(f">{name}")
        lines.append(_consensus(PROFILES / f"{name}.sto"))
    dest.write_text("\n".join(lines) + "\n")


def _release(base: Path, dest: Path) -> None:
    pieces: list[str] = []
    entries = parse_reference(base)
    for entry in entries:
        raw = entry.raw
        if entry.primary == "ToyA":
            raw = re.sub(r"(?m)^DESC\s+.*$", "DESC  release-note", raw, count=1)
        pieces.append(raw if raw.endswith("\n") else raw + "\n")
    clone = entries[-1].raw
    clone = re.sub(r"(?m)^NAME\s+\S+", "NAME  ToyClone", clone, count=1)
    clone = re.sub(r"(?m)^ACC\s+\S+", "ACC   TOY00005.1", clone, count=1)
    pieces.append(clone if clone.endswith("\n") else clone + "\n")
    dest.write_text("".join(pieces))


def _run(label: str, reference: Path, fasta: Path, out: Path, cache: Path):
    return ReferenceIncremental(
        argv=[
            "hmmscan",
            "--cpu",
            "1",
            "--cut_ga",
            "--noali",
            "--tblout",
            "{output:targets}",
            "{reference}",
            "{input}",
        ],
        input_path=fasta,
        out_dir=out,
        reference=reference,
        prep="hmmpress -f {reference}",
        verify="full",
        cache_path=cache,
        sample=True,
    ).run()


def _check(name: str, result, expect: dict) -> bool:
    extra = result.extra or {}
    got = {
        "decision": result.decision,
        "rows": extra.get("rows"),
        "reused_rows": extra.get("reused_rows"),
    }
    ok = got == expect
    print(
        f"{'PASS' if ok else 'FAIL'} {name}: "
        f"decision={got['decision']} rows={got['rows']} "
        f"reused_rows={got['reused_rows']} "
        f"expected decision={expect['decision']} rows={expect['rows']} "
        f"reused_rows={expect['reused_rows']} reason={result.reason}"
    )
    return ok


def main() -> int:
    if shutil.which("hmmbuild") is None or shutil.which("hmmscan") is None:
        print("FAIL hmmbuild and hmmscan are required (HMMER 3.4)")
        return 1
    banner = subprocess.run(["hmmscan", "-h"], capture_output=True, text=True)
    text = banner.stdout + banner.stderr
    if "HMMER 3.4" not in text:
        print("FAIL hmmscan is not HMMER 3.4")
        return 1
    started = time.perf_counter()
    work = Path(tempfile.mkdtemp(prefix="acts_artifact_refmerge_"))
    base = _build(work)
    fasta = work / "queries.faa"
    _queries(fasta)
    release = work / "release.hmm"
    _release(base, release)
    cache = work / "cache.sqlite"
    failures = 0
    if not _check("ref-merge-base", _run("base", base, fasta, work / "base", cache), EXPECT_BASE):
        failures += 1
    if not _check(
        "ref-merge-release",
        _run("release", release, fasta, work / "release", cache),
        EXPECT_RELEASE,
    ):
        failures += 1
    elapsed = time.perf_counter() - started
    print(f"wall_s={elapsed:.3f} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
