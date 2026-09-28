#!/usr/bin/env python3
"""Measure how often inference probes miss unsafe tools.

Locked by docs/PROBE_EVAL_PROTOCOL.md (b4c878f). Local only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
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
        "audit",
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


def run_cell(work: Path, kind: str, cls: str, p: float, probe_n: int) -> dict:
    cell = work / f"{kind}_{cls}_{p}_{probe_n}"
    cell.mkdir(parents=True, exist_ok=True)
    paths = write_inputs(cell / "data", kind, cls)
    tool = argv_for(kind, cls, p)
    cache = cell / "cache.jsonl"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["ACTS_PROBE_EVAL_ENV"] = "base"
    env["ACTS_PROBE_EVAL_SEED"] = str(SEED)

    d1 = acts_run(kind=kind, cache=cache, inp=paths["in1"], out=cell / "r1", tool=tool, probe_n=probe_n, env=env)
    d2 = {"decision": "SKIP", "reason": "input1 did not SHIP"}
    if d1["decision"] == "SHIP":
        d2 = acts_run(kind=kind, cache=cache, inp=paths["in2"], out=cell / "r2", tool=tool, probe_n=probe_n, env=env)

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
    }


def summarize(rows: list[dict]) -> dict:
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
    for n in PROBE_NS:
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


def _jobs() -> list[tuple[str, str, float, int]]:
    jobs: list[tuple[str, str, float, int]] = []
    for kind in FORMATS:
        for cls in CLASSES:
            for p in FREQS:
                for n in PROBE_NS:
                    jobs.append((kind, cls, p, n))
    for n in PROBE_NS:
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


def main() -> int:
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


if __name__ == "__main__":
    raise SystemExit(main())
