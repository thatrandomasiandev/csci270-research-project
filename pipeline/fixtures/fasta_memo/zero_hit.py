#!/usr/bin/env python3
"""Some queries emit no lines. Expected: EMPTY cached and reused."""
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

print("# mock sparse table")
for name, seq in recs:
    if name.startswith("skip") or seq.startswith("Q"):
        continue
    print(f"{name}\t1\thit")
