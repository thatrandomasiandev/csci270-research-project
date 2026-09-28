#!/usr/bin/env python3
"""Drive the 7eeb40e FASTA reuse test through generic table layout.

Does not edit scripts/run_fasta_reuse.py or overwrite
results/inference_fasta_reuse.json.
"""

from __future__ import annotations

import importlib.util
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.cache import RecordCache
from acts.fasta import parse_fasta, write_fasta
from acts.fasta_memo import cached_search, contract_path_for, prepare_table_contract
from acts.infer_fasta import InferError, run_table_tool
from acts.table import tables_match

SPEC = importlib.util.spec_from_file_location(
    "run_fasta_reuse", ROOT / "scripts" / "run_fasta_reuse.py"
)
reuse = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(reuse)

SEED = reuse.SEED
N = reuse.N
MODEL_NAMES = reuse.MODEL_NAMES
FAA = reuse.FAA
HMM_GZ = reuse.HMM_GZ
ACCESSIONS = reuse.ACCESSIONS
EMIT = reuse.EMIT
OUT = ROOT / "results" / "inference_fasta_reuse_bytes.json"


def run_mode(
    name: str,
    argv: list[str],
    g1,
    g2,
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
            "match_ws": None,
            "match_result": False,
            "layout": {},
        }

    cache = RecordCache(cache_path, argv=argv, kind="fasta")
    _rebuilt1, pop = cached_search(
        g1, cache, contract, argv, dest / "pop", contract_path=contract_path_for(cache_path)
    )
    cache.save()
    g1_empty = reuse.empty_keys(cache)

    rebuilt2, reuse_stats = cached_search(
        g2, cache, contract, argv, dest / "reuse", contract_path=contract_path_for(cache_path)
    )
    cache.save()
    stock2 = run_table_tool(argv, g2_path)
    (dest / "reassembled.out").write_text(rebuilt2)
    (dest / "full.out").write_text(stock2)

    matched = tables_match(
        rebuilt2, stock2, contract.match, match_ws=contract.match_ws
    )
    byte_matched = tables_match(
        rebuilt2, stock2, contract.match, match_ws=False
    )

    empty_hit_recs = [rec for rec in g2 if rec.key in keys1 and rec.key in g1_empty]
    n_empty_hits = sum(1 for rec in empty_hit_recs if cache.get(rec.key) is not None)
    miss_path = dest / "reuse" / "miss.fa"
    miss_keys = (
        {r.key for r in parse_fasta(miss_path.read_text())} if miss_path.is_file() else set()
    )
    empty_called = [rec.name for rec in empty_hit_recs if rec.key in miss_keys]

    diffs = [] if matched else reuse.first_diffs(
        rebuilt2, stock2, multiset=contract.match == "multiset"
    )
    decision = "SHIP" if matched and reuse_stats["n_cache_holes"] == 0 else "REFUSE_MATCH"
    layout = dict(contract.layout or {})
    return {
        "decision": decision,
        "reason": (
            f"MATCH {contract.match}; hits={reuse_stats['n_hits']} misses={reuse_stats['n_misses']}"
            if decision == "SHIP"
            else "reassembled body is not MATCH to a full run"
        ),
        "match": contract.match,
        "match_ws": contract.match_ws,
        "byte_match": byte_matched,
        "pad_widths": contract.pad_widths,
        "empty_desc": contract.empty_desc,
        "match_result": matched,
        "query_col": contract.query_col,
        "layout": layout,
        "layout_pinned": bool(layout.get("pinned")),
        "layout_scope": layout.get("scope"),
        "layout_reason": layout.get("reason") or "",
        "overlap": overlap,
        "n_hits": reuse_stats["n_hits"],
        "n_misses": reuse_stats["n_misses"],
        "n_empty_hits": n_empty_hits,
        "empty_hit_called_tool": empty_called,
        "populate": {
            "n_hits": pop["n_hits"],
            "n_misses": pop["n_misses"],
            "n_empty_cached": len(g1_empty),
        },
        "first_diffs": diffs,
        "diagnose": reuse.diagnose(diffs),
    }


def main() -> int:
    if not (shutil.which("hmmscan") and shutil.which("hmmsearch") and shutil.which("hmmfetch")):
        OUT.write_text(
            json.dumps({"status": "INCOMPLETE", "reason": "HMMER binaries missing"}, indent=2)
            + "\n"
        )
        print("INCOMPLETE: HMMER binaries missing")
        return 0
    if not FAA.is_file() or not HMM_GZ.is_file() or not ACCESSIONS.is_file():
        OUT.write_text(
            json.dumps({"status": "INCOMPLETE", "reason": "local data missing"}, indent=2)
            + "\n"
        )
        print("INCOMPLETE: local data missing")
        return 0

    acc = json.loads(ACCESSIONS.read_text())
    assemblies = acc["collections"]["A"]["genomes"]
    mg = reuse.load_faa(FAA)
    genome1 = random.Random(SEED).sample(mg, N)
    asm, genome2_raw, n_shared = reuse.pick_genome2(genome1, assemblies)
    g1 = reuse.rename(genome1, "G1", random.Random(SEED + 3))
    g2 = reuse.rename(genome2_raw, "G2", random.Random(SEED + 4))
    keys1 = {rec.key for rec in g1}
    overlap = sum(1 for rec in g2 if rec.key in keys1)

    work = Path(tempfile.mkdtemp(prefix="acts_fasta_reuse_bytes_"))
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
        "addendum": "2026-09-27 generic table column layout",
        "prior_fallback": "7eeb40e / results/inference_fasta_reuse.json",
        "seed": SEED,
        "n": N,
        "n_models": len(MODEL_NAMES),
        "models": list(MODEL_NAMES),
        "paper": (
            "Generic column-layout inference; byte MATCH when the layout is pinned. "
            "Whitespace-normalized MATCH remains the fallback (7eeb40e). No per-tool parser."
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
    for mode_name, argv in modes.items():
        print(f"mode {mode_name} …", flush=True)
        payload["modes"][mode_name] = run_mode(
            mode_name, argv, g1, g2, g1_path, g2_path, work, keys1, overlap
        )
        row = payload["modes"][mode_name]
        print(
            f"{mode_name} {row['decision']} match={row['match']} "
            f"match_ws={row['match_ws']} byte={row.get('byte_match')} "
            f"pinned={row.get('layout_pinned')} scope={row.get('layout_scope')} "
            f"result={row['match_result']} overlap={row['overlap']} "
            f"hits={row['n_hits']} misses={row['n_misses']} "
            f"empty_hits={row['n_empty_hits']} {row.get('diagnose') or ''}",
            flush=True,
        )

    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    failed = [n for n, row in payload["modes"].items() if not row.get("match_result")]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
