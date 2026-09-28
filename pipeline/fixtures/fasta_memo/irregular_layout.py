#!/usr/bin/env python3
"""Gaps that are not a single left/right width rule. Expected: ws fallback."""
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

print("# mock irregular gaps")
for name, seq in recs:
    extra = 2 + (len(name) * 3 + sum(ord(c) for c in seq)) % 9
    score = (sum(ord(c) for c in seq) * 3) % 90
    print(f"{name}{' ' * extra}{score} hit")
