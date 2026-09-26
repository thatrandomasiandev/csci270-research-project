#!/usr/bin/env python3
"""Part B: populate cache on HG00096 then HG00097; MATCH + time HG00099.

Does not edit the pre-registered prediction in VEP_PROTOCOL.md or snpeff_timing_fit.json.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.snpeff_ann import added_by_key, apply_added, run_snpeff
from acts.vcf import bodies_equal, body_lines, is_header, read_maybe_gz, variant_key

S96 = ROOT / "data" / "vep_chr22" / "HG00096.c1.vcf.gz"
S97 = ROOT / "data" / "vep_chr22" / "HG00097.c1.vcf.gz"
S99 = ROOT / "data" / "vep_chr22" / "HG00099.c1.vcf.gz"
PRED = ROOT / "results" / "snpeff_timing_fit.json"
WORKDIR = ROOT / "data" / "vep_chr22" / "cached_work"
OUT = ROOT / "results" / "snpeff_cached_identity.json"
RUNS = 3
DIFF_EXAMPLES = 12


def vcf_parts(path: Path) -> tuple[list[str], list[str]]:
    text = read_maybe_gz(path)
    header = [ln for ln in text.splitlines() if is_header(ln)]
    return header, body_lines(text)


def write_vcf(path: Path, header: list[str], body: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(header + body) + "\n")
    return path


def cached_annotate(
    header: list[str],
    body: list[str],
    cache: dict[str, str],
    tmp: Path,
) -> tuple[str, dict]:
    """SnpEff on misses only; splice ANN/LOF/NMD onto the query line.

    ID, FORMAT, and genotype columns stay on the query record.
    """
    t0 = time.perf_counter()
    hits: list[str] = []
    misses: list[str] = []
    for ln in body:
        if variant_key(ln) in cache:
            hits.append(ln)
        else:
            misses.append(ln)

    snpeff_s = 0.0
    if misses:
        tmp.mkdir(parents=True, exist_ok=True)
        miss_vcf = tmp / "miss.vcf"
        write_vcf(miss_vcf, header, misses)
        out, _err, wall = run_snpeff(miss_vcf)
        snpeff_s = wall
        cache.update(added_by_key(out))

    rebuilt: list[str] = []
    holes: list[str] = []
    for ln in body:
        k = variant_key(ln)
        added = cache.get(k)
        if added is None:
            holes.append(k)
            rebuilt.append(ln)
        else:
            rebuilt.append(apply_added(ln, added))
    wall = time.perf_counter() - t0
    text = "\n".join(header + rebuilt) + "\n"
    stats = {
        "n_records": len(body),
        "n_hits": len(hits),
        "n_misses": len(misses),
        "n_cache_holes": len(holes),
        "cache_size_after": len(cache),
        "snpeff_miss_s": snpeff_s,
        "wall_s": wall,
    }
    return text, stats


def diff_examples(reassembled: str, stock: str, limit: int = DIFF_EXAMPLES) -> dict:
    ca = Counter(body_lines(reassembled))
    cb = Counter(body_lines(stock))
    only_r = ca - cb
    only_s = cb - ca
    examples = []
    by_key_r: dict[str, list[str]] = {}
    by_key_s: dict[str, list[str]] = {}
    for ln in only_r:
        by_key_r.setdefault(variant_key(ln), []).append(ln)
    for ln in only_s:
        by_key_s.setdefault(variant_key(ln), []).append(ln)
    keys = sorted(set(by_key_r) | set(by_key_s))
    for k in keys[:limit]:
        rln = by_key_r.get(k, [""])[0]
        sln = by_key_s.get(k, [""])[0]
        r_parts = rln.split("\t") if rln else []
        s_parts = sln.split("\t") if sln else []
        examples.append(
            {
                "variant_key": k,
                "id_reassembled": r_parts[2] if len(r_parts) > 2 else None,
                "id_stock": s_parts[2] if len(s_parts) > 2 else None,
                "info_reassembled": r_parts[7][:240] if len(r_parts) > 7 else None,
                "info_stock": s_parts[7][:240] if len(s_parts) > 7 else None,
                "fmt_gt_reassembled": r_parts[8:] if len(r_parts) > 8 else None,
                "fmt_gt_stock": s_parts[8:] if len(s_parts) > 8 else None,
            }
        )
    return {
        "n_lines_only_reassembled": sum(only_r.values()),
        "n_lines_only_stock": sum(only_s.values()),
        "n_keys_differing": len(keys),
        "examples": examples,
    }


def main() -> int:
    for p in (S96, S97, S99, PRED):
        if not p.is_file():
            print(f"INCOMPLETE: missing {p}", file=sys.stderr)
            return 2

    pred = json.loads(PRED.read_text())
    WORKDIR.mkdir(parents=True, exist_ok=True)

    inputs = {}
    for name, src in (("HG00096", S96), ("HG00097", S97), ("HG00099", S99)):
        header, body = vcf_parts(src)
        dest = write_vcf(WORKDIR / f"{name}.vcf", header, body)
        inputs[name] = {"header": header, "body": body, "path": dest}

    cache: dict[str, str] = {}
    populate = {}
    for name in ("HG00096", "HG00097"):
        rec = inputs[name]
        _text, stats = cached_annotate(
            rec["header"], rec["body"], cache, WORKDIR / f"pop_{name}"
        )
        populate[name] = stats
        print(
            f"populate {name}: n={stats['n_records']} hits={stats['n_hits']} "
            f"misses={stats['n_misses']} wall_s={stats['wall_s']:.4f}",
            flush=True,
        )

    cache_prev = dict(cache)
    rec99 = inputs["HG00099"]
    rebuilt, match_stats = cached_annotate(
        rec99["header"], rec99["body"], dict(cache_prev), WORKDIR / "match_99"
    )
    stock_text, _err, stock_match_s = run_snpeff(rec99["path"])
    match = bodies_equal(rebuilt, stock_text) and match_stats["n_cache_holes"] == 0
    diffs = None if match else diff_examples(rebuilt, stock_text)
    (WORKDIR / "HG00099.reassembled.vcf").write_text(rebuilt)
    (WORKDIR / "HG00099.stock.vcf").write_text(stock_text)

    payload: dict = {
        "tool": "SnpEff 5.4c GRCh38.86",
        "flags": ["-noStats", "-noLog"],
        "cache_value": "ANN/LOF/NMD keyed by CHROM POS REF ALT (full ALT)",
        "query_fields_kept": ["ID", "QUAL", "FILTER", "non-SnpEff INFO", "FORMAT", "GT"],
        "populate": populate,
        "cache_size_after_96_97": len(cache_prev),
        "HG00099": match_stats,
        "stock_match_run_s": stock_match_s,
        "n_reassembled": len(body_lines(rebuilt)),
        "n_stock": len(body_lines(stock_text)),
        "bodies_equal": match,
        "diffs": diffs,
        "prediction_locked": {
            "source": str(PRED),
            "speedup": pred["prediction"]["speedup"],
            "t_stock_s": pred["prediction"]["t_stock_s"],
            "t_cached_s": pred["prediction"]["t_cached_s"],
            "a_s": pred["fit"]["a_s"],
            "b_s_per_record": pred["fit"]["b_s_per_record"],
            "miss_n": pred["miss_n"],
            "w_s": pred["wrapper_cat"]["mean_s"],
        },
        "timing": None,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"MATCH HG00099: bodies_equal={match} n={match_stats['n_records']} "
        f"hits={match_stats['n_hits']} misses={match_stats['n_misses']}",
        flush=True,
    )
    if not match:
        print("MATCH failed; not timing.", flush=True)
        print(json.dumps(payload, indent=2))
        return 1

    cached_times = []
    stock_times = []
    for i in range(RUNS):
        _text, st = cached_annotate(
            rec99["header"],
            rec99["body"],
            dict(cache_prev),
            WORKDIR / f"time_cached_{i}",
        )
        cached_times.append(st["wall_s"])
        print(f"cached run={i+1} wall_s={st['wall_s']:.4f}", flush=True)
    for i in range(RUNS):
        _out, _err, wall = run_snpeff(rec99["path"])
        stock_times.append(wall)
        print(f"stock run={i+1} wall_s={wall:.4f}", flush=True)

    mean_c = statistics.fmean(cached_times)
    mean_s = statistics.fmean(stock_times)
    measured = mean_s / mean_c if mean_c else None
    payload["timing"] = {
        "runs": RUNS,
        "cached_s": cached_times,
        "cached_mean_s": mean_c,
        "cached_stdev_s": statistics.stdev(cached_times),
        "stock_s": stock_times,
        "stock_mean_s": mean_s,
        "stock_stdev_s": statistics.stdev(stock_times),
        "measured_speedup": measured,
        "predicted_speedup": pred["prediction"]["speedup"],
        "measured_minus_predicted": (measured - pred["prediction"]["speedup"])
        if measured is not None
        else None,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
