#!/usr/bin/env python3
"""Rerun the locked safety controls under the shipped judge.

The judge is ReferenceIncremental._ic2 as of 1c8d3be: per-record
file-order neighbors, then the candidate union is removed from the pad
subject set. This is not a new check. Known-bad arms must refuse and
must not write a replay. Work stays under ~/tmp/ctlrerun_work.
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

import costpass_diamond_fresh as diamond_fresh  # noqa: E402
import costpass_dx3_regen as dx3  # noqa: E402
import costpass_ic2_pilot as ic2  # noqa: E402
from acts.exact_certificate import judge, neighbor_ids, pad_indices, sample_keys  # noqa: E402
from acts.provenance import provenance  # noqa: E402
from acts.reference_run import body_lines  # noqa: E402

WORK = Path.home() / "tmp" / "ctlrerun_work"
DATA = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data")
PFAM_GZ = DATA / "hmmer" / "Pfam-A.hmm.gz"
QUERY_GZ = DATA / "recurrence" / "A" / "GCF_013315695.1_protein.faa.gz"
STOCK_TBL_SRC = Path(
    "/Users/joshuaterranova/tmp/e1scale_work/measured/GCF_013315695.1/S382.tbl"
)
STOCK_DOM_SRC = Path(
    "/Users/joshuaterranova/tmp/e1scale_work/measured/GCF_013315695.1/S382.dom"
)
DROP_SEED = 20261013
SAMPLE_SEED = 20261034
SAMPLE_SIZE = 50
EXPECTED_DIAMOND = "GCF_023657995.1_protein.faa.gz"
OUT = PIPE / "results" / "exact_replay" / "costpass_controls_rerun.json"


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def require_free() -> None:
    free = shutil.disk_usage(Path.home() / "tmp").free
    if free < 8 * 1024**3:
        raise SystemExit(f"stop: {free} bytes free")


def git_state() -> dict:
    block = provenance()
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PIPE.parents[0],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return {
        "git_head": block["git"],
        "git_dirty": block["git_dirty"],
        "git_status": porcelain,
        "host": block["host"],
    }


def shipped_neighbor(entries, cand: dict[str, set[str]]):
    """The pad subject set ReferenceIncremental._ic2 ships after 1c8d3be."""
    expanded: dict[str, set[str]] = {}
    neighbor_pad: set[str] = set()
    for key, tokens in cand.items():
        extra = neighbor_ids(entries, set(tokens))
        expanded[key] = set(tokens) | extra
        neighbor_pad |= extra
    u_ids = {token for tokens in cand.values() for token in tokens}
    overlap = neighbor_pad & u_ids
    neighbor_pad -= u_ids
    return expanded, neighbor_pad, u_ids, overlap


def write_fasta_subset(src: Path, want: set[str], dest: Path) -> None:
    with gzip.open(src, "rt") as fh, dest.open("w") as out:
        keep = False
        for line in fh:
            if line.startswith(">"):
                keep = line[1:].split()[0] in want
            if keep:
                out.write(line)


def swissprot_order() -> list[str]:
    order: list[str] = []
    with gzip.open(dx3.SPROT, "rt") as fh:
        for line in fh:
            if line.startswith(">"):
                order.append(line[1:].split()[0])
    return order


def makedb(fasta: Path) -> None:
    proc = subprocess.run(
        [str(dx3.DIAMOND), "makedb", "--in", str(fasta), "--db", str(fasta), "--threads", "8"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"makedb failed {(proc.stderr or '')[-400:]}")


def pairs(text: str) -> dict[str, set[str]]:
    cand: dict[str, set[str]] = {}
    for line in body_lines(text):
        fields = line.split()
        cand.setdefault(fields[0], set()).add(fields[1])
    return cand


def refuse_view(verdict: dict) -> dict:
    """A known-bad arm. A pass is a kill of the judge change. No replay is written."""
    return {
        "verdict": verdict,
        "refused": not verdict["pass"],
        "fail_mode": verdict["fail_mode"],
        "emitted_replay": False,
    }


def dx2_arm(order: list[str]) -> dict:
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
    cand = pairs(replay)
    entries = [SimpleNamespace(primary=name) for name in order]
    _expanded, pad, shipped_u, overlap = shipped_neighbor(entries, cand)
    union_pad = neighbor_ids(entries, u_set)
    want = u_set | union_pad | pad
    write_fasta_subset(ic2.SPROT, want, dest / "db.faa")
    t0 = time.perf_counter()
    makedb(dest / "db.faa")
    out_m8 = dest / "plus.m8"
    cmd = [
        str(ic2.DIAMOND), "blastp", "--db", str(dest / "db.faa"),
        "--query", str(ic2.DX2 / "e1_q.faa"), "--out", str(out_m8),
        "--min-score", "40", "-k", "0", "--motif-masking", "0",
        "-b", "2.0", "--comp-based-stats", "1", "--threads", "8",
        "--dbsize", "209017843", "--outfmt", "6", "qseqid", "sseqid", "pident",
        "length", "mismatch", "gapopen", "qstart", "qend", "sstart", "send",
        "evalue", "bitscore",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"dx2 blastp failed {(proc.stderr or '')[-400:]}")
    wall = time.perf_counter() - t0
    verdict = judge(replay, out_m8.read_text(), shipped_u, pad, 1)
    log(f"dx2 {wall:.1f}s {verdict['fail_mode']} pass={verdict['pass']}")
    shutil.rmtree(dest)
    return {
        "arm": "dx2-known-bad",
        "wall_s": wall,
        "candidate_subjects": len(shipped_u),
        "fasta_subjects": len(u_set),
        "shipped_pad_subjects": len(pad),
        "union_pad_subjects": len(union_pad),
        "pad_equals_union_neighbors": pad == union_pad,
        "overlap_removed_by_1c8d3be": len(overlap),
        **refuse_view(verdict),
    }


def dx3_arm(order: list[str]) -> dict:
    log("dx3 regeneration")
    dest = WORK / "dx3"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    dx3.WORK = dest
    recs = dx3.records(dx3.QUERY_GZ)
    draw = sorted(random.Random(20261029).sample(range(len(recs)), 2000))
    query = dest / "q.faa"
    query.write_text("".join(recs[i] for i in draw))
    log(f"dx3 queries {len(draw)} of {len(recs)}")
    stock_wall = dx3.blast(dx3.SPROT, query, dest / "stock.m8", False)
    stock = (dest / "stock.m8").read_text()
    u_from_stock = {line.split()[1] for line in body_lines(stock)}
    write_fasta_subset(dx3.SPROT, u_from_stock, dest / "U.faa")
    makedb(dest / "U.faa")
    replay_wall = dx3.blast(dest / "U.faa", query, dest / "R.m8", True)
    replay = (dest / "R.m8").read_text()
    cand = pairs(replay)
    entries = [SimpleNamespace(primary=name) for name in order]
    _expanded, pad, shipped_u, overlap = shipped_neighbor(entries, cand)
    union_pad = neighbor_ids(entries, u_from_stock)
    write_fasta_subset(dx3.SPROT, u_from_stock | union_pad | pad, dest / "UP.faa")
    makedb(dest / "UP.faa")
    plus_wall = dx3.blast(dest / "UP.faa", query, dest / "Rplus.m8", True)
    verdict = judge(replay, (dest / "Rplus.m8").read_text(), shipped_u, pad, 1)
    stock_rows = body_lines(stock)
    replay_rows = body_lines(replay)
    log(
        f"dx3 stock {len(stock_rows)} replay {len(replay_rows)} "
        f"{verdict['fail_mode']} pass={verdict['pass']}"
    )
    report = {
        "arm": "dx3-regeneration",
        "queries": 2000,
        "records": len(recs),
        "seed": 20261029,
        "genome": "GCF_001515725.1",
        "stock_rows": len(stock_rows),
        "replay_rows": len(replay_rows),
        "bodies_equal": stock_rows == replay_rows,
        "stock_rows_match_dx3_json": len(stock_rows) == 227223,
        "replay_rows_match_dx3_json": len(replay_rows) == 227205,
        "candidate_subjects": len(shipped_u),
        "stock_subjects": len(u_from_stock),
        "shipped_pad_subjects": len(pad),
        "union_pad_subjects": len(union_pad),
        "pad_equals_union_neighbors": pad == union_pad,
        "overlap_removed_by_1c8d3be": len(overlap),
        "stock_wall_s": stock_wall,
        "replay_wall_s": replay_wall,
        "neighbor_wall_s": plus_wall,
        **refuse_view(verdict),
    }
    shutil.rmtree(dest)
    return report


def diamond_arm() -> dict:
    log("diamond fresh sample")
    part_name = "_ctlrerun_diamond_part.json"
    part = PIPE / "results" / "exact_replay" / part_name
    diamond_fresh.WORK = WORK / "diamond"
    argv = sys.argv
    sys.argv = [argv[0], "--seed", "20261017", "--out", part_name]
    try:
        diamond_fresh.main()
    except SystemExit as exc:
        if not part.is_file():
            raise
        log(f"diamond exit {exc}")
    finally:
        sys.argv = argv
    report = json.loads(part.read_text())
    part.unlink()
    if report.get("genome") != EXPECTED_DIAMOND:
        raise SystemExit(f"stop: diamond genome {report.get('genome')} != {EXPECTED_DIAMOND}")
    report["arm"] = "diamond-fresh"
    report["emitted_replay"] = False
    log(f"diamond {report.get('outcome')} neighbor {report.get('neighbor', {}).get('fail_mode')}")
    return report


def prepare_hmm() -> tuple[Path, Path, Path]:
    dest = WORK / "hmm"
    dest.mkdir(parents=True, exist_ok=True)
    ic2.WORK = dest
    ic2.PFAM = dest / "pfam38.2.hmm"
    ic2.QUERIES = dest / "queries.faa"
    if not ic2.PFAM.is_file():
        log("gunzip Pfam-A.hmm.gz")
        require_free()
        with gzip.open(PFAM_GZ, "rb") as inp, ic2.PFAM.open("wb") as out:
            shutil.copyfileobj(inp, out, length=1 << 20)
    if not ic2.QUERIES.is_file():
        log("gunzip GCF_013315695.1")
        with gzip.open(QUERY_GZ, "rb") as inp, ic2.QUERIES.open("wb") as out:
            shutil.copyfileobj(inp, out, length=1 << 20)
    tbl = dest / "stock.tbl"
    dom = dest / "stock.dom"
    if not tbl.is_file():
        shutil.copyfile(STOCK_TBL_SRC, tbl)
        shutil.copyfile(STOCK_DOM_SRC, dom)
    return ic2.PFAM, tbl, dom


def hmm_arms() -> dict:
    log("hmmer controls")
    pfam, tbl_path, dom_path = prepare_hmm()
    order_models = ic2.names_in_order(pfam)
    if len(order_models) != 30134:
        raise SystemExit(f"stop: Pfam model count {len(order_models)}")
    entries = [SimpleNamespace(primary=name) for name in order_models]
    mspans = ic2.model_spans(pfam)
    qorder, fspans = ic2.fasta_spans(ic2.QUERIES)
    stock_tbl = tbl_path.read_text()
    stock_dom = dom_path.read_text()
    cand = ic2.hits(stock_tbl, 2)
    expanded, pad, u_ids, overlap = shipped_neighbor(entries, cand)
    log(f"hmmer oracle records={len(expanded)} overlap_removed={len(overlap)}")
    oracle_tbl, oracle_dom, oracle_wall = ic2.scan_batches(
        qorder, cand, mspans, fspans, ic2.WORK / "oracle"
    )
    oracle_tbl_body = body_lines(oracle_tbl)
    oracle_dom_body = body_lines(oracle_dom)
    stock_tbl_body = body_lines(stock_tbl)
    stock_dom_body = body_lines(stock_dom)
    byte_identical = oracle_tbl_body == stock_tbl_body and oracle_dom_body == stock_dom_body
    log(f"hmmer oracle byte_identical={byte_identical} wall={oracle_wall:.1f}s")
    if not byte_identical:
        raise SystemExit("stop: oracle replay is not byte-identical to the stock body")
    tbl, dom, neighbor_wall = ic2.scan_batches(
        qorder, expanded, mspans, fspans, ic2.WORK / "neighbor"
    )
    neighbor = {
        "wall_s": neighbor_wall,
        "tbl": judge(oracle_tbl, tbl, u_ids, pad, 0),
        "dom": judge(oracle_dom, dom, u_ids, pad, 0),
    }
    neighbor_pass = neighbor["tbl"]["pass"] and neighbor["dom"]["pass"]
    log(
        f"hmmer neighbor {neighbor_wall:.1f}s "
        f"tbl={neighbor['tbl']['fail_mode']} dom={neighbor['dom']['fail_mode']}"
    )

    inject_tbl_text, inject_dom_text, inject_scan_wall, dropped = injected_body(
        cand, mspans, fspans, qorder
    )
    inject = random_pads(
        entries,
        order_models,
        qorder,
        mspans,
        fspans,
        cand,
        ic2.hits(inject_tbl_text, 2),
        inject_tbl_text,
        inject_dom_text,
        "inject",
    )
    inject["dropped_models"] = dropped
    inject["scan_wall_s"] = inject_scan_wall
    inject["body_differs"] = body_lines(inject_tbl_text) != stock_tbl_body or body_lines(inject_dom_text) != stock_dom_body
    log(f"hmmer inject refused={inject['refused']} modes={inject['modes']}")

    good = random_pads(
        entries,
        order_models,
        qorder,
        mspans,
        fspans,
        cand,
        cand,
        oracle_tbl,
        oracle_dom,
        "good",
    )
    log(f"hmmer good refused={good['refused']} modes={good['modes']}")
    positive_pass = byte_identical and neighbor_pass and not good["refused"]
    return {
        "arm": "hmmer-GCF_013315695.1",
        "proteome": "GCF_013315695.1",
        "stock_source": str(STOCK_TBL_SRC),
        "stock_tbl_lines": len(stock_tbl_body),
        "stock_dom_lines": len(stock_dom_body),
        "oracle_byte_identical": byte_identical,
        "oracle_wall_s": oracle_wall,
        "overlap_removed_by_1c8d3be": len(overlap),
        "shipped_pad_subjects": len(pad),
        "neighbor": neighbor,
        "neighbor_pass": neighbor_pass,
        "injected_drop_sample_50": inject,
        "good_sample_50": good,
        "pass": positive_pass,
        "byte_identical": byte_identical,
        "emitted_replay": False,
    }


def injected_body(cand, mspans, fspans, qorder):
    models = sorted({name for names in cand.values() for name in names})
    dropped_n = max(1, int(round(0.05 * len(models))))
    dropped = set(random.Random(DROP_SEED).sample(models, dropped_n))
    reduced = {key: names - dropped for key, names in cand.items()}
    tbl, dom, wall = ic2.scan_batches(qorder, reduced, mspans, fspans, ic2.WORK / "inject_body")
    return tbl, dom, wall, dropped_n


def random_pads(entries, order_models, qorder, mspans, fspans, full_cand, reduced, replay_tbl, replay_dom, tag: str) -> dict:
    pool = [key for key in qorder if key in reduced or key in full_cand]
    sample = sample_keys(pool, SAMPLE_SIZE, SAMPLE_SEED)
    keep = set(sample)
    u_red = {name for ids in reduced.values() for name in ids}
    affected = [key for key in full_cand if full_cand[key] - reduced.get(key, set())]
    t0 = time.perf_counter()
    refused = False
    modes = []
    for name, indices in pad_indices(entries, u_red):
        if not name.startswith("random") or not indices:
            continue
        pad = {order_models[i] for i in indices}
        sample_cand = {
            key: set(reduced.get(key, set())) | pad
            for key in sample
            if key in reduced or key in full_cand
        }
        plus_tbl, plus_dom, _wall = ic2.scan_batches(
            sample, sample_cand, mspans, fspans, ic2.WORK / f"{tag}_{name}"
        )
        for replay, plus, col in (
            (replay_tbl, plus_tbl, 2),
            (replay_dom, plus_dom, 3),
        ):
            verdict = judge(ic2.filter_text(replay, col, keep), plus, u_red, pad, 0)
            modes.append(verdict["fail_mode"])
            if not verdict["pass"]:
                refused = True
    return {
        "wall_s": time.perf_counter() - t0,
        "refused": refused,
        "modes": modes,
        "sample_size": len(sample),
        "sample_hits_affected": len(keep & set(affected)),
        "emitted_replay": False,
    }


def write_report(report: dict) -> None:
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    log(f"wrote {OUT}")


def main() -> None:
    require_free()
    WORK.mkdir(parents=True, exist_ok=True)
    state = git_state()
    log(f"git {state['git_head']} dirty={state['git_dirty']}")
    order = swissprot_order()
    report = {
        "test": "costpass-controls-rerun",
        "judge": "ReferenceIncremental._ic2 after 1c8d3be (neighbor_pad -= u_ids)",
        "label": "RERUN",
        **state,
    }
    report["dx2"] = dx2_arm(order)
    write_report(report)
    report["dx3"] = dx3_arm(order)
    write_report(report)
    report["diamond"] = diamond_arm()
    write_report(report)
    report["hmmer"] = hmm_arms()
    report.update(git_state())
    known_bad_passed = [
        name
        for name in ("dx2", "dx3")
        if report[name]["verdict"]["pass"]
    ]
    if not report["hmmer"]["injected_drop_sample_50"]["refused"]:
        known_bad_passed.append("injected_drop")
    report["known_bad_passed"] = known_bad_passed
    report["kill_1c8d3be"] = bool(known_bad_passed)
    write_report(report)
    shutil.rmtree(WORK, ignore_errors=True)
    log(f"kill_1c8d3be={report['kill_1c8d3be']} passed={known_bad_passed}")


if __name__ == "__main__":
    main()
