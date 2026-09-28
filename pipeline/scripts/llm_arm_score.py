#!/usr/bin/env python3
"""Score an arm-L work dir: MATCH on smoke/test fixtures; emit CARC timing inputs.

Do not time collections A/B here. Mac MATCH is labeled smoke (or fixture_test).
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from egas.llm_arm import match_fixture_table, write_json  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--config", type=Path, default=ROOT / "fixtures/llm_arm/agent.toml")
    p.add_argument(
        "--which",
        choices=("smoke", "test"),
        default="smoke",
        help=(
            "smoke = Mac fixture (labeled smoke). "
            "test = fixture stand-in for A/B (still not real collections)."
        ),
    )
    args = p.parse_args(argv)
    cfg = tomllib.loads(args.config.read_text())
    run = args.run_dir.resolve()
    stock = run / "stock_src"
    work = run / "work"
    if not stock.is_dir() or not work.is_dir():
        print("run-dir missing stock_src/ or work/", file=sys.stderr)
        return 2
    table = ROOT / cfg["data"][args.which]
    result = match_fixture_table(stock, work, table)
    matched = bool(result.get("match"))
    label = "smoke" if args.which == "smoke" else "fixture_test_not_collections_AB"
    carc = {
        "ready": matched,
        "host": "x86 epyc-7542 exclusive, interleaved stock anchors",
        "note": (
            "Do not time MATCH-fail runs. This script does not submit jobs "
            "and does not time collections A/B."
        ),
        "argv_template": [
            "python3",
            "work/score_rows.py",
            "INPUT.tsv",
            "OUT.tsv",
        ],
        "submit": False,
    }
    score = {
        "protocol": "docs/LLM_ARM_PROTOCOL.md",
        "run_dir": str(run),
        "split": args.which,
        "label": label,
        "match": matched,
        "speedup": (
            1.0
            if not matched
            else "MATCH-clean; Mac timing is smoke; CARC later"
        ),
        "score_if_test_match_fail": 1.0,
        "match_detail": result,
        "carc_timing": carc,
        "final_diff": str(run / "final.diff"),
        "final_diff_bytes": (run / "final.diff").stat().st_size
        if (run / "final.diff").is_file()
        else 0,
    }
    write_json(run / "score.json", score)
    write_json(run / f"score_{args.which}.json", score)
    write_json(run / "carc_timing_request.json", carc)
    print(
        json.dumps(
            {
                "match": matched,
                "split": args.which,
                "label": label,
                "speedup": score["speedup"],
                "wrote": str(run / "score.json"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
