"""Generic FASTA→table memo: cache PRODUCED cells, reassemble names."""

from __future__ import annotations

import json
from pathlib import Path

from acts.cache import RecordCache
from acts.fasta import FastaRec, write_fasta
from acts.infer_fasta import (
    PROBE_N,
    InferError,
    TableContract,
    extract_rows,
    load_or_infer_table,
    probe_late_cols,
    reassemble_rows,
    refuse_table,
    run_table_tool,
    unclassified_cols,
)
from acts.infer_fasta import _group, _group_raw, _split_body
from acts.table import align_body, body_lines, meta_lines


def cached_search(
    recs: list[FastaRec],
    cache: RecordCache,
    contract: TableContract,
    argv: list[str],
    work: Path,
    contract_path: Path | None = None,
) -> tuple[str, dict]:
    keys = [rec.key for rec in recs]
    hits: list[FastaRec] = []
    misses: list[FastaRec] = []
    for rec, k in zip(recs, keys):
        if cache.get(k) is not None:
            hits.append(rec)
        else:
            misses.append(rec)

    header: list[str] = []
    if misses:
        work.mkdir(parents=True, exist_ok=True)
        miss_path = write_fasta(work / "miss.fa", misses)
        miss_out = run_table_tool(argv, miss_path)
        header = meta_lines(miss_out)
        raw_body = body_lines(miss_out)
        _, rows = _split_body(miss_out, contract.delim)
        groups = _group(rows, contract.query_col)
        groups_raw = _group_raw(raw_body, rows, contract.query_col)
        unseen = unclassified_cols(rows, contract)
        if unseen:
            carriers = [r for r in misses if r.name in groups]
            probe_late_cols(argv, carriers, contract, work / "late", unseen)
            if contract_path is not None:
                contract.save(contract_path)
        for rec in misses:
            cache.put(
                rec.key,
                json.dumps(
                    extract_rows(
                        groups_raw.get(rec.name, []),
                        groups.get(rec.name, []),
                        contract,
                    )
                ),
            )
    elif recs:
        one = write_fasta(work / "header_harvest.fa", recs[:1])
        header = meta_lines(run_table_tool(argv, one))

    rebuilt_body: list[str] = []
    holes = 0
    for rec, k in zip(recs, keys):
        raw = cache.get(k)
        if raw is None:
            holes += 1
            continue
        rebuilt_body.extend(reassemble_rows(rec, json.loads(raw), contract))

    if contract.pad_widths:
        rebuilt_body = align_body(rebuilt_body, contract.delim, contract.pad_widths)
    text = "\n".join(header + rebuilt_body) + ("\n" if header or rebuilt_body else "")
    stats = {
        "n_records": len(recs),
        "n_hits": len(hits),
        "n_misses": len(misses),
        "n_cache_holes": holes,
        "cache_size_after": len(cache),
        "match": contract.match,
    }
    return text, stats


def contract_path_for(cache_path: Path) -> Path:
    return cache_path.with_name(cache_path.name + ".contract.json")


def prepare_table_contract(
    argv: list[str],
    recs: list[FastaRec],
    work: Path,
    cache_path: Path,
    *,
    probe_n: int = PROBE_N,
) -> TableContract:
    path = contract_path_for(cache_path)
    try:
        return load_or_infer_table(argv, recs, work / "probe", path, probe_n=probe_n)
    except InferError as exc:
        rec = refuse_table(exc, argv)
        rec.save(path)
        raise
