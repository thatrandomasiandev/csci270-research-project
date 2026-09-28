#!/usr/bin/env python3
"""Scripted fake agent. Applies a named fixture patch. No model API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _safe(src: Path) -> None:
    text = src.read_text()
    old = "def score(token: str) -> int:\n    return len(token)\n"
    new = (
        "def score(token: str) -> int:\n"
        "    n = len(token)  # trivial no-op rename; same output\n"
        "    return n\n"
    )
    if old not in text:
        raise SystemExit("safe patch: stock score() not found")
    src.write_text(text.replace(old, new, 1))


def _bad(src: Path) -> None:
    text = src.read_text()
    old = "def score(token: str) -> int:\n    return len(token)\n"
    new = (
        "def score(token: str) -> int:\n"
        "    return len(token) + 1  # changes the output column\n"
    )
    if old not in text:
        raise SystemExit("bad patch: stock score() not found")
    src.write_text(text.replace(old, new, 1))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--work", required=True, type=Path)
    p.add_argument("--patch", required=True, choices=("safe", "bad"))
    p.add_argument("--tokens", type=int, default=100)
    args = p.parse_args()
    src = args.work / "score_rows.py"
    if not src.is_file():
        raise SystemExit(f"no source at {src}")
    if args.patch == "safe":
        _safe(src)
    else:
        _bad(src)
    transcript = args.work / "transcript.txt"
    transcript.write_text(
        f"fake_agent patch={args.patch}\n"
        f"edited {src.name}\n"
        "no network\n"
    )
    tokens = {
        "prompt_tokens": max(1, args.tokens // 2),
        "completion_tokens": max(1, args.tokens - args.tokens // 2),
        "backend": "fake_agent",
        "patch": args.patch,
    }
    (args.work / "tokens.json").write_text(json.dumps(tokens, indent=2) + "\n")
    print(json.dumps({"ok": True, "patch": args.patch, **tokens}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
