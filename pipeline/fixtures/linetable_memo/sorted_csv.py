#!/usr/bin/env python3
"""Global sort by score. Expected: SHIP, multiset MATCH."""
import csv
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else sys.stdin.read()
rows: list[tuple[int, str, int]] = []
for ln in text.splitlines():
    score = sum(ord(c) for c in ln) % 97
    rows.append((score, ln, len(ln)))
writer = csv.writer(sys.stdout)
writer.writerow(["input", "len", "score"])
for score, ln, n in sorted(rows, key=lambda x: -x[0]):
    writer.writerow([ln, n, score])
