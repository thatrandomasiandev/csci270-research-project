#!/usr/bin/env python3
"""Pilot the cheap safety check. Not a measured result.

Neighbor pad on every replayed record. Three random pads on a fixed-seed
sample. HMMER uses the GCF_013315695.1 pilot bodies already on disk.
DX2 uses the stored known-bad replay and a fresh neighbor-pad search.
"""
from __future__ import annotations

import gzip
import json
import math
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

from acts.exact_certificate import judge, neighbor_ids, pad_indices, sample_keys  # noqa: E402
from acts.reference_run import body_lines  # noqa: E402
from acts.replay_batch import merge_bodies, plan_batches  # noqa: E402

WORK = Path("/Users/joshuaterranova/tmp/costpass_work")
HMMER = Path("/opt/homebrew/bin")
DIAMOND = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/builds/diamond-2.2.5/diamond")
DX2 = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data/reference_diamond_dx2/measured")
SPROT = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data/swissprot/uniprot_sprot_2026_03.fasta.gz")
PFAM = WORK / "pfam38.2.hmm"
QUERIES = WORK / "GCF_013315695.1.faa"
Z = "30134"
CPU = "4"
SAMPLE_SEED = 20261034
SIZES = (50, 100, 200)


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def names_in_order(hmm: Path) -> list[str]:
    names: list[str] = []
    name = None
    with hmm.open() as fh:
        for line in fh:
            if line.startswith("NAME "):
                name = line.split(None, 1)[1].strip()
            elif line.startswith("//") and name:
                names.append(name)
                name = None
    return names


def model_spans(hmm: Path) -> dict[str, tuple[int, int]]:
    spans: dict[str, tuple[int, int]] = {}
    start = None
    name = None
    with hmm.open(newline="") as fh:
        while True:
            line = fh.readline()
            if not line:
                break
            if line.startswith("HMMER3/"):
                start = fh.tell() - len(line)
                name = None
            elif line.startswith("NAME ") and start is not None:
                name = line.split(None, 1)[1].strip()
            elif line.startswith("//") and name and start is not None:
                spans[name] = (start, fh.tell())
                start = None
                name = None
    return spans


def fasta_spans(path: Path) -> tuple[list[str], dict[str, tuple[int, int]]]:
    order: list[str] = []
    spans: dict[str, tuple[int, int]] = {}
    with path.open(newline="") as fh:
        start = None
        key = None
        while True:
            pos = fh.tell()
            line = fh.readline()
            if not line:
                if key is not None and start is not None:
                    spans[key] = (start, pos)
                break
            if line.startswith(">"):
                if key is not None and start is not None:
                    spans[key] = (start, pos)
                key = line[1:].split()[0]
                start = pos
                order.append(key)
    return order, spans


def write_span(src: Path, spans: list[tuple[int, int]], dest: Path) -> None:
    with src.open("rb") as inp, dest.open("wb") as out:
        for a, b in spans:
            inp.seek(a)
            out.write(inp.read(b - a))


def scan_batches(order, cand, mspans, fspans, dest: Path) -> tuple[str, str, float]:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir()
    keys = [key for key in order if cand.get(key)]
    batches = plan_batches(keys, cand, startup_pairs=2000.0, press_pairs=84.0)
    tbl_parts: list[str] = []
    dom_parts: list[str] = []
    t0 = time.perf_counter()
    for index, batch in enumerate(batches):
        work = dest / f"b{index}"
        work.mkdir()
        union = sorted({model for key in batch for model in cand[key]}, key=lambda name: mspans[name][0])
        write_span(PFAM, [mspans[name] for name in union], work / "db.hmm")
        write_span(QUERIES, [fspans[key] for key in batch], work / "q.faa")
        press = subprocess.run([str(HMMER / "hmmpress"), "-f", str(work / "db.hmm")], check=False, capture_output=True)
        if press.returncode != 0:
            raise SystemExit("hmmpress failed")
        cmd = [
            str(HMMER / "hmmscan"), "-Z", Z, "--cut_ga", "--noali", "--cpu", CPU,
            "--tblout", str(work / "tbl"), "--domtblout", str(work / "dom"),
            "-o", os.devnull, str(work / "db.hmm"), str(work / "q.faa"),
        ]
        proc = subprocess.run(cmd, check=False, capture_output=True)
        if proc.returncode != 0:
            raise SystemExit(f"hmmscan failed {proc.returncode}")
        tbl_parts.append((work / "tbl").read_text())
        dom_parts.append((work / "dom").read_text())
        shutil.rmtree(work)
    wall = time.perf_counter() - t0
    return merge_bodies(tbl_parts, 2, keys), merge_bodies(dom_parts, 3, keys), wall


def filter_text(text: str, record_col: int, keep: set[str]) -> str:
    lines = []
    for line in text.splitlines(keepends=True):
        if not line.strip() or line.startswith("#"):
            lines.append(line)
            continue
        cells = line.split()
        if record_col < len(cells) and cells[record_col] in keep:
            lines.append(line)
    return "".join(lines)


def hits(text: str, record_col: int) -> dict[str, set[str]]:
    cand: dict[str, set[str]] = {}
    for line in body_lines(text):
        fields = line.split()
        cand.setdefault(fields[record_col], set()).add(fields[0])
    return cand


def p_miss(n: int, k: int, s: int, q: float) -> float:
    """Random-pad miss rate for one coupling entry that affects k of n records.

    The sample misses every affected record, or it hits one and all three
    pads miss the entry. q is the chance one pad contains the entry.
    """
    if s > n:
        s = n
    if s <= n - k:
        miss_records = math.comb(n - k, s) / math.comb(n, s)
    else:
        miss_records = 0.0
    miss_entry = (1.0 - q) ** 3
    return miss_records + (1.0 - miss_records) * miss_entry


def hmm_arm() -> dict:
    log("hmm index")
    order_models = names_in_order(PFAM)
    entries = [SimpleNamespace(primary=name) for name in order_models]
    mspans = model_spans(PFAM)
    qorder, fspans = fasta_spans(QUERIES)
    oracle_tbl = (WORK / "batch_oracle" / "tblout").read_text()
    oracle_dom = (WORK / "batch_oracle" / "domtblout").read_text()
    cand = hits(oracle_tbl, 2)
    expanded = {key: set(ids) | neighbor_ids(entries, ids) for key, ids in cand.items()}
    log(f"neighbor pad records={len(expanded)}")
    tbl, dom, wall = scan_batches(qorder, expanded, mspans, fspans, WORK / "ic2_neighbor")
    u_ids = {name for ids in cand.values() for name in ids}
    pad_ids = {name for ids in expanded.values() for name in ids} - u_ids
    neighbor = {
        "wall_s": wall,
        "load": [round(v, 2) for v in os.getloadavg()],
        "tbl": judge(oracle_tbl, tbl, u_ids, pad_ids, 0),
        "dom": judge(oracle_dom, dom, u_ids, pad_ids, 0),
    }
    log(f"neighbor {wall:.1f}s tbl={neighbor['tbl']['fail_mode']} dom={neighbor['dom']['fail_mode']}")
    inject_tbl = (WORK / "batch_inject" / "tblout").read_text()
    inject_dom = (WORK / "batch_inject" / "domtblout").read_text()
    reduced = hits(inject_tbl, 2)
    # Records that lost a model: present in the oracle, absent or smaller in the inject.
    affected = [key for key in cand if cand[key] - reduced.get(key, set())]
    log(f"inject affected records {len(affected)}")
    sizes = {}
    for size in SIZES:
        sample = sample_keys([key for key in qorder if key in reduced or key in cand], size, SAMPLE_SEED)
        keep = set(sample)
        # Pads from the reduced union, so a dropped model is eligible.
        u_red = {name for ids in reduced.values() for name in ids}
        entry_ids = [entry.primary for entry in entries]
        pads = pad_indices(entries, u_red)
        t0 = time.perf_counter()
        refused = False
        modes = []
        for name, indices in pads:
            if name == "neighbor":
                continue
            pad = {entry_ids[i] for i in indices}
            sample_cand = {key: set(reduced.get(key, set())) | pad for key in sample if key in reduced or key in cand}
            plus_tbl, plus_dom, _wall = scan_batches(
                sample, sample_cand, mspans, fspans, WORK / f"ic2_pad_{size}_{name}"
            )
            for kind, replay, plus, col in (
                ("tbl", inject_tbl, plus_tbl, 2),
                ("dom", inject_dom, plus_dom, 3),
            ):
                verdict = judge(filter_text(replay, col, keep), plus, u_red, pad, 0)
                modes.append(verdict["fail_mode"])
                if not verdict["pass"]:
                    refused = True
        sizes[str(size)] = {
            "wall_s": time.perf_counter() - t0,
            "refused": refused,
            "modes": modes,
            "sample_hits_affected": len(keep & set(affected)),
        }
        log(f"sample {size} refused={refused} wall={sizes[str(size)]['wall_s']:.1f}s modes={modes}")
    # Good replay must not be refused by the same pads.
    good = {}
    size = 200
    sample = sample_keys([key for key in qorder if key in cand], size, SAMPLE_SEED)
    keep = set(sample)
    u_ids = {name for ids in cand.values() for name in ids}
    pads = pad_indices(entries, u_ids)
    t0 = time.perf_counter()
    refused = False
    for name, indices in pads:
        if name == "neighbor":
            continue
        pad = {order_models[i] for i in indices}
        sample_cand = {key: set(cand[key]) | pad for key in sample if key in cand}
        plus_tbl, plus_dom, _wall = scan_batches(sample, sample_cand, mspans, fspans, WORK / f"ic2_good_{name}")
        for replay, plus, col in ((oracle_tbl, plus_tbl, 2), (oracle_dom, plus_dom, 3)):
            verdict = judge(filter_text(replay, col, keep), plus, u_ids, pad, 0)
            if not verdict["pass"]:
                refused = True
                good["fail_mode"] = verdict["fail_mode"]
    good["wall_s"] = time.perf_counter() - t0
    good["refused"] = refused
    log(f"good sample refused={refused}")
    q = 137090 / 438658
    curve = {
        str(s): p_miss(2000, 22, s, q) for s in (20, 50, 100, 200, 400, 2000)
    }
    return {
        "neighbor": neighbor,
        "inject_affected_records": len(affected),
        "inject_samples": sizes,
        "good_sample_200": good,
        "dx3_random_pad_miss": {
            "k": 22,
            "n": 2000,
            "q": q,
            "one_entry_three_pads": (1 - q) ** 3,
            "p_miss_by_sample": curve,
            "note": "This is the random-pad miss rate for one non-neighbor entry. File-order neighbors are in the neighbor pad, so that class is caught on every record.",
        },
    }


def dx2_arm() -> dict:
    log("dx2 neighbor")
    u_ids: list[str] = []
    for line in (DX2 / "e1_U.faa").read_text().splitlines():
        if line.startswith(">"):
            u_ids.append(line[1:].split()[0])
    u_set = set(u_ids)
    order: list[str] = []
    with gzip.open(SPROT, "rt") as fh:
        for line in fh:
            if line.startswith(">"):
                order.append(line[1:].split()[0])
    entries = [SimpleNamespace(primary=name) for name in order]
    pad = neighbor_ids(entries, u_set)
    log(f"dx2 U={len(u_set)} neighbors={len(pad)}")
    # Write U plus neighbors by streaming swissprot once.
    dest = WORK / "ic2_dx2"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir()
    want = u_set | pad
    with gzip.open(SPROT, "rt") as fh, (dest / "db.faa").open("w") as out:
        keep = False
        for line in fh:
            if line.startswith(">"):
                keep = line[1:].split()[0] in want
            if keep:
                out.write(line)
    t0 = time.perf_counter()
    mk = subprocess.run(
        [str(DIAMOND), "makedb", "--in", str(dest / "db.faa"), "--db", str(dest / "db.faa"), "--threads", "8"],
        check=False, capture_output=True, text=True,
    )
    if mk.returncode != 0:
        raise SystemExit(f"makedb failed {(mk.stderr or '')[-400:]}")
    out_m8 = dest / "plus.m8"
    cmd = [
        str(DIAMOND), "blastp", "--db", str(dest / "db.faa"), "--query", str(DX2 / "e1_q.faa"),
        "--out", str(out_m8), "--min-score", "40", "-k", "0", "--motif-masking", "0",
        "-b", "2.0", "--comp-based-stats", "1", "--threads", "8", "--dbsize", "209017843",
        "--outfmt", "6", "qseqid", "sseqid", "pident", "length", "mismatch", "gapopen",
        "qstart", "qend", "sstart", "send", "evalue", "bitscore",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"blastp failed {(proc.stderr or '')[-400:]}")
    wall = time.perf_counter() - t0
    replay = (DX2 / "e1_R.m8").read_text()
    plus = out_m8.read_text()
    verdict = judge(replay, plus, u_set, pad, 1)
    log(f"dx2 {wall:.1f}s {verdict['fail_mode']} pass={verdict['pass']}")
    # Drop the fasta and the database. The verdict is what we keep.
    shutil.rmtree(dest)
    return {"wall_s": wall, "neighbors": len(pad), "verdict": verdict, "refused": not verdict["pass"]}


def main() -> None:
    free = shutil.disk_usage(WORK).free
    if free < 8 * 1024**3:
        raise SystemExit(f"stop: {free} bytes free")
    report = {"hmm": hmm_arm(), "dx2": dx2_arm()}
    dest = PIPE / "results/exact_replay/costpass_ic2_pilot.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    log(f"wrote {dest}")


if __name__ == "__main__":
    main()
