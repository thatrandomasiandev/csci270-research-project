#!/usr/bin/env python3
"""Fixture tool: TSV id\\ttoken -> id\\ttoken\\tscore. Deterministic. No network."""

from __future__ import annotations

import sys
from pathlib import Path


def score(token: str) -> int:
    return len(token)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: score_rows.py INPUT.tsv OUTPUT.tsv", file=sys.stderr)
        return 2
    inp, outp = Path(args[0]), Path(args[1])
    lines = [ln for ln in inp.read_text().splitlines() if ln.strip()]
    if not lines:
        raise SystemExit("empty input")
    header = lines[0]
    rows: list[str] = []
    for line in lines[1:]:
        rid, token = line.split("\t", 1)
        rows.append(f"{rid}\t{token}\t{score(token)}")
    outp.write_text(header + "\tscore\n" + "\n".join(rows) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
