#!/usr/bin/env python3
"""Run a tool that writes a side table file; print that file on stdout.

Replace {table} in argv with a temp path. Format wiring, not a parser.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def main(argv: list[str]) -> int:
    work = Path(tempfile.mkdtemp(prefix="acts_table_"))
    dest = work / "out.tsv"
    cmd = [a.replace("{table}", str(dest)) for a in argv]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout or "")
        return proc.returncode
    if dest.is_file():
        sys.stdout.write(dest.read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
