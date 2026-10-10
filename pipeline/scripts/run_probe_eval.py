#!/usr/bin/env python3
"""Measure how often inference probes miss unsafe tools.

Locked by docs/PROBE_EVAL_PROTOCOL.md (b4c878f). Local only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "fixtures" / "probe_eval"))

from acts.cache import RecordCache
from acts.fasta import read_fasta
from acts.fasta_memo import cached_search, contract_path_for as fa_contract
from acts.infer_fasta import TableContract, run_table_tool
from acts.infer_vcf import RecordContract, run_vcf_tool
from acts.table import tables_match
from acts.vcf import bodies_equal
from acts.vcf_memo import cached_annotate, contract_path_for as vcf_contract, read_vcf_parts
from suite import (  # type: ignore
    CLASSES,
    CONTROLS,
    FORMATS,
    FREQS,
    N_REC,
    SEED,
    hidden_cfg_path,
    write_fasta,
    write_vcf,
)

PY = sys.executable
_STOCK_LOCK = threading.Lock()
TOOL = ROOT / "fixtures" / "probe_eval" / "tool.py"
PROTOCOL = "pipeline/docs/PROBE_EVAL_PROTOCOL.md"
PROBE_NS = (50, 200, 500, 2000)


def argv_for(kind: str, cls: str, p: float) -> list[str]:
    return [PY, str(TOOL), kind, cls, str(p), "{input}"]


def write_inputs(folder: Path, kind: str, cls: str) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    idx1 = list(range(N_REC))
    # Same length as input 1: 2000 overlapping keys + 500 new (F3 MATCH needs equal N).
    idx2 = list(range(200, 2200)) + list(range(N_REC, N_REC + 500))
    writer = write_vcf if kind == "vcf" else write_fasta
    paths = {
        "in1": writer(folder / f"{kind}_1.{ 'vcf' if kind == 'vcf' else 'fa'}", idx1),
        "in2": writer(folder / f"{kind}_2.{ 'vcf' if kind == 'vcf' else 'fa'}", idx2),
    }
    if cls == "F3":
        paths["in3"] = writer(folder / f"{kind}_3.{ 'vcf' if kind == 'vcf' else 'fa'}", idx1[:100])
    elif cls in {"F4", "F5"}:
        suffix = "_held"
        if kind == "vcf":
            paths["in3"] = write_vcf(folder / "vcf_3.vcf", idx1[:200], id_suffix=suffix)
        else:
            paths["in3"] = write_fasta(folder / "fa_3.fa", idx1[:200], desc_suffix=suffix)
    else:
        paths["in3"] = writer(folder / f"{kind}_3.{ 'vcf' if kind == 'vcf' else 'fa'}", idx1[:200])
    hidden_cfg_path(paths["in1"]).write_text("base\n")
    hidden_cfg_path(paths["in2"]).write_text("base\n")
    hidden_cfg_path(paths["in3"]).write_text("heldout\n" if cls == "F6-file" else "base\n")
    return paths


def parse_decision(out_dir: Path) -> dict:
    path = out_dir / "decision.txt"
    rec = {"decision": "MISSING", "reason": "", "extra": {}}
    if not path.is_file():
        return rec
    extra = {}
    for line in path.read_text().splitlines():
        if line.startswith("decision:"):
            rec["decision"] = line.split(":", 1)[1].strip()
        elif line.startswith("why:"):
            rec["reason"] = line.split(":", 1)[1].strip()
        elif ":" in line and not line.startswith("strategy:"):
            k, v = line.split(":", 1)
            extra[k.strip()] = v.strip()
    rec["extra"] = extra
    return rec


def acts_run(
    *,
    kind: str,
    cache: Path,
    inp: Path,
    out: Path,
    tool: list[str],
    probe_n: int,
    env: dict[str, str],
    verify: str = "audit",
) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    cmd = [
        PY,
        "-m",
        "acts",
        "run",
        "--strategy",
        "record_memo",
        "--kind",
        kind,
        "--probe-n",
        str(probe_n),
        "--verify",
        verify,
        "--cache",
        str(cache),
        "--input",
        str(inp),
        "-o",
        str(out),
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
    rec = parse_decision(out)
    rec["returncode"] = proc.returncode
    rec["stderr_tail"] = (proc.stderr or "")[-400:]
    return rec


def replay(kind: str, cache: Path, inp: Path, tool: list[str], work: Path) -> str:
    work.mkdir(parents=True, exist_ok=True)
    if kind == "vcf":
        header, body = read_vcf_parts(inp)
        contract = RecordContract.load(vcf_contract(cache))
        memo = RecordCache(cache, argv=tool, kind="vcf", extra_files=contract.traced_files)
        rebuilt, _ = cached_annotate(header, body, memo, contract, tool, work)
        return rebuilt
    recs = read_fasta(inp)
    contract = TableContract.load(fa_contract(cache))
    memo = RecordCache(cache, argv=tool, kind="fasta", extra_files=contract.traced_files)
    rebuilt, _ = cached_search(recs, memo, contract, tool, work)
    return rebuilt


def stock(kind: str, inp: Path, tool: list[str], env: dict[str, str]) -> str:
    old = os.environ.get("ACTS_PROBE_EVAL_ENV")
    os.environ["ACTS_PROBE_EVAL_ENV"] = env.get("ACTS_PROBE_EVAL_ENV", "base")
    try:
        if kind == "vcf":
            return run_vcf_tool(tool, inp)
        return run_table_tool(tool, inp)
    finally:
        if old is None:
            os.environ.pop("ACTS_PROBE_EVAL_ENV", None)
        else:
            os.environ["ACTS_PROBE_EVAL_ENV"] = old


def match_ok(kind: str, rebuilt: str, fresh: str, cache: Path) -> bool:
    if kind == "vcf":
        return bodies_equal(rebuilt, fresh)
    contract = TableContract.load(fa_contract(cache))
    return tables_match(rebuilt, fresh, contract.match, match_ws=contract.match_ws)


def first_probe(decision: str) -> str:
    mapping = {
        "REFUSE_NONDETERMINISTIC": "determinism",
        "REFUSE_NEIGHBORS": "shuffle",
        "REFUSE_GLOBAL": "subset",
        "REFUSE_AMBIGUOUS": "perturbation",
        "REFUSE_MATCH": "match",
        "REFUSE_IDENTITY": "identity",
        "REFUSE_AUDIT": "audit",
        "SHIP": "",
    }
    return mapping.get(decision, decision)


def run_cell(
    work: Path,
    kind: str,
    cls: str,
    p: float,
    probe_n: int,
    *,
    verify: str = "audit",
    subset_mode: str | None = None,
) -> dict:
    cell = work / f"{kind}_{cls}_{p}_{probe_n}"
    cell.mkdir(parents=True, exist_ok=True)
    paths = write_inputs(cell / "data", kind, cls)
    tool = argv_for(kind, cls, p)
    cache = cell / "cache.jsonl"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["ACTS_PROBE_EVAL_ENV"] = "base"
    env["ACTS_PROBE_EVAL_SEED"] = str(SEED)

    if subset_mode is None:
        d1 = acts_run(
            kind=kind, cache=cache, inp=paths["in1"], out=cell / "r1",
            tool=tool, probe_n=probe_n, env=env, verify=verify,
        )
    else:
        d1 = acts_run_subset(
            kind=kind, cache=cache, inp=paths["in1"], out=cell / "r1",
            tool=tool, probe_n=probe_n, env=env, verify=verify, subset_mode=subset_mode,
        )
    d2 = {"decision": "SKIP", "reason": "input1 did not SHIP"}
    if d1["decision"] == "SHIP":
        if subset_mode is None:
            d2 = acts_run(
                kind=kind, cache=cache, inp=paths["in2"], out=cell / "r2",
                tool=tool, probe_n=probe_n, env=env, verify=verify,
            )
        else:
            d2 = acts_run_subset(
                kind=kind, cache=cache, inp=paths["in2"], out=cell / "r2",
                tool=tool, probe_n=probe_n, env=env, verify=verify, subset_mode=subset_mode,
            )

    env3 = dict(env)
    if cls in {"F6", "F6-env"}:
        env3["ACTS_PROBE_EVAL_ENV"] = "heldout"

    third = {"replayed": False, "equal_stock": None}
    unsafe_ship = False
    if d1["decision"] == "SHIP" and d2["decision"] == "SHIP":
        try:
            rebuilt = replay(kind, cache, paths["in3"], tool, cell / "replay")
            if subset_mode is None:
                fresh = stock(kind, paths["in3"], tool, env3)
            else:
                with _STOCK_LOCK:
                    fresh = stock(kind, paths["in3"], tool, env3)
            eq = match_ok(kind, rebuilt, fresh, cache)
            third = {"replayed": True, "equal_stock": eq}
            unsafe_ship = not eq
        except Exception as exc:  # noqa: BLE001
            third = {"replayed": True, "equal_stock": False, "error": str(exc)[:300]}
            unsafe_ship = True

    row = {
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
    }
    if subset_mode is not None:
        extra = d1.get("extra") or {}
        row["tool_calls"] = extra.get("tool_calls")
        row["subset_mode"] = extra.get("subset_mode")
        row["probe_n_contract"] = extra.get("probe_n_contract")
    return row


def summarize(rows: list[dict], probe_ns: tuple[int, ...] = PROBE_NS) -> dict:
    unsafe = [r for r in rows if r["unsafe"]]
    controls = [r for r in rows if not r["unsafe"]]
    ships = [r for r in unsafe if r["unsafe_ship"]]
    per_class: dict[str, dict] = {}
    for cls in CLASSES:
        sub = [r for r in unsafe if r["class"] == cls]
        per_class[cls] = {
            "n": len(sub),
            "unsafe_ship": sum(1 for r in sub if r["unsafe_ship"]),
            "caught_input1": sum(1 for r in sub if r["input1"]["decision"] != "SHIP"),
            "by_probe": dict(sum_counter(r["caught_by"] for r in sub if r["caught_by"])),
            "by_p": {
                str(p): {
                    "n": len(at),
                    "caught": sum(1 for r in at if r["input1"]["decision"] != "SHIP"),
                    "unsafe_ship": sum(1 for r in at if r["unsafe_ship"]),
                }
                for p in FREQS
                for at in [[r for r in sub if r["p"] == p]]
            },
        }

    catch_p = {}
    f6_limit = {"F6-env"}
    for p in FREQS:
        at = [r for r in unsafe if r["p"] == p and r["class"] not in f6_limit]
        catch_p[str(p)] = {
            "n": len(at),
            "probe_caught": sum(1 for r in at if r.get("probe_caught")),
            "audit_caught": sum(1 for r in at if r.get("audit_caught")),
            "caught": sum(1 for r in at if r.get("probe_caught") or r.get("audit_caught")),
        }

    probe_counts = sum_counter(r["caught_by"] for r in unsafe if r["caught_by"])
    refused = sum(1 for r in unsafe if r.get("probe_caught") or r.get("audit_caught"))
    in_scope = [r for r in unsafe if r["class"] != "F6-env"]

    reliable = {}
    for n in probe_ns:
        hit = None
        for p in sorted(FREQS, reverse=True):
            cells = [
                r
                for r in unsafe
                if r["probe_n"] == n
                and r["p"] == p
                and r["class"] not in {"F6-env", "F6-file"}
            ]
            if cells and all(r.get("probe_caught") or r.get("audit_caught") for r in cells):
                hit = p
        reliable[str(n)] = hit if hit is not None else "none"

    return {
        "n_unsafe_cells": len(unsafe),
        "unsafe_ship_n": len(ships),
        "unsafe_ship_rate": (len(ships) / len(unsafe)) if unsafe else None,
        "in_scope_n": len(in_scope),
        "in_scope_unsafe_ship_n": sum(1 for r in in_scope if r["unsafe_ship"]),
        "false_refuse_n": sum(1 for r in controls if r["false_refuse"]),
        "false_refuse_rate": (
            sum(1 for r in controls if r["false_refuse"]) / len(controls) if controls else None
        ),
        "probe_only_catch": sum(1 for r in unsafe if r.get("probe_caught")),
        "audit_only_catch": sum(1 for r in unsafe if r.get("audit_caught")),
        "catch_rate_per_probe": {
            k: (v / refused) if refused else 0.0 for k, v in probe_counts.items()
        },
        "catch_rate_per_frequency": {
            p: ((row["caught"] / row["n"]) if row["n"] else None) for p, row in catch_p.items()
        },
        "per_class": per_class,
        "smallest_p_reliably_caught": reliable,
        "f6_note": "F6-env is outside the method guarantee. F6-file is caught only with Linux tracing.",
    }


def sum_counter(values) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for v in values:
        if v:
            out[v] += 1
    return dict(out)


def plot(rows: list[dict], dest: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    dest.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex=True, sharey=True)
    axes = axes.ravel()
    for ax, n in zip(axes, PROBE_NS):
        for cls in CLASSES:
            xs, ys = [], []
            for p in FREQS:
                at = [r for r in rows if r["class"] == cls and r["p"] == p and r["probe_n"] == n]
                if not at:
                    continue
                xs.append(p)
                ys.append(sum(1 for r in at if r["input1"]["decision"] != "SHIP") / len(at))
            ax.plot(xs, ys, marker="o", label=cls)
        ax.set_xscale("log")
        ax.set_title(f"probe_n={n}")
        ax.set_ylim(-0.05, 1.05)
        ax.set_ylabel("catch rate (input 1 refuse)")
        ax.set_xlabel("fault frequency p")
        ax.grid(True, alpha=0.3)
    axes[0].legend(ncol=4, fontsize=8)
    fig.suptitle("Probe catch rate vs fault frequency")
    fig.tight_layout()
    fig.savefig(dest, dpi=140)
    plt.close(fig)


def print_report(summary: dict) -> None:
    print("=== probe eval ===")
    print(f"unsafe-ship {summary['unsafe_ship_n']}/{summary['n_unsafe_cells']} "
          f"rate={summary['unsafe_ship_rate']}")
    print(f"false-refuse {summary['false_refuse_n']} rate={summary['false_refuse_rate']}")
    print("catch per probe", summary["catch_rate_per_probe"])
    print("catch per p", summary["catch_rate_per_frequency"])
    print("smallest p reliably caught", summary["smallest_p_reliably_caught"])
    print(summary["f6_note"])
    for cls, row in summary["per_class"].items():
        print(f"  {cls}: caught {row['caught_input1']}/{row['n']} "
              f"unsafe_ship {row['unsafe_ship']} probes={row['by_probe']}")


def _jobs(probe_ns: tuple[int, ...] = PROBE_NS) -> list[tuple[str, str, float, int]]:
    jobs: list[tuple[str, str, float, int]] = []
    for kind in FORMATS:
        for cls in CLASSES:
            for p in FREQS:
                for n in probe_ns:
                    jobs.append((kind, cls, p, n))
    for n in probe_ns:
        for cls in CONTROLS:
            kind = "vcf" if cls in {"C1", "C2", "C3"} else "fasta"
            jobs.append((kind, cls, 0.0, n))
    return jobs


def _write_payload(dest: Path, rows: list[dict], work: Path, *, finished: bool) -> dict:
    summary = summarize(rows)
    fig = ROOT / "results" / "figures" / "18_probe_eval_audit_catch.png"
    if finished and rows:
        plot(rows, fig)
    payload = {
        "protocol": PROTOCOL,
        "git_protocol": "4679264",
        "verify": "audit",
        "seed": SEED,
        "n_rec": N_REC,
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


def _run_default() -> int:
    work = Path(tempfile.mkdtemp(prefix="acts_probe_eval_"))
    dest = ROOT / "results" / "probe_eval_audit.json"
    jobs = _jobs()
    rows: list[dict] = []
    workers = min(4, os.cpu_count() or 2)
    print(f"cells={len(jobs)} workers={workers} work={work}", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(run_cell, work, kind, cls, p, n): (kind, cls, p, n)
            for kind, cls, p, n in jobs
        }
        for i, fut in enumerate(as_completed(futs), 1):
            kind, cls, p, n = futs[fut]
            row = fut.result()
            rows.append(row)
            tag = row["caught_by"] or row["input1"]["decision"]
            print(
                f"[{i}/{len(jobs)}] {kind} {cls} p={p} n={n} → {tag} "
                f"unsafe_ship={row['unsafe_ship']}",
                flush=True,
            )
            if i % 8 == 0 or i == len(jobs):
                _write_payload(dest, rows, work, finished=False)

    rows.sort(key=lambda r: (r["class"], r["kind"], r["p"], r["probe_n"]))
    payload = _write_payload(dest, rows, work, finished=True)
    print_report(payload["report"])
    print(f"wrote {dest}")
    print(f"wrote {payload['figure']}")
    return 0


OUT_OF_SCOPE = {"F6", "F6-env", "F6-file"}
LOCKED_OUT = ROOT / "results" / "probe_eval_audit.json"
LOCKED_FIG = ROOT / "results" / "figures" / "18_probe_eval_audit_catch.png"


def _install_subset_mode(mode: str) -> None:
    import acts.infer_fasta as iff
    import acts.infer_vcf as iv

    if getattr(iv, "_acts_n8_subset_orig", None) is None:
        iv._acts_n8_subset_orig = iv.infer_contract
        iff._acts_n8_subset_orig = iff.infer_table_contract

    def vcf_wrap(*args, **kwargs):
        kwargs["subset_mode"] = mode
        return iv._acts_n8_subset_orig(*args, **kwargs)

    def fa_wrap(*args, **kwargs):
        kwargs["subset_mode"] = mode
        return iff._acts_n8_subset_orig(*args, **kwargs)

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
    }


def _cell_worker(args: argparse.Namespace, tool: list[str]) -> int:
    if args.subset_mode not in {"singleton", "batched"}:
        print("cell-worker needs --subset-mode", file=sys.stderr)
        return 2
    if args.verify not in {"audit", "full"}:
        print("cell-worker verify must be audit or full", file=sys.stderr)
        return 2
    _install_subset_mode(args.subset_mode)
    from acts.strategies.record_memo import RecordMemo

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    try:
        rec = RecordMemo(
            kind=args.kind,
            argv=tool,
            input_path=Path(args.input),
            out_dir=out,
            cache_path=Path(args.cache),
            probe_n=args.probe_n,
            probe_seed=SEED,
            verify=args.verify,
        ).run()
        extra = dict(rec.extra)
        extra.update(_contract_stats(args.kind, Path(args.cache)))
        payload = {
            "decision": rec.decision,
            "reason": rec.reason,
            "extra": extra,
            "returncode": 0,
            "stderr_tail": "",
        }
    except Exception as exc:  # noqa: BLE001
        payload = {
            "decision": "MISSING",
            "reason": str(exc)[:400],
            "extra": {},
            "returncode": 1,
            "stderr_tail": str(exc)[:400],
        }
    (out / "cell_result.json").write_text(json.dumps(payload, default=str) + "\n")
    return 0 if payload["decision"] != "MISSING" else 1


def acts_run_subset(
    *,
    kind: str,
    cache: Path,
    inp: Path,
    out: Path,
    tool: list[str],
    probe_n: int,
    env: dict[str, str],
    verify: str,
    subset_mode: str,
) -> dict:
    cmd = [
        PY,
        str(Path(__file__).resolve()),
        "--cell-worker",
        "--subset-mode",
        subset_mode,
        "--verify",
        verify,
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
    if not sidecar.is_file():
        return {
            "decision": "MISSING",
            "reason": (proc.stderr or proc.stdout or "")[-400:],
            "extra": {},
            "returncode": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-400:],
        }
    rec = json.loads(sidecar.read_text())
    rec.setdefault("returncode", proc.returncode)
    rec.setdefault("stderr_tail", (proc.stderr or "")[-400:])
    return rec


def canonical_inscope(rows: list[dict]) -> dict:
    """Excl. F6-env and F6-file. The script report.in_scope_* still drops F6-env only."""
    unsafe = [r for r in rows if r["unsafe"] and r["class"] not in OUT_OF_SCOPE]
    controls = [r for r in rows if not r["unsafe"]]
    ships = [r for r in unsafe if r["unsafe_ship"]]
    per_class: dict[str, dict] = {}
    for cls in CLASSES:
        if cls in OUT_OF_SCOPE:
            continue
        sub = [r for r in unsafe if r["class"] == cls]
        per_class[cls] = {
            "n": len(sub),
            "input1_refuse": sum(1 for r in sub if r["input1"]["decision"] != "SHIP"),
            "audit_only": sum(1 for r in sub if r.get("audit_caught")),
            "match_catch": sum(1 for r in sub if r.get("caught_by") == "match"),
            "unsafe_ship": sum(1 for r in sub if r["unsafe_ship"]),
            "by_probe": dict(sum_counter(r["caught_by"] for r in sub if r["caught_by"])),
        }
    return {
        "definition": "excl. F6-env and F6-file",
        "n": len(unsafe),
        "unsafe_ship_n": len(ships),
        "false_refuse_n": sum(1 for r in controls if r["false_refuse"]),
        "false_refuse_denom": len(controls),
        "per_class": per_class,
        "unsafe_ship_cells": [
            {
                "kind": r["kind"],
                "class": r["class"],
                "p": r["p"],
                "probe_n": r["probe_n"],
                "input1": r["input1"].get("decision"),
                "input2": r["input2"].get("decision"),
                "caught_by": r.get("caught_by"),
                "subset_mode": r.get("subset_mode"),
                "probe_n_contract": r.get("probe_n_contract"),
                "tool_calls": r.get("tool_calls"),
            }
            for r in ships
        ],
    }


def _schedule_check(rows: list[dict], subset_mode: str) -> dict:
    bad_mode = [
        f"{r['kind']} {r['class']} p={r['p']} subset_mode={r.get('subset_mode')}"
        for r in rows
        if r.get("subset_mode") != subset_mode
    ]
    ship_bad_n = [
        f"{r['kind']} {r['class']} p={r['p']} probe_n_contract={r.get('probe_n_contract')}"
        for r in rows
        if r["input1"]["decision"] == "SHIP" and r.get("probe_n_contract") != r["probe_n"]
    ]
    calls = [r.get("tool_calls") for r in rows if r.get("tool_calls") is not None]
    return {
        "subset_mode_mismatches": bad_mode,
        "ship_probe_n_mismatches": ship_bad_n,
        "tool_calls_min": min(calls) if calls else None,
        "tool_calls_max": max(calls) if calls else None,
    }


def _run_one_verify(
    *,
    verify: str,
    probe_ns: tuple[int, ...],
    subset_mode: str,
    work: Path,
) -> dict:
    jobs = _jobs(probe_ns)
    rows: list[dict] = []
    workers = min(4, os.cpu_count() or 2)
    print(f"verify={verify} cells={len(jobs)} workers={workers}", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(
                run_cell, work, kind, cls, p, n, verify=verify, subset_mode=subset_mode
            ): (kind, cls, p, n)
            for kind, cls, p, n in jobs
        }
        for i, fut in enumerate(as_completed(futs), 1):
            kind, cls, p, n = futs[fut]
            row = fut.result()
            rows.append(row)
            tag = row["caught_by"] or row["input1"]["decision"]
            print(
                f"[{verify} {i}/{len(jobs)}] {kind} {cls} p={p} n={n} → {tag} "
                f"calls={row.get('tool_calls')} unsafe_ship={row['unsafe_ship']}",
                flush=True,
            )
    rows.sort(key=lambda r: (r["class"], r["kind"], r["p"], r["probe_n"]))
    summary = summarize(rows, probe_ns)
    canon = canonical_inscope(rows)
    print(
        f"=== {verify} canonical in-scope "
        f"{canon['unsafe_ship_n']}/{canon['n']} "
        f"false-refuse {canon['false_refuse_n']}/{canon['false_refuse_denom']}",
        flush=True,
    )
    print_report(summary)
    return {
        "verify": verify,
        "audit_p": 0.02 if verify == "audit" else 0.0,
        "report": summary,
        "canonical": canon,
        "schedule": _schedule_check(rows, subset_mode),
        "rows": rows,
    }


def _run_flagged(args: argparse.Namespace) -> int:
    from acts.predict import inference_call_sizes
    from acts.provenance import provenance

    probe_ns = tuple(int(part) for part in args.probe_ns.split(",") if part.strip())
    if not probe_ns or any(n <= 0 for n in probe_ns):
        print("probe-ns must be positive integers", file=sys.stderr)
        return 2
    if args.subset_mode is None:
        print("a flagged run needs --subset-mode", file=sys.stderr)
        return 2
    dest = args.out.resolve()
    if dest == LOCKED_OUT.resolve() or dest == (ROOT / "results" / "probe_eval.json").resolve():
        print(f"refusing to overwrite {dest}", file=sys.stderr)
        return 2
    if not args.no_figure:
        print(
            f"a flagged run does not write {LOCKED_FIG.name}; pass --no-figure",
            file=sys.stderr,
        )
        return 2
    verifies = ("full", "audit") if args.verify == "both" else (args.verify,)
    work = Path(tempfile.mkdtemp(prefix="acts_probe_eval_n8_"))
    columns = {}
    for verify in verifies:
        columns[verify] = _run_one_verify(
            verify=verify,
            probe_ns=probe_ns,
            subset_mode=args.subset_mode,
            work=work / verify,
        )
    priced = {
        str(n): inference_call_sizes(
            "fasta", N_REC, probe_n=n, subset_mode=args.subset_mode
        )
        for n in probe_ns
    }
    payload = {
        "protocol": PROTOCOL,
        "addendum": "2026-10-10",
        "label": "MEASURED",
        "probe_ns": list(probe_ns),
        "subset_mode": args.subset_mode,
        "priced_call_sizes": priced,
        "priced_call_n": {k: len(v) for k, v in priced.items()},
        "priced_call_note": (
            "PROJECTED schedule from acts.predict.inference_call_sizes. "
            "Row tool_calls are MEASURED and are not rewritten to this length."
        ),
        "seed": SEED,
        "n_rec": N_REC,
        "audit_q": 0.02,
        "canonical_denominator_note": (
            "Locked four sizes stay 224. This file's in-scope denominator is "
            "7 classes x 4 frequencies x 2 formats x len(probe_ns)."
        ),
        "provenance": provenance(),
        "work": str(work),
        "columns": columns,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"wrote {dest}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-worker", action="store_true")
    parser.add_argument("--probe-ns", default=None)
    parser.add_argument("--verify", choices=("audit", "full", "both"), default="audit")
    parser.add_argument("--subset-mode", choices=("batched", "singleton"), default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--no-figure", action="store_true")
    parser.add_argument("--kind", default=None)
    parser.add_argument("--cache", default=None)
    parser.add_argument("--input", default=None)
    parser.add_argument("--probe-n", type=int, default=None)
    args, rest = parser.parse_known_args(argv)
    if rest[:1] == ["--"]:
        rest = rest[1:]
    if args.cell_worker:
        return _cell_worker(args, rest)
    deviant = any(
        (
            args.probe_ns is not None,
            args.verify != "audit",
            args.subset_mode is not None,
            args.out is not None,
            args.no_figure,
        )
    )
    if not deviant:
        return _run_default()
    if args.out is None:
        print("refusing to overwrite probe_eval_audit.json; pass --out", file=sys.stderr)
        return 2
    if args.probe_ns is None:
        print("a flagged run needs --probe-ns", file=sys.stderr)
        return 2
    return _run_flagged(args)


if __name__ == "__main__":
    raise SystemExit(main())
