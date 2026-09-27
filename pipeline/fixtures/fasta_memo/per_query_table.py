#!/usr/bin/env python3
"""Grouped table: 0–3 lines per query, echoes the name. Expected: SHIP."""
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else sys.stdin.read()
recs: list[tuple[str, str, str]] = []
name = desc = None
chunks: list[str] = []
for line in text.splitlines():
    if line.startswith(">"):
        if name is not None:
            recs.append((name, desc or "", "".join(chunks)))
        parts = line[1:].strip().split(None, 1)
        name = parts[0] if parts else ""
        desc = parts[1] if len(parts) > 1 else ""
        chunks = []
    else:
        chunks.append(line.strip())
if name is not None:
    recs.append((name, desc or "", "".join(chunks)))

print("# mock per-query table")
for name, desc, seq in recs:
    n = sum(ord(c) for c in seq) % 4
    base = (sum(ord(c) for c in seq) * 3) % 90
    for j in range(n):
        print(f"{name}\t{base + j}\t{desc}")
