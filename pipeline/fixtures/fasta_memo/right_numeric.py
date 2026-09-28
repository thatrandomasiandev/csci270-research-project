#!/usr/bin/env python3
"""Right-aligned numeric column with a fixed minimum width. Expected: byte MATCH."""
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

print("# mock right-aligned numeric table")
for name, desc, seq in recs:
    if seq.startswith("Q"):
        continue
    score = (sum(ord(c) for c in seq) * 7) % 9000
    label = desc if desc else "-"
    print(f"{name.ljust(12)} {str(score).rjust(6)} {label}")
