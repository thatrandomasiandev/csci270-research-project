#!/usr/bin/env python3
"""Header + one row per line; echoes the input. Expected: SHIP, byte-order MATCH."""
import csv
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else sys.stdin.read()
writer = csv.writer(sys.stdout)
writer.writerow(["input", "len", "score"])
for ln in text.splitlines():
    score = sum(ord(c) for c in ln) % 97
    writer.writerow([ln, len(ln), score])
