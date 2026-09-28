#!/usr/bin/env python3
"""Score an arm-L work dir: MATCH on smoke/test fixtures; emit CARC timing inputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.table import tables_match  # noqa: E402
from egas.llm_arm import write_json  # noqa: E402


def _run_tool(py: Path, inp: Path, outp: Path) -> None:
    subprocess.run(
        [sys.executable, str(py), str(inp), str(outp)],
        check=True,
        capture_output=True,
        text=True,
    )


def match_pair(stock_src: Path, work_src: Path, table: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="llm_arm_score_") as td:
        tmp = Path(td)
        stock_out = tmp / "stock.tsv"
        work_out = tmp / "work.tsv"
        _run_tool(stock_src / "score_rows.py", table, stock_out)
        _run_tool(work_src / "score_rows.py", table, work_out)
        a, b = stock_out.read_text(), work_out.read_text()
        ok = tables_match(a, b, "order", match_ws=True)
        return {
            "match": ok,
            "match_type": "order+ws",
            "smoke_or_test_rows": len([ln for ln in a.splitlines() if ln.strip()]) - 1,
            "stock_head": a.splitlines()[:3],
            "work_head": b.splitlines()[:3],
        }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--config", type=Path, default=ROOT / "fixtures/llm_arm/agent.toml")
    p.add_argument("--which", choices=("smoke", "test"), default="smoke",
                   help="smoke = Mac fixture (labeled smoke). test = fixture stand-in for A/B (still not real collections).")
    args = p.parse_args(argv)
    cfg = tomllib.loads(args.config.read_text())
    run = args.run_dir.resolve()
    stock = run / "stock_src"
    work = run / "work"
    if not stock.is_dir() or not work.is_dir():
        print("run-dir missing stock_src/ or work/", file=sys.stderr)
        return 2
    table = ROOT / cfg["data"][args.which]
    result = match_pair(stock, work, table)
    score = {
        "protocol": "docs/LLM_ARM_PROTOCOL.md",
        "run_dir": str(run),
        "split": args.which,
        "label": "smoke" if args.which == "smoke" else "fixture_test_not_collections_AB",
        "match": result["match"],
        "speedup": 1.0 if not result["match"] else "MATCH-clean; Mac timing is smoke; CARC later",
        "score_if_test_match_fail": 1.0,
        "match_detail": result,
        "carc_timing": {
            "ready": bool(result["match"]),
            "host": "x86 epyc-7542 exclusive, interleaved stock anchors",
            "note": "Do not time MATCH-fail runs. This script does not submit jobs.",
            "argv_template": [
                "python3",
                "work/score_rows.py",
                "INPUT.tsv",
                "OUT.tsv",
            ],
        },
    }
    write_json(run / "score.json", score)
    write_json(run / "carc_timing_request.json", score["carc_timing"])
    print(json.dumps({
        "match": result["match"],
        "split": args.which,
        "speedup": 1.0 if not result["match"] else "MATCH-clean",
        "wrote": str(run / "score.json"),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
