#!/usr/bin/env python3
"""One TSV per input file; content from bytes only. Expected: SHIP."""
import hashlib
import sys
from pathlib import Path

indir, outdir = Path(sys.argv[1]), Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)
for p in sorted(indir.iterdir()):
    if not p.is_file() or p.name.startswith("."):
        continue
    data = p.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    (outdir / f"{p.stem}.tsv").write_text(f"len\tdigest\n{len(data)}\t{digest}\n")
