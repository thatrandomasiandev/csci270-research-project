#!/usr/bin/env python3
"""BLAST+ pin exactness pilot. Locked by docs/BLAST_PIN_PROTOCOL.md.

Seed 20261141 selects the 20 queries. Seed 20261142 selects the 5% drop.
The script does not change TARE's gate.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import random
import subprocess
import sys
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

QUERY_SEED = 20261141
DROP_SEED = 20261142
N_QUERIES = 20
MIN_ROWS = 1000
PIN = "-dbsize {total_entry_length}"
OUTFMT = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore"


def log(message: str) -> None:
    print(message, flush=True)


def write_queries(src: Path, dest: Path) -> dict:
    records = read_records(src)
    chosen = sample_record_indices(len(records), N_QUERIES, QUERY_SEED)
    picked = [records[i] for i in chosen]
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for rec in picked:
        header = rec.name if not rec.description else f"{rec.name} {rec.description}"
        lines.append(f">{header}\n{rec.seq}\n")
    dest.write_text("".join(lines))
    return {
        "source": str(src),
        "n_source_records": len(records),
        "seed": QUERY_SEED,
        "n": N_QUERIES,
        "indices": chosen,
        "ids": [rec.name for rec in picked],
        "md5": file_md5(dest),
    }


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
    payload = {
        "argv": cmd,
        "returncode": proc.returncode,
        "decision": decision,
        "why": why,
        "stdout_tail": (proc.stdout or "")[-2500:],
        "stderr_tail": (proc.stderr or "")[-2500:],
        "decision_md5": hashlib.md5(decision_text.encode()).hexdigest() if decision_text else "",
    }
    if proc.returncode not in (0, 1) or not decision:
        err = (proc.stderr or proc.stdout or "")[-800:]
        raise SystemExit(f"acts run failed ({proc.returncode}) for {reference.name}: {err}")
    stamp.write_text(json.dumps(payload, indent=2) + "\n")
    log(f"cli {reference.name} -> {decision or 'NO DECISION'} ({proc.returncode})")
    return payload


def table_text(path: Path) -> str:
    return path.read_text() if path.is_file() else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries-src", type=Path, required=True)
    parser.add_argument("--release-old", type=Path, required=True)
    parser.add_argument("--release-new", type=Path, required=True)
    parser.add_argument("--blastp", type=Path, required=True)
    parser.add_argument("--makeblastdb", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pipe", type=Path, required=True)
    args = parser.parse_args()

    work = args.work
    work.mkdir(parents=True, exist_ok=True)
    query_path = work / "queries.faa"
    query_info = write_queries(args.queries_src, query_path)
    log(f"queries {query_info['ids']}")

    versions = {
        "blastp": tool_version(str(args.blastp)),
        "makeblastdb": tool_version(str(args.makeblastdb)),
    }
    report: dict = {
        "protocol": "pipeline/docs/BLAST_PIN_PROTOCOL.md",
        "starting_note": "pilot seed 20261141; drop seed 20261142",
        "queries": query_info,
        "pin": PIN,
        "provenance": provenance(versions=versions),
    }

    log("parsing 2026_03 for the stock database")
    entries = parse_reference(args.release_new)
    values = pin_values(entries)
    report["release_new"] = {
        "path": str(args.release_new),
        "md5": file_md5(args.release_new),
        "n_entries": values["entry_count"],
        "total_entry_length": values["total_entry_length"],
    }
    fasta = work / "new.faa"
    db = work / "db" / "new"
    write_entries(entries, fasta)
    del entries
    gc.collect()
    make_db(str(args.makeblastdb), fasta, db)

    stock_a = blast(str(args.blastp), db, query_path, work / "stock_a.tsv", threads="2")
    stock_b = blast(str(args.blastp), db, query_path, work / "stock_b.tsv", threads="2")
    stock_text = table_text(work / "stock_a.tsv")
    stock_lines = body_lines(stock_text)
    identical = file_md5(work / "stock_a.tsv") == file_md5(work / "stock_b.tsv")
    report["stock_vs_stock"] = {
        "byte_identical": identical,
        "md5_a": stock_a["md5"],
        "md5_b": stock_b["md5"],
        "n_lines": len(stock_lines),
        "wall_a_s": stock_a["wall_s"],
        "wall_b_s": stock_b["wall_s"],
        "argv": stock_a["argv"],
    }
    if not identical:
        report["outcome"] = "STOP_STOCK"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        log("stop: stock versus stock differs")
        return 2
    if len(stock_lines) < MIN_ROWS:
        report["outcome"] = "INCONCLUSIVE"
        report["why"] = f"{len(stock_lines)} rows, floor is {MIN_ROWS}"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        log(report["why"])
        return 0

    cache = work / "cache.sqlite"
    cli_old = run_cli(
        pipe=args.pipe, queries=query_path, reference=args.release_old,
        out_dir=work / "cli_2026_01", cache=cache, blastp=str(args.blastp),
    )
    cli_new = run_cli(
        pipe=args.pipe, queries=query_path, reference=args.release_new,
        out_dir=work / "cli_2026_03", cache=cache, blastp=str(args.blastp),
    )
    report["cli"] = {"2026_01": cli_old, "2026_03": cli_new}

    log("candidate-subset controls")
    entries = parse_reference(args.release_new)
    by_name = {entry.primary: entry for entry in entries}
    subjects = subjects_of(stock_text)
    missing_names = [name for name in subjects if name not in by_name]
    kept_entries = [by_name[name] for name in subjects if name in by_name]
    rng = random.Random(DROP_SEED)
    k = max(1, int(round(0.05 * len(subjects))))
    dropped = sorted(rng.sample(subjects, k)) if len(subjects) >= k else list(subjects)
    dropped_set = set(dropped)
    reduced = [entry for entry in kept_entries if entry.primary not in dropped_set]
    positive_fa = work / "candidates.faa"
    negative_fa = work / "candidates_drop.faa"
    write_entries(kept_entries, positive_fa)
    write_entries(reduced, negative_fa)
    del entries, by_name, kept_entries, reduced
    gc.collect()
    make_db(str(args.makeblastdb), positive_fa, work / "db" / "candidates")
    make_db(str(args.makeblastdb), negative_fa, work / "db" / "candidates_drop")
    dbsize = str(values["total_entry_length"])
    positive = blast(
        str(args.blastp), work / "db" / "candidates", query_path, work / "positive.tsv",
        threads="2", extra=["-dbsize", dbsize],
    )
    negative = blast(
        str(args.blastp), work / "db" / "candidates_drop", query_path, work / "negative.tsv",
        threads="2", extra=["-dbsize", dbsize],
    )
    positive_cmp = compare_row_sets(stock_lines, body_lines(table_text(work / "positive.tsv")))
    negative_cmp = compare_row_sets(stock_lines, body_lines(table_text(work / "negative.tsv")))
    positive_cmp.pop("examples", None)
    negative_examples = negative_cmp.get("examples", [])[:3]
    negative_cmp["examples"] = negative_examples
    report["controls"] = {
        "candidate_subjects": len(subjects),
        "subjects_absent_from_parser": missing_names[:8],
        "n_absent": len(missing_names),
        "dbsize": values["total_entry_length"],
        "positive": {
            "n_lines": positive["n_lines"],
            "wall_s": positive["wall_s"],
            "argv": positive["argv"],
            "vs_stock": positive_cmp,
            "pass": positive_cmp.get("byte_identical") is True and not missing_names,
        },
        "negative": {
            "seed": DROP_SEED,
            "dropped": k,
            "dropped_ids": dropped,
            "n_lines": negative["n_lines"],
            "wall_s": negative["wall_s"],
            "argv": negative["argv"],
            "vs_stock": negative_cmp,
            "pass": (not negative_cmp.get("byte_identical")) and negative_cmp.get("missing", 0) > 0,
        },
    }
    positive_ok = report["controls"]["positive"]["pass"]
    negative_ok = report["controls"]["negative"]["pass"]
    cli_decisions = (cli_old.get("decision"), cli_new.get("decision"))
    if positive_ok and negative_ok and cli_decisions == ("SHIP", "SHIP"):
        report["outcome"] = "SHIP_THROUGH_TOOL"
    elif positive_ok and negative_ok:
        report["outcome"] = "PIN_EXACT_GATE_DID_NOT_SHIP"
    elif not positive_ok:
        report["outcome"] = "PIN_DOES_NOT_REPRODUCE_CANDIDATES"
    else:
        report["outcome"] = "NEGATIVE_CONTROL_FAILED"
    report["provenance"] = provenance(versions=versions)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    log(f"wrote {args.out} outcome={report['outcome']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
