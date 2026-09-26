#!/usr/bin/env python3
"""K-12 proteome recurrence: MG1655 ∪ W3110 → BW25113.

Key = MD5 of uppercase amino-acid sequence, headers ignored.
m = miss fraction on the later proteome. No timing.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.overlap import overlap

DEST = ROOT / "data" / "kprot"
OUT = ROOT / "results" / "kprot_overlap.json"

PROTEOMES = {
    "MG1655": {
        "role": "prev_A",
        "accession": "GCF_000005845.2",
        "assembly": "ASM584v2",
        "url": (
            "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/005/845/"
            "GCF_000005845.2_ASM584v2/GCF_000005845.2_ASM584v2_protein.faa.gz"
        ),
    },
    "W3110": {
        "role": "prev_B",
        "accession": "GCF_000010245.2",
        "assembly": "ASM1024v1",
        "note": "HEADLINE_SCREEN locked GCF_000010245.1; NCBI no longer ships protein.faa.gz in that directory. Same assembly ASM1024v1, current RefSeq increment.",
        "url": (
            "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/010/245/"
            "GCF_000010245.2_ASM1024v1/GCF_000010245.2_ASM1024v1_protein.faa.gz"
        ),
    },
    "BW25113": {
        "role": "later",
        "accession": "GCF_000750555.1",
        "assembly": "ASM75055v1",
        "url": (
            "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/750/555/"
            "GCF_000750555.1_ASM75055v1/GCF_000750555.1_ASM75055v1_protein.faa.gz"
        ),
    },
}


def seq_md5(seq: str) -> str:
    aa = "".join(ch for ch in seq.upper() if not ch.isspace())
    return hashlib.md5(aa.encode("ascii")).hexdigest()


def faa_keys(path: Path) -> list[str]:
    keys: list[str] = []
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:
        chunks: list[str] = []
        for line in fh:
            if line.startswith(">"):
                if chunks:
                    keys.append(seq_md5("".join(chunks)))
                    chunks = []
                continue
            chunks.append(line.strip())
        if chunks:
            keys.append(seq_md5("".join(chunks)))
    return keys


def fetch(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    print(f"fetch {url} -> {dest}", flush=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    subprocess.run(["curl", "-L", "--fail", "-o", str(tmp), url], check=True)
    tmp.replace(dest)
    return dest


def main() -> int:
    files = {}
    keys = {}
    for name, meta in PROTEOMES.items():
        path = fetch(meta["url"], DEST / f"{name}.faa.gz")
        seqs = faa_keys(path)
        files[name] = {
            **meta,
            "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "n_records": len(seqs),
            "n_unique": len(set(seqs)),
        }
        keys[name] = seqs
        print(f"{name}: n={len(seqs)} unique={len(set(seqs))} bytes={path.stat().st_size}", flush=True)

    prev = set(keys["MG1655"]) | set(keys["W3110"])
    later = set(keys["BW25113"])
    rep = overlap(prev, later)
    m = 1.0 - rep.recall_in_new
    payload = {
        "protocol": "pipeline/docs/HEADLINE_SCREEN.md",
        "key": "MD5 of uppercase amino-acid sequence, headers ignored",
        "prev": "MG1655 ∪ W3110",
        "later": "BW25113",
        "proteomes": files,
        "n_prev_union": len(prev),
        "n_later": rep.n_new,
        "n_shared": rep.n_shared,
        "recall_in_new": rep.recall_in_new,
        "miss_frac": m,
        "jaccard": rep.jaccard,
        "refuse_m": m > 1.0 / 3.0,
        "refuse_m_rule": "m > 1/3 cannot pass ceiling ≥ 3 even at a = w = 0",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
