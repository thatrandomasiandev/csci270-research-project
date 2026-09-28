#!/usr/bin/env python3
"""Each output records the number of files in this invocation. Expected: REFUSE_GLOBAL."""
import sys
from pathlib import Path

indir, outdir = Path(sys.argv[1]), Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)
files = [p for p in sorted(indir.iterdir()) if p.is_file() and not p.name.startswith(".")]
n = len(files)
for p in files:
    (outdir / f"{p.stem}.tsv").write_text(f"n\n{n}\n")
