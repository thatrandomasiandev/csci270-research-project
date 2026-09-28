"""Generic VCF memo: cache PRODUCED parts, reassemble onto the query record."""

from __future__ import annotations

import json
from pathlib import Path

from acts.cache import RecordCache
from acts.infer_vcf import (
    PROBE_N,
    InferError,
    RecordContract,
    extract_produced,
    load_or_infer,
    probe_new_info_keys,
    reassemble_record,
    refuse_result,
    run_vcf_tool,
    unclassified_info_keys,
    write_vcf,
)
from acts.vcf import body_lines, is_header, read_maybe_gz
from acts.vcf_fields import COL_INFO, cache_key, parse_info, split_record


def read_vcf_parts(path: Path) -> tuple[list[str], list[str]]:
    text = read_maybe_gz(path)
    header = [ln for ln in text.splitlines() if is_header(ln)]
    return header, body_lines(text)


def cached_annotate(
    header: list[str],
    body: list[str],
    cache: RecordCache,
    contract: RecordContract,
    argv: list[str],
    work: Path,
    contract_path: Path | None = None,
) -> tuple[str, dict]:
    hits: list[str] = []
    misses: list[str] = []
    keys: list[str] = []
    for ln in body:
        k = cache_key(ln, contract.cache_key_fields)
        keys.append(k)
        if cache.get(k) is not None:
            hits.append(ln)
        else:
            misses.append(ln)

    header_src = header
    if misses:
        work.mkdir(parents=True, exist_ok=True)
        miss_path = write_vcf(work / "miss.vcf", header, misses)
        miss_out = run_vcf_tool(argv, miss_path)
        header_src = [ln for ln in miss_out.splitlines() if is_header(ln)] or header
        out_body = body_lines(miss_out)
        if len(out_body) != len(misses):
            raise InferError(
                "REFUSE_MATCH",
                f"tool is not 1:1 on misses ({len(out_body)} outs / {len(misses)} ins)",
            )
        unseen = unclassified_info_keys(out_body, contract)
        if unseen:
            carriers: list[str] = []
            for rec_in, rec_out in zip(misses, out_body):
                parts = split_record(rec_out)
                keys_here = (
                    {k for k, _ in parse_info(parts[COL_INFO])}
                    if len(parts) > COL_INFO
                    else set()
                )
                if keys_here.intersection(unseen):
                    carriers.append(rec_in)
                if len(carriers) >= 200:
                    break
            probe_new_info_keys(argv, header, carriers, contract, work / "late", unseen)
            if contract_path is not None:
                contract.save(contract_path)
        for rec_in, rec_out in zip(misses, out_body):
            k = cache_key(rec_in, contract.cache_key_fields)
            cache.put(k, json.dumps(extract_produced(rec_out, contract, rec_in)))
    elif body:
        one = write_vcf(work / "header_harvest.vcf", header, body[:1])
        header_src = [ln for ln in run_vcf_tool(argv, one).splitlines() if is_header(ln)] or header

    rebuilt: list[str] = []
    holes = 0
    for ln, k in zip(body, keys):
        raw = cache.get(k)
        if raw is None:
            holes += 1
            rebuilt.append(ln)
            continue
        rebuilt.append(reassemble_record(ln, json.loads(raw), contract))

    text = "\n".join(header_src + rebuilt) + "\n"
    stats = {
        "n_records": len(body),
        "n_hits": len(hits),
        "n_misses": len(misses),
        "n_cache_holes": holes,
        "cache_size_after": len(cache),
        "cache_key_fields": list(contract.cache_key_fields),
    }
    return text, stats


def contract_path_for(cache_path: Path) -> Path:
    return cache_path.with_name(cache_path.name + ".contract.json")


def prepare_contract(
    argv: list[str],
    header: list[str],
    body: list[str],
    work: Path,
    cache_path: Path,
    *,
    probe_n: int = PROBE_N,
) -> RecordContract:
    path = contract_path_for(cache_path)
    try:
        return load_or_infer(argv, header, body, work / "probe", path, probe_n=probe_n)
    except InferError as exc:
        rec = refuse_result(exc, argv)
        rec.save(path)
        raise
