#!/usr/bin/env python3
"""Run TARE's shipped check against injected reference couplings.

The shim is ``scripts/coupling_shim.py``. TARE wraps it with the hmmscan
argv and the declared pin ``-Z {entry_count}``. Coupling mode and strength
are environment variables.

Laptop wall times are stored as ``indicative_wall_s`` and are not evidence.
"""

from __future__ import annotations

import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
REPO = PIPELINE.parent
sys.path.insert(0, str(PIPELINE))
sys.path.insert(0, str(PIPELINE / "scripts"))

import coupling_shim as shim  # noqa: E402
from acts.audit import AUDIT_FLOOR, AUDIT_P, AUDIT_SEED, pick_audit  # noqa: E402
from acts.exact_certificate import SEEDS, neighbor_ids, pad_indices, pad_miss_probability, sample_keys  # noqa: E402
from acts.reference_run import (  # noqa: E402
    IC2_SAMPLE_SEED,
    IC2_SAMPLE_SIZE,
    ReferenceIncremental,
    probe_fit,
)
import acts.reference_run as reference_run  # noqa: E402

SCRATCH = Path.home() / "tmp" / "tare_b"
OUT_DIR = PIPELINE / "results" / "adversarial"
PIN = "-Z {entry_count}"
HMMER = "/opt/homebrew/bin/hmmscan"

FORMS = (
    ("C0", "none", 0),
    ("C1", "residues", 0),
    ("C2", "presence", 0),
    ("C3", "order", 2),
    ("C3", "order", 5),
    ("C3", "order", 20),
    ("C4", "global", 0),
)
KS = (1, 5, 22, 100)
SEVERITY = (
    "missing_and_extra",
    "missing",
    "extra",
    "different_row",
    "value-only",
    "order",
    "identical",
)


class _Named:
    def __init__(self, name: str) -> None:
        self.primary = name


def trial_seed(base: int, form_i: int, k: int, distance: int, trial: int) -> int:
    """Derived from the block seed. Not an 8-digit seed from another block."""
    return int(f"{base}{form_i:02d}{k:03d}{distance:02d}{trial:02d}")


def cell_key(form: str, distance: int, k: int) -> str:
    if form == "C3":
        return f"C3/d{distance}/k{k}"
    return f"{form}/k{k}"


def body(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def combined_class(classes: list[str]) -> str:
    for name in SEVERITY:
        if name in classes:
            return name
    return "identical"


def wilson(successes: int, n: int, z: float = 1.959963984540054) -> list[float] | None:
    if n <= 0:
        return None
    p = successes / n
    den = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / den
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / den
    return [max(0.0, center - half), min(1.0, center + half)]


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def git_dirty_tracked() -> bool:
    out = subprocess.check_output(["git", "status", "--porcelain", "-uno"], cwd=REPO, text=True)
    return bool(out.strip())


def hmmer_version() -> str:
    proc = subprocess.run([HMMER, "-h"], check=False, capture_output=True, text=True)
    lines = [line for line in proc.stdout.splitlines() if line.startswith("# HMMER")]
    return lines[0] if lines else proc.stdout.splitlines()[0]


def argv_for(script: Path, hmm: Path, fasta: Path) -> list[str]:
    return [
        str(script),
        "--cut_ga",
        "--noali",
        "--cpu",
        "2",
        "--tblout",
        "{output:tblout}",
        "--domtblout",
        "{output:domtblout}",
        "-o",
        "/dev/null",
        str(hmm),
        str(fasta),
    ]


def apply_env(spec: dict) -> None:
    os.environ["TARE_COUPLING"] = spec["coupling"]
    os.environ["TARE_K"] = str(spec["k"])
    os.environ["TARE_SEED"] = str(spec["seed"])
    os.environ["TARE_N"] = str(spec["n_records"])
    os.environ["TARE_M"] = str(spec["n_models"])
    os.environ["TARE_D"] = str(spec["distance"])
    os.environ["TARE_AFFECT"] = ""
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"


def geometry(plan: shim.TrialPlan, n_models: int) -> dict:
    entries = [_Named(shim.model_name(i)) for i in range(n_models)]
    neighbors = neighbor_ids(entries, {plan.hit_name})
    fractions: list[bool] = []
    width = None
    for name, indices in pad_indices(entries, {plan.hit_name}):
        if not name.startswith("random"):
            continue
        width = len(indices)
        if plan.responsible_name is None:
            continue
        names = {shim.model_name(i) for i in indices}
        fractions.append(plan.responsible_name in names)
    q_trial = (sum(fractions) / len(fractions)) if fractions else None
    return {
        "hit": plan.hit_name,
        "responsible": plan.responsible_name,
        "neighbor_has_responsible": (
            plan.responsible_name in neighbors if plan.responsible_name else None
        ),
        "q_trial": q_trial,
        "pad_width": width,
    }


def sample_overlap(n_records: int) -> dict:
    keys = [shim.record_name(i) for i in range(n_records)]
    probe = shim.probe_indices(n_records)
    eligible = n_records - len(probe)
    sample = sample_keys(keys, min(IC2_SAMPLE_SIZE, n_records), IC2_SAMPLE_SEED)
    audit = pick_audit(keys, p=AUDIT_P, floor=AUDIT_FLOOR, rng=__import__("random").Random(AUDIT_SEED))

    def eligible_count(chosen: list[str]) -> int:
        return sum(1 for key in chosen if int(key[1:]) not in probe)

    return {
        "eligible_records": eligible,
        "random_sample_n": len(sample),
        "random_sample_eligible": eligible_count(sample),
        "audit_sample_n": len(audit),
        "audit_sample_eligible": eligible_count(audit),
    }


def score_stock(models: list[dict], queries: list[dict], spec: dict) -> dict[str, str]:
    return shim.score_models(models, queries, z_override=None, cut_ga=True, spec=spec)


def score_oracle(models: list[dict], queries: list[dict], spec: dict, plan: shim.TrialPlan) -> dict[str, str]:
    subset = [models[plan.hit_index]]
    return shim.score_models(
        subset, queries, z_override=spec["n_models"], cut_ga=True, spec=spec
    )


def run_trial(
    *,
    script: Path,
    hmm: Path,
    fasta: Path,
    models: list[dict],
    queries: list[dict],
    spec: dict,
    trial_dir: Path,
) -> dict:
    apply_env(spec)
    plan = shim.trial_plan(
        n_records=spec["n_records"],
        n_models=spec["n_models"],
        k=spec["k"],
        seed=spec["seed"],
        coupling=spec["coupling"],
        distance=spec["distance"],
    )
    if trial_dir.exists():
        shutil.rmtree(trial_dir)
    trial_dir.mkdir(parents=True)
    captured: list[dict[str, str]] = []
    original = reference_run._batched_replay

    def wrapped(*args, **kwargs):
        texts, n_batches = original(*args, **kwargs)
        captured.append(texts)
        return texts, n_batches

    reference_run._batched_replay = wrapped
    started = time.perf_counter()
    try:
        result = ReferenceIncremental(
            argv=argv_for(script, hmm, fasta),
            input_path=fasta,
            out_dir=trial_dir,
            reference=hmm,
            cache_path=trial_dir / "cache.sqlite",
            verify="audit",
            pin=PIN,
        ).run()
    finally:
        reference_run._batched_replay = original
        elapsed = time.perf_counter() - started

    stock = score_stock(models, queries, spec)
    oracle = score_oracle(models, queries, spec, plan)
    replay = captured[0] if captured else oracle
    classes = []
    per_table = {}
    for name in ("tblout", "domtblout"):
        kind = shim.diff_class(body(stock.get(name, "")), body(replay.get(name, "")))
        per_table[name] = kind
        classes.append(kind)
    diff = combined_class(classes)
    differs = diff != "identical"
    oracle_classes = [
        shim.diff_class(body(replay.get(name, "")), body(oracle.get(name, "")))
        for name in ("tblout", "domtblout")
    ]
    labeled = shim.classify(result.decision, result.reason, differs)
    stock_rows = len(body(stock["tblout"]))
    power_ok = stock_rows >= spec["n_records"]
    if not power_ok:
        labeled = {**labeled, "outcome": "INCONCLUSIVE"}
    geo = geometry(plan, spec["n_models"])
    extra = result.extra or {}
    payload = {
        "seed": spec["seed"],
        "decision": result.decision,
        "reason": result.reason,
        "outcome": labeled["outcome"],
        "layer": labeled["layer"],
        "replay_differs": differs,
        "diff_class": diff,
        "diff_class_by_table": per_table,
        "replay_oracle_mismatch": any(kind != "identical" for kind in oracle_classes),
        "stock_rows": stock_rows,
        "power_ok": power_ok,
        "hit": geo["hit"],
        "responsible": geo["responsible"],
        "neighbor_has_responsible": geo["neighbor_has_responsible"],
        "q_trial": geo["q_trial"],
        "pad_width": geo["pad_width"],
        "random_pads": extra.get("random_pads"),
        "audit": extra.get("audit"),
        "ic2": extra.get("ic2"),
        "indicative_wall_s": round(elapsed, 3),
    }
    shutil.rmtree(trial_dir, ignore_errors=True)
    return payload


def eq4_block(n_records: int, k: int, q: float | None, applies: bool) -> dict:
    if not applies or q is None or k <= 0:
        return {"eq4_applies": False, "eq4_p_miss": None, "eq4_detection": None}
    s = min(IC2_SAMPLE_SIZE, n_records)
    p_miss = pad_miss_probability(n=n_records, k=k, s=s, q=q)
    return {"eq4_applies": True, "eq4_p_miss": p_miss, "eq4_detection": 1.0 - p_miss}


def summarize_cell(trials: list[dict], *, n_records: int, k: int, coupling: str) -> dict:
    n = len(trials)
    triggered = [trial for trial in trials if trial["replay_differs"]]
    n_t = len(triggered)
    true_refusal = sum(trial["outcome"] == "true_refusal" for trial in trials)
    unsafe = sum(trial["outcome"] == "UNSAFE" for trial in trials)
    needless = sum(trial["outcome"] == "needless_refusal" for trial in trials)
    correct = sum(trial["outcome"] == "correct_ship" for trial in trials)
    contract = sum(trial["outcome"] == "contract_refuse" for trial in trials)
    inconclusive = sum(trial["outcome"] == "INCONCLUSIVE" for trial in trials)
    caught = sum(trial["outcome"] == "true_refusal" for trial in triggered)
    layers: dict[str, int] = {}
    classes: dict[str, int] = {}
    q_values = [trial["q_trial"] for trial in trials if trial["q_trial"] is not None]
    for trial in trials:
        if trial["layer"]:
            layers[trial["layer"]] = layers.get(trial["layer"], 0) + 1
        classes[trial["diff_class"]] = classes.get(trial["diff_class"], 0) + 1
    q_mean = (sum(q_values) / len(q_values)) if q_values else None
    applies = coupling in {"presence", "order"} and q_mean is not None
    random_hits = sum(trial["layer"] == "random_pad" for trial in triggered)
    detection = (caught / n_t) if n_t else None
    random_rate = (random_hits / n_t) if n_t else None
    formula = eq4_block(n_records, k, q_mean, applies)
    gap = None
    if detection is not None and formula["eq4_detection"] is not None:
        gap = detection - formula["eq4_detection"]
    power_ok = all(trial["power_ok"] for trial in trials) and inconclusive == 0
    return {
        "n_trials": n,
        "n_triggered": n_t,
        "true_refusal": true_refusal,
        "UNSAFE": unsafe,
        "needless_refusal": needless,
        "correct_ship": correct,
        "contract_refuse": contract,
        "INCONCLUSIVE": inconclusive,
        "detection_rate": detection,
        "detection_wilson95": wilson(caught, n_t) if n_t else None,
        "random_pad_rate": random_rate,
        "random_pad_wilson95": wilson(random_hits, n_t) if n_t else None,
        "needless_refusal_rate": needless / n if n else None,
        "correct_ship_rate": correct / n if n else None,
        "layers": layers,
        "diff_classes": classes,
        "q_mean": q_mean,
        "q_trials": len(q_values),
        "eq4_gap_detection": gap,
        "power_ok": power_ok,
        "status": "OK" if power_ok else "INCONCLUSIVE",
        **formula,
    }


def prepare_inputs(root: Path, n_records: int, n_models: int) -> tuple[Path, Path, list[dict], list[dict]]:
    root.mkdir(parents=True, exist_ok=True)
    hmm = root / f"ref_{n_models}.hmm"
    fasta = root / f"q_{n_records}.fa"
    if not hmm.is_file():
        shim.write_reference(hmm, n_models)
    if not fasta.is_file():
        shim.write_queries(fasta, n_records)
    models = shim.parse_hmm(hmm.read_text())
    queries = shim.parse_fasta(fasta.read_text())
    return hmm, fasta, models, queries


def run_grid(
    *,
    mode: str,
    base_seed: int,
    n_records: int,
    n_models: int,
    cells: list[tuple[str, str, int, int, int]],
) -> dict:
    script = PIPELINE / "scripts" / "coupling_shim.py"
    scratch = SCRATCH / mode
    checkpoint = SCRATCH / f"{mode}.checkpoint.json"
    if scratch.exists():
        shutil.rmtree(scratch)
    hmm, fasta, models, queries = prepare_inputs(scratch, n_records, n_models)
    # One contract probe on the clean scorer, recorded so a later refusal is not a surprise.
    from acts.reference_formats import parse_reference, read_records

    clean_spec = {
        "coupling": "none",
        "k": 0,
        "seed": base_seed,
        "n_records": n_records,
        "n_models": n_models,
        "distance": 1,
        "affect": "",
    }
    apply_env(clean_spec)
    fitted = probe_fit(
        parse_reference(hmm),
        read_records(fasta),
        lambda recs, ents: shim.score_models(
            [
                {"name": entry.primary, "length": entry.length, "ga": shim.DEFAULT_GA, "raw": entry.raw}
                for entry in ents
            ],
            [{"name": rec.key, "sequence": rec.sequence} for rec in recs],
            z_override=None,
            cut_ga=True,
            spec=clean_spec,
        ),
    )
    overlap = sample_overlap(n_records)
    trials: list[dict] = []
    if checkpoint.is_file():
        trials = json.loads(checkpoint.read_text())
    done = {(row["cell"], row["seed"]) for row in trials}
    grouped: dict[str, list[dict]] = {}
    for row in trials:
        grouped.setdefault(row["cell"], []).append(row)
    for form_i, (form, coupling, distance, k, n_trials) in enumerate(cells):
        key = cell_key(form, distance, k)
        grouped.setdefault(key, [])
        for trial in range(n_trials):
            seed = trial_seed(base_seed, form_i, k, distance, trial)
            if (key, seed) in done:
                continue
            spec = {
                "coupling": coupling,
                "k": k,
                "seed": seed,
                "n_records": n_records,
                "n_models": n_models,
                "distance": distance,
                "affect": "",
            }
            payload = run_trial(
                script=script,
                hmm=hmm,
                fasta=fasta,
                models=models,
                queries=queries,
                spec=spec,
                trial_dir=scratch / "trial",
            )
            payload.update({"form": form, "coupling": coupling, "distance": distance, "k": k, "cell": key})
            grouped[key].append(payload)
            trials.append(payload)
            checkpoint.write_text(json.dumps(trials))
            print(
                f"{mode} {key} t={trial} {payload['decision']} {payload['outcome']} "
                f"layer={payload['layer']} class={payload['diff_class']} {payload['indicative_wall_s']}s",
                flush=True,
            )
    cell_summaries = {}
    for key, rows in grouped.items():
        coupling = rows[0]["coupling"]
        k = rows[0]["k"]
        cell_summaries[key] = {
            "form": rows[0]["form"],
            "coupling": coupling,
            "distance": rows[0]["distance"],
            "k": k,
            **summarize_cell(rows, n_records=n_records, k=k, coupling=coupling),
        }
    payload = {
        "system": "TARE",
        "mode": mode,
        "git_head": git_head(),
        "git_dirty_tracked": git_dirty_tracked(),
        "seed": base_seed,
        "n_records": n_records,
        "n_models": n_models,
        "shim": shim.VERSION,
        "python": platform.python_version(),
        "hmmer": hmmer_version(),
        "pin": PIN,
        "argv": argv_for(script, hmm, fasta),
        "check": {
            "sample_s": IC2_SAMPLE_SIZE,
            "sample_seed": IC2_SAMPLE_SEED,
            "pad_seeds": list(SEEDS),
            "audit_p": AUDIT_P,
            "audit_floor": AUDIT_FLOOR,
            "audit_seed": AUDIT_SEED,
            "probe_n": shim.PROBE_N,
            "probe_seed": shim.PROBE_SEED,
            **overlap,
        },
        "clean_contract": {"decision": fitted.decision, "reason": fitted.reason},
        "indicative_walls_are_not_evidence": True,
        "cells": cell_summaries,
        "trials": trials,
    }
    checkpoint.unlink(missing_ok=True)
    return payload


def pilot_cells() -> list[tuple[str, str, int, int, int]]:
    """Small grid. C0 is the known-good ship. C3 d=1 is the known-bad neighbor catch."""
    return [
        ("C0", "none", 0, 5, 3),
        ("C3", "order", 1, 5, 3),
        ("C1", "residues", 0, 5, 1),
        ("C2", "presence", 0, 5, 2),
        ("C3", "order", 5, 5, 1),
        ("C4", "global", 0, 5, 1),
    ]


def measured_cells() -> list[tuple[str, str, int, int, int]]:
    rows = []
    for form, coupling, distance in FORMS:
        for k in KS:
            rows.append((form, coupling, distance, k, 50))
    return rows


def write_result(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path}", flush=True)


def main(argv: list[str]) -> int:
    try:
        os.nice(10)
    except OSError:
        pass
    mode = argv[1] if len(argv) > 1 else "pilot"
    if mode == "pilot":
        payload = run_grid(
            mode="pilot",
            base_seed=20261111,
            n_records=400,
            n_models=500,
            cells=pilot_cells(),
        )
        write_result(OUT_DIR / "pilot.json", payload)
        return 0
    if mode == "measured":
        payload = run_grid(
            mode="measured",
            base_seed=20261112,
            n_records=2000,
            n_models=2500,
            cells=measured_cells(),
        )
        write_result(OUT_DIR / "measured.json", payload)
        return 0
    if mode == "smoke":
        payload = run_grid(
            mode="smoke",
            base_seed=20261111,
            n_records=400,
            n_models=500,
            cells=[
                ("C0", "none", 0, 5, 1),
                ("C3", "order", 1, 5, 1),
            ],
        )
        print(json.dumps(payload["cells"], indent=2, sort_keys=True))
        return 0
    print("usage: run_adversarial.py pilot|measured|smoke", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
