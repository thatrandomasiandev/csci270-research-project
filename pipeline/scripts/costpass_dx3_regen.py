#!/usr/bin/env python3
"""Regenerate the locked DX3 draw. The m8 files were not on disk.

Seed 20261029, 2000 proteins from GCF_001515725.1, written in file order.
Stock and the union replay use the DX3 argv. The neighbor pad is the
check under test. This is a pilot of that check, not a new DX3 result.
"""
from __future__ import annotations

import gzip
import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.exact_certificate import judge, neighbor_ids  # noqa: E402
from acts.reference_run import body_lines  # noqa: E402

DIAMOND = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/builds/diamond-2.2.5/diamond")
SPROT = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data/swissprot/uniprot_sprot_2026_03.fasta.gz")
QUERY_GZ = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data/recurrence/A/GCF_001515725.1_protein.faa.gz")
WORK = Path("/Users/joshuaterranova/tmp/costpass_work/dx3_regen")
OUTFMT = ["qseqid", "sseqid", "pident", "length", "mismatch", "gapopen", "qstart", "qend", "sstart", "send", "evalue", "bitscore"]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def records(path: Path) -> list[str]:
    chunks: list[str] = []
    buf: list[str] = []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith(">") and buf:
                chunks.append("".join(buf))
                buf = []
            buf.append(line)
        if buf:
            chunks.append("".join(buf))
    return chunks


def blast(db: Path, query: Path, dest: Path, pin: bool) -> float:
    cmd = [
        str(DIAMOND), "blastp", "--db", str(db), "--query", str(query), "--out", str(dest),
        "--min-score", "40", "-k", "0", "--motif-masking", "0", "-b", "2.0",
        "--comp-based-stats", "1", "--threads", "8",
        "--outfmt", "6", *OUTFMT,
    ]
    if pin:
        cmd.extend(["--dbsize", "209017843"])
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"blastp failed {(proc.stderr or proc.stdout)[-500:]}")
    return time.perf_counter() - t0


def main() -> None:
    if shutil.disk_usage(WORK.parent).free < 8 * 1024**3:
        raise SystemExit("stop: disk")
    WORK.mkdir(parents=True, exist_ok=True)
    recs = records(QUERY_GZ)
    draw = sorted(random.Random(20261029).sample(range(len(recs)), 2000))
    query = WORK / "q.faa"
    query.write_text("".join(recs[i] for i in draw))
    log(f"queries {len(draw)} of {len(recs)}")
    stock_wall = blast(SPROT, query, WORK / "stock.m8", False)
    stock = (WORK / "stock.m8").read_text()
    u_ids = {line.split()[1] for line in body_lines(stock)}
    log(f"stock {stock_wall:.1f}s subjects {len(u_ids)} rows {len(body_lines(stock))}")
    order: list[str] = []
    with gzip.open(SPROT, "rt") as fh, (WORK / "U.faa").open("w") as out:
        keep = False
        for line in fh:
            if line.startswith(">"):
                name = line[1:].split()[0]
                order.append(name)
                keep = name in u_ids
            if keep:
                out.write(line)
    mk = subprocess.run(
        [str(DIAMOND), "makedb", "--in", str(WORK / "U.faa"), "--db", str(WORK / "U.faa"), "--threads", "8"],
        check=False, capture_output=True, text=True,
    )
    if mk.returncode != 0:
        raise SystemExit(f"makedb {(mk.stderr or '')[-400:]}")
    replay_wall = blast(WORK / "U.faa", query, WORK / "R.m8", True)
    replay = (WORK / "R.m8").read_text()
    log(f"replay {replay_wall:.1f}s rows {len(body_lines(replay))}")
    entries = [SimpleNamespace(primary=name) for name in order]
    pad = neighbor_ids(entries, u_ids)
    with gzip.open(SPROT, "rt") as fh, (WORK / "UP.faa").open("w") as out:
        keep = False
        want = u_ids | pad
        for line in fh:
            if line.startswith(">"):
                keep = line[1:].split()[0] in want
            if keep:
                out.write(line)
    mk = subprocess.run(
        [str(DIAMOND), "makedb", "--in", str(WORK / "UP.faa"), "--db", str(WORK / "UP.faa"), "--threads", "8"],
        check=False, capture_output=True, text=True,
    )
    if mk.returncode != 0:
        raise SystemExit(f"makedb pad {(mk.stderr or '')[-400:]}")
    plus_wall = blast(WORK / "UP.faa", query, WORK / "Rplus.m8", True)
    verdict = judge(replay, (WORK / "Rplus.m8").read_text(), u_ids, pad, 1)
    stock_rows = body_lines(stock)
    replay_rows = body_lines(replay)
    report = {
        "note": "DX3 m8 files were absent. This regenerates the locked draw (seed 20261029, 2000 from GCF_001515725.1).",
        "queries": 2000,
        "records": len(recs),
        "stock_rows": len(stock_rows),
        "replay_rows": len(replay_rows),
        "bodies_equal": stock_rows == replay_rows,
        "candidate_subjects": len(u_ids),
        "neighbors": len(pad),
        "stock_wall_s": stock_wall,
        "replay_wall_s": replay_wall,
        "neighbor_wall_s": plus_wall,
        "verdict": verdict,
        "refused": not verdict["pass"],
    }
    dest = PIPE / "results/exact_replay/costpass_dx3_regen.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    log(f"refused={report['refused']} equal={report['bodies_equal']} mode={verdict['fail_mode']}")
    shutil.rmtree(WORK)


if __name__ == "__main__":
    main()
