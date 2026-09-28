#!/usr/bin/env python3
"""Re-run probe_eval for batched vs singleton subset-invariance.

Does not overwrite results/probe_eval.json or probe_eval_audit.json.
Locked comparison: docs/INFERENCE_PROTOCOL.md addendum 2026-09-27.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "fixtures" / "probe_eval"))

from acts.fasta_memo import contract_path_for as fa_contract  # noqa: E402
from acts.strategies.record_memo import RecordMemo  # noqa: E402
from acts.vcf_memo import contract_path_for as vcf_contract  # noqa: E402
from run_probe_eval import (  # noqa: E402
    PROTOCOL,
    PROBE_NS,
    SEED,
    argv_for,
    first_probe,
    match_ok,
    plot,
    print_report,
    replay,
    stock,
    summarize,
    write_inputs,
    _jobs,
)

FIG_FOR = {
    "batched": ROOT / "results" / "figures" / "19_probe_eval_subset_batched.png",
    "singleton": ROOT / "results" / "figures" / "20_probe_eval_subset_singleton.png",
}
DEST_FOR = {
    "batched": ROOT / "results" / "probe_eval_subset_batched.json",
    "singleton": ROOT / "results" / "probe_eval_subset_singleton.json",
}


def _install_subset_mode(mode: str) -> None:
    import acts.infer_fasta as iff
    import acts.infer_vcf as iv

    if not getattr(iv, "_acts_subset_orig", None):
        iv._acts_subset_orig = iv.infer_contract
        iff._acts_subset_orig = iff.infer_table_contract

    def vcf_wrap(*args, **kwargs):
        kwargs["subset_mode"] = mode
        return iv._acts_subset_orig(*args, **kwargs)

    def fa_wrap(*args, **kwargs):
        kwargs["subset_mode"] = mode
        return iff._acts_subset_orig(*args, **kwargs)

    iv.infer_contract = vcf_wrap
    iff.infer_table_contract = fa_wrap


def _contract_stats(kind: str, cache: Path) -> dict:
    path = vcf_contract(cache) if kind == "vcf" else fa_contract(cache)
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text())
    return {
        "tool_calls": raw.get("tool_calls"),
        "subset_mode": raw.get("subset_mode"),
        "probe_n_contract": raw.get("probe_n"),
        "decision_contract": raw.get("decision"),
    }


def _run_one_memo(
    *,
    kind: str,
    cache: Path,
    inp: Path,
    out: Path,
    tool: list[str],
    probe_n: int,
    subset_mode: str,
) -> dict:
    _install_subset_mode(subset_mode)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    rec = RecordMemo(
        kind=kind,
        argv=tool,
        input_path=inp,
        out_dir=out,
        cache_path=cache,
        probe_n=probe_n,
        probe_seed=SEED,
        verify="audit",
    ).run()
    extra = dict(rec.extra)
    extra.update(_contract_stats(kind, cache))
    payload = {
        "decision": rec.decision,
        "reason": rec.reason,
        "extra": extra,
        "returncode": 0,
        "stderr_tail": "",
    }
    (out / "cell_result.json").write_text(json.dumps(payload) + "\n")
    return payload


def acts_run_memo(
    *,
    kind: str,
    cache: Path,
    inp: Path,
    out: Path,
    tool: list[str],
    probe_n: int,
    env: dict[str, str],
    subset_mode: str,
) -> dict:
    """Run one RecordMemo in a subprocess so F6 env and subset_mode do not race."""
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--cell-worker",
        "--subset-mode",
        subset_mode,
        "--kind",
        kind,
        "--cache",
        str(cache),
        "--input",
        str(inp),
        "--out",
        str(out),
        "--probe-n",
        str(probe_n),
        "--",
        *tool,
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    sidecar = out / "cell_result.json"
    if proc.returncode != 0 or not sidecar.is_file():
        return {
            "decision": "MISSING",
            "reason": (proc.stderr or "")[-400:],
            "extra": {},
            "returncode": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-400:],
        }
    rec = json.loads(sidecar.read_text())
    rec.setdefault("returncode", 0)
    rec.setdefault("stderr_tail", "")
    return rec


def run_cell(work: Path, kind: str, cls: str, p: float, probe_n: int, subset_mode: str) -> dict:
    cell = work / f"{kind}_{cls}_{p}_{probe_n}"
    cell.mkdir(parents=True, exist_ok=True)
    paths = write_inputs(cell / "data", kind, cls)
    tool = argv_for(kind, cls, p)
    cache = cell / "cache.jsonl"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["ACTS_PROBE_EVAL_ENV"] = "base"
    env["ACTS_PROBE_EVAL_SEED"] = str(SEED)

    d1 = acts_run_memo(
        kind=kind,
        cache=cache,
        inp=paths["in1"],
        out=cell / "r1",
        tool=tool,
        probe_n=probe_n,
        env=env,
        subset_mode=subset_mode,
    )
    d2 = {"decision": "SKIP", "reason": "input1 did not SHIP"}
    if d1["decision"] == "SHIP":
        d2 = acts_run_memo(
            kind=kind,
            cache=cache,
            inp=paths["in2"],
            out=cell / "r2",
            tool=tool,
            probe_n=probe_n,
            env=env,
            subset_mode=subset_mode,
        )

    env3 = dict(env)
    if cls in {"F6", "F6-env"}:
        env3["ACTS_PROBE_EVAL_ENV"] = "heldout"

    third = {"replayed": False, "equal_stock": None}
    unsafe_ship = False
    if d1["decision"] == "SHIP" and d2["decision"] == "SHIP":
        try:
            rebuilt = replay(kind, cache, paths["in3"], tool, cell / "replay")
            fresh = stock(kind, paths["in3"], tool, env3)
            eq = match_ok(kind, rebuilt, fresh, cache)
            third = {"replayed": True, "equal_stock": eq}
            unsafe_ship = not eq
        except Exception as exc:  # noqa: BLE001
            third = {"replayed": True, "equal_stock": False, "error": str(exc)[:300]}
            unsafe_ship = True

    return {
        "kind": kind,
        "class": cls,
        "p": p,
        "probe_n": probe_n,
        "unsafe": not cls.startswith("C"),
        "input1": d1,
        "input2": d2,
        "input3": third,
        "caught_by": first_probe(d1["decision"])
        if d1["decision"] != "SHIP"
        else (first_probe(d2.get("decision", "")) if d2.get("decision") == "REFUSE_AUDIT" else ""),
        "probe_caught": d1["decision"] != "SHIP",
        "audit_caught": d1["decision"] == "SHIP" and d2.get("decision") == "REFUSE_AUDIT",
        "unsafe_ship": unsafe_ship,
        "false_refuse": cls.startswith("C") and (d1["decision"] != "SHIP" or d2.get("decision") != "SHIP"),
        "tool_calls": (d1.get("extra") or {}).get("tool_calls"),
        "subset_mode": (d1.get("extra") or {}).get("subset_mode"),
    }


def tool_call_summary(rows: list[dict]) -> dict:
    by_n: dict[str, dict] = {}
    for n in PROBE_NS:
        at = [r for r in rows if r["probe_n"] == n and r.get("tool_calls") is not None]
        if not at:
            by_n[str(n)] = {"n": 0}
            continue
        vals = [int(r["tool_calls"]) for r in at]
        by_n[str(n)] = {
            "n": len(vals),
            "mean": sum(vals) / len(vals),
            "min": min(vals),
            "max": max(vals),
        }
    f3 = {}
    for n in PROBE_NS:
        cells = [r for r in rows if r["class"] == "F3" and r["probe_n"] == n]
        f3[str(n)] = {
            "n": len(cells),
            "caught_input1": sum(1 for r in cells if r["input1"]["decision"] != "SHIP"),
            "unsafe_ship": sum(1 for r in cells if r["unsafe_ship"]),
            "by_p": {
                str(p): {
                    "n": len(at),
                    "caught": sum(1 for r in at if r["input1"]["decision"] != "SHIP"),
                    "unsafe_ship": sum(1 for r in at if r["unsafe_ship"]),
                }
                for p in (1.0, 0.1, 0.01, 0.001)
                for at in [[r for r in cells if r["p"] == p]]
            },
        }
    return {"tool_calls_by_probe_n": by_n, "f3": f3}


def _write_payload(
    dest: Path, rows: list[dict], work: Path, fig: Path, mode: str, *, finished: bool
) -> dict:
    summary = summarize(rows)
    summary.update(tool_call_summary(rows))
    if finished and rows:
        plot(rows, fig)
    payload = {
        "protocol": PROTOCOL,
        "inference_addendum": "pipeline/docs/INFERENCE_PROTOCOL.md#addendum-2026-09-27-batched-subset-invariance",
        "git_protocol": "427fcbb",
        "verify": "audit",
        "subset_mode": mode,
        "seed": SEED,
        "probe_ns": list(PROBE_NS),
        "finished_utc": datetime.now(timezone.utc).isoformat() if finished else None,
        "n_done": len(rows),
        "report": summary,
        "rows": rows,
        "figure": str(fig.relative_to(ROOT)),
        "work": str(work),
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def run_mode(mode: str) -> dict:
    work = Path(tempfile.mkdtemp(prefix=f"acts_probe_subset_{mode}_"))
    dest = DEST_FOR[mode]
    fig = FIG_FOR[mode]
    jobs = _jobs()
    rows: list[dict] = []
    workers = min(4, os.cpu_count() or 2)
    print(f"mode={mode} cells={len(jobs)} workers={workers} work={work}", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(run_cell, work, kind, cls, p, n, mode): (kind, cls, p, n)
            for kind, cls, p, n in jobs
        }
        for i, fut in enumerate(as_completed(futs), 1):
            kind, cls, p, n = futs[fut]
            row = fut.result()
            rows.append(row)
            tag = row["caught_by"] or row["input1"]["decision"]
            print(
                f"[{mode} {i}/{len(jobs)}] {kind} {cls} p={p} n={n} → {tag} "
                f"calls={row.get('tool_calls')} unsafe_ship={row['unsafe_ship']}",
                flush=True,
            )
            if i % 8 == 0 or i == len(jobs):
                _write_payload(dest, rows, work, fig, mode, finished=False)

    rows.sort(key=lambda r: (r["class"], r["kind"], r["p"], r["probe_n"]))
    payload = _write_payload(dest, rows, work, fig, mode, finished=True)
    print_report(payload["report"])
    print("tool_calls_by_probe_n", payload["report"]["tool_calls_by_probe_n"])
    print("F3", payload["report"]["f3"])
    print(f"wrote {dest}")
    print(f"wrote {payload['figure']}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cell-worker", action="store_true")
    parser.add_argument("--mode", choices=("batched", "singleton", "both"), default="both")
    parser.add_argument("--subset-mode", choices=("batched", "singleton"), default="batched")
    parser.add_argument("--kind")
    parser.add_argument("--cache")
    parser.add_argument("--input")
    parser.add_argument("--out")
    parser.add_argument("--probe-n", type=int, default=500)
    args, rest = parser.parse_known_args()
    if rest[:1] == ["--"]:
        rest = rest[1:]
    if args.cell_worker:
        _run_one_memo(
            kind=args.kind,
            cache=Path(args.cache),
            inp=Path(args.input),
            out=Path(args.out),
            tool=rest,
            probe_n=args.probe_n,
            subset_mode=args.subset_mode,
        )
        return 0
    modes = ("batched", "singleton") if args.mode == "both" else (args.mode,)
    for mode in modes:
        run_mode(mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
