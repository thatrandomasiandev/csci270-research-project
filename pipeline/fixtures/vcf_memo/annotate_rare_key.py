#!/usr/bin/env python3
"""ANN on every record; RARE=1 only on POS=99999999 (unprobed-key fixture)."""
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
    info = f"ANN={chrom}:{pos}:{ref}>{alt.split(',')[0]}"
    if pos == "99999999":
        info = f"{info};RARE=1"
    tail[2] = info
    print("\t".join([chrom, pos, _id, ref, alt] + tail))
