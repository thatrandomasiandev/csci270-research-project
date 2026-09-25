#!/usr/bin/env python3
"""joint_called_c1 overlap. Not separately-called. Full-ALT keys."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.overlap import overlap
from acts.vcf import body_lines, read_maybe_gz, variant_key

SAMPLES = ("HG00096", "HG00097", "HG00099")
PAIRS = (
    ("HG00096", "HG00097"),
    ("HG00097", "HG00099"),
    ("HG00096", "HG00099"),
)
OUT = ROOT / "results" / "vep_chr22_overlap.json"


def keys(path: Path) -> set[str]:
    return {variant_key(ln) for ln in body_lines(read_maybe_gz(path))}


def c1_path(sample: str) -> Path:
    return ROOT / "data" / "vep_chr22" / f"{sample}.c1.vcf.gz"


def n_multiallelic(path: Path) -> int:
    n = 0
    for ln in body_lines(read_maybe_gz(path)):
        alt = ln.split("\t")[4]
        if "," in alt:
            n += 1
    return n


def row(prev: str, new: str, sets: dict[str, set[str]]) -> dict:
    fwd = overlap(sets[prev], sets[new])
    return {
        "prev": prev,
        "new": new,
        "n_prev": fwd.n_prev,
        "n_new": fwd.n_new,
        "n_shared": fwd.n_shared,
        "recall_in_new": round(fwd.recall_in_new, 6),
        "jaccard": round(fwd.jaccard, 6),
    }


def main() -> int:
    missing = [s for s in SAMPLES if not c1_path(s).is_file()]
    if missing:
        print(f"INCOMPLETE: missing -c1 extracts: {missing}", file=sys.stderr)
        return 2
    sets = {s: keys(c1_path(s)) for s in SAMPLES}
    multi = {s: n_multiallelic(c1_path(s)) for s in SAMPLES}
    union = sets["HG00096"] | sets["HG00097"]
    grow = overlap(union, sets["HG00099"])
    report = {
        "label": "joint_called_c1",
        "key": "CHROM POS REF ALT (full ALT)",
        "chrom": "22",
        "cohort": "1000G GRCh38 phased 20190312",
        "population_note": "HG00096/97/99 are CEU in 1000G",
        "n_multiallelic": multi,
        "rows": [row(a, b, sets) for a, b in PAIRS],
        "growing_cohort": {
            "prev": "HG00096∪HG00097",
            "new": "HG00099",
            "n_prev": grow.n_prev,
            "n_new": grow.n_new,
            "n_shared": grow.n_shared,
            "recall_in_new": round(grow.recall_in_new, 6),
            "miss_frac": round(1 - grow.recall_in_new, 6),
        },
        "note": "carried ALTs only (-c1). Not separately-called per-sample VCFs.",
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
