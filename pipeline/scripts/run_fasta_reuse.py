#!/usr/bin/env python3
"""Populate FASTA→table cache on genome 1, reuse on a renamed genome 2.

Locked by docs/INFERENCE_PROTOCOL.md addendum 2026-09-27. Local only.
Writes results/inference_fasta_reuse.json. No speedup numbers.
"""

from __future__ import annotations

import gzip
import json
import random
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.cache import RecordCache
from acts.fasta import FastaRec, parse_fasta, seq_key, write_fasta
from acts.fasta_memo import cached_search, contract_path_for, prepare_table_contract
from acts.infer_fasta import InferError, run_table_tool
from acts.table import body_lines, tables_match, ws_line

SEED = 20260927
N = 500
MODEL_NAMES = (
    "ABC_tran",
    "GTP_EFTU",
    "Response_reg",
    "AAA",
    "HATPase_c",
    "Helicase_C",
)
WIDTHS = (1, 2, 3, 4, 6, 8)
FAA = ROOT / "data" / "kprot" / "MG1655.faa.gz"
HMM_GZ = ROOT / "data" / "hmmer" / "Pfam-A.hmm.gz"
ACCESSIONS = ROOT / "results" / "recurrence_accessions.json"
OUT = ROOT / "results" / "inference_fasta_reuse.json"
EMIT = [sys.executable, str(ROOT / "scripts" / "emit_side_table.py")]


def load_faa(path: Path) -> list[FastaRec]:
    return parse_fasta(gzip.open(path, "rt").read())


def synthetic_names(prefix: str, n: int, rng: random.Random) -> list[str]:
    nums = list(range(n))
    rng.shuffle(nums)
    names: list[str] = []
    for k, num in enumerate(nums):
        w = WIDTHS[k % len(WIDTHS)]
        names.append(f"{prefix}_{num:0{w}d}")
    return names


def rename(recs: list[FastaRec], prefix: str, rng: random.Random) -> list[FastaRec]:
    return [
        FastaRec(name, "", rec.seq)
        for rec, name in zip(recs, synthetic_names(prefix, len(recs), rng))
    ]


def pick_genome2(genome1: list[FastaRec], assemblies: list[dict]) -> tuple[dict, list[FastaRec], int]:
    keys1 = {rec.key for rec in genome1}
    lo, hi = int(0.30 * N), int(0.70 * N)
    for asm in assemblies:
        path = ROOT / asm["path"]
        if not path.is_file():
            continue
        recs = load_faa(path)
        seen: set[str] = set()
        shared: list[FastaRec] = []
        novel: list[FastaRec] = []
        for rec in recs:
            k = rec.key
            if k in seen:
                continue
            seen.add(k)
            if k in keys1:
                shared.append(rec)
            else:
                novel.append(rec)
        if len(shared) < lo:
            continue
        rng_share = random.Random(SEED + 1)
        if len(shared) > hi:
            shared = rng_share.sample(shared, 350)
        need = N - len(shared)
        if len(novel) < need:
            continue
        rng_fill = random.Random(SEED + 2)
        chosen = shared + rng_fill.sample(novel, need)
        rng_fill.shuffle(chosen)
        return asm, chosen, len(shared)
    raise SystemExit("no collection-A assembly on disk with 30–70% shared keys")


def first_diffs(a: str, b: str, n: int = 5, *, multiset: bool = False) -> list[dict]:
    la, lb = body_lines(a), body_lines(b)
    out: list[dict] = []
    if multiset:
        ca, cb = Counter(map(ws_line, la)), Counter(map(ws_line, lb))
        only_a = [ln for ln in la if ca[ws_line(ln)] > cb[ws_line(ln)]]
        only_b = [ln for ln in lb if cb[ws_line(ln)] > ca[ws_line(ln)]]
        for i, (x, y) in enumerate(zip(only_a, only_b)):
            out.append({"i": i, "rebuilt": x, "stock": y})
            if len(out) == n:
                return out
        if len(la) != len(lb):
            out.append({"i": 0, "rebuilt": f"n={len(la)}", "stock": f"n={len(lb)}"})
        return out
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            out.append({"i": i, "rebuilt": x, "stock": y})
            if len(out) == n:
                return out
    if len(la) != len(lb):
        out.append({"i": min(len(la), len(lb)), "rebuilt": f"n={len(la)}", "stock": f"n={len(lb)}"})
    return out


def diagnose(diffs: list[dict]) -> str:
    if not diffs:
        return ""
    pad = order = desc = eval_ = other = 0
    for d in diffs:
        if "n=" in str(d.get("rebuilt")):
            continue
        ra, rb = d["rebuilt"].split(), d["stock"].split()
        if ra == rb:
            pad += 1
        elif Counter(ra) == Counter(rb):
            order += 1
        else:
            joined_a, joined_b = " ".join(ra), " ".join(rb)
            if any(tok in joined_a and tok not in joined_b for tok in ra[-1:]):
                desc += 1
            elif any(("e-" in x or "e+" in x) for x in ra + rb):
                eval_ += 1
            else:
                other += 1
    bits = []
    if pad:
        bits.append(f"padding ({pad})")
    if order:
        bits.append(f"ordering ({order})")
    if desc:
        bits.append(f"description ({desc})")
    if eval_:
        bits.append(f"E-value/tokens ({eval_})")
    if other:
        bits.append(f"other ({other})")
    return ", ".join(bits) or "line-count"


def empty_keys(cache: RecordCache) -> set[str]:
    out: set[str] = set()
    for rec, raw in cache._data.items():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if payload.get("rows") == []:
            out.add(rec)
    return out


def run_mode(
    name: str,
    argv: list[str],
    g1: list[FastaRec],
    g2: list[FastaRec],
    g1_path: Path,
    g2_path: Path,
    work: Path,
    keys1: set[str],
    overlap: int,
) -> dict:
    dest = work / name
    dest.mkdir(parents=True, exist_ok=True)
    cache_path = dest / "cache.jsonl"
    try:
        contract = prepare_table_contract(argv, g1, dest / "infer", cache_path)
    except InferError as exc:
        return {
            "decision": exc.decision,
            "reason": exc.reason,
            "overlap": overlap,
            "n_hits": None,
            "n_misses": None,
            "n_empty_hits": None,
            "match": None,
            "match_result": False,
        }

    cache = RecordCache(cache_path, argv=argv, kind="fasta")
    _rebuilt1, pop = cached_search(
        g1, cache, contract, argv, dest / "pop", contract_path=contract_path_for(cache_path)
    )
    cache.save()
    g1_empty = empty_keys(cache)

    rebuilt2, reuse = cached_search(
        g2, cache, contract, argv, dest / "reuse", contract_path=contract_path_for(cache_path)
    )
    cache.save()
    stock2 = run_table_tool(argv, g2_path)
    (dest / "reassembled.out").write_text(rebuilt2)
    (dest / "full.out").write_text(stock2)

    matched = tables_match(rebuilt2, stock2, contract.match, match_ws=contract.match_ws)

    empty_hit_recs = [rec for rec in g2 if rec.key in keys1 and rec.key in g1_empty]
    n_empty_hits = sum(1 for rec in empty_hit_recs if cache.get(rec.key) is not None)
    miss_path = dest / "reuse" / "miss.fa"
    miss_keys = {r.key for r in parse_fasta(miss_path.read_text())} if miss_path.is_file() else set()
    empty_called = [rec.name for rec in empty_hit_recs if rec.key in miss_keys]

    diffs = [] if matched else first_diffs(
        rebuilt2, stock2, multiset=contract.match == "multiset"
    )
    decision = "SHIP" if matched and reuse["n_cache_holes"] == 0 else "REFUSE_MATCH"
    return {
        "decision": decision,
        "reason": (
            f"MATCH {contract.match}; hits={reuse['n_hits']} misses={reuse['n_misses']}"
            if decision == "SHIP"
            else "reassembled body is not MATCH to a full run"
        ),
        "match": contract.match,
        "match_ws": contract.match_ws,
        "pad_widths": contract.pad_widths,
        "empty_desc": contract.empty_desc,
        "match_result": matched,
        "query_col": contract.query_col,
        "overlap": overlap,
        "n_hits": reuse["n_hits"],
        "n_misses": reuse["n_misses"],
        "n_empty_hits": n_empty_hits,
        "empty_hit_called_tool": empty_called,
        "populate": {
            "n_hits": pop["n_hits"],
            "n_misses": pop["n_misses"],
            "n_empty_cached": len(g1_empty),
        },
        "first_diffs": diffs,
        "diagnose": diagnose(diffs),
    }


def main() -> int:
    if not (shutil.which("hmmscan") and shutil.which("hmmsearch") and shutil.which("hmmfetch")):
        OUT.write_text(json.dumps({"status": "INCOMPLETE", "reason": "HMMER binaries missing"}, indent=2) + "\n")
        print("INCOMPLETE: HMMER binaries missing")
        return 0
    if not FAA.is_file() or not HMM_GZ.is_file() or not ACCESSIONS.is_file():
        OUT.write_text(json.dumps({"status": "INCOMPLETE", "reason": "local data missing"}, indent=2) + "\n")
        print("INCOMPLETE: local data missing")
        return 0

    acc = json.loads(ACCESSIONS.read_text())
    assemblies = acc["collections"]["A"]["genomes"]
    mg = load_faa(FAA)
    genome1 = random.Random(SEED).sample(mg, N)
    asm, genome2_raw, n_shared = pick_genome2(genome1, assemblies)
    g1 = rename(genome1, "G1", random.Random(SEED + 3))
    g2 = rename(genome2_raw, "G2", random.Random(SEED + 4))
    keys1 = {rec.key for rec in g1}
    overlap = sum(1 for rec in g2 if rec.key in keys1)

    work = Path(tempfile.mkdtemp(prefix="acts_fasta_reuse_"))
    models = work / "tiny.hmm"
    keyfile = work / "models.txt"
    keyfile.write_text("\n".join(MODEL_NAMES) + "\n")
    subprocess.run(
        ["hmmfetch", "-f", "-o", str(models), str(HMM_GZ), str(keyfile)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["hmmpress", "-f", str(models)], check=True, capture_output=True, text=True)
    g1_path = write_fasta(work / "genome1.fa", g1)
    g2_path = write_fasta(work / "genome2.fa", g2)

    modes = {
        "scan_cut_ga": EMIT
        + ["hmmscan", "--cut_ga", "--tblout", "{table}", "--noali", str(models), "{input}"],
        "search_fixed_Z": EMIT
        + [
            "hmmsearch",
            "-Z",
            "1e6",
            "--domZ",
            "1e6",
            "--tblout",
            "{table}",
            "--noali",
            str(models),
            "{input}",
        ],
    }

    payload = {
        "status": "RAN",
        "protocol": "pipeline/docs/INFERENCE_PROTOCOL.md",
        "addendum": "2026-09-27 reuse test",
        "seed": SEED,
        "n": N,
        "n_models": len(MODEL_NAMES),
        "models": list(MODEL_NAMES),
        "paper": (
            "MATCH on whitespace tables is whitespace-normalized "
            "(split()); tblout column padding and right-aligned numbers "
            "are not reproduced byte-for-byte. No per-tool parser."
        ),
        "work": str(work),
        "genome1": {"source": str(FAA.relative_to(ROOT)), "n": len(g1)},
        "genome2": {
            "accession": asm["accession"],
            "strain": asm.get("strain"),
            "path": asm["path"],
            "n": len(g2),
            "n_shared_constructed": n_shared,
            "overlap": overlap,
            "overlap_frac": round(overlap / N, 4),
        },
        "modes": {},
    }
    for name, argv in modes.items():
        print(f"mode {name} …", flush=True)
        payload["modes"][name] = run_mode(
            name, argv, g1, g2, g1_path, g2_path, work, keys1, overlap
        )
        row = payload["modes"][name]
        print(
            f"{name} {row['decision']} match={row['match']} result={row['match_result']} "
            f"overlap={row['overlap']} hits={row['n_hits']} misses={row['n_misses']} "
            f"empty_hits={row['n_empty_hits']} {row.get('diagnose') or ''}",
            flush=True,
        )

    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    failed = [
        n
        for n, row in payload["modes"].items()
        if not row.get("match_result")
    ]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
