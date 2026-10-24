#!/usr/bin/env python3
"""PROJECTED RefSeq-bacteria × Pfam re-annotation cost (stock vs TARE).

Reads:
  - NCBI assembly_summary.txt (path via --assembly-summary; not in the repo)
  - pipeline/results/exact_replay/headline_carc.json + headline_measured/*.json
  - pipeline/results/diverse_genomes/carc/measured_*.json (W8)
  - pipeline/results/release_chain/pairs.json

Writes pipeline/results/scale/projection.json.

Every number is MEASURED (committed file / downloaded summary) or PROJECTED
(formula + named assumptions). No CARC submit. No silent imputation of
protein_coding_gene_count.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PIPELINE = REPO / "pipeline"
HEADLINE_JSON = PIPELINE / "results" / "exact_replay" / "headline_carc.json"
HEADLINE_DIR = PIPELINE / "results" / "exact_replay" / "headline_measured"
W8_DIR = PIPELINE / "results" / "diverse_genomes" / "carc"
PAIRS_JSON = PIPELINE / "results" / "release_chain" / "pairs.json"
OUT_JSON = PIPELINE / "results" / "scale" / "projection.json"

SECONDS_PER_YEAR = 365.25 * 24 * 3600.0
# Paper Figure 1 / intro: eight Pfam releases in 25 months (May 2024–June 2026).
PFAM_RELEASES = 8
PFAM_MONTHS = 25
# Rebuild-like release: measured 37.4→38.0 f_delta ≈ 0.931; under TARE ≈ one full rerun.
REBUILD_F_DELTA_MIN = 0.9
VALIDATION_WIDEN_THRESHOLD = 0.25
DEFAULT_ASSEMBLY_SHA256 = (
    "7034587bd874e2ef5ba670c6efd4a5f422dfd487fe4e6db1afb3f92288d4c626"
)
DEFAULT_ASSEMBLY_URL = (
    "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/assembly_summary.txt"
)
REP_CATEGORIES = frozenset({"reference genome", "representative genome"})


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def find_n_records(obj):
    if isinstance(obj, dict):
        if "n_records" in obj and isinstance(obj["n_records"], int):
            return obj["n_records"]
        for v in obj.values():
            found = find_n_records(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_n_records(v)
            if found is not None:
                return found
    return None


def parse_cpu(argv) -> int:
    if isinstance(argv, list):
        text = " ".join(str(x) for x in argv)
    else:
        text = str(argv or "")
    m = re.search(r"--cpu\s+(\d+)", text)
    if not m:
        raise ValueError(f"no --cpu in argv: {argv!r}")
    return int(m.group(1))


def median(xs: list[float]) -> float:
    return float(statistics.median(xs))


def parse_protein_count(raw: str):
    s = (raw or "").strip()
    if s == "" or s.lower() == "na":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def parse_assembly_summary(path: Path) -> dict:
    header = None
    n_assemblies = 0
    n_missing = 0
    n_with = 0
    sum_all = 0
    n_ref = 0
    n_repr = 0
    n_rep_cat = 0
    n_rep_missing = 0
    n_rep_with = 0
    sum_rep = 0
    version_status = {}
    refseq_category = {}

    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("#assembly_accession"):
                header = line.lstrip("#").rstrip("\n").split("\t")
                continue
            if line.startswith("#") or not line.strip():
                continue
            if header is None:
                raise RuntimeError("assembly_summary header not found")
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(header):
                parts = parts + [""] * (len(header) - len(parts))
            row = dict(zip(header, parts))
            n_assemblies += 1
            vs = row.get("version_status", "")
            version_status[vs] = version_status.get(vs, 0) + 1
            cat = row.get("refseq_category", "")
            refseq_category[cat] = refseq_category.get(cat, 0) + 1
            if cat == "reference genome":
                n_ref += 1
            elif cat == "representative genome":
                n_repr += 1
            pc = parse_protein_count(row.get("protein_coding_gene_count", ""))
            if pc is None:
                n_missing += 1
            else:
                n_with += 1
                sum_all += pc
            if cat in REP_CATEGORIES:
                n_rep_cat += 1
                if pc is None:
                    n_rep_missing += 1
                else:
                    n_rep_with += 1
                    sum_rep += pc

    return {
        "n_assemblies": n_assemblies,
        "version_status_counts": version_status,
        "refseq_category_counts": refseq_category,
        "n_reference_genome": n_ref,
        "n_representative_genome": n_repr,
        "n_reference_or_representative": n_rep_cat,
        "all_bacteria": {
            "n_with_protein_coding_gene_count": n_with,
            "n_missing_or_blank_protein_coding_gene_count": n_missing,
            "sum_protein_coding_gene_count": sum_all,
            "excluded_from_sum": n_missing,
            "imputation": "none; blank/na excluded",
        },
        "representatives_only": {
            "definition": "refseq_category in {reference genome, representative genome}",
            "n_with_protein_coding_gene_count": n_rep_with,
            "n_missing_or_blank_protein_coding_gene_count": n_rep_missing,
            "sum_protein_coding_gene_count": sum_rep,
            "excluded_from_sum": n_rep_missing,
            "imputation": "none; blank/na excluded",
        },
    }


def headline_genomes(hc: dict) -> list[dict]:
    rows = []
    for g in hc["genomes"]:
        if g.get("outcome") != "EXACT" or not g.get("completed"):
            continue
        rel = g["path"]
        path = PIPELINE / rel if not str(rel).startswith("pipeline/") else REPO / rel
        # paths in JSON are results/... under pipeline/
        if not path.exists():
            path = PIPELINE / rel
        d = load_json(path)
        n = find_n_records(d)
        if n is None:
            raise RuntimeError(f"n_records missing in {path}")
        cpus = parse_cpu(d.get("argv_stock"))
        stock = float(g["stock_median_s"])
        node = None
        repeats = d.get("repeats") or []
        if repeats:
            node = (repeats[0].get("before") or {}).get("node")
        rows.append(
            {
                "source": "headline",
                "proteome": g["proteome"],
                "stock_wall_s": stock,
                "cpus": cpus,
                "n_proteins": n,
                "n_proteins_source": "fill.n_records",
                "core_seconds_per_protein": stock * cpus / n,
                "cpu_model": d.get("cpu_model"),
                "node": node,
                "path": str(path.relative_to(REPO)),
            }
        )
    return rows


def w8_genomes() -> list[dict]:
    rows = []
    for path in sorted(W8_DIR.glob("measured_*.json")):
        d = load_json(path)
        g = d.get("genome") or {}
        stock_obj = g.get("stock") or {}
        stock = stock_obj.get("wall_s")
        if stock is None:
            continue
        stock = float(stock)
        headers = g.get("headers") or {}
        n_fa = headers.get("fasta_records")
        n_ncbi = g.get("ncbi_protein_coding_gene_count")
        if n_fa is not None:
            n = int(n_fa)
            n_src = "headers.fasta_records"
        elif n_ncbi is not None:
            n = int(n_ncbi)
            n_src = "ncbi_protein_coding_gene_count"
        else:
            continue
        cpus = parse_cpu(d.get("argv_stock") or stock_obj.get("argv"))
        m = re.search(r"(GC[AF]_[0-9]+\.[0-9]+)", path.name)
        acc = m.group(1) if m else path.stem
        rows.append(
            {
                "source": "w8_diverse",
                "proteome": acc,
                "stock_wall_s": stock,
                "cpus": cpus,
                "n_proteins": n,
                "n_proteins_source": n_src,
                "ncbi_protein_coding_gene_count": n_ncbi,
                "fasta_records": n_fa,
                "core_seconds_per_protein": stock * cpus / n,
                "host": d.get("host"),
                "outcome": d.get("outcome"),
                "path": str(path.relative_to(REPO)),
            }
        )
    return rows


def core_years(n_proteins: float, core_s_per_protein: float) -> float:
    return (n_proteins * core_s_per_protein) / SECONDS_PER_YEAR


def build_projection(
    assembly_path: Path,
    expected_sha256: str | None,
    download_meta: dict | None,
) -> dict:
    digest = sha256_file(assembly_path)
    if expected_sha256 and digest != expected_sha256:
        raise SystemExit(
            f"assembly_summary sha256 mismatch: got {digest}, expected {expected_sha256}"
        )

    assembly = parse_assembly_summary(assembly_path)
    hc = load_json(HEADLINE_JSON)
    pairs_doc = load_json(PAIRS_JSON)
    headline = headline_genomes(hc)
    w8 = w8_genomes()
    if len(headline) < 1:
        raise SystemExit("no EXACT headline genomes")

    csp_headline = [r["core_seconds_per_protein"] for r in headline]
    rate = median(csp_headline)

    # Validate predicted stock wall vs measured for every genome.
    validation_rows = []
    for r in headline + w8:
        pred_wall = r["n_proteins"] * rate / r["cpus"]
        meas = r["stock_wall_s"]
        abs_rel = abs(pred_wall - meas) / meas
        validation_rows.append(
            {
                "source": r["source"],
                "proteome": r["proteome"],
                "n_proteins": r["n_proteins"],
                "cpus": r["cpus"],
                "measured_stock_wall_s": meas,
                "predicted_stock_wall_s": pred_wall,
                "abs_rel_error": abs_rel,
                "measured_core_s_per_protein": r["core_seconds_per_protein"],
            }
        )
    abs_errs = [v["abs_rel_error"] for v in validation_rows]
    median_abs_err = median(abs_errs)
    widen = median_abs_err > VALIDATION_WIDEN_THRESHOLD

    # Observed bacterial csp band (exclude nothing; Drosophila stays as measured).
    all_csp = [r["core_seconds_per_protein"] for r in headline + w8]
    csp_sorted = sorted(all_csp)
    p10 = csp_sorted[max(0, int(math.floor(0.10 * (len(csp_sorted) - 1))))]
    p90 = csp_sorted[min(len(csp_sorted) - 1, int(math.ceil(0.90 * (len(csp_sorted) - 1))))]

    S = float(hc["headline_median"])
    S_lo = float(hc["bootstrap_ci95"]["low"])
    S_hi = float(hc["bootstrap_ci95"]["high"])
    first_run = float(hc["first_run_overhead_median"])
    break_even = float(hc["break_even_n_median"])

    pairs = pairs_doc["pairs"]
    f_deltas = [float(p["f_delta"]) for p in pairs]
    rebuild_pairs = [
        {
            "old_release": p["old_release"],
            "new_release": p["new_release"],
            "f_delta": float(p["f_delta"]),
        }
        for p in pairs
        if float(p["f_delta"]) >= REBUILD_F_DELTA_MIN
    ]
    n_pairs = len(pairs)
    n_rebuild = len(rebuild_pairs)
    rebuild_frac = n_rebuild / n_pairs if n_pairs else float("nan")
    releases_per_year = PFAM_RELEASES / (PFAM_MONTHS / 12.0)

    def stock_bundle(n_prot: int, label: str) -> dict:
        point = core_years(n_prot, rate)
        # Validation widen: multiply point by (1 ± median abs rel error).
        lo_val = point * (1.0 - median_abs_err)
        hi_val = point * (1.0 + median_abs_err)
        # Sensitivity from observed csp p10/p90 across measured genomes.
        lo_csp = core_years(n_prot, p10)
        hi_csp = core_years(n_prot, p90)
        # Stated widened stock range when validation fails the 25% gate.
        if widen:
            stock_lo = min(lo_val, lo_csp, point)
            stock_hi = max(hi_val, hi_csp, point)
        else:
            stock_lo = min(lo_csp, point)
            stock_hi = max(hi_csp, point)

        # TARE update at headline f (38.1→38.2 timed regime): stock / S.
        tare_update = point / S
        tare_update_lo = stock_lo / S_hi  # higher speedup → lower TARE cost
        tare_update_hi = stock_hi / S_lo
        # Rebuild fallback ≈ one full stock rerun under TARE.
        tare_rebuild = point
        tare_rebuild_lo = stock_lo
        tare_rebuild_hi = stock_hi

        # Per-year under historical pair mix.
        annual_stock = releases_per_year * point
        per_release_tare_mix = (1.0 - rebuild_frac) * (point / S) + rebuild_frac * point
        annual_tare_mix = releases_per_year * per_release_tare_mix
        # Range: CI on S and rebuild vs all-typical vs all-rebuild, plus widened stock.
        annual_tare_lo = releases_per_year * (
            (1.0 - rebuild_frac) * (stock_lo / S_hi) + rebuild_frac * stock_lo
        )
        annual_tare_hi = releases_per_year * (
            (1.0 - rebuild_frac) * (stock_hi / S_lo) + rebuild_frac * stock_hi
        )
        annual_tare_all_typical = releases_per_year * (point / S)
        annual_tare_all_rebuild = releases_per_year * point

        return {
            "scope": label,
            "n_proteins": n_prot,
            "stock_core_years_per_release": {
                "point": point,
                "widened_lo": stock_lo,
                "widened_hi": stock_hi,
                "validation_band_lo": lo_val,
                "validation_band_hi": hi_val,
                "csp_p10_lo": lo_csp,
                "csp_p90_hi": hi_csp,
            },
            "tare_core_years_per_typical_update": {
                "point": tare_update,
                "widened_lo": tare_update_lo,
                "widened_hi": tare_update_hi,
                "speedup_point": S,
                "speedup_ci95": [S_lo, S_hi],
            },
            "tare_core_years_per_rebuild_release": {
                "point": tare_rebuild,
                "widened_lo": tare_rebuild_lo,
                "widened_hi": tare_rebuild_hi,
                "assumption": (
                    "f_delta≈0.93 like 37.4→38.0 ≈ one full rerun under TARE "
                    "(paper: measured speedup ≈1.00× at that churn)"
                ),
            },
            "per_year": {
                "pfam_releases_per_year": releases_per_year,
                "stock_core_years": annual_stock,
                "tare_core_years_historical_mix": {
                    "point": annual_tare_mix,
                    "widened_lo": annual_tare_lo,
                    "widened_hi": annual_tare_hi,
                    "rebuild_fraction_among_measured_pairs": rebuild_frac,
                },
                "tare_core_years_if_all_typical_updates": annual_tare_all_typical,
                "tare_core_years_if_all_rebuilds": annual_tare_all_rebuild,
            },
        }

    n_all = assembly["all_bacteria"]["sum_protein_coding_gene_count"]
    n_rep = assembly["representatives_only"]["sum_protein_coding_gene_count"]

    payload = {
        "system": "TARE",
        "claim_class": "PROJECTED",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {
            "assembly_summary": {
                "url": (download_meta or {}).get("url", DEFAULT_ASSEMBLY_URL),
                "path": str(assembly_path),
                "sha256": digest,
                "bytes": assembly_path.stat().st_size,
                "download_start_utc": (download_meta or {}).get("download_start_utc"),
                "download_end_utc": (download_meta or {}).get("download_end_utc"),
                "expected_sha256": expected_sha256 or digest,
            },
            "headline_carc": {
                "path": str(HEADLINE_JSON.relative_to(REPO)),
                "sha256": sha256_file(HEADLINE_JSON),
            },
            "pairs": {
                "path": str(PAIRS_JSON.relative_to(REPO)),
                "sha256": sha256_file(PAIRS_JSON),
            },
            "w8_dir": str(W8_DIR.relative_to(REPO)),
        },
        "assembly_counts": assembly,
        "cost_model": {
            "definition": (
                "core_seconds_per_protein = stock_median_wall_s * n_cpus / n_proteins; "
                "rate = median over headline EXACT genomes on the headline server"
            ),
            "headline_server": {
                "cpu_model": headline[0].get("cpu_model"),
                "cpus_per_run": headline[0]["cpus"],
                "nodes_seen": sorted({r.get("node") for r in headline if r.get("node")}),
                "n_exact_genomes": len(headline),
                "core_seconds_per_protein_per_genome": [
                    {
                        "proteome": r["proteome"],
                        "value": r["core_seconds_per_protein"],
                        "stock_wall_s": r["stock_wall_s"],
                        "n_proteins": r["n_proteins"],
                        "cpus": r["cpus"],
                    }
                    for r in headline
                ],
                "core_seconds_per_protein_median": rate,
                "core_seconds_per_protein_min": min(csp_headline),
                "core_seconds_per_protein_max": max(csp_headline),
            },
            "headline_speedup": {
                "median": S,
                "bootstrap_ci95": {"low": S_lo, "high": S_hi},
                "source": "pipeline/results/exact_replay/headline_carc.json headline_median / bootstrap_ci95",
            },
            "first_run_overhead_median": first_run,
            "break_even_n_median": break_even,
            "first_run_note": (
                "1.32× first-run overhead and 0.26-update break-even apply when filling "
                "the cache; the per-release projection below assumes a warm cache and "
                "charges only the update (or rebuild) cost."
            ),
            "pfam_cadence": {
                "releases": PFAM_RELEASES,
                "months": PFAM_MONTHS,
                "releases_per_year": releases_per_year,
                "source": "paper Figure 1 / intro (eight releases in 25 months)",
            },
            "rebuild": {
                "threshold_f_delta": REBUILD_F_DELTA_MIN,
                "measured_pairs": [
                    {
                        "old_release": p["old_release"],
                        "new_release": p["new_release"],
                        "f_delta": float(p["f_delta"]),
                    }
                    for p in pairs
                ],
                "rebuild_pairs": rebuild_pairs,
                "rebuild_fraction_among_measured_pairs": rebuild_frac,
                "fallback": "≈ one full stock rerun under TARE",
            },
        },
        "validation": {
            "n_genomes": len(validation_rows),
            "n_headline": len(headline),
            "n_w8": len(w8),
            "rate_core_seconds_per_protein": rate,
            "median_abs_rel_error_stock_wall": median_abs_err,
            "mean_abs_rel_error_stock_wall": float(statistics.mean(abs_errs)),
            "widen_threshold": VALIDATION_WIDEN_THRESHOLD,
            "widen_stated_range": widen,
            "widen_reason": (
                f"median abs relative error {median_abs_err:.4f} > {VALIDATION_WIDEN_THRESHOLD}"
                if widen
                else "median abs relative error within 25%"
            ),
            "observed_core_seconds_per_protein": {
                "min": min(all_csp),
                "p10": p10,
                "median": median(all_csp),
                "p90": p90,
                "max": max(all_csp),
            },
            "per_genome": validation_rows,
        },
        "projection": {
            "all_refseq_bacteria": stock_bundle(n_all, "all_refseq_bacteria"),
            "representatives_only": stock_bundle(n_rep, "representatives_only"),
        },
        "assumptions": [
            "Protein work scales as sum of NCBI protein_coding_gene_count over assemblies with a non-blank count; blank/na rows are excluded, never imputed.",
            "Per-protein cost is the median headline-server core-seconds/protein (stock wall × --cpu / n_records) against current Pfam (38.2 in the timed headline).",
            "A typical Pfam update matches the timed 38.1→38.2 regime (headline median speedup); a rebuild-like release (f_delta≥0.9, as in 37.4→38.0) costs ≈ one full stock rerun under TARE.",
            "Annual cadence uses eight Pfam releases in 25 months; historical rebuild fraction is n_rebuild/n_pairs from release_chain/pairs.json.",
            "Projection assumes a warm TARE cache (first-run 1.32× paid once, break-even 0.26 updates); per-release figures are update costs only.",
            "Core-year uses 365.25 SI days. Hardware is the headline AMD EPYC 7542 regime; W8 used 8 CPUs on other nodes and drives the validation widen.",
        ],
        "what_would_make_the_number_wrong": [
            "NCBI protein_coding_gene_count systematically differs from hmmscan FASTA record counts at scale.",
            "hmmscan core-seconds/protein on production queues differs from the headline EPYC 7542/--cpu 4 median (validation already shows ~26% median wall error across W8).",
            "Future Pfam releases are mostly rebuilds (or mostly tiny), so the historical 1/7 rebuild mix is a bad prior.",
            "Caches are cold every release, or verify/refuse rates force full reruns far above the timed 13.4% pair.",
            "Counting every assembly (including near-duplicates) overstates unique protein work relative to a deduplicated proteome catalog.",
        ],
        "headline_sentence": {
            "all_refseq_bacteria": (
                f"PROJECTED: re-annotating every RefSeq bacterial genome "
                f"({n_all:,} proteins over {assembly['all_bacteria']['n_with_protein_coding_gene_count']:,} "
                f"assemblies with counts; {assembly['all_bacteria']['n_missing_or_blank_protein_coding_gene_count']} excluded) "
                f"against each new Pfam release costs "
                f"{core_years(n_all, rate):.0f} core-years with a full stock hmmscan; "
                f"with TARE it costs {core_years(n_all, rate)/S:.0f} core-years on a typical update "
                f"(headline median {S:.2f}×) and ≈{core_years(n_all, rate):.0f} core-years on a rebuild-like release."
            ),
            "representatives_only": (
                f"PROJECTED (reference/representative only, {n_rep:,} proteins): "
                f"{core_years(n_rep, rate):.1f} core-years stock / "
                f"{core_years(n_rep, rate)/S:.1f} TARE typical update per release."
            ),
        },
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--assembly-summary",
        type=Path,
        default=Path.home() / "tmp" / "tare_scale" / "assembly_summary.txt",
        help="Path to NCBI bacteria assembly_summary.txt (outside the repo)",
    )
    ap.add_argument(
        "--expected-sha256",
        default=DEFAULT_ASSEMBLY_SHA256,
        help="Require this sha256 of the assembly file (empty to skip)",
    )
    ap.add_argument("--download-start-utc", default="2026-10-24T07:39:25Z")
    ap.add_argument("--download-end-utc", default="2026-10-24T07:40:51Z")
    ap.add_argument("--url", default=DEFAULT_ASSEMBLY_URL)
    ap.add_argument(
        "--out",
        type=Path,
        default=OUT_JSON,
        help="Output JSON path",
    )
    args = ap.parse_args(argv)

    if not args.assembly_summary.is_file():
        print(f"missing assembly summary: {args.assembly_summary}", file=sys.stderr)
        return 2

    meta = {
        "url": args.url,
        "download_start_utc": args.download_start_utc,
        "download_end_utc": args.download_end_utc,
    }
    expected = args.expected_sha256.strip() or None
    payload = build_projection(args.assembly_summary, expected, meta)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    print(f"wrote {args.out}")
    print(payload["headline_sentence"]["all_refseq_bacteria"])
    print(
        "validation median abs rel error:",
        payload["validation"]["median_abs_rel_error_stock_wall"],
        "widen:",
        payload["validation"]["widen_stated_range"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
