#!/usr/bin/env python3
"""Indicative Mac smoke for reference incrementality. Not an acceptance gate.

Uses the 78-model subset named in scripts/repro_savings_desc_stop.py. A fake
release edits the description of seven entries and appends one cloned entry,
about 10% of the new reference. The second run must ref-merge MATCH a stock
full run. Wall times are indicative only.
"""

from __future__ import annotations

import gzip
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import repro_savings_desc_stop as repro  # noqa: E402

from acts.fasta import write_fasta  # noqa: E402
from acts.provenance import provenance  # noqa: E402
from acts.reference_formats import parse_reference  # noqa: E402
from acts.reference_run import ReferenceIncremental  # noqa: E402

WORK = Path("/tmp/acts_reference_fitter/smoke")
N_RECORDS = 40
N_DESC = 7


def extract(dest: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 0:
        return
    want = set(repro.MODELS)
    found: dict[str, str] = {}
    buf: list[str] = []
    name = None
    src = ROOT / "data" / "hmmer" / "Pfam-A.hmm.gz"
    with gzip.open(src, "rt") as handle:
        for line in handle:
            if line.startswith("HMMER3/f"):
                buf = [line]
                name = None
                continue
            if not buf:
                continue
            buf.append(line)
            if line.startswith("NAME ") and name is None:
                name = line.split()[1]
            if line.strip() == "//":
                if name in want:
                    found[name] = "".join(buf)
                buf = []
                name = None
                if len(found) == len(want):
                    break
    missing = want - set(found)
    if missing:
        raise SystemExit(f"missing models: {sorted(missing)[:5]}")
    dest.write_text("".join(found[name] for name in repro.MODELS))


def perturb(src: Path, dest: Path) -> dict:
    entries = parse_reference(src)
    pieces: list[str] = []
    edited: list[str] = []
    for index, entry in enumerate(entries):
        raw = entry.raw
        if index < N_DESC:
            raw = re.sub(r"(?m)^DESC\s+.*$", "DESC  acts-release-note", raw, count=1)
            edited.append(entry.primary)
        pieces.append(raw if raw.endswith("\n") else raw + "\n")
    clone = entries[-1].raw
    clone = re.sub(r"(?m)^NAME\s+\S+", "NAME  Clone_release", clone, count=1)
    clone = re.sub(r"(?m)^ACC\s+\S+", "ACC   CLONE000.1", clone, count=1)
    pieces.append(clone if clone.endswith("\n") else clone + "\n")
    dest.write_text("".join(pieces))
    return {
        "n_base": len(entries),
        "desc_edited": edited,
        "added": "Clone_release",
        "n_release": len(entries) + 1,
        "changed_fraction": (N_DESC + 1) / (len(entries) + 1),
    }


def records(dest: Path) -> int:
    rng = random.Random(20261006)
    subset = repro.genome_subset(repro.GENOMES[0], rng)
    # genome_subset draws SAMPLE=300. Keep a fixed prefix so the smoke stays small.
    keep = subset[:N_RECORDS]
    write_fasta(dest, keep)
    return len(keep)


def once(label: str, reference: Path, fasta: Path, out: Path, cache: Path) -> dict:
    strategy = ReferenceIncremental(
        argv=[
            "hmmscan",
            "--cpu",
            "4",
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
    )
    t0 = time.perf_counter()
    result = strategy.run()
    wall = time.perf_counter() - t0
    return {
        "label": label,
        "decision": result.decision,
        "reason": result.reason,
        "extra": result.extra,
        "wall_s_indicative": wall,
    }


def tool_banner(binary: str) -> str:
    proc = subprocess.run([binary, "-h"], capture_output=True, text=True)
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        if "HMMER" in line:
            return line.lstrip("# ").strip()
    return ""


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    base = WORK / "subset.hmm"
    print(f"extracting {len(repro.MODELS)} models", flush=True)
    extract(base)
    release = WORK / "release.hmm"
    note = perturb(base, release)
    fasta = WORK / "queries.faa"
    n_records = records(fasta)
    cache = WORK / "reference.sqlite"
    if cache.exists():
        cache.unlink()
    print("first reference", flush=True)
    first = once("base", base, fasta, WORK / "base", cache)
    print(first["decision"], first["wall_s_indicative"], flush=True)
    print("release", flush=True)
    second = once("release", release, fasta, WORK / "release", cache)
    print(second["decision"], second["wall_s_indicative"], second["extra"], flush=True)
    passed = (
        first["decision"] == "SHIP"
        and second["decision"] == "SHIP"
        and int(second["extra"].get("reused_rows") or 0) > 0
    )
    payload = {
        "test": "smoke",
        "acceptance_gate": False,
        "timing": "INDICATIVE",
        "host_note": "Mac wall time. Not a CARC measurement.",
        "pass": passed,
        "perturbation": note,
        "n_records": n_records,
        "runs": [first, second],
        "provenance": {
            **provenance(),
            "tools": {"hmmscan": tool_banner("hmmscan"), "hmmpress": tool_banner("hmmpress")},
        },
    }
    dest = ROOT / "results" / "reference_fitter_smoke.json"
    dest.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"smoke {'PASS' if passed else 'FAIL'} -> {dest}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
