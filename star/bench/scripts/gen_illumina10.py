#!/usr/bin/env python3
"""Generate 10 Illumina-like PE FASTQ pairs on a shared synthetic genome (Suite A)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--n-reads", type=int, default=500_000)
    ap.add_argument("--n-genes", type=int, default=300)
    ap.add_argument("--read-len", type=int, default=100)
    args = ap.parse_args()

    star_root = Path(__file__).resolve().parents[1].parent  # .../star
    base = args.out_dir or (star_root / "bench" / "datasets")
    gen = Path(__file__).resolve().parent / "gen_synthetic_rnaseq.py"
    suite = base / "illumina10"
    suite.mkdir(parents=True, exist_ok=True)

    shared = suite / "shared"
    subprocess.check_call(
        [
            sys.executable,
            str(gen),
            "--out-dir",
            str(shared),
            "--seed",
            "7",
            "--n-genes",
            str(args.n_genes),
            "--n-reads",
            "1000",
            "--read-len",
            str(args.read_len),
        ]
    )
    for p in shared.glob("reads_*.fastq.gz"):
        p.unlink(missing_ok=True)

    raw_shared = shared / "raw"
    for i in range(1, 11):
        did = f"d{i:02d}"
        out = suite / did
        subprocess.check_call(
            [
                sys.executable,
                str(gen),
                "--out-dir",
                str(out),
                "--seed",
                str(100 + i),
                "--n-genes",
                str(args.n_genes),
                "--n-reads",
                str(args.n_reads),
                "--read-len",
                str(args.read_len),
                "--reuse-genome",
                str(raw_shared),
            ]
        )
        print(f"wrote {did}")

    (suite / "README.txt").write_text(
        f"Suite A synthetic Illumina-like PE, n_reads={args.n_reads}, read_len={args.read_len}\n"
        "Shared reference: shared/raw/genome.fa + genes.gtf\n"
        "See ILLUMINA10.md — Suite B (public Illumina) is the graded target.\n"
    )
    print(f"Done → {suite}")


if __name__ == "__main__":
    main()
