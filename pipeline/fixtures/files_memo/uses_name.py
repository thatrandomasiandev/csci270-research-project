#!/usr/bin/env python3
"""Output bytes depend on the file name (not a copy of the name). Expected: SHIP after widen."""
import hashlib
import sys
from pathlib import Path

indir, outdir = Path(sys.argv[1]), Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)
for p in sorted(indir.iterdir()):
    if not p.is_file() or p.name.startswith("."):
        continue
    data = p.read_bytes()
    derived = hashlib.sha256(p.name.encode("utf-8") + b"\0" + data).hexdigest()
    (outdir / f"{p.stem}.tsv").write_text(f"derived\n{derived}\n")
