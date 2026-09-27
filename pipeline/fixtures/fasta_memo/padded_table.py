#!/usr/bin/env python3
"""Whitespace-padded name column; empty description is '-'."""
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

hits = [(n, d, s) for n, d, s in recs if not s.startswith("Q")]
width = max([8] + [len(n) for n, _d, _s in hits])
print("# mock padded table")
for name, desc, seq in hits:
    score = (sum(ord(c) for c in seq) * 3) % 90
    label = desc if desc else "-"
    print(f"{name.ljust(width)} {score} {label}")
