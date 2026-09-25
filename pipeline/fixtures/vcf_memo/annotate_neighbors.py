#!/usr/bin/env python3
"""Forbidden annotator: each record's output includes the previous POS."""
import sys

prev = "NA"
for line in sys.stdin:
    line = line.rstrip("\n")
    if not line or line.startswith("#"):
        print(line)
        continue
    parts = line.split("\t")
    chrom, pos, _id, ref, alt = parts[:5]
    print(f"{chrom}\t{pos}\t{_id}\t{ref}\t{alt}\tPREV={prev}")
    prev = pos
