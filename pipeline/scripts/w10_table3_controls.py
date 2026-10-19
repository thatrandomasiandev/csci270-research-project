#!/usr/bin/env python3
"""Rerun the paper's Table 3 controls under the current judge.

Threads are 2 for DIAMOND and 1 for HMMER. The neighbor pad refuses
before the exact-mode audit, so a pad refusal does not exercise the
cold-cache audit. The HMMER correct arm is the pad check on the stored
stock body. Laptop wall times are not a speed claim.
"""

from __future__ import annotations

import gzip
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "scripts"))

import costpass_controls_rerun as controls  # noqa: E402
import costpass_dx3_regen as dx3  # noqa: E402
import costpass_ic2_pilot as ic2  # noqa: E402
from acts.exact_certificate import judge, neighbor_ids  # noqa: E402
from acts.provenance import provenance  # noqa: E402
from acts.reference_run import body_lines  # noqa: E402

DIAMOND = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/builds/diamond-2.2.5/diamond")
SPROT = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data/swissprot/uniprot_sprot_2026_03.fasta.gz")
SPROT_DB = SPROT.with_suffix(SPROT.suffix + ".dmnd")
WORK = Path.home() / "tmp" / "tare_w10" / "controls"
OUT = PIPE / "results" / "adversarial" / "controls_v2.json"
OUTFMT = [
    "qseqid", "sseqid", "pident", "length", "mismatch", "gapopen",
    "qstart", "qend", "sstart", "send", "evalue", "bitscore",
]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def blast(db: Path, query: Path, dest: Path, *, pin: bool, threads: int = 2) -> float:
    cmd = [
        str(DIAMOND), "blastp", "--db", str(db), "--query", str(query), "--out", str(dest),
        "--min-score", "40", "-k", "0", "--motif-masking", "0", "-b", "2.0",
        "--comp-based-stats", "1", "--threads", str(threads),
        "--outfmt", "6", *OUTFMT,
    ]
    if pin:
        cmd.extend(["--dbsize", "209017843"])
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"blastp failed {(proc.stderr or proc.stdout)[-500:]}")
    return time.perf_counter() - t0


def makedb(fasta: Path) -> None:
    proc = subprocess.run(
        [str(DIAMOND), "makedb", "--in", str(fasta), "--db", str(fasta), "--threads", "2"],
        check=False, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"makedb failed {(proc.stderr or '')[-400:]}")


def dx2() -> dict:
    log("dx2 known-bad")
    dest = WORK / "dx2"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    u_ids = []
    for line in (ic2.DX2 / "e1_U.faa").read_text().splitlines():
        if line.startswith(">"):
            u_ids.append(line[1:].split()[0])
    u_set = set(u_ids)
    replay = (ic2.DX2 / "e1_R.m8").read_text()
    cand = controls.pairs(replay)
    order = []
    with gzip.open(SPROT, "rt") as handle:
        for line in handle:
            if line.startswith(">"):
                order.append(line[1:].split()[0])
    entries = [SimpleNamespace(primary=name) for name in order]
    _expanded, pad, shipped_u, overlap = controls.shipped_neighbor(entries, cand)
    union_pad = neighbor_ids(entries, u_set)
    controls.write_fasta_subset(SPROT, u_set | union_pad | pad, dest / "db.faa")
    makedb(dest / "db.faa")
    wall = blast(dest / "db.faa", ic2.DX2 / "e1_q.faa", dest / "plus.m8", pin=True)
    verdict = judge(replay, (dest / "plus.m8").read_text(), shipped_u, pad, 1)
    log(f"dx2 {wall:.1f}s pass={verdict['pass']} {verdict['fail_mode']}")
    shutil.rmtree(dest)
    return {
        "arm": "diamond-known-bad-6",
        "expected": "refuse",
        "refused": not verdict["pass"],
        "fail_mode": verdict["fail_mode"],
        "wall_s": wall,
        "threads": 2,
        "pad_subjects": len(pad),
        "overlap_removed": len(overlap),
        "audit_reached": False,
        "why_audit_not_reached": "neighbor pad refuses before the exact-mode audit",
    }


def dx3_arm(order: list[str]) -> dict:
    log("dx3 22-line")
    dest = WORK / "dx3"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    recs = dx3.records(dx3.QUERY_GZ)
    draw = sorted(random.Random(20261029).sample(range(len(recs)), 2000))
    query = dest / "q.faa"
    query.write_text("".join(recs[i] for i in draw))
    if not SPROT_DB.is_file():
        raise SystemExit(f"missing {SPROT_DB}")
    stock_wall = blast(SPROT_DB, query, dest / "stock.m8", pin=False)
    stock = (dest / "stock.m8").read_text()
    u_from_stock = {line.split()[1] for line in body_lines(stock)}
    controls.write_fasta_subset(SPROT, u_from_stock, dest / "U.faa")
    makedb(dest / "U.faa")
    replay_wall = blast(dest / "U.faa", query, dest / "R.m8", pin=True)
    replay = (dest / "R.m8").read_text()
    cand = controls.pairs(replay)
    entries = [SimpleNamespace(primary=name) for name in order]
    _expanded, pad, shipped_u, overlap = controls.shipped_neighbor(entries, cand)
    union_pad = neighbor_ids(entries, u_from_stock)
    controls.write_fasta_subset(SPROT, u_from_stock | union_pad | pad, dest / "UP.faa")
    makedb(dest / "UP.faa")
    plus_wall = blast(dest / "UP.faa", query, dest / "Rplus.m8", pin=True)
    verdict = judge(replay, (dest / "Rplus.m8").read_text(), shipped_u, pad, 1)
    stock_rows = body_lines(stock)
    replay_rows = body_lines(replay)
    log(
        f"dx3 stock {len(stock_rows)} replay {len(replay_rows)} "
        f"pass={verdict['pass']} {verdict['fail_mode']}"
    )
    missing = len(stock_rows) - len(replay_rows)
    report = {
        "arm": "diamond-22-line",
        "expected": "refuse",
        "seed": 20261029,
        "queries": 2000,
        "genome": "GCF_001515725.1",
        "stock_rows": len(stock_rows),
        "replay_rows": len(replay_rows),
        "row_delta": missing,
        "refused": not verdict["pass"],
        "fail_mode": verdict["fail_mode"],
        "stock_wall_s": stock_wall,
        "replay_wall_s": replay_wall,
        "plus_wall_s": plus_wall,
        "threads": 2,
        "audit_reached": False,
        "why_audit_not_reached": "neighbor pad refuses before the exact-mode audit",
        "overlap_removed": len(overlap),
    }
    shutil.rmtree(dest)
    return report


def hmmer() -> dict:
    """Same pad/judge procedure as residue_budget_controls.json, at 1 thread.

    The correct arm passes when the candidate replay is byte-identical to
    the stored stock body and the neighbor pad and the size-50 random pads
    pass. The 5% drop must refuse. This path is judge(), which runs before
    the exact-mode audit, so a pad decision does not enter the audit.
    """
    log("hmmer controls")
    controls.WORK = WORK / "hmm_parent"
    ic2.CPU = "1"
    body = controls.hmm_arms()
    inject = body["injected_drop_sample_50"]
    good = body["good_sample_50"]
    report = {
        "arm": "hmmer-GCF_013315695.1",
        "expected_correct": "pass",
        "expected_drop": "refuse",
        "correct_passed": bool(body["pass"] and body["byte_identical"] and not good["refused"]),
        "drop_refused": bool(inject["refused"]),
        "oracle_byte_identical": body["oracle_byte_identical"],
        "neighbor_pass": body["neighbor_pass"],
        "stock_tbl_lines": body["stock_tbl_lines"],
        "stock_dom_lines": body["stock_dom_lines"],
        "dropped_models": inject["dropped_models"],
        "inject_modes": inject["modes"],
        "inject_sample_hits_affected": inject["sample_hits_affected"],
        "good_modes": good["modes"],
        "good_refused": good["refused"],
        "threads": 1,
        "cpu": ic2.CPU,
        "audit_reached": False,
        "why_audit_not_reached": (
            "Table 3's HMMER rows are the pad/judge on the stored stock body; "
            "judge() returns before the exact-mode audit"
        ),
        "oracle_wall_s": body["oracle_wall_s"],
        "neighbor_wall_s": body["neighbor"]["wall_s"],
        "inject_scan_wall_s": inject["scan_wall_s"],
        "inject_pad_wall_s": inject["wall_s"],
        "good_pad_wall_s": good["wall_s"],
    }
    shutil.rmtree(controls.WORK, ignore_errors=True)
    log(
        f"hmmer correct_passed={report['correct_passed']} "
        f"drop_refused={report['drop_refused']} modes={inject['modes']}"
    )
    return report


def main() -> None:
    try:
        os.nice(10)
    except OSError:
        pass
    arm = sys.argv[1] if len(sys.argv) > 1 else "dx2"
    WORK.mkdir(parents=True, exist_ok=True)
    block = provenance()
    if arm == "dx2":
        payload = dx2()
    elif arm == "dx3":
        order = []
        with gzip.open(SPROT, "rt") as handle:
            for line in handle:
                if line.startswith(">"):
                    order.append(line[1:].split()[0])
        payload = dx3_arm(order)
    elif arm == "hmmer":
        payload = hmmer()
    else:
        raise SystemExit("usage: w10_table3_controls.py dx2|dx3|hmmer")
    payload["git_head"] = block["git"]
    payload["host"] = block["host"]
    dest = OUT if arm == "dx2" else OUT.with_name(f"controls_v2_{arm}.json")
    if arm == "dx2" and OUT.is_file():
        prior = json.loads(OUT.read_text())
    else:
        prior = {}
    if arm == "dx2":
        prior["dx2"] = payload
        OUT.write_text(json.dumps(prior, indent=2) + "\n")
        log(f"wrote {OUT}")
    else:
        dest.write_text(json.dumps(payload, indent=2) + "\n")
        log(f"wrote {dest}")


if __name__ == "__main__":
    main()
