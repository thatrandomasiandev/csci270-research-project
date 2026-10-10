#!/usr/bin/env python3
"""Post-hoc check of why B1 column 2 matched no normalizer.

The shipped fitter is not modified. This script re-runs the locked probe,
keeps the three tabular outputs, and classifies each joined row whose
alignment body differs. Classification is:

- ``same_hsp``: query, subject, and the alignment interval match, and the
  geometry columns match.
- ``same_interval_different_score``: the interval matches and pident,
  length, mismatch, or gapopen does not.
- ``misaligned_row_key``: the whole interval is present on a different
  part row for that pair, and the fitter joined another row.
- ``different_hsp``: the whole interval is absent from the part.

A duplicate ``(qseqid, sseqid, index)`` is reported separately. ``index_rows``
refuses that case, so it is not a joined row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

from acts.provenance import provenance  # noqa: E402
from acts.reference_fit import (  # noqa: E402
    PROBE_K,
    PROBE_SEED,
    infer_key_columns,
    parse_table_text,
    partition_indices,
    row_key,
)
from acts.reference_formats import alias_map, parse_reference, read_records  # noqa: E402
from acts.reference_run import probe_fit, subprocess_invoke  # noqa: E402

from run_reference_boundary import (  # noqa: E402
    OUTFMT_FIELDS,
    b1_argv,
    column_residuals,
    file_md5,
    prep_command,
    select_queries,
    tool_version,
)

# qstart, qend, sstart, send
INTERVAL = (6, 7, 8, 9)
# pident, length, mismatch, gapopen, plus the interval
BODY = (2, 3, 4, 5, 6, 7, 8, 9)


def _sig(row: list[str], cols: tuple[int, ...]) -> tuple[str, ...]:
    return tuple(row[c] for c in cols)


def classify_joined(
    whole_row: list[str],
    part_row: list[str],
    part_pair_rows: list[list[str]],
) -> str:
    """Classify one fitter join. ``part_pair_rows`` is every part HSP for the pair."""
    if _sig(whole_row, BODY) == _sig(part_row, BODY):
        return "same_hsp"
    whole_interval = _sig(whole_row, INTERVAL)
    if whole_interval == _sig(part_row, INTERVAL):
        return "same_interval_different_score"
    try:
        joined_at = part_pair_rows.index(part_row)
    except ValueError:
        joined_at = None
    elsewhere = [
        row
        for i, row in enumerate(part_pair_rows)
        if _sig(row, INTERVAL) == whole_interval and i != joined_at
    ]
    if elsewhere:
        return "misaligned_row_key"
    return "different_hsp"


def index_trace(rows: list[list[str]], record_col: int, entry_col: int) -> dict:
    """Why ``infer_key_columns`` stopped on its chosen index. One collision example."""
    width = min(len(row) for row in rows)
    groups: Counter[tuple[str, str]] = Counter(
        (row[record_col], row[entry_col]) for row in rows
    )
    columns = []
    chosen = None
    for col in range(width):
        if col in (record_col, entry_col):
            continue
        digits = all(row[col].lstrip("-").isdigit() for row in rows)
        seen: dict[tuple[str, str, str], list[str]] = {}
        example = None
        for row in rows:
            key = (row[record_col], row[entry_col], row[col])
            if key in seen and example is None:
                example = {"key": list(key), "row_a": seen[key], "row_b": row}
            else:
                seen[key] = row
        unique = example is None
        field = OUTFMT_FIELDS[col] if col < len(OUTFMT_FIELDS) else str(col)
        columns.append(
            {
                "index": col,
                "field": field,
                "all_digits": digits,
                "unique_within_pair": unique,
                "collision": example,
            }
        )
        if digits and unique and chosen is None:
            chosen = col
            break
    return {
        "pairs": len(groups),
        "pairs_with_multiple_rows": sum(1 for count in groups.values() if count > 1),
        "chosen_index": chosen,
        "chosen_field": OUTFMT_FIELDS[chosen] if chosen is not None else None,
        "columns_examined": columns,
    }


def _pair_rows(indexed: dict[tuple[str, str, str], list[str]]) -> dict[tuple[str, str], list[list[str]]]:
    grouped: dict[tuple[str, str], list[list[str]]] = {}
    for (record, entry, _index), cells in indexed.items():
        grouped.setdefault((record, entry), []).append(cells)
    return grouped


def analyze_tables(
    entries,
    record_ids: set[str],
    part_lists: list[list[int]],
    whole_text: str,
    part_texts: list[str],
) -> dict:
    """Classify joined mismatches and refit columns on the matching subset."""
    aliases = alias_map(entries)
    whole = parse_table_text("out", whole_text)
    parts = [parse_table_text("out", text) for text in part_texts]
    record_col, entry_col, index_col = infer_key_columns(whole.rows, record_ids, set(aliases))
    whole_idx = {}
    part_idx = []
    duplicate_errors = []
    try:
        from acts.reference_fit import index_rows

        whole_idx = index_rows(whole.rows, record_col, entry_col, index_col)
        part_idx = [index_rows(part.rows, record_col, entry_col, index_col) for part in parts]
    except ValueError as exc:
        duplicate_errors.append(str(exc))
    if duplicate_errors:
        return {
            "duplicate_row_key": duplicate_errors,
            "index_trace": index_trace(whole.rows, record_col, entry_col),
        }

    union: set = set()
    overlap: set = set()
    for indexed in part_idx:
        overlap |= union & set(indexed)
        union |= set(indexed)
    whole_pairs = _pair_rows(whole_idx)
    part_pairs = [_pair_rows(indexed) for indexed in part_idx]
    mismatches = []
    geometry_keys = []
    for key, cells in whole_idx.items():
        producers = [i for i, indexed in enumerate(part_idx) if key in indexed]
        if len(producers) != 1:
            continue
        part_i = producers[0]
        part_cells = part_idx[part_i][key]
        pair = (cells[record_col], cells[entry_col])
        kind = classify_joined(cells, part_cells, part_pairs[part_i].get(pair, []))
        if kind == "same_hsp":
            geometry_keys.append(key)
            continue
        mismatches.append(
            {
                "classification": kind,
                "part": part_i,
                "record": pair[0],
                "subject": pair[1],
                "index_field": OUTFMT_FIELDS[index_col] if index_col is not None else None,
                "index_value": key[2],
                "whole": cells,
                "part_row": part_cells,
                "whole_hsps": whole_pairs.get(pair, []),
                "part_hsps": part_pairs[part_i].get(pair, []),
            }
        )

    def _keep(indexed: dict, keys: set) -> str:
        lines = [" ".join(indexed[key]) for key in indexed if key in keys]
        return "\n".join(lines) + ("\n" if lines else "")

    matched = set(geometry_keys)
    matched_residuals = column_residuals(
        entries,
        record_ids,
        part_lists,
        _keep(whole_idx, matched),
        [_keep(indexed, matched) for indexed in part_idx],
    )
    return {
        "duplicate_row_key": [],
        "index_col": index_col,
        "index_field": OUTFMT_FIELDS[index_col] if index_col is not None else None,
        "index_trace": index_trace(whole.rows, record_col, entry_col),
        "key_sets": {
            "whole": len(whole_idx),
            "union": len(union),
            "only_union": len(union - set(whole_idx)),
            "only_whole": len(set(whole_idx) - union),
            "in_two_parts": len(overlap),
            "aligned": len(geometry_keys) + len(mismatches),
        },
        "joined_same_hsp": len(geometry_keys),
        "joined_mismatch": len(mismatches),
        "mismatch_counts": dict(Counter(item["classification"] for item in mismatches)),
        "mismatches": mismatches,
        "geometry_matched_residuals": _slim(matched_residuals),
    }


def _slim(residuals: dict) -> dict:
    """Fits and the worst row. Drops nothing the addendum needs; the file is small."""
    columns = []
    for col in residuals.get("columns", []):
        members = {}
        for name, info in col.get("members", {}).items():
            if "fits" in info:
                members[name] = {
                    "fits": info["fits"],
                    "n": info["n"],
                    "n_consistent": info["n_consistent"],
                    "max_abs_residual": info["max_abs_residual"],
                }
            else:
                members[name] = info
        columns.append(
            {
                "index": col["index"],
                "field": col.get("field"),
                "index_col": col.get("index_col"),
                "members": members,
            }
        )
    return {"key_sets": residuals.get("key_sets"), "columns": columns}


def _md5_text(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def run(args: argparse.Namespace) -> dict:
    if not os.environ.get("SLURM_JOB_ID") and not args.allow_login:
        raise RuntimeError("refusing to search outside a SLURM job; submit with sbatch")
    blast_text = tool_version(args.blastp)
    make_text = tool_version(args.makeblastdb)
    reference = Path(args.reference)
    queries = Path(args.queries)
    entries = parse_reference(reference)
    records = select_queries(read_records(queries))
    record_ids = {record.key for record in records}
    parts = partition_indices(len(entries), PROBE_K, PROBE_SEED)
    calls: list[dict] = []

    def invoke(probe_records, probe_entries):
        print(
            f"invoke n_records={len(probe_records)} n_entries={len(probe_entries)}",
            file=sys.stderr,
            flush=True,
        )
        tables = raw_invoke(probe_records, probe_entries)
        calls.append(
            {
                "n": len(probe_entries),
                "hashes": [entry.content_hash for entry in probe_entries],
                "tables": tables,
            }
        )
        return tables

    raw_invoke = subprocess_invoke(
        b1_argv(args.blastp, threads=args.threads),
        input_slot=Path("{input}"),
        reference_slot=Path("{reference}"),
        prep=prep_command(args.makeblastdb),
        scratch=Path(args.work),
    )
    fit = probe_fit(entries, records, invoke)
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
    table_dir = Path(args.tables)
    table_dir.mkdir(parents=True, exist_ok=True)
    (table_dir / "whole.tsv").write_text(whole)
    for i, text in enumerate(part_texts):
        (table_dir / f"part{i}.tsv").write_text(text)
    diagnosis = analyze_tables(entries, record_ids, parts, whole, part_texts)
    diagnosis.update(
        {
            "label": "POST-HOC",
            "job_compared": 12864923,
            "fit_decision": fit.decision,
            "fit_reason": fit.reason,
            "probe_invocations": fit.probe_invocations,
            "table_md5": {"whole": _md5_text(whole), **{f"part{i}": _md5_text(text) for i, text in enumerate(part_texts)}},
            "table_rows": {
                "whole": len(parse_table_text("out", whole).rows),
                **{f"part{i}": len(parse_table_text("out", text).rows) for i, text in enumerate(part_texts)},
            },
            "queries": {"ids": [record.key for record in records], "md5": file_md5(queries)},
            "reference": {
                "path": str(reference),
                "md5": file_md5(reference),
                "n_entries": len(entries),
            },
            "argv": b1_argv(args.blastp, threads=args.threads),
            "old_fsc": os.environ.get("OLD_FSC"),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "slurm_partition": os.environ.get("SLURM_JOB_PARTITION"),
            "provenance": provenance(versions={"blastp": blast_text, "makeblastdb": make_text}),
        }
    )
    return diagnosis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Post-hoc HSP diagnosis for the BLAST boundary")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--blastp", required=True)
    parser.add_argument("--makeblastdb", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--tables", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--threads", default="4")
    parser.add_argument("--allow-login", action="store_true")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        document = run(args)
    except Exception as exc:
        document = {
            "label": "POST-HOC",
            "error": str(exc),
            "provenance": provenance(versions={}),
        }
        out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        print(f"DIAGNOSIS_ERROR {exc}", file=sys.stderr)
        return 1
    out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(
        f"mismatches={document.get('joined_mismatch')} "
        f"counts={document.get('mismatch_counts')} "
        f"fit={document.get('fit_decision')} {document.get('fit_reason')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
