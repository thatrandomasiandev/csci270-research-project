#!/usr/bin/env python3
"""Output INFO/ANN depends on the ID column (non-key). Key must widen."""
import sys

src = open(sys.argv[1]) if len(sys.argv) > 1 else sys.stdin
for line in src:
    line = line.rstrip("\n")
    if not line or line.startswith("#"):
        print(line)
        continue
    parts = line.split("\t")
    chrom, pos, _id, ref, alt = parts[:5]
    tail = parts[5:] if len(parts) > 5 else [".", "PASS", "."]
    while len(tail) < 3:
        tail.append(".")
    tail[2] = f"ANN={_id}|{chrom}:{pos}"
    print("\t".join([chrom, pos, _id, ref, alt] + tail))
