#!/usr/bin/env python3
"""Right-aligned scores padded to the max width of this query's rows."""
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

print("# mock per-query width table")
for name, seq in recs:
    n = 1 + (sum(ord(c) for c in seq) % 3)
    base = 1 + (sum(ord(c) for c in seq) % 9)
    scores = [base * (10**j) for j in range(n)]
    width = max(len(str(s)) for s in scores)
    for score in scores:
        print(f"{name} {str(score).rjust(width)} x")
