#!/usr/bin/env python3
"""Whitespace table that echoes the query description as a trailing free-text field.

Mirrors hmmsearch --tblout: an empty description prints as "-", and a multi-word
description spans several whitespace tokens at the end of the line. Every other value
depends only on the sequence. Expected: SHIP, with reuse surviving renamed records and
changed descriptions (including a different word count).
"""
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

print("# mock whitespace table with trailing description")
for name, desc, seq in recs:
    s = sum(ord(c) for c in seq)
    for j in range(s % 3):
        model = f"M{(s + j) % 7}"
        print(f"{name:<12} - {model:<6} PF{(s + j) % 97:05d} {(s * 7 + j) % 1000:>6} {(s + j) % 13:>3} {desc or '-'}")
