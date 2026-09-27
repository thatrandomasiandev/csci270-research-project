#!/usr/bin/env python3
"""Global sort by score. Expected: SHIP, multiset MATCH."""
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else sys.stdin.read()
recs: list[tuple[str, str]] = []
name = None
chunks: list[str] = []
for line in text.splitlines():
    if line.startswith(">"):
        if name is not None:
            recs.append((name, "".join(chunks)))
        name = line[1:].split()[0]
        chunks = []
    else:
        chunks.append(line.strip())
if name is not None:
    recs.append((name, "".join(chunks)))

rows: list[tuple[int, str]] = []
for name, seq in recs:
    score = sum(ord(c) for c in seq) % 40
    rows.append((score, f"{name}\t{score}\thit"))

print("# mock score-sorted table")
for _score, line in sorted(rows, key=lambda x: -x[0]):
    print(line)
