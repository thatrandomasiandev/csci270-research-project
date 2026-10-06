#!/usr/bin/env python3
"""Per-query target-name padding that a short probe can miss.

Every query emits two target names. Ordinary sequences only hit names
shorter than 20, so every target field is 20 wide and a fixed floor, a
per-query max, and a per-file max all explain the lines. A sequence that
contains the marker RAREWIDEN also hits A6-like_Thioredoxin-like_C (26
characters); both of that query's target fields are then 26 wide.

The score column is left-aligned and overflows its floor on one row of
every query, so that column's fixed minimum is unique whenever the target
column is. Left alignment keeps each field's padding in its own gap; a
right-aligned neighbour would hide a per-query width inside the measured gap.
"""
import sys
from pathlib import Path

FLOOR = 20
LONG = "A6-like_Thioredoxin-like_C"
SHORT = ("Pkinase", "Globin")


def _records(text: str) -> list[tuple[str, str]]:
    recs: list[tuple[str, str]] = []
    name = None
    chunks: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if name is not None:
                recs.append((name, "".join(chunks)))
            name = line[1:].split()[0] if line[1:].strip() else ""
            chunks = []
        else:
            chunks.append(line.strip())
    if name is not None:
        recs.append((name, "".join(chunks)))
    return recs


def main() -> None:
    text = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else sys.stdin.read()
    print("# mock per-query widen")
    for name, seq in _records(text):
        targets = (LONG, SHORT[0]) if "RAREWIDEN" in seq else SHORT
        width = max(FLOOR, max(len(t) for t in targets))
        qwidth = max(12, len(name))
        scores = ("3", "1234567")
        for target, score in zip(targets, scores):
            print(f"{target.ljust(width)} {score.ljust(max(4, len(score)))} {name.ljust(qwidth)} -")


if __name__ == "__main__":
    main()
