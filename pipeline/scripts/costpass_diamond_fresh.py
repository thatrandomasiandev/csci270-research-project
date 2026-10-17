#!/usr/bin/env python3
"""Fresh DIAMOND sample for the shipped batched check. A pilot, not DX2/DX3.

Genome and 300 queries are drawn with seed 20261016 from recurrence/A,
excluding the DX2, DX3, and locked HMMER proteomes. The replay is the
same batch plan the CLI uses. The check is the neighbor pad on every
replayed query plus three random pads on 50 queries.
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

from acts.audit import residue_cap_binds  # noqa: E402
from acts.exact_certificate import judge, neighbor_ids, pad_indices, sample_keys  # noqa: E402
from acts.reference_run import body_lines  # noqa: E402
from acts.replay_batch import merge_bodies, plan_batches  # noqa: E402

DATA = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data")
DIAMOND = DATA.parent / "builds" / "diamond-2.2.5" / "diamond"
SPROT_GZ = DATA / "swissprot" / "uniprot_sprot_2026_03.fasta.gz"
WORK = Path("/Users/joshuaterranova/tmp/costpass_work/diamond_fresh")
OUTFMT = ["qseqid", "sseqid", "pident", "length", "mismatch", "gapopen", "qstart", "qend", "sstart", "send", "evalue", "bitscore"]
EXCLUDE = {
    "GCF_002853805.1_protein.faa.gz",
    "GCF_002090355.1_protein.faa.gz",
    "GCF_001515725.1_protein.faa.gz",
    "GCF_001513615.1_protein.faa.gz",
    "GCF_016806025.1_protein.faa.gz",
    "GCF_017165095.1_protein.faa.gz",
    "GCF_013315695.1_protein.faa.gz",
}


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def blast(db: Path, query: Path, dest: Path, pin: bool) -> None:
    cmd = [
        str(DIAMOND), "blastp", "--db", str(db), "--query", str(query), "--out", str(dest),
        "--min-score", "40", "-k", "0", "--motif-masking", "0", "-b", "2.0",
        "--comp-based-stats", "1", "--threads", "8", "--outfmt", "6", *OUTFMT,
    ]
    if pin:
        cmd.extend(["--dbsize", "209017843"])
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit((proc.stderr or proc.stdout)[-500:])


def main() -> None:
    seed = 20261016
    out_name = "costpass_diamond_fresh.json"
    argv = sys.argv[1:]
    if "--seed" in argv:
        seed = int(argv[argv.index("--seed") + 1])
    if "--out" in argv:
        out_name = argv[argv.index("--out") + 1]
    if seed != 20261016:
        EXCLUDE.add("GCF_013085185.1_protein.faa.gz")
    if shutil.disk_usage("/Users/joshuaterranova/tmp").free < 8 * 1024**3:
        raise SystemExit("stop: disk")
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir()
    pool = sorted(p.name for p in (DATA / "recurrence" / "A").glob("*.faa.gz") if p.name not in EXCLUDE)
    genome = random.Random(seed).choice(pool)
    log(f"genome {genome}")
    recs: list[str] = []
    with gzip.open(DATA / "recurrence" / "A" / genome, "rt") as fh:
        buf: list[str] = []
        for line in fh:
            if line.startswith(">") and buf:
                recs.append("".join(buf))
                buf = []
            buf.append(line)
        if buf:
            recs.append("".join(buf))
    k = min(300, len(recs))
    draw = sorted(random.Random(seed).sample(range(len(recs)), k))
    query = WORK / "q.faa"
    query.write_text("".join(recs[i] for i in draw))
    qkeys = [recs[i].split()[0][1:] for i in draw]
    log(f"stock {k} queries")
    t0 = time.perf_counter()
    blast(SPROT_GZ, query, WORK / "stock.m8", False)
    stock_wall = time.perf_counter() - t0
    stock = (WORK / "stock.m8").read_text()
    cand: dict[str, set[str]] = {}
    for line in body_lines(stock):
        fields = line.split()
        cand.setdefault(fields[0], set()).add(fields[1])
    log("index swissprot")
    fasta = WORK / "sprot.faa"
    with gzip.open(SPROT_GZ, "rb") as inp, fasta.open("wb") as out:
        shutil.copyfileobj(inp, out, length=1 << 20)
    order: list[str] = []
    spans: dict[str, tuple[int, int]] = {}
    with fasta.open(newline="") as fh:
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
    entries = [SimpleNamespace(primary=name) for name in order]

    def search(groups: dict[str, set[str]], keys: list[str], dest: Path, pin: bool) -> tuple[str, float]:
        dest.mkdir(parents=True)
        batches = plan_batches(keys, groups, startup_pairs=2000.0, press_pairs=84.0)
        parts: list[str] = []
        t0 = time.perf_counter()
        for index, batch in enumerate(batches):
            work = dest / f"b{index}"
            work.mkdir()
            union = [name for name in order if any(name in groups[key] for key in batch)]
            with fasta.open("rb") as inp, (work / "db.faa").open("wb") as out:
                for name in union:
                    a, b = spans[name]
                    inp.seek(a)
                    out.write(inp.read(b - a))
            (work / "q.faa").write_text("".join(recs[draw[qkeys.index(key)]] for key in batch))
            mk = subprocess.run(
                [str(DIAMOND), "makedb", "--in", str(work / "db.faa"), "--db", str(work / "db.faa"), "--threads", "8"],
                check=False, capture_output=True, text=True,
            )
            if mk.returncode != 0:
                raise SystemExit(f"makedb {(mk.stderr or '')[-300:]}")
            blast(work / "db.faa", work / "q.faa", work / "out.m8", pin)
            parts.append((work / "out.m8").read_text())
            shutil.rmtree(work)
        return merge_bodies(parts, 0, keys), time.perf_counter() - t0

    replay_keys = [key for key in qkeys if cand.get(key)]
    log(f"replay records {len(replay_keys)}")
    replay, replay_wall = search(cand, replay_keys, WORK / "replay", True)
    equal = body_lines(replay) == body_lines(stock)
    log(f"replay equal={equal} wall={replay_wall:.1f}s")
    expanded = {key: set(ids) | neighbor_ids(entries, ids) for key, ids in cand.items()}
    neighbor_pad = {name for ids in expanded.values() for name in ids} - {name for ids in cand.values() for name in ids}
    plus, neighbor_wall = search(expanded, replay_keys, WORK / "neighbor", True)
    u_ids = {name for ids in cand.values() for name in ids}
    neighbor_verdict = judge(replay, plus, u_ids, neighbor_pad, 1)
    query_lengths = []
    by_key = {}
    for index in draw:
        text = recs[index]
        header, _, body = text.partition("\n")
        by_key[header.split()[0][1:]] = sum(len(line.strip()) for line in body.splitlines())
    query_lengths = [by_key[key] for key in replay_keys]
    if residue_cap_binds(query_lengths):
        raise SystemExit("stop: residue cap bound on the DIAMOND queries; the locked draw would change")
    sample = sample_keys(replay_keys, 50, 20261034)
    keep = set(sample)
    random_refused = False
    random_modes = []
    t0 = time.perf_counter()
    for name, indices in pad_indices(entries, u_ids):
        if not name.startswith("random") or not indices:
            continue
        pad = {order[i] for i in indices}
        sample_cand = {key: set(cand.get(key, set())) | pad for key in sample}
        got, _wall = search(sample_cand, sample, WORK / name, True)
        verdict = judge(
            "\n".join(line for line in body_lines(replay) if line.split()[0] in keep) + "\n",
            got,
            u_ids,
            pad,
            1,
        )
        random_modes.append(verdict["fail_mode"])
        random_refused = random_refused or not verdict["pass"]
    random_wall = time.perf_counter() - t0
    refused = (not neighbor_verdict["pass"]) or random_refused
    if equal and not refused:
        outcome = "EXACT"
    elif (not equal) and refused:
        outcome = "SAFE-REFUSE"
    elif (not equal) and not refused:
        outcome = "UNSAFE"
    else:
        outcome = "SAFE-REFUSE"
    report = {
        "genome": genome,
        "seed": seed,
        "queries": k,
        "stock_rows": len(body_lines(stock)),
        "replay_rows": len(body_lines(replay)),
        "bodies_equal": equal,
        "stock_wall_s": stock_wall,
        "replay_wall_s": replay_wall,
        "neighbor_wall_s": neighbor_wall,
        "neighbor": neighbor_verdict,
        "random_modes": random_modes,
        "random_wall_s": random_wall,
        "refused": refused,
        "outcome": outcome,
        "load": [round(v, 2) for v in os.getloadavg()],
    }
    dest = PIPE / "results/exact_replay" / out_name
    dest.write_text(json.dumps(report, indent=2) + "\n")
    log(f"outcome {outcome}")
    shutil.rmtree(WORK)
    if outcome == "UNSAFE":
        raise SystemExit("stop: UNSAFE")


if __name__ == "__main__":
    main()
