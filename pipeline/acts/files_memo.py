"""Generic files→directory memo: cache per-input output files, reassemble stems."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from acts.cache import RecordCache
from acts.infer_files import (
    PROBE_N,
    FileRec,
    FilesContract,
    InferError,
    default_output_dir,
    load_or_infer_files,
    materialize,
    probe_late_suffixes,
    rec_key,
    record_payload,
    refuse_files,
    run_files_tool,
    unclassified_suffixes,
    write_payload,
)


def cached_files(
    recs: list[FileRec],
    cache: RecordCache,
    contract: FilesContract,
    argv: list[str],
    work: Path,
    dest: Path,
    contract_path: Path | None = None,
) -> tuple[Path, dict]:
    keys = [rec_key(rec, contract.cache_key_fields) for rec in recs]
    hits: list[FileRec] = []
    misses: list[FileRec] = []
    for rec, k in zip(recs, keys):
        if cache.get(k) is not None:
            hits.append(rec)
        else:
            misses.append(rec)

    if misses:
        work.mkdir(parents=True, exist_ok=True)
        miss_dir = work / "miss"
        miss_recs = materialize(misses, miss_dir)
        run_files_tool(argv, miss_dir)
        miss_out = default_output_dir(miss_dir)
        unseen = unclassified_suffixes(miss_out, miss_recs, contract)
        if unseen:
            probe_late_suffixes(argv, miss_recs, contract, work / "late", unseen)
            if contract_path is not None:
                contract.save(contract_path)
        for rec in miss_recs:
            cache.put(
                rec_key(rec, contract.cache_key_fields),
                json.dumps(record_payload(rec, miss_out, contract)),
            )

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    holes = 0
    for rec, k in zip(recs, keys):
        raw = cache.get(k)
        if raw is None:
            holes += 1
            continue
        write_payload(dest, rec, json.loads(raw), contract)

    stats = {
        "n_records": len(recs),
        "n_hits": len(hits),
        "n_misses": len(misses),
        "n_cache_holes": holes,
        "cache_size_after": len(cache),
        "hit_recs": hits,
    }
    return dest, stats


def contract_path_for(cache_path: Path) -> Path:
    return cache_path.with_name(cache_path.name + ".contract.json")


def prepare_files_contract(
    argv: list[str],
    recs: list[FileRec],
    work: Path,
    cache_path: Path,
    *,
    probe_n: int = PROBE_N,
    probe_seed: int = 20260927,
    subset_mode: str = "batched",
) -> FilesContract:
    path = contract_path_for(cache_path)
    try:
        return load_or_infer_files(
            argv,
            recs,
            work / "probe",
            path,
            probe_n=probe_n,
            probe_seed=probe_seed,
            subset_mode=subset_mode,
        )
    except InferError as exc:
        rec = refuse_files(exc, argv)
        rec.subset_mode = subset_mode
        rec.save(path)
        raise
