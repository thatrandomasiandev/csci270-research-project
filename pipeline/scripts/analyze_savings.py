#!/usr/bin/env python3
"""Analyze HMMER accumulated-savings job dumps (docs/SAVINGS_PROTOCOL.md).

Reads per-genome JSON written by scripts/run_hmmer_savings.py. Does not
run HMMER, does not submit jobs, and does not invent numbers when dumps
are missing.

Locked formulas (do not silently replace):

    stock̂_i = a + b · N_i          # unsampled genomes
    P       = Σ_j (a + b · n_j)    # singleton_8 / 12 calls, probe_n = 8
    cum_cached_with_P = P + Σ_i cached_i

hmmsearch is the pre-registered primary. hmmscan is post-hoc everywhere.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(os.environ.get("ACTS_PIPELINE_ROOT", Path(__file__).resolve().parents[1]))

PROTOCOL = "pipeline/docs/SAVINGS_PROTOCOL.md"
ERROR_FLAG = 0.10
KILL_FRAC = 0.50
KILL_COLLECTION = "A"
KILL_MODE = "hmmscan"
PRIMARY = "hmmsearch"
POST_HOC = "hmmscan"
EXPECTED_N = {"A": 30, "B": 40}
STOCK_POS = {"A": {1, 2, 5, 10, 20, 30}, "B": {1, 2, 5, 10, 20, 40}}
EXPECTED_MATCH = {"hmmscan": "order", "hmmsearch": "multiset"}
PROBE_N = 8
PROBE_ACCOUNT = "singleton_8"
PROBE_N_CALLS = 12
# Queued jobs: singleton subset-invariance at probe_n=8 (12 FASTA→table calls).
PROBE_SIZES = (8, 8, 8, 8, 1, 1, 1, 1, 1, 1, 1, 1)
JOB_NAME = {"A", "B"}
JOB_MODE = {PRIMARY, POST_HOC}
DEFAULT_JOB_NAMES = (
    "A_hmmsearch.json",
    "A_hmmscan.json",
    "B_hmmsearch.json",
    "B_hmmscan.json",
)

STOCK = "#4A5568"
SEARCH = "#C05621"
SCAN = "#2B6CB0"
CLAIM = "#2F855A"
MUTED = "#718096"
PRED = "#6B46C1"
FAIL = "#C53030"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 140,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    }
)


def hours(seconds: float | None) -> float | None:
    if seconds is None:
        return None
    return seconds / 3600.0


def probe_cost_s(a: float, b: float, sizes: tuple[int, ...] = PROBE_SIZES) -> float:
    """Locked P = Σ (a + b · n_j)."""
    return sum(a + b * n for n in sizes)


def mode_label(mode: str) -> str:
    if mode == PRIMARY:
        return "hmmsearch (PRIMARY)"
    if mode == POST_HOC:
        return "hmmscan (post-hoc)"
    return mode


def collection_title(cid: str) -> str:
    return {
        "A": "A · diverse E. coli (30)",
        "B": "B · O157:H7 (40)",
    }.get(cid, cid)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def is_job_payload(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    if raw.get("collection") not in JOB_NAME:
        return False
    if raw.get("mode") not in JOB_MODE:
        return False
    return isinstance(raw.get("genomes"), list)


def job_stem_ok(path: Path) -> bool:
    name = path.name
    if name in {"savings_summary.json", "STOP.json"}:
        return False
    if name.startswith("savings_A") or name.startswith("savings_B"):
        return False
    return name in DEFAULT_JOB_NAMES or (
        len(name) > 5
        and name[0] in JOB_NAME
        and name.endswith(".json")
        and any(name[2:].startswith(m) for m in JOB_MODE)
    )


def discover_jobs(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        path = raw.expanduser().resolve()
        candidates: list[Path] = []
        if path.is_dir():
            candidates.extend(path / name for name in DEFAULT_JOB_NAMES)
            candidates.extend(sorted(path.glob("*.json")))
        elif path.is_file():
            candidates.append(path)
        for cand in candidates:
            if not cand.is_file() or cand in seen:
                continue
            if not job_stem_ok(cand) and path.is_dir():
                continue
            try:
                payload = load_json(cand)
            except (OSError, json.JSONDecodeError):
                continue
            if not is_job_payload(payload):
                continue
            seen.add(cand)
            found.append(cand)
    return found


def fit_from_job(payload: dict[str, Any], predicted: dict[str, Any] | None) -> dict[str, float]:
    fit = payload.get("fit") or {}
    mode = payload["mode"]
    a = fit.get("a")
    b = fit.get("b")
    w = fit.get("w")
    if a is None or b is None:
        if predicted is None:
            raise KeyError(f"no a,b for {mode} and no predicted-speedup file")
        block = predicted["modes"][mode]
        a = block["a"]
        b = block["b"]
        w = block.get("w")
    return {
        "a": float(a),
        "b": float(b),
        "w": float(w) if w is not None else 0.0,
        "N_screen": float(fit.get("N_screen") or (predicted or {}).get("N") or 0.0),
    }


def lookup_per_k(predicted: dict[str, Any] | None, collection: str, mode: str, k: int) -> dict[str, Any] | None:
    if predicted is None or k < 1:
        return None
    try:
        rows = predicted["collections"][collection]["modes"][mode]["per_k"]
    except (KeyError, TypeError):
        return None
    for row in rows:
        if row.get("k") == k:
            return row
    return None


def lookup_cum(predicted: dict[str, Any] | None, collection: str, mode: str, genome: int) -> dict[str, Any] | None:
    if predicted is None:
        return None
    try:
        rows = predicted["collections"][collection]["modes"][mode]["cumulative"]
    except (KeyError, TypeError):
        return None
    for row in rows:
        if row.get("genome") == genome:
            return row
    return None


def lookup_probe_block(
    predicted_p: dict[str, Any] | None, mode: str, account: str = PROBE_ACCOUNT
) -> dict[str, Any] | None:
    if predicted_p is None:
        return None
    try:
        return predicted_p["P"][mode][account]
    except (KeyError, TypeError):
        return None


def lookup_cum_with_p(
    predicted_p: dict[str, Any] | None,
    collection: str,
    mode: str,
    genome: int,
    account: str = PROBE_ACCOUNT,
) -> dict[str, Any] | None:
    if predicted_p is None:
        return None
    try:
        rows = predicted_p["collections"][collection]["modes"][mode][account]["cumulative"]
    except (KeyError, TypeError):
        return None
    for row in rows:
        if row.get("genome") == genome:
            return row
    return None


def mean(xs: list[float]) -> float | None:
    if not xs:
        return None
    return sum(xs) / len(xs)


def stock_cpu_ratio(rows: list[dict[str, Any]]) -> float | None:
    ratios: list[float] = []
    for row in rows:
        wall = row.get("stock_wall_s")
        cpu = row.get("stock_cpu_s")
        if wall and cpu is not None and wall > 0:
            ratios.append(float(cpu) / float(wall))
    return mean(ratios)


def stop_code(payload: dict[str, Any]) -> str | None:
    decision = payload.get("decision")
    if isinstance(decision, str) and decision.startswith("STOP_"):
        return decision
    stopped = payload.get("stopped")
    if isinstance(stopped, dict):
        inner = stopped.get("decision")
        if isinstance(inner, str) and inner.startswith("STOP_"):
            return inner
        where = str(stopped.get("where") or "")
        if where in {"stock MATCH", "cached MATCH"}:
            return "STOP_MATCH"
        if where == "audit":
            return "STOP_AUDIT"
        if where == "contract":
            return "STOP_CONTRACT"
        if stopped.get("stopped"):
            return f"STOP_{where.replace(' ', '_').upper() or 'UNKNOWN'}"
    return None


def analyze_job(
    payload: dict[str, Any],
    *,
    predicted: dict[str, Any] | None,
    predicted_p: dict[str, Any] | None,
    source: str,
) -> dict[str, Any]:
    collection = payload["collection"]
    mode = payload["mode"]
    fit = fit_from_job(payload, predicted)
    a, b = fit["a"], fit["b"]
    p_s = probe_cost_s(a, b)
    file_p = lookup_probe_block(predicted_p, mode)
    file_p_s = file_p.get("P_s") if file_p else None
    p_mismatch = None
    if file_p_s is not None and file_p_s > 0:
        rel = abs(p_s - float(file_p_s)) / float(file_p_s)
        if rel > 1e-6:
            p_mismatch = {"computed_s": p_s, "file_s": file_p_s, "rel": rel}

    rows_in = list(payload.get("genomes") or [])
    rows_in.sort(key=lambda r: int(r.get("position") or 0))
    ratio = stock_cpu_ratio(rows_in)

    per_genome: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []
    match_failures: list[dict[str, Any]] = []
    audit_failures: list[dict[str, Any]] = []
    missing_match: list[int] = []

    stock_wall = cached_wall = 0.0
    stock_cpu = cached_cpu = 0.0
    stock_cpu_measured = cached_cpu_measured = 0.0
    n_hits = n_misses = n_empty = n_nonempty = 0
    n_complete = 0

    for raw in rows_in:
        pos = int(raw["position"])
        n_i = float(raw["N_i"])
        pred_wall = a + b * n_i
        measured_wall = raw.get("stock_wall_s")
        measured_cpu = raw.get("stock_cpu_s")
        cached = raw.get("cached_wall_s")
        sampled = pos in STOCK_POS.get(collection, set())

        rel_err = None
        stock_source = "predicted a+b*N_i"
        stock_used = pred_wall
        if measured_wall is not None:
            stock_used = float(measured_wall)
            stock_source = "measured"
            if measured_wall:
                rel_err = abs(float(measured_wall) - pred_wall) / float(measured_wall)
                if rel_err > ERROR_FLAG:
                    flags.append(
                        {
                            "genome": pos,
                            "accession": raw.get("accession"),
                            "measured_s": float(measured_wall),
                            "predicted_s": pred_wall,
                            "rel_error": rel_err,
                        }
                    )

        cpu_source = None
        stock_cpu_used = None
        if measured_cpu is not None:
            stock_cpu_used = float(measured_cpu)
            cpu_source = "measured"
        elif ratio is not None:
            stock_cpu_used = ratio * stock_used
            cpu_source = "imputed cpu/wall × stock wall"

        k = pos - 1
        part2 = lookup_per_k(predicted, collection, mode, k)
        measured_speedup = None
        if cached:
            measured_speedup = stock_used / float(cached)

        match = raw.get("match")
        audit = raw.get("audit")
        if sampled and cached is not None and match is False:
            match_failures.append({"position": pos, "accession": raw.get("accession")})
        if sampled and cached is not None and match is None:
            missing_match.append(pos)
        if isinstance(audit, dict) and audit.get("ok") is False:
            audit_failures.append({"position": pos, "accession": raw.get("accession")})

        row = {
            "position": pos,
            "k": k,
            "accession": raw.get("accession"),
            "strain": raw.get("strain"),
            "N_i": n_i,
            "sampled_stock": sampled,
            "stock_source": stock_source,
            "stock_wall_s": stock_used if cached is not None or measured_wall is not None else None,
            "stock_predicted_s": pred_wall,
            "stock_measured_s": float(measured_wall) if measured_wall is not None else None,
            "stock_pred_rel_error": rel_err,
            "stock_cpu_s": stock_cpu_used,
            "stock_cpu_source": cpu_source,
            "cached_wall_s": float(cached) if cached is not None else None,
            "cached_cpu_s": raw.get("cached_cpu_s"),
            "measured_speedup": measured_speedup,
            "predicted_speedup_part2": part2.get("speedup_median") if part2 else None,
            "predicted_speedup_part2_lo": part2.get("speedup_lo") if part2 else None,
            "predicted_speedup_part2_hi": part2.get("speedup_hi") if part2 else None,
            "n_hits": raw.get("n_hits"),
            "n_misses": raw.get("n_misses"),
            "n_empty_hits": raw.get("n_empty_hits"),
            "n_nonempty_hits": raw.get("n_nonempty_hits"),
            "match": match,
            "audit": audit,
        }
        per_genome.append(row)

        if cached is None:
            continue
        n_complete += 1
        stock_wall += stock_used
        cached_wall += float(cached)
        if stock_cpu_used is not None:
            stock_cpu += stock_cpu_used
        if measured_cpu is not None:
            stock_cpu_measured += float(measured_cpu)
        if raw.get("cached_cpu_s") is not None:
            cached_cpu += float(raw["cached_cpu_s"])
            cached_cpu_measured += float(raw["cached_cpu_s"])
        n_hits += int(raw.get("n_hits") or 0)
        n_misses += int(raw.get("n_misses") or 0)
        n_empty += int(raw.get("n_empty_hits") or 0)
        n_nonempty += int(raw.get("n_nonempty_hits") or 0)

    expected = EXPECTED_N.get(collection)
    complete_collection = expected is not None and n_complete >= expected
    stop = stop_code(payload)
    gates_ok = not match_failures and not audit_failures and stop is None and not missing_match

    cached_with_p = (p_s + cached_wall) if n_complete else None
    pred_cum = lookup_cum(predicted, collection, mode, n_complete) if n_complete else None
    pred_cum_p = lookup_cum_with_p(predicted_p, collection, mode, n_complete) if n_complete else None

    kill = None
    if collection == KILL_COLLECTION and mode == KILL_MODE:
        if not complete_collection:
            kill = {
                "rule": "cached wall must be < 50% of stock wall at end of A / hmmscan",
                "evaluable": False,
                "reason": f"collection A incomplete ({n_complete}/{expected})",
            }
        elif stock_wall > 0:
            frac = cached_wall / stock_wall
            kill = {
                "rule": "cached wall must be < 50% of stock wall at end of A / hmmscan",
                "evaluable": True,
                "includes_P": False,
                "cached_over_stock": frac,
                "fails": cached_wall >= KILL_FRAC * stock_wall,
                "note": "Kill is on measured totals without probe cost P.",
            }

    three_x = None
    if complete_collection and n_complete and cached_wall > 0:
        speedup = stock_wall / cached_wall
        if speedup >= 3.0:
            if mode == POST_HOC:
                three_x = (
                    f"hmmscan cumulative wall is {speedup:.2f}× "
                    "(post-hoc; not paper_uses)."
                )
            else:
                three_x = f"hmmsearch cumulative wall is {speedup:.2f}× (primary)."

    return {
        "source": source,
        "collection": collection,
        "mode": mode,
        "primary": mode == PRIMARY,
        "post_hoc": mode == POST_HOC,
        "paper_uses": mode == PRIMARY,
        "resumed": bool(payload.get("resumed")),
        "decision": payload.get("decision"),
        "stopped": payload.get("stopped"),
        "stop": stop,
        "host": payload.get("host"),
        "git": payload.get("git"),
        "fit": fit,
        "n_rows": len(rows_in),
        "n_complete": n_complete,
        "n_expected": expected,
        "complete_collection": complete_collection,
        "per_genome": per_genome,
        "fit_error_flags": flags,
        "gates": {
            "match_expected": EXPECTED_MATCH[mode],
            "match_failures": match_failures,
            "missing_match_on_sampled": missing_match,
            "audit_failures": audit_failures,
            "stop": stop,
            "ok": gates_ok,
        },
        "hits": {
            "n_hits": n_hits,
            "n_misses": n_misses,
            "n_empty_hits": n_empty,
            "n_nonempty_hits": n_nonempty,
        },
        "probe": {
            "probe_n": PROBE_N,
            "account": PROBE_ACCOUNT,
            "n_calls": PROBE_N_CALLS,
            "sizes": list(PROBE_SIZES),
            "formula": "P = Σ (a + b · n_j)",
            "P_s": p_s,
            "P_h": hours(p_s),
            "file_P_s": file_p_s,
            "file_mismatch": p_mismatch,
            "note": (
                "Queued jobs used singleton probe_n=8 (12 calls), not "
                "batched_500 / probe_n=500."
            ),
        },
        "cumulative": {
            "n_genomes": n_complete,
            "stock_wall_s": stock_wall if n_complete else None,
            "stock_wall_h": hours(stock_wall) if n_complete else None,
            "stock_cpu_s": stock_cpu if n_complete else None,
            "stock_cpu_h": hours(stock_cpu) if n_complete else None,
            "stock_cpu_measured_s": stock_cpu_measured,
            "stock_cpu_note": (
                "Unsampled stock wall is a + b·N_i. Unsampled stock CPU is "
                "imputed from the sampled CPU/wall ratio times that wall "
                f"({ratio:.4f} CPU-s/wall-s)."
                if ratio is not None
                else "No sampled stock CPU; imputed CPU-hours omitted."
            ),
            "cached_wall_s": cached_wall if n_complete else None,
            "cached_wall_h": hours(cached_wall) if n_complete else None,
            "cached_cpu_s": cached_cpu if n_complete else None,
            "cached_cpu_h": hours(cached_cpu) if n_complete else None,
            "cached_with_P_wall_s": cached_with_p,
            "cached_with_P_wall_h": hours(cached_with_p),
            "cum_speedup_wall": (stock_wall / cached_wall) if cached_wall else None,
            "cum_speedup_wall_with_P": (
                (stock_wall / cached_with_p) if cached_with_p else None
            ),
            "stock_model": "measured at sampled positions; a + b·N_i otherwise",
            "predicted_part2_N": 4192,
            "predicted_part2_cum_speedup": pred_cum.get("cum_speedup") if pred_cum else None,
            "predicted_part2_cum_stock_s": pred_cum.get("cum_stock_s") if pred_cum else None,
            "predicted_part2_cum_cached_s": pred_cum.get("cum_cached_s") if pred_cum else None,
            "predicted_singleton_8_cum_speedup": (
                pred_cum_p.get("cum_speedup") if pred_cum_p else None
            ),
            "predicted_singleton_8_cum_cached_s": (
                pred_cum_p.get("cum_cached_s") if pred_cum_p else None
            ),
        },
        "kill": kill,
        "three_x": three_x,
    }


def analyze(
    job_paths: list[Path],
    *,
    predicted: dict[str, Any] | None,
    predicted_p: dict[str, Any] | None,
) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for path in job_paths:
        payload = load_json(path)
        if not is_job_payload(payload):
            continue
        row = analyze_job(
            payload, predicted=predicted, predicted_p=predicted_p, source=str(path)
        )
        jobs.append(row)
        by_key[f"{row['collection']}_{row['mode']}"] = row

    a_scan = by_key.get("A_hmmscan")
    kill = (a_scan or {}).get("kill")
    any_stop = [j["stop"] for j in jobs if j.get("stop")]
    any_gate_fail = [j for j in jobs if not j["gates"]["ok"]]
    headline_ok = not any_stop and not any_gate_fail
    if kill and kill.get("evaluable") and kill.get("fails"):
        headline_ok = False

    return {
        "protocol": PROTOCOL,
        "analyzer": "pipeline/scripts/analyze_savings.py",
        "analyzed_utc": datetime.now(timezone.utc).isoformat(),
        "primary": PRIMARY,
        "post_hoc": POST_HOC,
        "paper_uses": PRIMARY,
        "probe_n": PROBE_N,
        "probe_account": PROBE_ACCOUNT,
        "probe_n_calls": PROBE_N_CALLS,
        "error_flag": ERROR_FLAG,
        "invented": False,
        "jobs": jobs,
        "by_key": {k: {"source": v["source"], "n_complete": v["n_complete"]} for k, v in by_key.items()},
        "gates_ok": not any_gate_fail,
        "stops": any_stop,
        "kill": kill,
        "diverse_collection_headline_fails": bool(
            kill and kill.get("evaluable") and kill.get("fails")
        ),
        "headline_ok": headline_ok,
        "note": (
            "hmmsearch is the locked primary (paper_uses). hmmscan is "
            "post-hoc. Part 2 predictions used N = 4,192 for every genome; "
            "measured stock uses each proteome's N_i. Probe cost P uses "
            "singleton_8 (12 calls) because that is what the queued jobs ran."
        ),
    }


def _speedup_claim_lines(summary: dict[str, Any]) -> list[str]:
    lines = ["## 3×"]
    if summary.get("diverse_collection_headline_fails"):
        lines.append(
            "Kill rule tripped on A / hmmscan: cached wall is not below 50% of "
            "stock. The diverse-collection headline fails. Stop talking about 3× on A."
        )
        return lines
    claims = [j["three_x"] for j in summary["jobs"] if j.get("three_x")]
    if not claims:
        lines.append(
            "No 3× sentence: no completed (collection, mode) has measured "
            "cumulative wall speedup ≥ 3."
        )
        return lines
    lines.extend(f"- {c}" for c in claims)
    return lines


def write_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# HMMER accumulated-savings analysis",
        "",
        f"Protocol: `{summary['protocol']}`.",
        f"Analyzer: `{summary['analyzer']}`.",
        f"Analyzed: {summary['analyzed_utc']}.",
        "",
        f"**Primary / `paper_uses`:** {PRIMARY}. **hmmscan is post-hoc** "
        "and is not promoted after seeing numbers.",
        "",
        f"Probe cost *P* uses **{PROBE_ACCOUNT}** (`probe_n = {PROBE_N}`, "
        f"{PROBE_N_CALLS} calls): `P = Σ (a + b · n_j)`, "
        "`cum_cached = P + Σ cached_i`. This is the queued-job account, "
        "not `batched_500`.",
        "",
        summary["note"],
        "",
        "## Correctness gates",
        "",
    ]
    if summary["stops"]:
        lines.append("STOP codes: " + ", ".join(sorted(set(summary["stops"]))))
        lines.append("")
    if summary["gates_ok"]:
        lines.append("No MATCH / audit / STOP failures in the dumps that were present.")
    else:
        lines.append("**Gate failure.** Do not continue a 3× or savings headline.")
    lines.append("")

    if summary.get("kill"):
        kill = summary["kill"]
        lines.append("## Kill rule (A / hmmscan, post-hoc)")
        lines.append("")
        lines.append(kill["rule"] + ". Kill is evaluated **without** *P*.")
        if not kill.get("evaluable"):
            lines.append(f"Not yet evaluable: {kill.get('reason')}.")
        elif kill.get("fails"):
            lines.append(
                f"**FAILS.** cached/stock = {kill['cached_over_stock']:.3f}. "
                "Diverse-collection headline fails."
            )
        else:
            lines.append(
                f"Does not trip: cached/stock = {kill['cached_over_stock']:.3f} "
                "(< 0.50)."
            )
        lines.append("")

    for job in summary["jobs"]:
        label = mode_label(job["mode"])
        lines.append(f"## {collection_title(job['collection'])} — {label}")
        lines.append("")
        lines.append(
            f"Source `{job['source']}` · {job['n_complete']}/{job['n_expected']} "
            f"genomes with cached wall · resumed={job['resumed']}."
        )
        if job.get("stop"):
            lines.append(f"**{job['stop']}**")
        gates = job["gates"]
        if not gates["ok"]:
            lines.append(
                f"Gates failed: MATCH {gates['match_failures']}, "
                f"missing MATCH {gates['missing_match_on_sampled']}, "
                f"audit {gates['audit_failures']}, stop={gates['stop']}."
            )
        cum = job["cumulative"]
        if cum["n_genomes"]:
            lines.append("")
            lines.append("| Metric | Stock | Cached (no P) | Cached + P |")
            lines.append("|--------|------:|--------------:|-----------:|")
            lines.append(
                f"| wall hours | {cum['stock_wall_h']:.4f} | "
                f"{cum['cached_wall_h']:.4f} | "
                f"{(cum['cached_with_P_wall_h'] or 0):.4f} |"
            )
            stock_cpu_h = cum["stock_cpu_h"]
            cached_cpu_h = cum["cached_cpu_h"]
            lines.append(
                f"| CPU hours | "
                f"{'—' if stock_cpu_h is None else f'{stock_cpu_h:.4f}'} | "
                f"{'—' if cached_cpu_h is None else f'{cached_cpu_h:.4f}'} | "
                f"— |"
            )
            lines.append(
                f"| cum. speedup (wall) | 1 | "
                f"{cum['cum_speedup_wall']:.3f}× | "
                f"{(cum['cum_speedup_wall_with_P'] or float('nan')):.3f}× |"
            )
            lines.append("")
            lines.append(
                f"Stock wall = measured at sampled positions "
                f"{sorted(STOCK_POS[job['collection']])} plus `a + b·N_i` "
                f"elsewhere (a={job['fit']['a']:.6g}, b={job['fit']['b']:.6g}). "
                f"{cum['stock_cpu_note']}"
            )
            if cum.get("predicted_part2_cum_speedup") is not None:
                lines.append(
                    f"Part 2 predicted cum. speedup at this prefix "
                    f"(N=4192 stand-in, no P): "
                    f"{cum['predicted_part2_cum_speedup']:.3f}×. "
                    f"singleton_8 predicted (with P): "
                    f"{cum.get('predicted_singleton_8_cum_speedup') or float('nan'):.3f}×."
                )
            probe = job["probe"]
            lines.append(
                f"P = {probe['P_s']:.3f} s ({probe['P_h']:.4f} h) from "
                f"{probe['n_calls']} calls {probe['sizes']}."
            )
        else:
            lines.append("No completed genomes in this dump.")
        if job["fit_error_flags"]:
            lines.append("")
            lines.append(
                f"**Fit error > {ERROR_FLAG:.0%} at sampled points "
                f"(do not replace the fit):**"
            )
            for flag in job["fit_error_flags"]:
                lines.append(
                    f"- genome {flag['genome']}: |error|/measured = {flag['rel_error']:.3f} "
                    f"(measured {flag['measured_s']:.3f}s, predicted {flag['predicted_s']:.3f}s)"
                )
        lines.append("")

    lines.extend(_speedup_claim_lines(summary))
    lines.append("")
    lines.append("## What this is not")
    lines.append("")
    lines.append("- Not permission to promote hmmscan to `paper_uses`.")
    lines.append("- Not `probe_n = 500` and not the batched-18 deployable probe.")
    lines.append("- Not invented numbers: every total comes from a job dump plus the locked fit.")
    lines.append("")
    return "\n".join(lines) + "\n"


def _panel_job(by_cm: dict[tuple[str, str], dict[str, Any]], cid: str, mode: str) -> dict[str, Any] | None:
    return by_cm.get((cid, mode))


def write_figures(summary: dict[str, Any], fig_dir: Path) -> list[str]:
    fig_dir.mkdir(parents=True, exist_ok=True)
    by_cm = {(j["collection"], j["mode"]): j for j in summary["jobs"]}
    written: list[str] = []

    def save(fig: Any, name: str) -> None:
        dest = fig_dir / name
        fig.savefig(dest)
        plt.close(fig)
        written.append(name)

    # 25 — cumulative wall, stock vs cached (no P). hmmsearch on top.
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.2), sharey=False)
    for r, mode in enumerate((PRIMARY, POST_HOC)):
        color = SEARCH if mode == PRIMARY else SCAN
        for c, cid in enumerate(("A", "B")):
            ax = axes[r][c]
            job = _panel_job(by_cm, cid, mode)
            ax.set_title(f"{collection_title(cid)} · {mode_label(mode)}")
            if not job:
                ax.text(0.5, 0.5, "no job dump", ha="center", va="center", color=MUTED)
                ax.set_xticks([])
                ax.set_yticks([])
                continue
            xs, stock_h, cached_h = [], [], []
            s = csum = 0.0
            for row in job["per_genome"]:
                if row["cached_wall_s"] is None or row["stock_wall_s"] is None:
                    continue
                s += row["stock_wall_s"]
                csum += row["cached_wall_s"]
                xs.append(row["position"])
                stock_h.append(s / 3600.0)
                cached_h.append(csum / 3600.0)
            if not xs:
                ax.text(0.5, 0.5, "no completed genomes", ha="center", va="center", color=MUTED)
                continue
            ax.plot(xs, stock_h, color=STOCK, lw=1.8, label="stock (meas. + a+b·Nᵢ)")
            ax.plot(xs, cached_h, color=color, lw=1.8, label="cached (no P)")
            ax.set_xlabel("genome (collection order)")
            if c == 0:
                ax.set_ylabel("cumulative wall hours")
            ax.set_xlim(1, xs[-1])
            ax.set_ylim(bottom=0)
            ax.legend(fontsize=8, loc="upper left")
    fig.suptitle("Accumulated wall — stock vs cached (probe cost P not included)", fontsize=12)
    fig.tight_layout()
    save(fig, "25_savings_cum_wall.png")

    # 26 — per-genome speedup vs k, measured vs Part 2.
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.2))
    for r, mode in enumerate((PRIMARY, POST_HOC)):
        color = SEARCH if mode == PRIMARY else SCAN
        for c, cid in enumerate(("A", "B")):
            ax = axes[r][c]
            job = _panel_job(by_cm, cid, mode)
            ax.set_title(f"{collection_title(cid)} · {mode_label(mode)}")
            if not job:
                ax.text(0.5, 0.5, "no job dump", ha="center", va="center", color=MUTED)
                ax.set_xticks([])
                ax.set_yticks([])
                continue
            xs, meas, pred, lo, hi = [], [], [], [], []
            for row in job["per_genome"]:
                if row["k"] < 1 or row["measured_speedup"] is None:
                    continue
                xs.append(row["k"])
                meas.append(row["measured_speedup"])
                pred.append(row["predicted_speedup_part2"])
                lo.append(row["predicted_speedup_part2_lo"])
                hi.append(row["predicted_speedup_part2_hi"])
            if pred and all(p is not None for p in pred):
                ax.fill_between(
                    xs,
                    [float(x) for x in lo],
                    [float(x) for x in hi],
                    color=PRED,
                    alpha=0.18,
                    linewidth=0,
                    label="Part 2 10–90% (N=4192)",
                )
                ax.plot(xs, pred, color=PRED, lw=1.4, label="Part 2 median")
            if xs:
                ax.plot(xs, meas, color=color, lw=1.8, label="measured Nᵢ")
            ax.axhline(3.0, color=STOCK, ls="--", lw=1.0, label="3×")
            ax.set_xlabel("k (genomes already seen)")
            if c == 0:
                ax.set_ylabel("speedup of genome k+1")
            ax.set_ylim(bottom=0)
            if xs:
                ax.set_xlim(1, xs[-1])
            ax.legend(fontsize=8, loc="upper left")
    fig.suptitle(
        "Per-genome speedup vs k — measured (Nᵢ) vs Part 2 (N=4,192 stand-in)",
        fontsize=12,
    )
    fig.tight_layout()
    save(fig, "26_savings_speedup_vs_k.png")

    # 27 — cumulative with / without P.
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.2))
    for r, mode in enumerate((PRIMARY, POST_HOC)):
        color = SEARCH if mode == PRIMARY else SCAN
        for c, cid in enumerate(("A", "B")):
            ax = axes[r][c]
            job = _panel_job(by_cm, cid, mode)
            ax.set_title(f"{collection_title(cid)} · {mode_label(mode)}")
            if not job:
                ax.text(0.5, 0.5, "no job dump", ha="center", va="center", color=MUTED)
                ax.set_xticks([])
                ax.set_yticks([])
                continue
            p_s = job["probe"]["P_s"]
            xs, no_p, with_p = [], [], []
            stock_h = []
            s = csum = 0.0
            for row in job["per_genome"]:
                if row["cached_wall_s"] is None or row["stock_wall_s"] is None:
                    continue
                s += row["stock_wall_s"]
                csum += row["cached_wall_s"]
                xs.append(row["position"])
                stock_h.append(s / 3600.0)
                no_p.append(csum / 3600.0)
                with_p.append((p_s + csum) / 3600.0)
            if not xs:
                ax.text(0.5, 0.5, "no completed genomes", ha="center", va="center", color=MUTED)
                continue
            ax.plot(xs, stock_h, color=STOCK, lw=1.6, label="stock")
            ax.plot(xs, no_p, color=color, lw=1.8, label="cached, no P")
            ax.plot(xs, with_p, color=color, lw=1.6, ls="--", label="cached + P (singleton_8)")
            ax.set_xlabel("genome (collection order)")
            if c == 0:
                ax.set_ylabel("cumulative wall hours")
            ax.set_xlim(1, xs[-1])
            ax.set_ylim(bottom=0)
            ax.legend(fontsize=8, loc="upper left")
    fig.suptitle(
        "Cumulative cached wall with and without probe cost P (singleton_8, probe_n=8)",
        fontsize=12,
    )
    fig.tight_layout()
    save(fig, "27_savings_cum_with_without_P.png")

    # 28 — sampled stock measured vs a+b·N_i.
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.2))
    for r, mode in enumerate((PRIMARY, POST_HOC)):
        color = SEARCH if mode == PRIMARY else SCAN
        for c, cid in enumerate(("A", "B")):
            ax = axes[r][c]
            job = _panel_job(by_cm, cid, mode)
            ax.set_title(f"{collection_title(cid)} · {mode_label(mode)}")
            if not job:
                ax.text(0.5, 0.5, "no job dump", ha="center", va="center", color=MUTED)
                ax.set_xticks([])
                ax.set_yticks([])
                continue
            xs, meas, pred, flagged = [], [], [], []
            for row in job["per_genome"]:
                if row["stock_measured_s"] is None:
                    continue
                xs.append(row["position"])
                meas.append(row["stock_measured_s"] / 3600.0)
                pred.append(row["stock_predicted_s"] / 3600.0)
                flagged.append(bool(row["stock_pred_rel_error"] and row["stock_pred_rel_error"] > ERROR_FLAG))
            if not xs:
                ax.text(0.5, 0.5, "no sampled stock", ha="center", va="center", color=MUTED)
                continue
            ax.plot(xs, pred, color=PRED, lw=1.5, marker="o", label="a + b·Nᵢ")
            ax.plot(xs, meas, color=color, lw=1.5, marker="s", label="measured")
            for x, y, bad in zip(xs, meas, flagged):
                if bad:
                    ax.scatter([x], [y], s=80, facecolors="none", edgecolors=FAIL, linewidths=1.6, zorder=5)
            ax.axhline(0, color=MUTED, lw=0.4)
            ax.set_xlabel("sampled genome position")
            if c == 0:
                ax.set_ylabel("stock wall hours")
            ax.set_ylim(bottom=0)
            ax.legend(fontsize=8, loc="best")
    fig.suptitle(
        f"Sampled stock: measured vs a+b·Nᵢ (open red = |error|/measured > {ERROR_FLAG:.0%})",
        fontsize=12,
    )
    fig.tight_layout()
    save(fig, "28_savings_stock_pred_error.png")

    return written


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--jobs",
        nargs="*",
        default=None,
        help="Job JSON files or directories. Default: results/savings/{A,B}_{hmmsearch,hmmscan}.json",
    )
    p.add_argument(
        "--predicted",
        default=str(ROOT / "results" / "hmmer_predicted_speedup.json"),
        help="Part 2 predictions (no P).",
    )
    p.add_argument(
        "--predicted-with-probe",
        default=str(ROOT / "results" / "hmmer_predicted_speedup_with_probe.json"),
        help="Predictions that include singleton_8 / batched_500 P.",
    )
    p.add_argument(
        "--out-json",
        default=str(ROOT / "results" / "savings_summary.json"),
        help="Analysis summary JSON (not a job dump).",
    )
    p.add_argument(
        "--out-md",
        default=str(ROOT / "results" / "savings_summary.md"),
        help="Analysis write-up.",
    )
    p.add_argument(
        "--fig-dir",
        default=str(ROOT / "results" / "figures"),
        help="Directory for figures 25–28.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    job_args = [Path(x) for x in (args.jobs or [ROOT / "results" / "savings"])]
    job_paths = discover_jobs(job_args)
    if not job_paths:
        print(
            "no savings job dumps found; refusing to invent numbers",
            file=sys.stderr,
        )
        return 2

    pred_path = Path(args.predicted)
    pred_p_path = Path(args.predicted_with_probe)
    predicted = load_json(pred_path) if pred_path.is_file() else None
    predicted_p = load_json(pred_p_path) if pred_p_path.is_file() else None

    summary = analyze(job_paths, predicted=predicted, predicted_p=predicted_p)
    summary["inputs"] = {
        "jobs": [str(p) for p in job_paths],
        "predicted": str(pred_path) if predicted is not None else None,
        "predicted_with_probe": str(pred_p_path) if predicted_p is not None else None,
    }
    fig_dir = Path(args.fig_dir)
    summary["figures"] = write_figures(summary, fig_dir)
    summary["figures"] = [str(fig_dir / name) for name in summary["figures"]]

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    for dest in (out_json, out_md):
        name = dest.name
        if name.startswith("savings_A") or name.startswith("savings_B"):
            print(f"refusing to write job-dump name {dest}", file=sys.stderr)
            return 2

    atomic_write(out_json, json.dumps(summary, indent=2) + "\n")
    atomic_write(out_md, write_markdown(summary))
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    for fig in summary["figures"]:
        print(f"wrote {fig}")
    return 0 if summary["gates_ok"] and not summary.get("stops") else 3


if __name__ == "__main__":
    raise SystemExit(main())
