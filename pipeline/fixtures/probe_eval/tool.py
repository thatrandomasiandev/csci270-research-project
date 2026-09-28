#!/usr/bin/env python3
"""One argv-named input. Class/frequency via argv, not hidden files."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from suite import run_tool  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 4:
        print("usage: tool.py KIND CLASS P INPUT", file=sys.stderr)
        return 2
    kind, cls, p_raw, src = args[0], args[1], args[2], Path(args[3])
    sys.stdout.write(run_tool(kind, cls, float(p_raw), src))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
