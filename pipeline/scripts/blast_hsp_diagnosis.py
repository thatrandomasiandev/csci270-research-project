#!/usr/bin/env python3
"""Diagnose the one BLAST+ line that matched no normalizer.

The shipped fitter is not modified. This reruns the locked B1 probe
(seed 20261006, 20 queries, Swiss-Prot 2026_03, the B1 argv) and then
pins one option at a time on the query whose HSP differed.

A size pin is applied the way TARE applies it: the placeholder is the
whole reference's value, and the flag is inserted after the tool name.
The half-plus-pin output is compared with the unpinned whole run.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.fasta import FastaRec, write_fasta  # noqa: E402
from acts.provenance import provenance  # noqa: E402
from acts.reference_fit import PROBE_K, PROBE_SEED, partition_indices, sample_record_indices  # noqa: E402
from acts.reference_formats import parse_reference, read_records, write_entries  # noqa: E402
from acts.reference_run import write_record_file  # noqa: E402

QUERY_N = 20
TARGET_QUERY = "WP_000153074.1"
TARGET_SUBJECT = "sp|A0KJE6|LOLA_AERHH"
EXPECTED_IDS = [
    "WP_000020880.1",
    "WP_000066560.1",
    "WP_000149991.1",
    "WP_000153074.1",
    "WP_000211501.1",
    "WP_000230277.1",
    "WP_000551020.1",
    "WP_000679812.1",
    "WP_000687768.1",
    "WP_000763311.1",
    "WP_000833470.1",
    "WP_000839596.1",
    "WP_001287378.1",
    "WP_001297409.1",
    "WP_001303782.1",
    "WP_001324445.1",
    "WP_001324556.1",
    "WP_001425728.1",
    "WP_029396194.1",
    "WP_071448054.1",
]
EXPECTED_WHOLE = (
    "WP_000153074.1\tsp|A0KJE6|LOLA_AERHH\t33.333\t36\t23\t1\t3\t37\t1\t36\t205\t25.0"
)
EXPECTED_PART = (
    "WP_000153074.1\tsp|A0KJE6|LOLA_AERHH\t21.875\t128\t72\t5\t3\t105\t1\t125\t180\t24.3"
)
EXPECTED_PART_LENGTHS = [104399849, 104617994]
EXPECTED_PART_COUNTS = [287874, 287874]
EXPECTED_TOTAL = 209017843
EXPECTED_N = 575748
OUTFMT = (
    "6 qseqid sseqid pident length mismatch gapopen "
    "qstart qend sstart send evalue bitscore"
)
INTERVAL = (6, 7, 8, 9)
BODY = (2, 3, 4, 5, 6, 7, 8, 9)


def log(message: str) -> None:
    print(message, flush=True)


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tool_version(binary: str) -> str:
    proc = subprocess.run([binary, "-version"], check=False, capture_output=True, text=True)
    text = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0 or "2.14.1" not in text:
        raise SystemExit(f"{binary} -version did not report 2.14.1:\n{text[:400]}")
    return text


def help_lines(binary: str) -> list[str]:
    proc = subprocess.run([binary, "-help"], check=False, capture_output=True, text=True)
    text = (proc.stdout or "") + (proc.stderr or "")
    needles = (
        "dbsize",
        "searchsp",
        "comp_based_stats",
        "max_hsps",
        "max_target_seqs",
        "ungapped",
        "num_threads",
        "xdrop",
        "evalue",
        "sum_stats",
        "culling",
    )
    return [line.strip() for line in text.splitlines() if any(needle in line for needle in needles)]


def b1_argv(blastp: str, threads: str) -> list[str]:
    return [
        blastp,
        "-query",
        "{input}",
        "-db",
        "{reference}",
        "-out",
        "{output}",
        "-outfmt",
        OUTFMT,
        "-max_target_seqs",
        "100000",
        "-evalue",
        "1000",
        "-num_threads",
        threads,
    ]


def run_cmd(argv: list[str], out_path: Path) -> dict:
    """Run one command. A nonempty ``.ok`` marker skips it on resume."""
    marker = out_path.with_suffix(out_path.suffix + ".ok")
    stamp_path = out_path.with_suffix(out_path.suffix + ".argv.json")
    stamp = {"argv": argv}
    if marker.is_file() and out_path.is_file() and out_path.stat().st_size > 0:
        recorded = json.loads(stamp_path.read_text()) if stamp_path.is_file() else None
        if recorded == stamp:
            log(f"resume {out_path.name}")
            return json.loads(marker.read_text())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    proc = subprocess.run(argv, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - started
    if proc.returncode != 0:
        err = ((proc.stderr or "") + (proc.stdout or ""))[-800:]
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(argv[:6])}\n{err}")
    payload = {
        "argv": argv,
        "wall_s": wall,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-1500:],
        "stderr_tail": (proc.stderr or "")[-1500:],
    }
    stamp_path.write_text(json.dumps(stamp))
    marker.write_text(json.dumps(payload))
    log(f"ran {out_path.name} in {wall:.1f}s")
    return payload


def make_db(makeblastdb: str, fasta: Path, db_out: Path) -> dict:
    argv = [makeblastdb, "-in", str(fasta), "-dbtype", "prot", "-out", str(db_out)]
    # The marker lives beside the db title, which is not a file blastp reads.
    marker_host = Path(str(db_out) + ".make.ok")
    if marker_host.is_file() and Path(str(db_out) + ".psq").is_file():
        log(f"resume db {db_out.name}")
        return json.loads(marker_host.read_text())
    db_out.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    proc = subprocess.run(argv, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - started
    if proc.returncode != 0:
        err = ((proc.stderr or "") + (proc.stdout or ""))[-800:]
        raise SystemExit(f"makeblastdb failed ({proc.returncode}): {err}")
    payload = {
        "argv": argv,
        "wall_s": wall,
        "stdout_tail": (proc.stdout or "")[-1500:],
        "stderr_tail": (proc.stderr or "")[-1500:],
    }
    marker_host.write_text(json.dumps(payload))
    log(f"makeblastdb {db_out.name} in {wall:.1f}s")
    return payload


def blast(
    blastp: str,
    db: Path,
    query: Path,
    out_path: Path,
    *,
    threads: str,
    extra: list[str] | None = None,
    outfmt: str | None = OUTFMT,
    evalue: str | None = "1000",
    max_target_seqs: str | None = "100000",
) -> dict:
    argv = [blastp, *(extra or []), "-query", str(query), "-db", str(db), "-out", str(out_path)]
    if outfmt is not None:
        argv.extend(["-outfmt", outfmt])
    if max_target_seqs is not None:
        argv.extend(["-max_target_seqs", max_target_seqs])
    if evalue is not None:
        argv.extend(["-evalue", evalue])
    argv.extend(["-num_threads", threads])
    payload = run_cmd(argv, out_path)
    payload["n_lines"] = sum(1 for line in out_path.read_text().splitlines() if line.strip())
    payload["md5"] = file_md5(out_path)
    return payload


def body_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def cells_of(line: str) -> list[str]:
    return line.split("\t") if "\t" in line else line.split()


def multiset_md5(lines: list[str]) -> str:
    digest = hashlib.md5()
    for line in sorted(lines):
        digest.update(line.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def pair_rows(text: str, query: str, subject: str) -> list[str]:
    found = []
    for line in body_lines(text):
        cells = cells_of(line)
        if len(cells) >= 2 and cells[0] == query and cells[1] == subject:
            found.append(line)
    return found


def classify_line(whole_line: str, part_line: str) -> str:
    whole = cells_of(whole_line)
    part = cells_of(part_line)
    if tuple(whole[i] for i in BODY) == tuple(part[i] for i in BODY):
        if whole == part:
            return "same_line"
        return "same_interval_different_score"
    if tuple(whole[i] for i in INTERVAL) == tuple(part[i] for i in INTERVAL):
        return "same_interval_different_score"
    return "different_hsp"


def self_check() -> dict:
    kind = classify_line(EXPECTED_WHOLE, EXPECTED_PART)
    same = classify_line(EXPECTED_WHOLE, EXPECTED_WHOLE)
    if kind != "different_hsp" or same != "same_line":
        raise SystemExit(f"classifier self-check failed: published={kind} control={same}")
    stats = parse_report_stats(
        "           575,748 sequences; 209,017,843 total letters\n"
        "Effective search space used: 12,345,678,901\n"
    )
    if stats.get("total_letters_printed") != 209017843 or stats.get("effective_search_space") != 12345678901:
        raise SystemExit(f"report parser self-check failed: {stats}")
    return {"published_pair": kind, "identical_control": same, "report_parser": "ok"}


def subject_index(entries, subject: str) -> int:
    found = [i for i, entry in enumerate(entries) if subject in entry.keys or entry.primary == subject]
    if len(found) != 1:
        raise SystemExit(f"{subject} matched {len(found)} entries")
    return found[0]


def write_subset(entries, indices: list[int], path: Path) -> None:
    if path.is_file() and path.stat().st_size > 0:
        log(f"resume fasta {path.name}")
        return
    chosen = [entries[i] for i in sorted(indices)]
    write_entries(chosen, path)


def _integers(line: str) -> list[int]:
    cleaned = line.replace(",", "")
    return [int(token) for token in cleaned.split() if token.isdigit()]


def parse_report_stats(text: str) -> dict:
    stats: dict = {"lines": []}
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if "total letters" in lowered or "effective search space" in lowered:
            stats["lines"].append(stripped)
        if "Effective search space" in stripped:
            digits = _integers(stripped)
            if digits:
                stats["effective_search_space"] = digits[-1]
        if "total letters" in lowered:
            digits = _integers(stripped)
            if len(digits) >= 2:
                stats["n_sequences_printed"] = digits[0]
                stats["total_letters_printed"] = digits[1]
    return stats


def rows_touching(text: str, subjects: set[str]) -> list[str]:
    out = []
    for line in body_lines(text):
        cells = cells_of(line)
        if len(cells) >= 2 and cells[1] in subjects:
            out.append(line)
    return out


def compare_row_sets(whole_lines: list[str], part_lines: list[str]) -> dict:
    """Difference classes for one subject-restricted table pair."""
    if not whole_lines:
        return {
            "byte_identical": False,
            "missing": 0,
            "extra": len(part_lines),
            "different_hsp": 0,
            "same_interval_different_score": 0,
            "value_only": 0,
            "examples": [],
            "reason": "no whole rows joined on subject id",
        }
    whole_counts: dict[str, int] = {}
    part_counts: dict[str, int] = {}
    for line in whole_lines:
        whole_counts[line] = whole_counts.get(line, 0) + 1
    for line in part_lines:
        part_counts[line] = part_counts.get(line, 0) + 1
    missing = []
    extra = []
    for line, count in whole_counts.items():
        gap = count - part_counts.get(line, 0)
        if gap > 0:
            missing.extend([line] * gap)
    for line, count in part_counts.items():
        gap = count - whole_counts.get(line, 0)
        if gap > 0:
            extra.extend([line] * gap)
    whole_by_pair: dict[tuple[str, str], list[str]] = {}
    part_by_pair: dict[tuple[str, str], list[str]] = {}
    for line in missing:
        cells = cells_of(line)
        whole_by_pair.setdefault((cells[0], cells[1]), []).append(line)
    for line in extra:
        cells = cells_of(line)
        part_by_pair.setdefault((cells[0], cells[1]), []).append(line)
    classes = {
        "byte_identical": not missing and not extra,
        "missing": len(missing),
        "extra": len(extra),
        "different_hsp": 0,
        "same_interval_different_score": 0,
        "value_only": 0,
        "examples": [],
    }
    for pair, whole_group in whole_by_pair.items():
        part_group = part_by_pair.get(pair, [])
        if not part_group:
            classes["examples"].append({"class": "missing", "pair": list(pair), "whole": whole_group[:2]})
            continue
        kind = classify_line(whole_group[0], part_group[0])
        classes[kind] = classes.get(kind, 0) + 1
        if len(classes["examples"]) < 6:
            classes["examples"].append(
                {"class": kind, "pair": list(pair), "whole": whole_group[0], "part": part_group[0]}
            )
    for pair, part_group in part_by_pair.items():
        if pair not in whole_by_pair and len(classes["examples"]) < 6:
            classes["examples"].append({"class": "extra", "pair": list(pair), "part": part_group[0]})
    return classes


def key_sets(whole_text: str, part_texts: list[str]) -> dict:
    def keys(text: str) -> set[tuple[str, str, str]]:
        found = set()
        for line in body_lines(text):
            cells = cells_of(line)
            if len(cells) >= 9:
                found.add((cells[0], cells[1], cells[8]))
        return found

    whole = keys(whole_text)
    parts = [keys(text) for text in part_texts]
    union: set[tuple[str, str, str]] = set()
    overlap: set[tuple[str, str, str]] = set()
    for part in parts:
        overlap |= union & part
        union |= part
    return {
        "whole": len(whole),
        "union": len(union),
        "only_union": len(union - whole),
        "only_whole": len(whole - union),
        "in_two_parts": len(overlap),
        "aligned": len(whole & union),
    }


def dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--blastp")
    parser.add_argument("--makeblastdb")
    parser.add_argument("--work", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--threads", default="4")
    parser.add_argument("--self-check-only", action="store_true")
    args = parser.parse_args()

    checked = self_check()
    if args.self_check_only:
        print(json.dumps(checked))
        return 0
    missing = [
        name
        for name in ("reference", "queries", "blastp", "makeblastdb", "work", "out")
        if getattr(args, name) is None
    ]
    if missing:
        raise SystemExit("missing arguments: " + ", ".join(missing))

    work = args.work
    work.mkdir(parents=True, exist_ok=True)
    threads = str(args.threads)
    versions = {
        "blastp": tool_version(args.blastp),
        "makeblastdb": tool_version(args.makeblastdb),
    }
    log("parsing reference and queries")
    entries = parse_reference(args.reference)
    records = read_records(args.queries)
    chosen = sample_record_indices(len(records), QUERY_N, PROBE_SEED)
    probe = [records[i] for i in chosen]
    parts = partition_indices(len(entries), PROBE_K, PROBE_SEED)
    total = sum(entry.length for entry in entries)
    part_lengths = [sum(entries[i].length for i in indices) for indices in parts]
    subject_at = subject_index(entries, TARGET_SUBJECT)
    subject_part = next(i for i, indices in enumerate(parts) if subject_at in indices)
    query_ids = [rec.key for rec in probe]
    setup = {
        "n_entries": len(entries),
        "total_entry_length": total,
        "part_counts": [len(indices) for indices in parts],
        "part_lengths": part_lengths,
        "query_ids": query_ids,
        "query_ids_match_b1": query_ids == EXPECTED_IDS,
        "partition_matches_b1": (
            len(entries) == EXPECTED_N
            and total == EXPECTED_TOTAL
            and [len(indices) for indices in parts] == EXPECTED_PART_COUNTS
            and part_lengths == EXPECTED_PART_LENGTHS
        ),
        "subject_index": subject_at,
        "subject_part": subject_part,
        "reference_md5": file_md5(args.reference),
        "queries_md5": file_md5(args.queries),
        "b1_argv": b1_argv(args.blastp, threads),
        "help_lines": help_lines(args.blastp),
    }
    if not setup["query_ids_match_b1"] or not setup["partition_matches_b1"]:
        payload = {
            "decision": "STOP",
            "reason": "parsed probe does not match the locked B1 sample",
            "setup": setup,
            "self_check": checked,
            "provenance": provenance(versions=versions),
        }
        dump(args.out, payload)
        raise SystemExit("parsed probe does not match the locked B1 sample")
    if TARGET_QUERY not in query_ids:
        raise SystemExit("target query is not in the probe")

    query_path = work / "probe.faa"
    write_record_file(probe, query_path)
    one_path = work / "one.faa"
    one = next(rec for rec in probe if rec.key == TARGET_QUERY)
    if not one_path.is_file():
        write_fasta(one_path, [FastaRec(one.name, one.description, one.sequence)])

    log("writing databases, then releasing the parsed FASTA")
    whole_fa = work / "whole.faa"
    write_subset(entries, list(range(len(entries))), whole_fa)
    part_subjects = []
    for part_i, indices in enumerate(parts):
        write_subset(entries, indices, work / f"part{part_i}.faa")
        part_subjects.append({entries[i].primary for i in indices})
    del entries
    gc.collect()
    whole_db = work / "db" / "whole"
    whole_prep = make_db(args.makeblastdb, whole_fa, whole_db)

    log("stock versus stock")
    stock_a = blast(args.blastp, whole_db, query_path, work / "stock_a.tsv", threads=threads)
    stock_b = blast(args.blastp, whole_db, query_path, work / "stock_b.tsv", threads=threads)
    lines_a = body_lines((work / "stock_a.tsv").read_text())
    lines_b = body_lines((work / "stock_b.tsv").read_text())
    stock = {
        "byte_identical": (work / "stock_a.tsv").read_bytes() == (work / "stock_b.tsv").read_bytes(),
        "multiset_identical": sorted(lines_a) == sorted(lines_b),
        "n_lines": len(lines_a),
        "md5_a": stock_a["md5"],
        "md5_b": stock_b["md5"],
        "multiset_md5": multiset_md5(lines_a),
        "wall_a_s": stock_a["wall_s"],
        "wall_b_s": stock_b["wall_s"],
    }
    if not stock["multiset_identical"]:
        payload = {
            "decision": "STOP",
            "reason": "stock versus stock hit sets differ",
            "setup": setup,
            "stock_vs_stock": stock,
            "self_check": checked,
            "provenance": provenance(versions=versions),
        }
        dump(args.out, payload)
        raise SystemExit("stock versus stock hit sets differ")

    log("half databases")
    part_texts = []
    part_runs = []
    for part_i in range(len(parts)):
        fasta = work / f"part{part_i}.faa"
        db = work / "db" / f"part{part_i}"
        prep = make_db(args.makeblastdb, fasta, db)
        run = blast(args.blastp, db, query_path, work / f"part{part_i}.tsv", threads=threads)
        run["prep"] = prep
        part_runs.append(run)
        part_texts.append((work / f"part{part_i}.tsv").read_text())

    whole_text = (work / "stock_a.tsv").read_text()
    whole_target = pair_rows(whole_text, TARGET_QUERY, TARGET_SUBJECT)
    part_target = pair_rows(part_texts[subject_part], TARGET_QUERY, TARGET_SUBJECT)
    other_target = pair_rows(part_texts[1 - subject_part], TARGET_QUERY, TARGET_SUBJECT)
    query_sample = []
    n_query_lines = 0
    for line in body_lines(whole_text):
        cells = cells_of(line)
        if cells and cells[0] == TARGET_QUERY:
            n_query_lines += 1
            if len(query_sample) < 3:
                query_sample.append(line)
    reproduction = {
        "key_sets": key_sets(whole_text, part_texts),
        "whole_lines": whole_target,
        "part_lines": part_target,
        "other_part_lines": other_target,
        "subject_part": subject_part,
        "matches_published_whole": whole_target == [EXPECTED_WHOLE],
        "matches_published_part": part_target == [EXPECTED_PART],
        "n_query_lines": n_query_lines,
        "sample_query_lines": query_sample,
        "classification": (
            classify_line(whole_target[0], part_target[0])
            if len(whole_target) == 1 and len(part_target) == 1
            else "not_one_line_each"
        ),
    }
    log(
        f"target class={reproduction['classification']} "
        f"published_whole={reproduction['matches_published_whole']} "
        f"published_part={reproduction['matches_published_part']}"
    )
    if reproduction["classification"] != "different_hsp":
        payload = {
            "decision": "STOP",
            "reason": "the locked probe did not reproduce one different HSP for the published pair",
            "self_check": checked,
            "setup": setup,
            "whole_prep": whole_prep,
            "stock_vs_stock": stock,
            "part_runs": [
                {"wall_s": run["wall_s"], "n_lines": run["n_lines"], "md5": run["md5"]} for run in part_runs
            ],
            "reproduction": reproduction,
            "starting_commit": "507c45fcd2eb3c3e7850791cb2daf5e84400ffab",
            "provenance": provenance(versions=versions),
        }
        dump(args.out, payload)
        log(f"wrote {args.out} decision=STOP")
        return 0

    log("reading effective search space")
    stats_run = blast(
        args.blastp,
        whole_db,
        one_path,
        work / "one_stats.txt",
        threads=threads,
        outfmt="0",
        evalue="10",
        max_target_seqs="1",
    )
    stats = parse_report_stats((work / "one_stats.txt").read_text())
    searchsp = stats.get("effective_search_space")
    letters = stats.get("total_letters_printed", total)

    def one_pair(
        db: Path,
        label: str,
        extra: list[str] | None,
        threads_override: str | None = None,
        query_file: Path = one_path,
    ) -> dict:
        path = work / "pins" / f"{label}.tsv"
        run = blast(
            args.blastp,
            db,
            query_file,
            path,
            threads=threads_override or threads,
            extra=extra,
        )
        lines = pair_rows(path.read_text(), TARGET_QUERY, TARGET_SUBJECT)
        return {
            "label": label,
            "query": str(query_file),
            "extra": extra or [],
            "threads": threads_override or threads,
            "wall_s": run["wall_s"],
            "n_lines": run["n_lines"],
            "target_lines": lines,
            "matches_unpinned_whole": bool(whole_target) and lines == whole_target,
            "matches_probe_part": bool(part_target) and lines == part_target,
        }

    part_db = work / "db" / f"part{subject_part}"
    one_half = one_pair(part_db, "one_half_unpinned", None)
    one_whole = one_pair(whole_db, "one_whole_unpinned", None)
    one_matches_probe = one_half["target_lines"] == part_target and one_whole["target_lines"] == whole_target
    sweep_query = one_path if one_matches_probe else query_path
    if not one_matches_probe:
        log("one-query lines differ from the 20-query probe; the pin sweep uses the probe file")
    pin_runs = [
        one_half,
        one_whole,
        one_pair(part_db, "half_unpinned", None, query_file=sweep_query),
        one_pair(whole_db, "whole_unpinned_one", None, query_file=sweep_query),
        one_pair(part_db, "half_dbsize", ["-dbsize", str(total)], query_file=sweep_query),
        one_pair(whole_db, "whole_dbsize", ["-dbsize", str(total)], query_file=sweep_query),
    ]
    if letters != total:
        pin_runs.append(
            one_pair(part_db, "half_dbsize_printed", ["-dbsize", str(letters)], query_file=sweep_query)
        )
    if searchsp is not None:
        pin_runs.append(
            one_pair(part_db, "half_searchsp", ["-searchsp", str(searchsp)], query_file=sweep_query)
        )
        pin_runs.append(
            one_pair(whole_db, "whole_searchsp", ["-searchsp", str(searchsp)], query_file=sweep_query)
        )
    for mode in ("0", "1", "2"):
        extra = ["-comp_based_stats", mode]
        pin_runs.append(one_pair(part_db, f"half_cbs_{mode}", extra, query_file=sweep_query))
        pin_runs.append(one_pair(whole_db, f"whole_cbs_{mode}", extra, query_file=sweep_query))
    pin_runs.append(one_pair(part_db, "half_max_hsps_1", ["-max_hsps", "1"], query_file=sweep_query))
    pin_runs.append(one_pair(whole_db, "whole_max_hsps_1", ["-max_hsps", "1"], query_file=sweep_query))
    # Mode 2 rejects -ungapped. The arm turns composition adjustment off with it.
    ungapped = ["-ungapped", "-comp_based_stats", "0"]
    pin_runs.append(one_pair(part_db, "half_ungapped", ungapped, query_file=sweep_query))
    pin_runs.append(one_pair(whole_db, "whole_ungapped", ungapped, query_file=sweep_query))
    pin_runs.append(one_pair(part_db, "half_threads_1", None, "1", sweep_query))
    pin_runs.append(one_pair(whole_db, "whole_threads_1", None, "1", sweep_query))

    by_label = {item["label"]: item for item in pin_runs}

    def both_match(half_label: str, whole_label: str) -> bool:
        half_lines = by_label[half_label]["target_lines"]
        whole_lines = by_label[whole_label]["target_lines"]
        return bool(half_lines) and half_lines == whole_lines

    candidates = []
    if by_label["half_dbsize"]["matches_unpinned_whole"]:
        candidates.append(
            {
                "name": "dbsize",
                "template": "-dbsize {total_entry_length}",
                "value": total,
                "tare_pin": True,
                "reason": "half plus the whole-reference letter count reproduces the unpinned whole line",
            }
        )
    if searchsp is not None and by_label["half_searchsp"]["matches_unpinned_whole"]:
        candidates.append(
            {
                "name": "searchsp",
                "template": None,
                "value": searchsp,
                "tare_pin": False,
                "reason": (
                    "half plus this query's effective search space reproduces the unpinned whole line; "
                    "TARE placeholders are entry_count and total_entry_length, not a per-query search space"
                ),
            }
        )
    for mode in ("0", "1", "2"):
        if both_match(f"half_cbs_{mode}", f"whole_cbs_{mode}"):
            candidates.append(
                {
                    "name": f"comp_based_stats_{mode}",
                    "template": f"-comp_based_stats {mode}",
                    "tare_pin": False,
                    "matches_unpinned_whole": by_label[f"half_cbs_{mode}"]["matches_unpinned_whole"],
                    "reason": "both sides with this mode report the same line; it changes the scoring mode, not only the subset",
                }
            )
    if both_match("half_ungapped", "whole_ungapped"):
        candidates.append(
            {
                "name": "ungapped",
                "template": "-ungapped",
                "tare_pin": False,
                "matches_unpinned_whole": by_label["half_ungapped"]["matches_unpinned_whole"],
                "reason": "ungapped searches agree; gapped extension is where the two databases diverge",
            }
        )

    confirmation = None
    ship = None
    # Checkpoint the one-query sweep before the full-probe searches.
    checkpoint = {
        "decision": "IN_PROGRESS",
        "self_check": checked,
        "setup": setup,
        "stock_vs_stock": stock,
        "reproduction": reproduction,
        "report_stats": stats,
        "one_query_matches_probe": one_matches_probe,
        "sweep_query": str(sweep_query),
        "pins": pin_runs,
        "one_query_candidates": candidates,
        "starting_commit": "507c45fcd2eb3c3e7850791cb2daf5e84400ffab",
        "provenance": provenance(versions=versions),
    }
    dump(args.out, checkpoint)

    # A shippable pin has to be one flag value on the full 20-query probe.
    # -dbsize is one database-wide number. One -searchsp is the target
    # query's search space and is not expected to fit the other queries.
    confirm_plan = None
    if any(item["name"] == "dbsize" for item in candidates):
        confirm_plan = ("dbsize", "-dbsize {total_entry_length}", ["-dbsize", str(total)], True)
    elif searchsp is not None and any(item["name"] == "searchsp" for item in candidates):
        confirm_plan = ("searchsp", None, ["-searchsp", str(searchsp)], False)
    if confirm_plan is not None:
        name, template, extra, tare_pin = confirm_plan
        log(f"confirming {name} on the full probe")
        confirm_parts = []
        all_ok = True
        for part_i, subjects in enumerate(part_subjects):
            db = work / "db" / f"part{part_i}"
            run = blast(
                args.blastp,
                db,
                query_path,
                work / f"part{part_i}_{name}.tsv",
                threads=threads,
                extra=extra,
            )
            whole_rows = rows_touching(whole_text, subjects)
            part_rows = rows_touching((work / f"part{part_i}_{name}.tsv").read_text(), subjects)
            compared = compare_row_sets(whole_rows, part_rows)
            compared["part"] = part_i
            compared["wall_s"] = run["wall_s"]
            compared["n_part_lines"] = run["n_lines"]
            compared["n_whole_rows_in_part"] = len(whole_rows)
            if len(whole_rows) == 0:
                all_ok = False
            confirm_parts.append(compared)
            all_ok = all_ok and compared["byte_identical"] and len(whole_rows) > 0
        confirmation = {
            "pin": template,
            "name": name,
            "extra": extra,
            "tare_placeholder": tare_pin,
            "parts": confirm_parts,
            "reproduces_whole": all_ok,
        }
        if all_ok and tare_pin:
            ship = {"candidate": True, "pin": template, "value": total}
        elif all_ok:
            ship = {
                "candidate": False,
                "reason": (
                    f"{name} reproduces this probe but is not a TARE placeholder pin; "
                    "the value is per query"
                ),
            }
        else:
            ship = {"candidate": False, "reason": f"{name} does not reproduce the full probe"}
    else:
        ship = {
            "candidate": False,
            "reason": "no tested option makes the half reproduce the unpinned whole line",
        }

    payload = {
        "decision": "SHIP_CANDIDATE" if ship.get("candidate") else "REFUSE",
        "ship": ship,
        "self_check": checked,
        "setup": setup,
        "whole_prep": whole_prep,
        "stock_vs_stock": stock,
        "part_runs": [
            {"wall_s": run["wall_s"], "n_lines": run["n_lines"], "md5": run["md5"]} for run in part_runs
        ],
        "reproduction": reproduction,
        "report_stats": stats,
        "stats_wall_s": stats_run["wall_s"],
        "one_query_matches_probe": one_matches_probe,
        "sweep_query": str(sweep_query),
        "pins": pin_runs,
        "one_query_candidates": candidates,
        "full_probe_confirmation": confirmation,
        "starting_commit": "507c45fcd2eb3c3e7850791cb2daf5e84400ffab",
        "provenance": provenance(versions=versions),
    }
    dump(args.out, payload)
    log(f"wrote {args.out} decision={payload['decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
