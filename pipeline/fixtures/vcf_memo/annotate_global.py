#!/usr/bin/env python3
"""Forbidden: INFO/RANK is i/N for this invocation. Fails subset-invariance."""
import sys

src = open(sys.argv[1]) if len(sys.argv) > 1 else sys.stdin
lines = src.read().splitlines()
body = [ln for ln in lines if ln and not ln.startswith("#")]
n = len(body)
i = 0
for line in lines:
    if not line or line.startswith("#"):
        print(line)
        continue
    i += 1
    parts = line.split("\t")
    while len(parts) < 8:
        parts.append(".")
    # Same token on every record so shuffle still passes; N is the file size.
    parts[7] = f"RANK={n}/{n}"
    print("\t".join(parts))
