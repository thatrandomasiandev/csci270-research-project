#!/usr/bin/env python3
"""A score scaled by the total query count. Expected: REFUSE_GLOBAL."""
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else sys.stdin.read()
names: list[str] = []
for line in text.splitlines():
    if line.startswith(">"):
        names.append(line[1:].split()[0])

n = len(names) or 1
print("# mock file-size score")
for name in names:
    print(f"{name}\t{100.0 / n}\tok")
