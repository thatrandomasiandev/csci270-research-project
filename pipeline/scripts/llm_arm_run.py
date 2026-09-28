#!/usr/bin/env python3
"""Isolated arm-L run: task file, pluggable agent CLI, budget, artifacts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from egas.llm_arm import (  # noqa: E402
    Budget,
    WallClock,
    budget_ok,
    isolate_source,
    parse_tokens,
    unified_diff,
    write_json,
    write_task_file,
)


def _load_cfg(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def _budget(cfg: dict, *, hours: float | None, tokens: int | None, model_id: str | None) -> Budget:
    b = cfg.get("budget", {})
    return Budget(
        hours=float(hours if hours is not None else b.get("hours", 8)),
        tokens=int(tokens if tokens is not None else b.get("tokens", 2_000_000)),
        n_runs=int(b.get("n_runs", 3)),
        model_id=str(model_id or b.get("model_id", "TBD")),
        dollar_cap=b.get("dollar_cap"),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LLM arm L harness. No live model unless the config CLI is one.")
    p.add_argument("--config", type=Path, default=ROOT / "fixtures/llm_arm/agent.toml")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--patch", choices=("safe", "bad"), default="safe",
                   help="Fixture fake-agent only. Ignored by a real CLI that does not use {patch}.")
    p.add_argument("--allow-fake", action="store_true",
                   help="Permit model_id=TBD (scripted fake agent). Required for dry-run.")
    p.add_argument("--hours", type=float, default=None)
    p.add_argument("--tokens", type=int, default=None)
    p.add_argument("--model-id", default=None)
    args = p.parse_args(argv)

    cfg = _load_cfg(args.config)
    budget = _budget(cfg, hours=args.hours, tokens=args.tokens, model_id=args.model_id)
    if budget.model_id == "TBD" and not args.allow_fake:
        print("model_id is TBD; Josh must set the exact API id, or pass --allow-fake for the scripted agent.",
              file=sys.stderr)
        return 2

    src = ROOT / cfg["source"]["path"]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    stock_copy = out / "stock_src"
    isolate_source(src, stock_copy)
    isolate_source(src, work)
    (out / "diffs").mkdir(exist_ok=True)

    task = write_task_file(
        out / "task.md",
        budget=budget,
        workdir=work,
        dev_input=str(ROOT / cfg["data"]["dev"]),
    )

    cmd_t = cfg["agent"]["command"]
    cmd = cmd_t.format(
        python=sys.executable,
        root=str(ROOT),
        work=str(work),
        patch=args.patch,
        task=str(task),
    )
    clock = WallClock()
    env = os.environ.copy()
    env["ACTS_LLM_ARM_NO_NETWORK"] = "1"
    proc = subprocess.run(
        cmd,
        shell=True,
        cwd=work,
        capture_output=True,
        text=True,
        env=env,
        timeout=max(5.0, budget.hours * 3600),
    )
    elapsed = clock.elapsed()
    (out / "transcript").write_text(
        f"$ {cmd}\nexit {proc.returncode}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}\n"
    )
    if (work / "transcript.txt").is_file():
        (out / "agent_transcript.txt").write_text((work / "transcript.txt").read_text())
    tokens_path = work / "tokens.json"
    tokens_obj = json.loads(tokens_path.read_text()) if tokens_path.is_file() else {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "note": "backend did not write tokens.json",
    }
    shutil.copy(tokens_path, out / "tokens.json") if tokens_path.is_file() else write_json(out / "tokens.json", tokens_obj)
    ntok = parse_tokens(tokens_obj)
    ok, why = budget_ok(budget, elapsed_s=elapsed, tokens=ntok)

    diff = unified_diff(stock_copy, work)
    (out / "diffs" / "01_agent.diff").write_text(diff)
    (out / "final.diff").write_text(diff)
    build_note = "fixture: interpreted Python; no compile\n"
    (out / "build.log").write_text(build_note)
    (out / "build_log.txt").write_text(build_note)
    write_json(out / "config.used.toml.json", {
        "run_id": args.run_id,
        "budget": budget.as_dict(),
        "command": cmd,
        "elapsed_s": elapsed,
        "tokens": ntok,
        "budget_ok": ok,
        "budget_why": why,
        "agent_exit": proc.returncode,
        "allow_fake": args.allow_fake,
        "protocol": "docs/LLM_ARM_PROTOCOL.md",
    })
    write_json(out / "run.json", {
        "run_id": args.run_id,
        "elapsed_s": elapsed,
        "tokens": ntok,
        "budget_ok": ok,
        "budget_why": why,
        "agent_exit": proc.returncode,
        "diff_bytes": len(diff.encode()),
        "changed": bool(diff.strip()),
    })
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode
    if not ok:
        print(why, file=sys.stderr)
        return 3
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
