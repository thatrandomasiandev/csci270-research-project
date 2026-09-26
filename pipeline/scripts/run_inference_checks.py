#!/usr/bin/env python3
"""Generic VCF inference checks. MATCH only; no timing, no speedup."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.cache import RecordCache
from acts.infer_vcf import InferError, infer_contract, run_vcf_tool, write_vcf
from acts.vcf import bodies_equal, body_lines
from acts.vcf_memo import cached_annotate, contract_path_for, read_vcf_parts

OUT = ROOT / "results" / "inference_checks.json"
JAR = ROOT / "tools" / "snpEff" / "snpEff.jar"
DATA = ROOT / "tools" / "snpEff" / "data"
S96 = ROOT / "data" / "vep_chr22" / "HG00096.c1.vcf.gz"
S97 = ROOT / "data" / "vep_chr22" / "HG00097.c1.vcf.gz"
S99 = ROOT / "data" / "vep_chr22" / "HG00099.c1.vcf.gz"
WORKDIR = ROOT / "data" / "vep_chr22" / "inference_work"


def snpeff_argv() -> list[str]:
    return [
        "java",
        "-Xmx4g",
        "-jar",
        str(JAR),
        "-dataDir",
        str(DATA),
        "-noStats",
        "-noLog",
        "GRCh38.86",
        "{input}",
    ]


def contract_payload(c) -> dict:
    return {
        "decision": c.decision,
        "reason": c.reason,
        "cache_key_fields": c.cache_key_fields,
        "column_roles": c.column_roles,
        "info_roles": c.info_roles,
        "produced_info_order": c.produced_info_order,
        "sample_role": c.sample_role,
        "widen_history": c.widen_history,
        "late_key_probes": getattr(c, "late_key_probes", []),
        "probe_n": c.probe_n,
    }


def check_snpeff() -> dict:
    if not JAR.is_file() or not all(p.is_file() for p in (S96, S97, S99)):
        return {"skipped": True, "why": "SnpEff jar or chr22 VCFs missing"}
    argv = snpeff_argv()
    work = WORKDIR / "snpeff"
    work.mkdir(parents=True, exist_ok=True)
    inputs = {}
    for name, src in (("HG00096", S96), ("HG00097", S97), ("HG00099", S99)):
        header, body = read_vcf_parts(src)
        dest = write_vcf(work / f"{name}.vcf", header, body)
        inputs[name] = {"header": header, "body": body, "path": dest}

    header96, body96 = inputs["HG00096"]["header"], inputs["HG00096"]["body"]
    try:
        contract = infer_contract(argv, header96, body96, work / "probe")
    except InferError as exc:
        return {"tool": "SnpEff", "decision": exc.decision, "reason": exc.reason}

    cache_path = work / "cache.jsonl"
    cache = RecordCache(cache_path, argv=argv, kind="vcf")
    cpath = contract_path_for(cache_path)
    contract.save(cpath)
    populate = {}
    for name in ("HG00096", "HG00097"):
        rec = inputs[name]
        _text, stats = cached_annotate(
            rec["header"],
            rec["body"],
            cache,
            contract,
            argv,
            work / f"pop_{name}",
            contract_path=cpath,
        )
        populate[name] = stats
        print(
            f"populate {name}: n={stats['n_records']} hits={stats['n_hits']} "
            f"misses={stats['n_misses']}",
            flush=True,
        )

    rec99 = inputs["HG00099"]
    rebuilt, match_stats = cached_annotate(
        rec99["header"],
        rec99["body"],
        cache,
        contract,
        argv,
        work / "match_99",
        contract_path=cpath,
    )
    stock = run_vcf_tool(argv, rec99["path"])
    match = bodies_equal(rebuilt, stock) and match_stats["n_cache_holes"] == 0
    (work / "HG00099.reassembled.vcf").write_text(rebuilt)
    (work / "HG00099.stock.vcf").write_text(stock)
    print(
        f"MATCH HG00099: bodies_equal={match} n={match_stats['n_records']} "
        f"hits={match_stats['n_hits']} misses={match_stats['n_misses']}",
        flush=True,
    )
    return {
        "tool": "SnpEff 5.4c GRCh38.86",
        "flags": ["-noStats", "-noLog"],
        "path": "generic",
        "contract": contract_payload(contract),
        "populate": populate,
        "HG00099": match_stats,
        "n_reassembled": len(body_lines(rebuilt)),
        "n_stock": len(body_lines(stock)),
        "bodies_equal": match,
        "expected_hits": 41447,
        "expected_misses": 11191,
        "hits_match_handbuilt": match_stats["n_hits"] == 41447
        and match_stats["n_misses"] == 11191,
    }


def check_fill_tags() -> dict:
    if not shutil.which("bcftools"):
        return {"skipped": True, "why": "bcftools missing"}
    src = ROOT / "fixtures" / "vcf_memo" / "with_gt.vcf"
    argv = ["bcftools", "+fill-tags", "{input}", "-Ov", "--", "-t", "AF,AC"]
    header, body = read_vcf_parts(src)
    work = WORKDIR / "fill_tags"
    try:
        contract = infer_contract(argv, header, body, work / "probe")
    except InferError as exc:
        return {
            "tool": "bcftools +fill-tags",
            "decision": exc.decision,
            "reason": exc.reason,
        }
    cache = RecordCache(work / "cache.jsonl", argv=argv, kind="vcf")
    rebuilt, stats = cached_annotate(header, body, cache, contract, argv, work / "memo")
    stock = run_vcf_tool(argv, src)
    return {
        "tool": "bcftools +fill-tags AF,AC",
        "contract": contract_payload(contract),
        "bodies_equal": bodies_equal(rebuilt, stock) and stats["n_cache_holes"] == 0,
        "stats": stats,
        "same_site_hits_collapse": "SAMPLES" in contract.cache_key_fields,
        "note": "AF/AC depend on genotypes; key widened so same-site hits collapse",
    }


def check_fill_tags_real() -> dict:
    """HG00096 → HG00097 → HG00099 with genotype-widened key."""
    if not shutil.which("bcftools") or not all(p.is_file() for p in (S96, S97, S99)):
        return {"skipped": True, "why": "bcftools or chr22 VCFs missing"}
    argv = ["bcftools", "+fill-tags", "{input}", "-Ov", "--", "-t", "AF,AC"]
    work = WORKDIR / "fill_tags_real"
    work.mkdir(parents=True, exist_ok=True)
    inputs = {}
    for name, src in (("HG00096", S96), ("HG00097", S97), ("HG00099", S99)):
        header, body = read_vcf_parts(src)
        dest = write_vcf(work / f"{name}.vcf", header, body)
        inputs[name] = {"header": header, "body": body, "path": dest}
    try:
        contract = infer_contract(
            argv, inputs["HG00096"]["header"], inputs["HG00096"]["body"], work / "probe"
        )
    except InferError as exc:
        return {"tool": "bcftools +fill-tags real", "decision": exc.decision, "reason": exc.reason}
    cache_path = work / "cache.jsonl"
    cache = RecordCache(cache_path, argv=argv, kind="vcf")
    cpath = contract_path_for(cache_path)
    contract.save(cpath)
    populate = {}
    for name in ("HG00096", "HG00097"):
        rec = inputs[name]
        _text, stats = cached_annotate(
            rec["header"], rec["body"], cache, contract, argv, work / f"pop_{name}", contract_path=cpath
        )
        populate[name] = stats
        print(
            f"fill-tags populate {name}: n={stats['n_records']} hits={stats['n_hits']} "
            f"misses={stats['n_misses']}",
            flush=True,
        )
    rec99 = inputs["HG00099"]
    rebuilt, match_stats = cached_annotate(
        rec99["header"], rec99["body"], cache, contract, argv, work / "match_99", contract_path=cpath
    )
    stock = run_vcf_tool(argv, rec99["path"])
    match = bodies_equal(rebuilt, stock) and match_stats["n_cache_holes"] == 0
    print(
        f"fill-tags MATCH HG00099: bodies_equal={match} hits={match_stats['n_hits']} "
        f"misses={match_stats['n_misses']} key={contract.cache_key_fields}",
        flush=True,
    )
    return {
        "tool": "bcftools +fill-tags AF,AC on chr22 -c1",
        "contract": contract_payload(contract),
        "populate": populate,
        "HG00099": match_stats,
        "n_reassembled": len(body_lines(rebuilt)),
        "n_stock": len(body_lines(stock)),
        "bodies_equal": match,
        "same_site_hits_collapse": "SAMPLES" in contract.cache_key_fields,
    }


def check_annotate() -> dict:
    if not (shutil.which("bcftools") and shutil.which("bgzip") and shutil.which("tabix")):
        return {"skipped": True, "why": "bcftools/bgzip/tabix missing"}
    work = WORKDIR / "annotate"
    work.mkdir(parents=True, exist_ok=True)
    src = ROOT / "fixtures" / "vcf_memo" / "with_gt.vcf"
    table = work / "annot.tsv"
    table.write_text(
        "22\t16050075\tA\tG\tfrom_table\n"
        "22\t16050115\tG\tT\tfrom_table\n"
        "22\t16050200\tC\tA\tfrom_table\n"
    )
    gz = work / "annot.tsv.gz"
    with gz.open("wb") as fh:
        subprocess.run(["bgzip", "-c", str(table)], check=True, stdout=fh)
    subprocess.run(["tabix", "-s", "1", "-b", "2", "-e", "2", str(gz)], check=True)
    hdr = work / "annot.hdr"
    hdr.write_text('##INFO=<ID=NOTE,Number=1,Type=String,Description="table">\n')
    argv = [
        "bcftools",
        "annotate",
        "-a",
        str(gz),
        "-h",
        str(hdr),
        "-c",
        "CHROM,POS,REF,ALT,INFO/NOTE",
        "-Ov",
        "{input}",
    ]
    header, body = read_vcf_parts(src)
    try:
        contract = infer_contract(argv, header, body, work / "probe")
    except InferError as exc:
        return {"tool": "bcftools annotate", "decision": exc.decision, "reason": exc.reason}
    cache = RecordCache(work / "cache.jsonl", argv=argv, kind="vcf")
    rebuilt, stats = cached_annotate(header, body, cache, contract, argv, work / "memo")
    stock = run_vcf_tool(argv, src)
    return {
        "tool": "bcftools annotate INFO/NOTE",
        "contract": contract_payload(contract),
        "bodies_equal": bodies_equal(rebuilt, stock) and stats["n_cache_holes"] == 0,
        "stats": stats,
    }


def main() -> int:
    payload = {
        "protocol": "pipeline/docs/INFERENCE_PROTOCOL.md",
        "snpeff": check_snpeff(),
        "fill_tags": check_fill_tags(),
        "fill_tags_real": check_fill_tags_real(),
        "annotate": check_annotate(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    snp = payload["snpeff"]
    if not snp.get("skipped") and not snp.get("bodies_equal"):
        return 1
    if not payload["annotate"].get("skipped") and not payload["annotate"].get("bodies_equal"):
        return 1
    real = payload["fill_tags_real"]
    if not real.get("skipped") and not real.get("bodies_equal"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
