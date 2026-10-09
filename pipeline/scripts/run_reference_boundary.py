#!/usr/bin/env python3
"""B1 boundary: shipped fitter against NCBI BLAST+ blastp.

The closed family is not extended here. Decisions come from probe_fit.
Residuals are computed with the public half-ULP predicate so the JSON
can show every member, including members the fitter rejected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.provenance import provenance  # noqa: E402
from acts.reference_fit import (  # noqa: E402
    ENTRY_COUNT,
    IDENTITY,
    MEMBERS,
    PER_KEY,
    PROBE_K,
    PROBE_SEED,
    TOTAL_LENGTH,
    consistent,
    half_ulp,
    infer_key_columns,
    index_rows,
    parse_finite,
    parse_table_text,
    partition_indices,
)
from acts.reference_formats import Entry, RecordItem, alias_map, parse_reference, read_records  # noqa: E402
from acts.reference_run import probe_fit, subprocess_invoke  # noqa: E402

BLAST_VERSION = "2.14.1"
QUERY_N = 20
OUTFMT = (
    "6 qseqid sseqid pident length mismatch gapopen "
    "qstart qend sstart send evalue bitscore"
)
OUTFMT_FIELDS = OUTFMT.split()[1:]
EVALUE_FIELD = "evalue"
BITSCORE_FIELD = "bitscore"
PREP_TEMPLATE = "{makeblastdb} -in {{reference}} -dbtype prot -out {{reference}}"


def b1_argv(blastp: str, *, threads: str = "4") -> list[str]:
    """The pre-registered B1 command. Placeholders are filled by the fitter."""
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
        str(threads),
    ]


def prep_command(makeblastdb: str) -> str:
    return PREP_TEMPLATE.format(makeblastdb=makeblastdb)


def select_queries(records: list[RecordItem], *, n: int = QUERY_N, seed: int = PROBE_SEED) -> list[RecordItem]:
    """Shipped sampler. File order of the chosen records is preserved."""
    from acts.reference_fit import sample_record_indices

    chosen = sample_record_indices(len(records), n, seed)
    return [records[i] for i in chosen]


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tool_version(binary: str) -> str:
    proc = subprocess.run([binary, "-version"], check=False, capture_output=True, text=True)
    text = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0 or BLAST_VERSION not in text:
        raise RuntimeError(f"{binary} -version did not report {BLAST_VERSION}: {text[:400]}")
    return text


def _phi(kind: str, row: dict, *, n_entries: int, part_counts: list[int], total_length: int, part_lengths: list[int], whole_counts: dict[str, int], part_row_counts: list[dict[str, int]]) -> float:
    if kind == IDENTITY:
        return 1.0
    if kind == ENTRY_COUNT:
        part_n = part_counts[row["part"]]
        if part_n == 0:
            return float("nan")
        return n_entries / part_n
    if kind == TOTAL_LENGTH:
        part_l = part_lengths[row["part"]]
        if part_l == 0:
            return float("nan")
        return total_length / part_l
    part_c = part_row_counts[row["part"]].get(row["record_key"], 0)
    whole_c = whole_counts.get(row["record_key"], 0)
    if part_c == 0:
        return float("nan")
    return whole_c / part_c


def _finite(value: float) -> float | None:
    if isinstance(value, float) and math.isfinite(value):
        return value
    return None


def column_residuals(
    entries: list[Entry],
    record_ids: set[str],
    part_lists: list[list[int]],
    whole_text: str,
    part_texts: list[str],
) -> dict:
    """Key-set counts and per-member residuals on one partition.

    The decision stays with probe_fit. This report uses the same printed
    tokens, the same alias map, and the public half-ULP predicate.
    """
    aliases = alias_map(entries)
    entry_ids = set(aliases)
    part_of = {}
    for part_i, indices in enumerate(part_lists):
        for index in indices:
            part_of[index] = part_i
    whole = parse_table_text("out", whole_text)
    parts = [parse_table_text("out", text) for text in part_texts]
    source = whole.rows or next((part.rows for part in parts if part.rows), [])
    if not source:
        return {"key_sets": {"whole": 0, "union": 0, "only_union": 0, "only_whole": 0, "equal": True}, "columns": []}
    try:
        record_col, entry_col, index_col = infer_key_columns(source, record_ids, entry_ids)
        whole_idx = index_rows(whole.rows, record_col, entry_col, index_col)
        part_idx = [index_rows(part.rows, record_col, entry_col, index_col) for part in parts]
    except ValueError as exc:
        return {"error": str(exc), "columns": []}
    union: set = set()
    overlap: set = set()
    for indexed in part_idx:
        overlap |= union & set(indexed)
        union |= set(indexed)
    only_union = union - set(whole_idx)
    only_whole = set(whole_idx) - union
    aligned = []
    for key, cells in whole_idx.items():
        producers = [i for i, indexed in enumerate(part_idx) if key in indexed]
        if len(producers) != 1:
            continue
        entry_index = aliases[cells[entry_col]]
        aligned.append(
            {
                "record_key": cells[record_col],
                "part": producers[0],
                "whole": cells,
                "part_cells": part_idx[producers[0]][key],
                "entry_index": entry_index,
            }
        )
    part_counts = [len(indices) for indices in part_lists]
    lengths = [entry.length for entry in entries]
    part_lengths = [sum(lengths[i] for i in indices) for indices in part_lists]
    whole_counts: dict[str, int] = {}
    for key in whole_idx:
        whole_counts[key[0]] = whole_counts.get(key[0], 0) + 1
    part_row_counts: list[dict[str, int]] = []
    for indexed in part_idx:
        counts: dict[str, int] = {}
        for key in indexed:
            counts[key[0]] = counts.get(key[0], 0) + 1
        part_row_counts.append(counts)
    width = 0
    if aligned:
        width = min(min(len(row["whole"]), len(row["part_cells"])) for row in aligned)
    columns = []
    kinds = (
        (IDENTITY, IDENTITY),
        (ENTRY_COUNT, ENTRY_COUNT),
        (TOTAL_LENGTH, TOTAL_LENGTH),
        (f"{PER_KEY}:out", PER_KEY),
    )
    for col in range(width):
        tokens = [row["whole"][col] for row in aligned] + [row["part_cells"][col] for row in aligned]
        numeric = all(parse_finite(token) is not None for token in tokens) and bool(tokens)
        members = {}
        if numeric:
            for label, kind in kinds:
                residuals = []
                n_ok = 0
                worst = None
                for row in aligned:
                    phi = _phi(
                        kind,
                        row,
                        n_entries=len(entries),
                        part_counts=part_counts,
                        total_length=sum(lengths),
                        part_lengths=part_lengths,
                        whole_counts=whole_counts,
                        part_row_counts=part_row_counts,
                    )
                    part = row["part_cells"][col]
                    whole_token = row["whole"][col]
                    if kind == IDENTITY:
                        ok = part == whole_token
                        residual = 0.0 if ok else None
                        if (
                            not ok
                            and parse_finite(part) is not None
                            and parse_finite(whole_token) is not None
                        ):
                            residual = abs(float(part) - float(whole_token))
                    elif (
                        parse_finite(part) is None
                        or parse_finite(whole_token) is None
                        or not math.isfinite(phi)
                    ):
                        residual = None
                        ok = False
                    else:
                        residual = abs(float(part) * phi - float(whole_token))
                        tolerance = half_ulp(whole_token) + half_ulp(part) * abs(phi)
                        ok = residual <= tolerance
                    if ok:
                        n_ok += 1
                    if residual is not None:
                        residuals.append(residual)
                    score = residual if residual is not None else -1.0
                    if worst is None or score > (worst["abs_residual"] if worst["abs_residual"] is not None else -1.0):
                        worst = {
                            "record_key": row["record_key"],
                            "part": row["part"],
                            "part_printed": part,
                            "whole_printed": whole_token,
                            "phi": _finite(phi),
                            "abs_residual": residual,
                        }
                members[label] = {
                    "n": len(aligned),
                    "n_consistent": n_ok,
                    "fits": n_ok == len(aligned) and len(aligned) > 0,
                    "max_abs_residual": max(residuals) if residuals else None,
                    "worst": worst,
                }
        else:
            same = all(row["whole"][col] == row["part_cells"][col] for row in aligned)
            members["byte"] = {"n": len(aligned), "byte_identical": same}
        field = OUTFMT_FIELDS[col] if col < len(OUTFMT_FIELDS) else None
        columns.append(
            {
                "index": col,
                "field": field,
                "record_col": record_col,
                "entry_col": entry_col,
                "index_col": index_col,
                "numeric": numeric,
                "members": members,
            }
        )
    return {
        "key_sets": {
            "whole": len(whole_idx),
            "union": len(union),
            "only_union": len(only_union),
            "only_whole": len(only_whole),
            "in_two_parts": len(overlap),
            "aligned": len(aligned),
            "equal": union == set(whole_idx) and not overlap,
        },
        "part_counts": part_counts,
        "part_lengths": part_lengths,
        "total_length": sum(lengths),
        "n_entries": len(entries),
        "columns": columns,
    }


def result_document(**payload: object) -> dict:
    """Every measured file carries the decision, the residuals, and provenance."""
    versions = dict(payload.pop("versions", {}) or {})
    block = provenance(versions=versions)
    document = dict(payload)
    document["provenance"] = block
    return document


def _write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def run(args: argparse.Namespace) -> dict:
    if not os.environ.get("SLURM_JOB_ID") and not args.allow_login:
        raise RuntimeError("refusing to search outside a SLURM job; submit with sbatch")
    blast_text = tool_version(args.blastp)
    make_text = tool_version(args.makeblastdb)
    reference = Path(args.reference)
    queries = Path(args.queries)
    entries = parse_reference(reference)
    records = select_queries(read_records(queries))
    if len(records) != QUERY_N:
        raise RuntimeError(f"query draw returned {len(records)} records, expected {QUERY_N}")
    parts = partition_indices(len(entries), PROBE_K, PROBE_SEED)
    calls: list[dict] = []

    def invoke(probe_records, probe_entries):
        print(
            f"invoke n_records={len(probe_records)} n_entries={len(probe_entries)}",
            file=sys.stderr,
            flush=True,
        )
        tables = raw_invoke(probe_records, probe_entries)
        calls.append({"n": len(probe_entries), "hashes": [entry.content_hash for entry in probe_entries], "tables": tables})
        return tables

    raw_invoke = subprocess_invoke(
        b1_argv(args.blastp, threads=args.threads),
        input_slot=Path("{input}"),
        reference_slot=Path("{reference}"),
        prep=prep_command(args.makeblastdb),
        scratch=Path(args.work),
    )
    # The name raw_invoke is bound before invoke runs. probe_fit calls invoke later.
    fit = probe_fit(entries, records, invoke)
    primary = None
    primary_error = None
    try:
        if calls:
            whole = calls[0]["tables"]["out"]
            part_texts = []
            for indices in parts:
                expected = {entries[i].content_hash for i in indices}
                match = next(
                    call
                    for call in calls[1:]
                    if set(call["hashes"]) == expected and len(call["hashes"]) == len(expected)
                )
                part_texts.append(match["tables"]["out"])
            primary = column_residuals(
                entries,
                {record.key for record in records},
                parts,
                whole,
                part_texts,
            )
    except Exception as exc:
        primary_error = str(exc)
    document = result_document(
        setting="B1",
        protocol="docs/REFERENCE_BOUNDARY_PROTOCOL.md",
        decision=fit.decision,
        reason=fit.reason,
        used_tie_break=fit.used_tie_break,
        primary_key_equal=fit.primary_key_equal,
        probe_invocations=fit.probe_invocations,
        fit=fit.as_dict(),
        primary_residuals=primary,
        primary_residuals_error=primary_error,
        family=list(MEMBERS),
        queries={
            "n": len(records),
            "seed": PROBE_SEED,
            "sampler": "sample_record_indices",
            "ids": [record.key for record in records],
            "path": str(queries),
            "md5": file_md5(queries),
        },
        reference={
            "path": str(reference),
            "md5": file_md5(reference),
            "n_entries": len(entries),
            "total_entry_length": sum(entry.length for entry in entries),
        },
        argv=b1_argv(args.blastp, threads=args.threads),
        prep=prep_command(args.makeblastdb),
        old_fsc=os.environ.get("OLD_FSC"),
        versions={"blastp": blast_text, "makeblastdb": make_text},
    )
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BLAST+ blastp boundary for the closed reference fitter")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--blastp", required=True)
    parser.add_argument("--makeblastdb", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--threads", default="4")
    parser.add_argument("--allow-login", action="store_true", help="tests only; the job must not set this")
    args = parser.parse_args(argv)
    out = Path(args.out)
    try:
        document = run(args)
    except Exception as exc:
        document = result_document(
            setting="B1",
            protocol="docs/REFERENCE_BOUNDARY_PROTOCOL.md",
            decision="REFUSE",
            reason=str(exc),
            used_tie_break=False,
            primary_key_equal=None,
            probe_invocations=0,
            fit=None,
            primary_residuals=None,
            family=list(MEMBERS),
            versions={},
        )
        _write(out, document)
        print(f"REFUSE {exc}", file=sys.stderr)
        return 1
    _write(out, document)
    print(f"{document['decision']} {document['reason']}")
    return 0 if document["decision"] in {"SHIP", "REFUSE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
