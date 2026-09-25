#!/usr/bin/env python3
"""Per-variant annotator. Output line depends only on CHROM POS REF ALT."""
import sys

for line in sys.stdin:
    line = line.rstrip("\n")
    if not line or line.startswith("#"):
        print(line)
        continue
    parts = line.split("\t")
    chrom, pos, _id, ref, alt = parts[:5]
    print(f"{chrom}\t{pos}\t{_id}\t{ref}\t{alt}\tANN={chrom}:{pos}:{ref}>{alt.split(',')[0]}")
