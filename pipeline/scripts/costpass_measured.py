#!/usr/bin/env python3
"""Measured batched replay on the two proteomes named in the lock.

One stock 38.2, an oracle batched replay, an unpinned batched replay,
and the shipped CLI filled on 38.1 then replayed on 38.2. Walls are
one run and indicative. The runner recomputes the draw and stops if
the names differ from the lock.
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

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "scripts"))

import costpass_batch_pilot as bp  # noqa: E402
from acts.reference_run import body_lines  # noqa: E402

DATA = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data")
WORK = Path("/Users/joshuaterranova/tmp/costpass_work/measured")
HMMER = Path("/opt/homebrew/bin")
PFAM382 = Path("/Users/joshuaterranova/tmp/costpass_work/pfam38.2.hmm")
PFAM381 = Path("/Users/joshuaterranova/tmp/costpass_work/pfam38.1.hmm")
Z = "30134"
CPU = "4"
EXCLUDE = {
    "GCF_013315695.1_protein.faa.gz",
    "GCF_049201905.1_protein.faa.gz",
    "GCF_059719525.1_protein.faa.gz",
    "GCF_002853805.1_protein.faa.gz",
    "GCF_002090355.1_protein.faa.gz",
    "GCF_001515725.1_protein.faa.gz",
    "GCF_001513615.1_protein.faa.gz",
}
EXPECTED = [
    "GCF_016806025.1_protein.faa.gz",
    "GCF_017165095.1_protein.faa.gz",
]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def loadavg() -> list[float]:
    return [round(v, 2) for v in os.getloadavg()]


def require_free() -> None:
    free = shutil.disk_usage("/Users/joshuaterranova/tmp").free
    if free < 8 * 1024**3:
        raise SystemExit(f"stop: {free} bytes free")


def draw() -> list[str]:
    pool = sorted(p.name for p in (DATA / "recurrence" / "A").glob("*.faa.gz") if p.name not in EXCLUDE)
    names = sorted(random.Random(20261015).sample(pool, 2))
    if names != EXPECTED:
        raise SystemExit(f"stop: draw {names} != {EXPECTED}")
    return names


def gunzip_to(src: Path, dest: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 0:
        return
    require_free()
    log(f"decompress {src.name}")
    tmp = dest.with_suffix(".partial")
    with gzip.open(src, "rb") as inp, tmp.open("wb") as out:
        shutil.copyfileobj(inp, out, length=1 << 20)
    tmp.replace(dest)


def stock(db: Path, queries: Path, tag: Path) -> dict:
    stamp = Path(str(tag) + ".json")
    if stamp.is_file() and Path(str(tag) + ".tbl").is_file():
        log(f"reuse stock {tag.name}")
        return json.loads(stamp.read_text())
    require_free()
    cmd = [
        str(HMMER / "hmmscan"), "--cut_ga", "--noali", "--cpu", CPU,
        "--tblout", str(tag) + ".tbl", "--domtblout", str(tag) + ".dom",
        "-o", os.devnull, str(db), str(queries),
    ]
    load_before = loadavg()
    log(f"stock {tag.name} load={load_before}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        raise SystemExit(f"hmmscan failed ({proc.returncode}): {(proc.stderr or proc.stdout)[-600:]}")
    payload = {"wall_s": wall, "load_before": load_before, "load_after": loadavg()}
    stamp.write_text(json.dumps(payload) + "\n")
    log(f"stock {tag.name} {wall:.1f}s")
    return payload


def cli(reference: Path, queries: Path, cache: Path, out: Path) -> dict:
    stamp = out / "cli.json"
    if stamp.is_file() and (out / "decision.txt").is_file():
        log(f"reuse cli {out.name}")
        return json.loads(stamp.read_text())
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    require_free()
    cmd = [
        sys.executable, "-m", "acts", "run",
        "--strategy", "reference",
        "--pin", "-Z {entry_count}",
        "--verify", "audit",
        "--prep", "hmmpress -f {reference}",
        "--input", str(queries),
        "--reference", str(reference),
        "--cache", str(cache),
        "-o", str(out),
        "--",
        "hmmscan", "--cut_ga", "--noali", "--cpu", CPU,
        "--tblout", "{output:tblout}",
        "--domtblout", "{output:domtblout}",
        "-o", "/dev/null",
        "{reference}", "{input}",
    ]
    load_before = loadavg()
    log(f"cli {out.name} load={load_before}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=PIPE, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    for folder in ("calls", "calls_pinned", "calls_infer", "calls_slack"):
        path = out / folder
        if path.is_dir():
            shutil.rmtree(path)
    if proc.returncode not in (0, 1):
        raise SystemExit(f"cli crashed ({proc.returncode}): {(proc.stderr or proc.stdout)[-1500:]}")
    decision = bp.parse_decision(out / "decision.txt")
    payload = {
        "returncode": proc.returncode,
        "wall_s": wall,
        "load_before": load_before,
        "load_after": loadavg(),
        "decision": decision.get("decision"),
        "why": decision.get("why"),
        "n_batches": decision.get("n_batches"),
        "phases": decision.get("phases") or {},
        "stderr_tail": (proc.stderr or "")[-400:],
    }
    stamp.write_text(json.dumps(payload) + "\n")
    log(f"cli {out.name} {payload['decision']} {wall:.1f}s")
    return payload


def outcome(e1: dict, rn: dict, e2_tbl: bool, e2_dom: bool, e2_token_tbl: bool, e2_token_dom: bool, decision: str) -> str:
    e1_byte = e1["tbl"]["byte_equal"] and e1["dom"]["byte_equal"]
    e1_token = e1["tbl"]["token_equal"] and e1["dom"]["token_equal"]
    rn_differs = not (rn["tbl"]["byte_equal"] and rn["dom"]["byte_equal"])
    e2_byte = e2_tbl and e2_dom
    e2_token = e2_token_tbl and e2_token_dom
    if decision != "SHIP" or not rn_differs:
        return "FAIL"
    if e1_byte and e2_byte:
        return "EXACT"
    if e1_token and e2_token:
        return "TOKEN-EQUAL"
    return "FAIL"


def one(name: str) -> dict:
    stem = name.replace("_protein.faa.gz", "")
    root = WORK / stem
    root.mkdir(parents=True, exist_ok=True)
    queries = root / "queries.faa"
    gunzip_to(DATA / "recurrence" / "A" / name, queries)
    stock_tag = root / "stock"
    stock_run = stock(PFAM382, queries, stock_tag)
    bp.QUERIES = queries
    bp.PFAM = PFAM382
    bp.STOCK_TBL = Path(str(stock_tag) + ".tbl")
    bp.STOCK_DOM = Path(str(stock_tag) + ".dom")
    bp.WORK = root
    log("index")
    model_spans = bp.index_models(PFAM382)
    if len(model_spans) != int(Z):
        raise SystemExit(f"stop: model count {len(model_spans)} != {Z}")
    order, fasta_spans = bp.index_fasta(queries)
    cand = bp.candidates(bp.STOCK_TBL)
    e1 = bp.batched_scan(order, cand, model_spans, fasta_spans, root / "e1", pin=True)
    rn = bp.batched_scan(order, cand, model_spans, fasta_spans, root / "rn", pin=False)
    cache_fill = root / "cache_38.1.sqlite"
    if not (root / "fill" / "cli.json").is_file():
        cache_fill.unlink(missing_ok=True)
    fill = cli(PFAM381, queries, cache_fill, root / "fill")
    if fill["decision"] != "SHIP":
        log(f"{stem} fill {fill['decision']}")
        return {
            "proteome": stem,
            "queries": len(order),
            "stock": stock_run,
            "e1": e1,
            "rn": {"wall_s": rn["wall_s"], "tbl": rn["tbl"], "dom": rn["dom"]},
            "fill": {"wall_s": fill["wall_s"], "decision": fill["decision"], "why": fill.get("why")},
            "e2": None,
            "outcome": "FAIL",
        }
    cache_replay = root / "cache_38.2.sqlite"
    if not (root / "e2" / "cli.json").is_file():
        shutil.copy2(cache_fill, cache_replay)
    e2 = cli(PFAM382, queries, cache_replay, root / "e2")
    tbl_path = root / "e2" / "tables" / "tblout"
    dom_path = root / "e2" / "tables" / "domtblout"
    stock_tbl = body_lines(bp.STOCK_TBL.read_text())
    stock_dom = body_lines(bp.STOCK_DOM.read_text())
    e2_tbl = body_lines(tbl_path.read_text()) if tbl_path.is_file() else []
    e2_dom = body_lines(dom_path.read_text()) if dom_path.is_file() else []
    e2_tbl_class = bp.classify(e2_tbl, stock_tbl, "tbl")
    e2_dom_class = bp.classify(e2_dom, stock_dom, "dom")
    label = outcome(
        e1, rn,
        e2_tbl_class["byte_equal"], e2_dom_class["byte_equal"],
        e2_tbl_class["token_equal"], e2_dom_class["token_equal"],
        e2.get("decision") or "",
    )
    log(f"{stem} {label}")
    return {
        "proteome": stem,
        "queries": len(order),
        "stock": stock_run,
        "e1": e1,
        "rn": {
            "wall_s": rn["wall_s"],
            "tbl": rn["tbl"],
            "dom": rn["dom"],
            "load_before": rn["load_before"],
        },
        "fill": {"wall_s": fill["wall_s"], "decision": fill["decision"], "load_before": fill["load_before"]},
        "e2": {
            "wall_s": e2["wall_s"],
            "decision": e2["decision"],
            "why": e2.get("why"),
            "n_batches": e2.get("n_batches"),
            "phases": e2.get("phases") or {},
            "load_before": e2["load_before"],
            "load_after": e2["load_after"],
            "tbl": e2_tbl_class,
            "dom": e2_dom_class,
        },
        "outcome": label,
    }


def main() -> None:
    for path in (PFAM381, PFAM382):
        if not path.is_file():
            raise SystemExit(f"missing {path}")
    names = draw()
    log(f"draw {names}")
    WORK.mkdir(parents=True, exist_ok=True)
    results = []
    dest = PIPE / "results/exact_replay/costpass_measured.json"
    if dest.is_file():
        prior = json.loads(dest.read_text())
        results = prior.get("proteomes") or []
    done = {row["proteome"] for row in results}
    for name in names:
        stem = name.replace("_protein.faa.gz", "")
        if stem in done:
            log(f"reuse {stem}")
            continue
        results.append(one(name))
        partial = {
            "test": "costpass-measured",
            "git_head": subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=PIPE, check=True, capture_output=True, text=True
            ).stdout.strip(),
            "proteomes": results,
            "partial": True,
        }
        dest.write_text(json.dumps(partial, indent=2) + "\n")
    labels = [row["outcome"] for row in results]
    if all(label == "EXACT" for label in labels):
        overall = "EXACT"
    elif any(label == "FAIL" for label in labels):
        overall = "FAIL"
    else:
        overall = "TOKEN-EQUAL"
    report = {
        "test": "costpass-measured",
        "git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PIPE, check=True, capture_output=True, text=True
        ).stdout.strip(),
        "draw_seed": 20261015,
        "proteomes": results,
        "outcome": overall,
        "walls_indicative": True,
        "load": loadavg(),
    }
    dest.write_text(json.dumps(report, indent=2) + "\n")
    log(f"wrote {dest} {overall}")


if __name__ == "__main__":
    main()
