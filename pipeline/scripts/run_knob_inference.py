#!/usr/bin/env python3
"""K1 driver for docs/KNOB_INFERENCE_PROTOCOL.md.

The inference code does not name this tool. This driver does: it builds the
locked sub-reference, fits the contract, and records the probe.
"""

from __future__ import annotations

import hashlib
import json
import platform
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.infer_knobs import apply_extra_argv, capture_help, infer_knobs  # noqa: E402
from acts.reference_fit import partition_indices  # noqa: E402
from acts.reference_formats import (  # noqa: E402
    iter_profile_raw,
    parse_reference_text,
    read_records,
    write_entries,
)
from acts.reference_run import probe_fit, write_record_file  # noqa: E402

SEED = 20261014
N_RECORDS = 50
N_MODELS = 400
QUERY_GZ = ROOT / "data" / "recurrence" / "A" / "GCF_002853805.1_protein.faa.gz"
REF_GZ = ROOT / "data" / "hmmer" / "Pfam-A.hmm.gz"
MUST_REJECT = ("--F1", "--F2", "--F3", "--seed", "--cpu")
ALLOWED_THRESHOLDS = {"-E", "--domE", "--incE", "--incdomE"}


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _git_hash() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT.parents[0],
        check=False,
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "").strip()


def _select_models():
    _log(f"counting models in {REF_GZ.name}")
    total = sum(1 for _ in iter_profile_raw(REF_GZ))
    if total < N_MODELS:
        return None, total
    chosen = set(random.Random(SEED).sample(range(total), N_MODELS))
    _log(f"extracting {N_MODELS} of {total}")
    blocks = [raw for index, raw in enumerate(iter_profile_raw(REF_GZ)) if index in chosen]
    if len(blocks) != N_MODELS:
        raise RuntimeError(f"extracted {len(blocks)} models, wanted {N_MODELS}")
    return parse_reference_text("".join(blocks)), total


def _judge(result: dict) -> list[str]:
    reasons: list[str] = []
    pin = str(result.get("pin"))
    if pin != "-Z {entry_count}":
        reasons.append(f"pin is {pin!r}")
    found = {item["option"] for item in result.get("thresholds") or []}
    if "-E" not in found:
        reasons.append("missing -E")
    if "--domE" not in found:
        reasons.append("missing --domE")
    for item in result.get("thresholds") or []:
        option = item["option"]
        if option in MUST_REJECT:
            reasons.append(f"accepted decoy threshold {option}")
        elif option not in ALLOWED_THRESHOLDS:
            reasons.append(f"unexpected threshold {option}")
    for candidate in result.get("candidates") or []:
        option = candidate["option"]
        if option not in MUST_REJECT:
            continue
        norms = candidate.get("normalizer") or {}
        if any(value == "accept" for value in norms.values()):
            reasons.append(f"accepted decoy normalizer {option}")
    return reasons


def main() -> int:
    out = ROOT / "results" / "knob_inference" / "k1.json"
    work = Path("/tmp/acts_knob_k1")
    work.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    hmmscan = shutil.which("hmmscan")
    hmmpress = shutil.which("hmmpress")
    meta = {
        "protocol": "docs/KNOB_INFERENCE_PROTOCOL.md",
        "git": _git_hash(),
        "host": platform.node(),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "seed": SEED,
        "n_records": N_RECORDS,
        "n_models": N_MODELS,
    }
    if not hmmscan or not hmmpress or not QUERY_GZ.is_file() or not REF_GZ.is_file():
        meta.update(
            {
                "verdict": "inconclusive",
                "reason": "missing binary or data",
                "hmmscan": hmmscan,
                "query": QUERY_GZ.is_file(),
                "reference": REF_GZ.is_file(),
                "k2": "skipped: diamond not on PATH" if shutil.which("diamond") is None else "not run",
            }
        )
        out.write_text(json.dumps(meta, indent=2) + "\n")
        _log("INCONCLUSIVE")
        return 0

    help_text = capture_help(hmmscan)
    banner = [line for line in help_text.splitlines() if line.startswith("#")][:3]
    entries, total = _select_models()
    if entries is None:
        meta.update({"verdict": "inconclusive", "reason": f"only {total} models", "banner": banner})
        out.write_text(json.dumps(meta, indent=2) + "\n")
        _log("INCONCLUSIVE")
        return 0

    all_records = read_records(QUERY_GZ)
    record_index = sorted(random.Random(SEED).sample(range(len(all_records)), N_RECORDS))
    records = [all_records[i] for i in record_index]
    write_record_file(records, work / "queries.faa")
    parts = partition_indices(len(entries), 2, SEED)
    half = [entries[i] for i in sorted(parts[0])]
    scans = {"n": 0}
    cache: dict[tuple, dict[str, str]] = {}

    def reference_file(subset) -> Path:
        digest = hashlib.sha256("".join(entry.content_hash for entry in subset).encode()).hexdigest()[:16]
        path = work / f"{digest}.hmm"
        if path.exists() and Path(str(path) + ".h3m").exists():
            return path
        write_entries(list(subset), path)
        _log(f"press {len(subset)} models")
        proc = subprocess.run([hmmpress, "-f", str(path)], check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "")[-500:]
            raise RuntimeError(f"press failed ({proc.returncode}): {detail}")
        return path

    def scan(recs, subset, extra) -> dict[str, str]:
        key = (tuple(entry.content_hash for entry in subset), tuple(extra))
        if key in cache:
            return cache[key]
        paired = list(extra)
        for index, token in enumerate(paired):
            if token == "--cpu" and index + 1 < len(paired) and paired[index + 1] != "1":
                raise RuntimeError("worker-count probe refused")
        scans["n"] += 1
        ref = reference_file(subset)
        call = work / f"call{scans['n']}"
        call.mkdir(parents=True, exist_ok=True)
        base = [
            hmmscan,
            "--noali",
            "--cpu",
            "1",
            "--tblout",
            str(call / "tbl"),
            "--domtblout",
            str(call / "dom"),
        ]
        cmd = apply_extra_argv(base, list(extra)) + [str(ref), str(work / "queries.faa")]
        started = time.perf_counter()
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        elapsed = time.perf_counter() - started
        _log(f"scan {scans['n']} n={len(subset)} extra={list(extra)} {elapsed:.1f}s rc={proc.returncode}")
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "")[-500:]
            raise RuntimeError(f"tool failed ({proc.returncode}): {detail}")
        tables = {}
        for name in ("tbl", "dom"):
            dest = call / name
            if not dest.is_file():
                raise RuntimeError(f"tool did not write {name}")
            tables[name] = dest.read_text()
        cache[key] = tables
        return tables

    _log("fitting contract")
    before_fit = scans["n"]
    try:
        fit = probe_fit(
            entries,
            records,
            lambda recs, subset: scan(recs, subset, ()),
            primary_parts=parts,
            sample=False,
        )
    except Exception as exc:
        meta.update({"verdict": "inconclusive", "reason": f"fit failed: {exc}", "banner": banner})
        out.write_text(json.dumps(meta, indent=2) + "\n")
        _log("INCONCLUSIVE")
        return 0
    fit_calls = scans["n"] - before_fit
    columns = [
        {"table": table.name, "index": col.index, "role": col.role, "member": col.member}
        for table in fit.tables
        for col in table.columns
    ]
    has_count = any(col["member"] == "entry_count" for col in columns)
    fit_summary = {
        "decision": fit.decision,
        "reason": fit.reason,
        "probe_invocations": fit.probe_invocations,
        "columns": columns,
    }
    if not has_count:
        meta.update(
            {
                "verdict": "inconclusive",
                "reason": "fit assigned no entry_count column",
                "banner": banner,
                "model_total": total,
                "fit": fit_summary,
                "fit_calls": fit_calls,
                "subprocess_calls": scans["n"],
            }
        )
        out.write_text(json.dumps(meta, indent=2) + "\n")
        _log("INCONCLUSIVE")
        return 0

    _log("inferring knobs")
    result = infer_knobs(
        help_text,
        records,
        entries,
        half,
        fit.tables,
        lambda recs, subset, extra: scan(recs, subset, extra),
    )
    kills = _judge(result)
    verdict = "killed" if kills else "pass"
    payload = {
        **meta,
        **result,
        "verdict": verdict,
        "kill_reasons": kills,
        "banner": banner,
        "model_total": total,
        "query_index_head": record_index[:8],
        "half": len(half),
        "whole": len(entries),
        "fit": fit_summary,
        "fit_calls": fit_calls,
        "subprocess_calls": scans["n"],
        "probe_cost_P": scans["n"],
        "k2": "skipped: diamond not on PATH",
    }
    out.write_text(json.dumps(payload, indent=2) + "\n")
    _log(f"{verdict} pin={result['pin']!r} P={scans['n']} tool_calls={result['tool_calls']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
