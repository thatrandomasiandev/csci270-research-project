#!/usr/bin/env python3
"""Tool rewrites FILTER. FILTER is PRODUCED, never taken from the query."""
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
    tail[1] = "ANNOTATED"
    tail[2] = f"ANN={chrom}:{pos}:{ref}>{alt.split(',')[0]}"
    print("\t".join([chrom, pos, _id, ref, alt] + tail))
