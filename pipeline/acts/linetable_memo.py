"""Generic lines→table memo: cache PRODUCED cells, reassemble the echo column."""

from __future__ import annotations

import json
from pathlib import Path

from acts.cache import RecordCache
from acts.infer_linetable import (
    PROBE_N,
    InferError,
    LineTableContract,
    _group,
    _record_raw,
    extract_rows,
    header_and_body,
    load_or_infer_linetable,
    parse_linetable,
    probe_late_cols,
    reassemble_rows,
    refuse_linetable,
    run_linetable_tool,
    unclassified_cols,
    write_lines,
)


def cached_linetable(
    lines: list[str],
    cache: RecordCache,
    contract: LineTableContract,
    argv: list[str],
    work: Path,
    contract_path: Path | None = None,
) -> tuple[str, dict]:
    hits: list[str] = []
    misses: list[str] = []
    miss_unique: list[str] = []
    seen_miss: set[str] = set()
    for line in lines:
        if cache.get(line) is not None:
            hits.append(line)
        else:
            misses.append(line)
            if line not in seen_miss:
                seen_miss.add(line)
                miss_unique.append(line)

    header: list[str] = []
    if miss_unique:
        work.mkdir(parents=True, exist_ok=True)
        miss_path = write_lines(work / "miss.txt", miss_unique)
        miss_out = run_linetable_tool(argv, miss_path)
        header, _ = header_and_body(miss_out)
        _, _, raw_body, rows = parse_linetable(miss_out)
        groups_raw = _record_raw(miss_unique, raw_body, rows, contract)
        unseen = unclassified_cols(rows, contract)
        if unseen:
            carriers = [ln for ln in miss_unique if groups_raw.get(ln)]
            probe_late_cols(argv, carriers, contract, work / "late", unseen)
            if contract_path is not None:
                contract.save(contract_path)
        if contract.correspondence == "echo":
            grouped_rows = _group(rows, contract.query_col)
        else:
            k = contract.rows_per_record
            grouped_rows = {
                line: rows[i * k : (i + 1) * k] for i, line in enumerate(miss_unique)
            }
        for line in miss_unique:
            cache.put(
                line,
                json.dumps(
                    extract_rows(
                        groups_raw.get(line, []),
                        grouped_rows.get(line, []),
                        contract,
                    )
                ),
            )
    elif lines:
        one = write_lines(work / "header_harvest.txt", lines[:1])
        header, _ = header_and_body(run_linetable_tool(argv, one))

    rebuilt_body: list[str] = []
    holes = 0
    for line in lines:
        raw = cache.get(line)
        if raw is None:
            holes += 1
            continue
        rebuilt_body.extend(reassemble_rows(line, json.loads(raw), contract))

    hit_unique: list[str] = []
    seen_hit: set[str] = set()
    for line in hits:
        if line not in seen_hit:
            seen_hit.add(line)
            hit_unique.append(line)

    text = "\n".join(header + rebuilt_body) + ("\n" if header or rebuilt_body else "")
    stats = {
        "n_records": len(lines),
        "n_hits": len(hits),
        "n_misses": len(misses),
        "n_cache_holes": holes,
        "cache_size_after": len(cache),
        "match": contract.match,
        "hit_recs": hit_unique,
    }
    return text, stats


def contract_path_for(cache_path: Path) -> Path:
    return cache_path.with_name(cache_path.name + ".contract.json")


def prepare_linetable_contract(
    argv: list[str],
    lines: list[str],
    work: Path,
    cache_path: Path,
    *,
    probe_n: int = PROBE_N,
    probe_seed: int = 20260927,
    subset_mode: str = "batched",
) -> LineTableContract:
    path = contract_path_for(cache_path)
    try:
        return load_or_infer_linetable(
            argv,
            lines,
            work / "probe",
            path,
            probe_n=probe_n,
            probe_seed=probe_seed,
            subset_mode=subset_mode,
        )
    except InferError as exc:
        rec = refuse_linetable(exc, argv)
        rec.subset_mode = subset_mode
        rec.save(path)
        raise
