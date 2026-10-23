"""``tare`` CLI — product front door for the research engine.

Calls the same ``acts`` package. ``python3 -m acts`` remains for research
scripts and committed result recipes. Do not reimplement reuse here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _cmd_version(_: argparse.Namespace) -> int:
    from acts import __version__

    print(f"tare {__version__}")
    print("engine: acts (research package; thin product alias)")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    # Delegate to the existing acts runner so behaviour stays identical.
    from acts.__main__ import main as acts_main

    argv = ["acts", "run", "--strategy", "reference"]
    if args.pin is not None:
        argv.extend(["--pin", args.pin])
    if args.verify is not None:
        argv.extend(["--verify", args.verify])
    if args.prep is not None:
        argv.extend(["--prep", args.prep])
    if args.cache is not None:
        argv.extend(["--cache", str(args.cache)])
    if args.input is not None:
        argv.extend(["--input", str(args.input)])
    if args.reference is not None:
        argv.extend(["--reference", str(args.reference)])
    if args.out is not None:
        argv.extend(["--out", str(args.out)])
    if args.slack:
        argv.append("--slack")
    tool = list(args.tool)
    if tool and tool[0] == "--":
        tool = tool[1:]
    argv.append("--")
    argv.extend(tool)
    sys.argv = argv
    return acts_main()


def _cmd_selftest(_: argparse.Namespace) -> int:
    """Minimal install-time check. Full campaign is Phase 3."""
    from acts.row_diff import classify

    body = ["PF1 - Q1 - a", "PF2 - Q2 - b"]
    ok = classify(body, body, "tbl")["byte_equal"]
    missing = "missing" in classify(body[:1], body, "tbl")["classes"]
    value = "value-only" in classify(
        ["PF1 - Q1 - z"], ["PF1 - Q1 - a"], "tbl"
    )["classes"]
    report = {
        "tool": "tare",
        "check": "row_diff_controls",
        "pass": bool(ok and missing and value),
        "controls": {
            "positive_identity": ok,
            "negative_missing": missing,
            "negative_value_only": value,
        },
    }
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


def _cmd_console(args: argparse.Namespace) -> int:
    print(
        "TARE console is not on this branch yet. Josh must commit "
        "tools/tare-console source (see docs/release/DECISIONS_NEEDED.md S1).",
        file=sys.stderr,
    )
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tare",
        description="TARE — Tool Annotation Reuse, Exact. Product CLI over the acts engine.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ver = sub.add_parser("version", help="Print TARE / engine version")
    p_ver.set_defaults(func=_cmd_version)

    p_run = sub.add_parser(
        "run",
        help="Run exact reference reuse (delegates to acts reference strategy)",
    )
    p_run.add_argument("--input", type=Path)
    p_run.add_argument("--reference", type=Path)
    p_run.add_argument("--cache", type=Path)
    p_run.add_argument("--out", type=Path)
    p_run.add_argument("--pin")
    p_run.add_argument("--verify")
    p_run.add_argument("--prep")
    p_run.add_argument("--slack", action="store_true")
    p_run.add_argument("tool", nargs=argparse.REMAINDER, help="Tool argv after --")
    p_run.set_defaults(func=_cmd_run)

    p_st = sub.add_parser("selftest", help="Install-time control checks (expanding)")
    p_st.set_defaults(func=_cmd_selftest)

    p_con = sub.add_parser("console", help="Open the local TARE console")
    p_con.add_argument("--port", type=int, default=8768)
    p_con.set_defaults(func=_cmd_console)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
