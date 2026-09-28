#!/usr/bin/env python3
"""Isolated arm-L run: task file, pluggable agent CLI, budget, EGAS host loop.

No live model unless the config CLI is one and Josh has set model_id.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from egas.contract import load_contract  # noqa: E402
from egas.llm_arm import (  # noqa: E402
    Budget,
    WallClock,
    budget_ok,
    finish_host,
    isolate_source,
    parse_tokens,
    prepare_host,
    smoke_dev_oracle,
    snapshot_tree,
    t1_t3_plan,
    unified_diff,
    write_json,
    write_task_file,
    write_toml,
)
from egas.profile_io import load_profile  # noqa: E402


def _load_cfg(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def _budget(cfg: dict, *, hours: float | None, tokens: int | None, model_id: str | None) -> Budget:
    b = cfg.get("budget", {})
    cap = b.get("dollar_cap")
    return Budget(
        hours=float(hours if hours is not None else b.get("hours", 8)),
        tokens=int(tokens if tokens is not None else b.get("tokens", 2_000_000)),
        n_runs=int(b.get("n_runs", 3)),
        model_id=str(model_id or b.get("model_id", "TBD")),
        dollar_cap=float(cap) if cap not in (None, "") else None,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="LLM arm L harness. No live model unless the config CLI is one."
    )
    p.add_argument("--config", type=Path, default=ROOT / "fixtures/llm_arm/agent.toml")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument(
        "--patch",
        choices=("safe", "bad"),
        default="safe",
        help="Fixture fake-agent only. Ignored by a real CLI that does not use {patch}.",
    )
    p.add_argument(
        "--allow-fake",
        action="store_true",
        help="Permit model_id=TBD (scripted fake agent). Required for dry-run.",
    )
    p.add_argument("--hours", type=float, default=None)
    p.add_argument("--tokens", type=int, default=None)
    p.add_argument("--model-id", default=None)
    p.add_argument(
        "--builds-root",
        type=Path,
        default=None,
        help="Isolated trees go here (default pipeline/builds/llm_arm).",
    )
    args = p.parse_args(argv)

    cfg = _load_cfg(args.config)
    budget = _budget(cfg, hours=args.hours, tokens=args.tokens, model_id=args.model_id)
    if budget.model_id == "TBD" and not args.allow_fake:
        print(
            "model_id is TBD; Josh must set the exact API id, or pass --allow-fake "
            "for the scripted agent.",
            file=sys.stderr,
        )
        return 2

    src = ROOT / cfg["source"]["path"]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "diffs").mkdir(exist_ok=True)

    builds_root = (args.builds_root or (ROOT / "builds" / "llm_arm")).resolve()
    build_dir = builds_root / args.run_id
    stock = isolate_source(src, build_dir / "stock_src")
    work = isolate_source(src, build_dir / "work")

    contract_path = Path(cfg.get("egas", {}).get("contract", ROOT / "fixtures/llm_arm/contract.toml"))
    if not contract_path.is_absolute():
        contract_path = ROOT / contract_path
    contract = load_contract(contract_path)
    profile = None
    if contract.profile_path and contract.profile_path.is_file():
        profile = load_profile(contract.profile_path)
    prep = prepare_host(contract, profile)
    rungs = prep.rungs or t1_t3_plan()

    task = write_task_file(
        out / "task.md",
        budget=budget,
        workdir=work,
        rungs=rungs,
        dev_input=str(ROOT / cfg["data"]["dev"]),
    )

    steps = ["contract", "amdahl", "propose_t1_t3"]
    agent_ran = False
    proc: subprocess.CompletedProcess[str] | None = None
    cmd = ""
    elapsed = 0.0
    tokens_obj: dict = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "note": "agent not started",
    }
    ntok = 0
    ok, why = True, "agent skipped"
    applied: list[str] = []

    if not prep.proceed:
        write_json(
            out / "egas_host.json",
            {
                "steps": steps + ["refuse_skip_agent", "decide"],
                "proceed": False,
                "reason": prep.reason,
                "t4_used": False,
                "t5_used": False,
                "skipped_agent": True,
            },
        )
        rec, _report = finish_host(
            contract=contract, prep=prep, match=None, out_dir=out, applied=[]
        )
        snapshot_tree(stock, out / "stock_src")
        snapshot_tree(work, out / "work")
        (out / "final.diff").write_text("")
        write_json(out / "oracle_dev.json", {"skipped": True, "reason": prep.reason})
        _write_used(out, args, budget, cmd, elapsed, ntok, ok, why, proc)
        print(f"Amdahl refuse; skipped agent. decision={rec.decision.value} wrote {out}")
        return 0

    cmd_t = cfg["agent"]["command"]
    cmd = cmd_t.format(
        python=sys.executable,
        root=str(ROOT),
        work=str(work),
        patch=args.patch,
        task=str(task),
        out=str(out),
        model_id=budget.model_id,
    )
    env = os.environ.copy()
    env["ACTS_LLM_ARM_NO_NETWORK"] = "1"
    clock = WallClock()
    timeout_s = max(5.0, min(budget.hours * 3600.0, 8 * 3600.0))
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=work,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = clock.elapsed()
        (out / "transcript").write_text(
            f"$ {cmd}\nTIMEOUT after {elapsed:.1f}s (cap {budget.hours}h)\n"
            f"stdout:\n{exc.stdout or ''}\nstderr:\n{exc.stderr or ''}\n"
        )
        print(f"wall cap: agent killed after {elapsed:.1f}s", file=sys.stderr)
        snapshot_tree(stock, out / "stock_src")
        snapshot_tree(work, out / "work")
        return 3

    elapsed = clock.elapsed()
    agent_ran = True
    steps.append("agent")
    (out / "transcript").write_text(
        f"$ {cmd}\nexit {proc.returncode}\n--- stdout ---\n{proc.stdout}\n"
        f"--- stderr ---\n{proc.stderr}\n"
    )
    agent_tr = out / "agent_transcript.txt"
    for cand in (out / "transcript.txt", work / "transcript.txt"):
        if cand.is_file():
            agent_tr.write_text(cand.read_text())
            break

    tokens_path = out / "tokens.json"
    if not tokens_path.is_file() and (work / "tokens.json").is_file():
        tokens_path.write_text((work / "tokens.json").read_text())
    if tokens_path.is_file():
        tokens_obj = json.loads(tokens_path.read_text())
    else:
        tokens_obj = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "note": "backend did not write tokens.json",
        }
        write_json(tokens_path, tokens_obj)
    ntok = parse_tokens(tokens_obj)
    ok, why = budget_ok(budget, elapsed_s=elapsed, tokens=ntok)

    diff = unified_diff(stock, work)
    (out / "diffs" / "01_agent.diff").write_text(diff)
    (out / "final.diff").write_text(diff)
    (out / "build.log").write_text("fixture: interpreted Python; no compile\n")
    if diff.strip():
        applied.append("agent_source_edit")

    snapshot_tree(stock, out / "stock_src")
    snapshot_tree(work, out / "work")

    dev_table = ROOT / cfg["data"]["dev"]
    oracle = smoke_dev_oracle(out / "stock_src", out / "work", dev_table)
    write_json(out / "oracle_dev.json", oracle)
    steps.append("match_dev")
    dev_match = bool(oracle.get("match", {}).get("match")) if oracle.get("match") else False

    rec, _report = finish_host(
        contract=contract,
        prep=prep,
        match=dev_match,
        out_dir=out,
        applied=applied,
    )
    steps.append("decide")
    write_json(
        out / "egas_host.json",
        {
            "steps": steps,
            "proceed": True,
            "reason": prep.reason,
            "t4_used": False,
            "t5_used": False,
            "skipped_agent": False,
            "agent_ran": agent_ran,
            "dev_match": dev_match,
            "decision": rec.decision.value,
            "rung_classes": [r.cls.value for r in rungs],
        },
    )
    _write_used(out, args, budget, cmd, elapsed, ntok, ok, why, proc)
    write_json(
        out / "run.json",
        {
            "run_id": args.run_id,
            "elapsed_s": elapsed,
            "tokens": ntok,
            "budget_ok": ok,
            "budget_why": why,
            "agent_exit": None if proc is None else proc.returncode,
            "diff_bytes": len(diff.encode()),
            "changed": bool(diff.strip()),
            "dev_match": dev_match,
            "decision": rec.decision.value,
            "builds": str(build_dir),
        },
    )
    if proc is not None and proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode
    if not ok:
        print(why, file=sys.stderr)
        return 3
    print(f"wrote {out} decision={rec.decision.value} dev_match={dev_match}")
    return 0


def _write_used(out, args, budget, cmd, elapsed, ntok, ok, why, proc) -> None:
    write_toml(
        out / "config.used.toml",
        {
            "run": {
                "run_id": args.run_id,
                "protocol": "docs/LLM_ARM_PROTOCOL.md",
                "allow_fake": args.allow_fake,
                "command": cmd,
                "elapsed_s": elapsed,
                "tokens_used": ntok,
                "budget_ok": ok,
                "budget_why": why,
                "agent_exit": "" if proc is None else proc.returncode,
            },
            "budget": budget.as_dict(),
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
