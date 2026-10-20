#!/usr/bin/env python3
"""Shipped BLAST+ exactness after the row-occurrence index.

Pre-registered in docs/BLAST_PIN_PROTOCOL.md, addendum 2026-10-19.
Pilot seed 20261201 (300 queries). Measured seed 20261202 (2,000).
Drop seed 20261203. This file does not edit acts/.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import random
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "pipeline" / "scripts"))

from acts.provenance import provenance  # noqa: E402
from acts.reference_fit import sample_record_indices  # noqa: E402
from acts.reference_formats import parse_reference, read_records, write_entries  # noqa: E402
from acts.reference_run import pin_values  # noqa: E402
from blast_hsp_diagnosis import (  # noqa: E402
    blast,
    body_lines,
    compare_row_sets,
    file_md5,
    make_db,
    tool_version,
)

PILOT_SEED = 20261201
MEASURED_SEED = 20261202
DROP_SEED = 20261203
PILOT_N = 300
MEASURED_N = 2000
MIN_ROWS = 1000
# Raised after the pilot (addendum 2026-10-19, post-pilot). Not applied to the
# pilot, which already cleared 297,810 rows against the original floor.
MEASURED_MIN_ROWS = 100_000
PIN = "-dbsize {total_entry_length}"
OUTFMT = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore"
PAYLOAD: dict | None = None


def log(message: str) -> None:
    print(message, flush=True)


def write_out(dest: Path, payload: dict) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(dest)
    log(f"wrote {dest}")


def _on_term(signum: int, _frame: object) -> None:
    if PAYLOAD is not None and os.environ.get("ACTS_OUT"):
        PAYLOAD["stopped"] = f"signal {signum}"
        PAYLOAD["outcome"] = "FAIL"
        write_out(Path(os.environ["ACTS_OUT"]), PAYLOAD)
    raise SystemExit(2)


def ordered_compare(stock: list[str], other: list[str]) -> dict:
    classes = compare_row_sets(stock, other)
    examples = classes.pop("examples", [])[:3]
    ordered = stock == other
    if not ordered and classes.get("byte_identical"):
        classes["order"] = 1
    classes["ordered_body_equal"] = ordered
    classes["examples"] = examples
    return classes


def write_queries(src: Path, dest: Path, n: int, seed: int) -> dict:
    if dest.is_file() and (dest.with_suffix(".json")).is_file():
        log(f"resume queries {dest.name}")
        return json.loads(dest.with_suffix(".json").read_text())
    records = read_records(src)
    if n > len(records):
        raise SystemExit(f"need {n} queries, file has {len(records)}")
    chosen = sample_record_indices(len(records), n, seed)
    picked = [records[i] for i in chosen]
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for rec in picked:
        header = rec.name if not rec.description else f"{rec.name} {rec.description}"
        lines.append(f">{header}\n{rec.sequence}\n")
    dest.write_text("".join(lines))
    info = {
        "source": str(src),
        "n_source_records": len(records),
        "seed": seed,
        "n": n,
        "indices": chosen,
        "ids": [rec.name for rec in picked],
        "md5": file_md5(dest),
    }
    dest.with_suffix(".json").write_text(json.dumps(info) + "\n")
    return info


def subjects_of(text: str) -> list[str]:
    found = []
    seen = set()
    for line in body_lines(text):
        cells = line.split("\t") if "\t" in line else line.split()
        if len(cells) < 2 or cells[1] in seen:
            continue
        seen.add(cells[1])
        found.append(cells[1])
    return found


def tool_body(out_dir: Path) -> list[str]:
    path = out_dir / "tables" / "out"
    if not path.is_file():
        return []
    return body_lines(path.read_text(errors="replace"))


def run_cli(
    *,
    pipe: Path,
    queries: Path,
    reference: Path,
    out_dir: Path,
    cache: Path,
    blastp: str,
) -> dict:
    stamp = out_dir / "cli_stamp.json"
    if stamp.is_file():
        log(f"resume cli {out_dir.name}")
        return json.loads(stamp.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "acts", "run",
        "--strategy", "reference",
        "--pin", PIN,
        "--verify", "full",
        "--prep", "makeblastdb -in {reference} -dbtype prot -out {reference}",
        "--input", str(queries),
        "--reference", str(reference),
        "--cache", str(cache),
        "-o", str(out_dir),
        "--",
        blastp,
        "-query", "{input}",
        "-db", "{reference}",
        "-out", "{output}",
        "-outfmt", OUTFMT,
        "-max_target_seqs", "100000",
        "-evalue", "1000",
        "-num_threads", "2",
    ]
    log("cli " + reference.name)
    proc = subprocess.run(cmd, cwd=pipe, check=False, capture_output=True, text=True)
    decision_path = out_dir / "decision.txt"
    decision_text = decision_path.read_text() if decision_path.is_file() else ""
    decision = ""
    why = ""
    for line in decision_text.splitlines():
        if line.startswith("decision:"):
            decision = line.split(":", 1)[1].strip()
        elif line.startswith("why:"):
            why = line.split(":", 1)[1].strip()
    body = tool_body(out_dir)
    payload = {
        "argv": cmd,
        "returncode": proc.returncode,
        "decision": decision,
        "why": why,
        "n_body_lines": len(body),
        "body_md5": hashlib.md5("\n".join(body).encode()).hexdigest(),
        "stdout_tail": (proc.stdout or "")[-2500:],
        "stderr_tail": (proc.stderr or "")[-2500:],
    }
    if proc.returncode not in (0, 1) or not decision:
        err = (proc.stderr or proc.stdout or "")[-800:]
        raise SystemExit(f"acts run failed ({proc.returncode}) for {reference.name}: {err}")
    stamp.write_text(json.dumps(payload, indent=2) + "\n")
    log(f"cli {reference.name} -> {decision} ({proc.returncode})")
    return payload


def shipped_drop(cache: Path, queries: Path, release: Path, blastp: str, cand: dict[str, set[str]], work: Path) -> dict:
    """Run the shipped neighbor check on a dropped candidate map."""
    from acts.reference_cache import connect_cache
    from acts.reference_formats import parse_reference as parse_ref
    from acts.reference_run import ReferenceIncremental, _batched_replay, tables_from_dict

    report: dict = {}
    cache_obj = connect_cache(cache)
    try:
        rows = cache_obj._conn.execute("SELECT payload FROM contracts").fetchall()
    finally:
        cache_obj.close()
    stored_tables = None
    for (blob,) in rows:
        stored = json.loads(blob)
        if stored.get("decision") == "SHIP" and stored.get("tables"):
            stored_tables = tables_from_dict(stored["tables"])
    if not stored_tables:
        report["control"] = "INCONCLUSIVE"
        report["reason"] = "cache has no SHIP contract"
        return report
    table = stored_tables[0]
    if table.record_col != 0 or table.entry_col != 1:
        report["control"] = "INCONCLUSIVE"
        report["reason"] = f"columns record={table.record_col} entry={table.entry_col}"
        return report
    entries = parse_ref(release)
    records = read_records(queries)
    rep_records = [rec for rec in records if rec.key in cand]
    dest = work / "drop_check"
    dest.mkdir(parents=True, exist_ok=True)
    memo = ReferenceIncremental(
        argv=[
            blastp, "-query", "{input}", "-db", "{reference}", "-out", "{output}",
            "-outfmt", OUTFMT, "-max_target_seqs", "100000", "-evalue", "1000",
            "-num_threads", "2",
        ],
        input_path=queries,
        out_dir=dest,
        reference=release,
        prep="makeblastdb -in {reference} -dbtype prot -out {reference}",
        cache_path=cache,
        verify="full",
        pin=PIN,
    )
    memo._n_entries = len(entries)
    memo._entry_names = {key for entry in entries for key in entry.keys}
    memo.clock = {}
    memo._t_all = time.perf_counter()
    pinned = memo._pinned(release)
    texts, n_batches = _batched_replay(
        pinned, rep_records, entries, cand, entries, stored_tables
    )
    why = memo._ic2(pinned, entries, rep_records, texts, stored_tables, cand)
    report["n_batches"] = n_batches
    report["check_why"] = why
    report["check_refused"] = bool(why)
    report["queries_kept"] = len(cand)
    return report


def finish(report: dict, dest: Path) -> int:
    # NOT_SHIP still finished the test, so the measured sample may be drawn.
    # A failed control or a stop does not.
    report["pilot_complete"] = report.get("mode") == "pilot" and report.get("outcome") in {
        "SHIP",
        "NOT_SHIP",
    }
    write_out(dest, report)
    log(f"outcome={report.get('outcome')}")
    if report.get("outcome") == "STOP_STOCK":
        return 2
    return 0


def main() -> int:
    global PAYLOAD
    parser = argparse.ArgumentParser(description="TARE W6 BLAST+ shipped exactness")
    parser.add_argument("--mode", choices=("pilot", "measured"), required=True)
    parser.add_argument("--queries-src", type=Path, required=True)
    parser.add_argument("--release-old", type=Path, required=True)
    parser.add_argument("--release-new", type=Path, required=True)
    parser.add_argument("--blastp", type=Path, required=True)
    parser.add_argument("--makeblastdb", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pipe", type=Path, required=True)
    parser.add_argument("--pilot-json", type=Path, default=None)
    args = parser.parse_args()
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("STOP: this run executes only under sbatch")

    signal.signal(signal.SIGTERM, _on_term)
    os.environ["ACTS_OUT"] = str(args.out)
    seed = PILOT_SEED if args.mode == "pilot" else MEASURED_SEED
    n_queries = PILOT_N if args.mode == "pilot" else MEASURED_N
    row_floor = MIN_ROWS if args.mode == "pilot" else MEASURED_MIN_ROWS
    if args.mode == "measured":
        pilot_path = args.pilot_json
        if pilot_path is None or not pilot_path.is_file():
            raise SystemExit("STOP: measured mode needs the pilot JSON")
        pilot = json.loads(pilot_path.read_text())
        if not pilot.get("pilot_complete"):
            raise SystemExit(
                f"STOP: pilot outcome {pilot.get('outcome')!r} did not complete the test"
            )

    work = args.work
    work.mkdir(parents=True, exist_ok=True)
    versions = {
        "blastp": tool_version(str(args.blastp)),
        "makeblastdb": tool_version(str(args.makeblastdb)),
    }
    report: dict = {
        "protocol": "pipeline/docs/BLAST_PIN_PROTOCOL.md",
        "addendum": "2026-10-19",
        "system": "TARE",
        "mode": args.mode,
        "seed": seed,
        "n_queries": n_queries,
        "drop_seed": DROP_SEED,
        "min_rows": row_floor,
        "pin": PIN,
        "frozen_code_commit": os.environ.get("ACTS_COMMIT", ""),
        "starting_commit": os.environ.get("ACTS_START_COMMIT", ""),
        "provenance": provenance(versions=versions),
    }
    PAYLOAD = report

    query_path = work / "queries.faa"
    report["queries"] = write_queries(args.queries_src, query_path, n_queries, seed)
    log(f"queries n={report['queries']['n']} md5={report['queries']['md5']}")

    log("parsing 2026_03")
    entries = parse_reference(args.release_new)
    values = pin_values(entries)
    report["release_new"] = {
        "path": str(args.release_new),
        "md5": file_md5(args.release_new),
        "n_entries": values["entry_count"],
        "total_entry_length": values["total_entry_length"],
    }
    report["release_old"] = {
        "path": str(args.release_old),
        "md5": file_md5(args.release_old),
    }
    fasta = work / "new.faa"
    old_fasta = work / "old.faa"
    if not fasta.is_file():
        write_entries(entries, fasta)
    del entries
    gc.collect()
    if not old_fasta.is_file():
        old_entries = parse_reference(args.release_old)
        report["release_old"]["n_entries"] = len(old_entries)
        report["release_old"]["total_entry_length"] = pin_values(old_entries)["total_entry_length"]
        write_entries(old_entries, old_fasta)
        del old_entries
        gc.collect()
    make_db(str(args.makeblastdb), fasta, work / "db" / "new")
    make_db(str(args.makeblastdb), old_fasta, work / "db" / "old")

    stock_old = blast(str(args.blastp), work / "db" / "old", query_path, work / "stock_old.tsv", threads="2")
    stock_a = blast(str(args.blastp), work / "db" / "new", query_path, work / "stock_a.tsv", threads="2")
    stock_b = blast(str(args.blastp), work / "db" / "new", query_path, work / "stock_b.tsv", threads="2")
    stock_lines = body_lines(Path(work / "stock_a.tsv").read_text())
    old_lines = body_lines(Path(work / "stock_old.tsv").read_text())
    identical = stock_a["md5"] == stock_b["md5"]
    report["stock_vs_stock"] = {
        "byte_identical": identical,
        "ordered_body_equal": body_lines(Path(work / "stock_a.tsv").read_text()) == body_lines(Path(work / "stock_b.tsv").read_text()),
        "md5_a": stock_a["md5"],
        "md5_b": stock_b["md5"],
        "n_lines": len(stock_lines),
        "wall_a_s": stock_a["wall_s"],
        "wall_b_s": stock_b["wall_s"],
        "argv": stock_a["argv"],
        "release": "2026_03",
    }
    report["stock_old"] = {"n_lines": len(old_lines), "md5": stock_old["md5"], "wall_s": stock_old["wall_s"]}
    write_out(args.out, report)
    if not identical or not report["stock_vs_stock"]["ordered_body_equal"]:
        report["outcome"] = "STOP_STOCK"
        return finish(report, args.out)
    if len(stock_lines) < row_floor:
        report["outcome"] = "INCONCLUSIVE"
        report["why"] = f"{len(stock_lines)} rows, floor is {row_floor}"
        return finish(report, args.out)

    cache = work / "cache.sqlite"
    cli_old = run_cli(
        pipe=args.pipe, queries=query_path, reference=args.release_old,
        out_dir=work / "cli_2026_01", cache=cache, blastp=str(args.blastp),
    )
    cli_new = run_cli(
        pipe=args.pipe, queries=query_path, reference=args.release_new,
        out_dir=work / "cli_2026_03", cache=cache, blastp=str(args.blastp),
    )
    old_body = tool_body(work / "cli_2026_01")
    new_body = tool_body(work / "cli_2026_03")
    cli_old["vs_stock"] = ordered_compare(old_lines, old_body)
    cli_new["vs_stock"] = ordered_compare(stock_lines, new_body)
    report["cli"] = {"2026_01": cli_old, "2026_03": cli_new}
    write_out(args.out, report)

    log("unpinned and drop controls")
    entries = parse_reference(args.release_new)
    by_name = {entry.primary: entry for entry in entries}
    subjects = subjects_of(Path(work / "stock_a.tsv").read_text())
    missing_names = [name for name in subjects if name not in by_name]
    kept = [by_name[name] for name in subjects if name in by_name]
    rng = random.Random(DROP_SEED)
    k = max(1, int(round(0.05 * len(subjects))))
    dropped = sorted(rng.sample(list(subjects), k)) if len(subjects) >= k else list(subjects)
    dropped_set = set(dropped)
    reduced = [entry for entry in kept if entry.primary not in dropped_set]
    write_entries(kept, work / "candidates.faa")
    write_entries(reduced, work / "candidates_drop.faa")
    del entries, by_name, kept, reduced
    gc.collect()
    make_db(str(args.makeblastdb), work / "candidates.faa", work / "db" / "candidates")
    make_db(str(args.makeblastdb), work / "candidates_drop.faa", work / "db" / "candidates_drop")
    dbsize = str(values["total_entry_length"])
    unpinned = blast(
        str(args.blastp), work / "db" / "candidates", query_path, work / "unpinned.tsv", threads="2",
    )
    negative = blast(
        str(args.blastp), work / "db" / "candidates_drop", query_path, work / "negative.tsv",
        threads="2", extra=["-dbsize", dbsize],
    )
    unpinned_cmp = ordered_compare(stock_lines, body_lines(Path(work / "unpinned.tsv").read_text()))
    negative_cmp = ordered_compare(stock_lines, body_lines(Path(work / "negative.tsv").read_text()))
    digest = hashlib.sha256("\n".join(dropped).encode()).hexdigest()
    report["controls"] = {
        "candidate_subjects": len(subjects),
        "n_absent": len(missing_names),
        "dbsize": values["total_entry_length"],
        "unpinned": {
            "n_lines": unpinned["n_lines"],
            "wall_s": unpinned["wall_s"],
            "argv": unpinned["argv"],
            "vs_stock": unpinned_cmp,
            "pass": unpinned_cmp["ordered_body_equal"] is False,
        },
        "negative": {
            "seed": DROP_SEED,
            "dropped": k,
            "dropped_sha256": digest,
            "n_lines": negative["n_lines"],
            "wall_s": negative["wall_s"],
            "argv": negative["argv"],
            "vs_stock": negative_cmp,
            "body_pass": (not negative_cmp["ordered_body_equal"]) and negative_cmp.get("missing", 0) > 0,
        },
    }
    if cli_new.get("decision") == "SHIP":
        cand: dict[str, set[str]] = {}
        for line in stock_lines:
            cells = line.split("\t") if "\t" in line else line.split()
            if len(cells) < 2 or cells[1] in dropped_set:
                continue
            cand.setdefault(cells[0], set()).add(cells[1])
        cand = {key: names for key, names in cand.items() if names}
        try:
            report["controls"]["negative"]["shipped_check"] = shipped_drop(
                cache, query_path, args.release_new, str(args.blastp), cand, work,
            )
        except Exception as exc:
            report["controls"]["negative"]["shipped_check"] = {
                "control": "INCONCLUSIVE",
                "reason": f"{type(exc).__name__}: {exc}"[:1500],
            }
    else:
        report["controls"]["negative"]["shipped_check"] = {
            "control": "not_reached",
            "reason": "2026_03 decision was not SHIP",
        }
    shipped = report["controls"]["negative"]["shipped_check"]
    drop_refused = bool(shipped.get("check_refused"))
    report["controls"]["negative"]["pass"] = bool(
        report["controls"]["negative"]["body_pass"] and drop_refused
    )
    write_out(args.out, report)

    both_ship = cli_old.get("decision") == "SHIP" and cli_new.get("decision") == "SHIP"
    both_bytes = (
        cli_old["vs_stock"]["ordered_body_equal"] and cli_new["vs_stock"]["ordered_body_equal"]
    )
    controls_ok = report["controls"]["unpinned"]["pass"] and report["controls"]["negative"]["pass"]
    if both_ship and both_bytes and controls_ok:
        report["outcome"] = "SHIP"
    elif not report["controls"]["negative"]["body_pass"] or not report["controls"]["unpinned"]["pass"]:
        report["outcome"] = "CONTROL_FAILED"
    elif not both_ship or not both_bytes:
        report["outcome"] = "NOT_SHIP"
    else:
        report["outcome"] = "NOT_SHIP"
    report["provenance"] = provenance(versions=versions)
    return finish(report, args.out)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException as exc:
        if PAYLOAD is not None and os.environ.get("ACTS_OUT") and "outcome" not in PAYLOAD:
            PAYLOAD["crashed"] = f"{type(exc).__name__}: {exc}"[:2000]
            PAYLOAD["outcome"] = "FAIL"
            write_out(Path(os.environ["ACTS_OUT"]), PAYLOAD)
        raise
