#!/usr/bin/env python3
"""Generate a tiny spliced genome + paired RNA-seq-like FASTQs for STAR iteration.

Creates:
  bench/datasets/raw/genome.fa
  bench/datasets/raw/genes.gtf
  bench/datasets/reads_1.fastq.gz
  bench/datasets/reads_2.fastq.gz
"""

import argparse
import gzip
import random
from pathlib import Path
from typing import List, Tuple


def rand_dna(n: int, rng: random.Random) -> str:
    return "".join(rng.choice("ACGT") for _ in range(n))


def write_fasta(path: Path, name: str, seq: str, width: int = 80) -> None:
    with path.open("w") as f:
        f.write(f">{name}\n")
        for i in range(0, len(seq), width):
            f.write(seq[i : i + width] + "\n")


def revcomp(s: str) -> str:
    t = str.maketrans("ACGTNacgtn", "TGCANtgcan")
    return s.translate(t)[::-1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=Path("star/bench/datasets"))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--n-genes", type=int, default=200)
    ap.add_argument("--n-reads", type=int, default=200_000)
    ap.add_argument("--read-len", type=int, default=100)
    ap.add_argument("--frag-mean", type=int, default=300)
    ap.add_argument(
        "--reuse-genome",
        type=Path,
        default=None,
        help="Reuse existing genome.fa + genes.gtf from this raw/ directory (reads only)",
    )
    args = ap.parse_args()

    rng = random.Random(args.seed)
    raw = args.out_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    if args.reuse_genome is not None:
        src = args.reuse_genome
        fa = raw / "genome.fa"
        gtf = raw / "genes.gtf"
        fa.write_text((src / "genome.fa").read_text())
        gtf.write_text((src / "genes.gtf").read_text())
        # Parse simple chrSyn FASTA
        lines = fa.read_text().splitlines()
        chrom = "".join(L.strip() for L in lines if not L.startswith(">"))
        # Rebuild transcript mats from GTF exons (paired consecutive exons per transcript)
        from collections import defaultdict

        exons = defaultdict(list)
        for line in gtf.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            f = line.split("\t")
            if len(f) < 9 or f[2] != "exon":
                continue
            attrs = f[8]
            tid = None
            for part in attrs.split(";"):
                part = part.strip()
                if part.startswith("transcript_id"):
                    tid = part.split('"')[1]
                    break
            if tid:
                # GTF 1-based inclusive → 0-based half-open
                exons[tid].append((int(f[3]) - 1, int(f[4])))
        mats = []
        for tid, spans in exons.items():
            spans = sorted(spans)
            mats.append("".join(chrom[s:e] for s, e in spans))
        if not mats:
            raise SystemExit("reuse-genome: no exons parsed from GTF")
    else:
        # Build chrom as intergenic + genes (exon-intron-exon)
        parts = []  # type: List[str]
        gtf_lines = []  # type: List[str]

        chrom_pos = 0
        transcript_exons = []  # type: List[Tuple[str, int, int, int, int]]
        # (gene_name, e1_start, e1_end, e2_start, e2_end) 0-based half-open in final chrom

        for g in range(args.n_genes):
            inter = rand_dna(rng.randint(200, 800), rng)
            parts.append(inter)
            chrom_pos += len(inter)

            e1 = rand_dna(rng.randint(80, 200), rng)
            intron = rand_dna(rng.randint(100, 500), rng)
            e2 = rand_dna(rng.randint(80, 200), rng)

            e1_s = chrom_pos
            parts.append(e1)
            chrom_pos += len(e1)
            e1_e = chrom_pos

            parts.append(intron)
            chrom_pos += len(intron)

            e2_s = chrom_pos
            parts.append(e2)
            chrom_pos += len(e2)
            e2_e = chrom_pos

            gname = f"G{g:04d}"
            transcript_exons.append((gname, e1_s, e1_e, e2_s, e2_e))
            # GTF is 1-based inclusive
            gtf_lines.append(
                f"chrSyn\tsynth\tgene\t{e1_s+1}\t{e2_e}\t.\t+\t.\tgene_id \"{gname}\"; gene_name \"{gname}\";"
            )
            gtf_lines.append(
                f"chrSyn\tsynth\ttranscript\t{e1_s+1}\t{e2_e}\t.\t+\t.\tgene_id \"{gname}\"; transcript_id \"{gname}.1\";"
            )
            gtf_lines.append(
                f"chrSyn\tsynth\texon\t{e1_s+1}\t{e1_e}\t.\t+\t.\tgene_id \"{gname}\"; transcript_id \"{gname}.1\"; exon_number \"1\";"
            )
            gtf_lines.append(
                f"chrSyn\tsynth\texon\t{e2_s+1}\t{e2_e}\t.\t+\t.\tgene_id \"{gname}\"; transcript_id \"{gname}.1\"; exon_number \"2\";"
            )

        parts.append(rand_dna(1000, rng))
        chrom = "".join(parts)

        fa = raw / "genome.fa"
        gtf = raw / "genes.gtf"
        write_fasta(fa, "chrSyn", chrom)
        gtf.write_text("\n".join(gtf_lines) + "\n")

        # Mature transcript sequences for sampling
        mats = []  # type: List[str]
        for _, e1_s, e1_e, e2_s, e2_e in transcript_exons:
            mats.append(chrom[e1_s:e1_e] + chrom[e2_s:e2_e])

    r1_path = args.out_dir / "reads_1.fastq.gz"
    r2_path = args.out_dir / "reads_2.fastq.gz"
    rl = args.read_len

    with gzip.open(r1_path, "wt") as f1, gzip.open(r2_path, "wt") as f2:
        for i in range(args.n_reads):
            mat = mats[rng.randrange(len(mats))]
            if len(mat) < rl + 50:
                continue
            frag = min(len(mat), max(rl + 20, int(rng.gauss(args.frag_mean, 40))))
            frag = min(frag, len(mat))
            start = rng.randint(0, len(mat) - frag)
            fragment = mat[start : start + frag]
            # PE: read1 from 5' of fragment, read2 revcomp of 3'
            s1 = fragment[:rl]
            s2 = revcomp(fragment[-rl:])
            # light substitution noise
            def mutate(s: str) -> str:
                out = []
                for c in s:
                    if rng.random() < 0.001:
                        out.append(rng.choice("ACGT"))
                    else:
                        out.append(c)
                return "".join(out)

            s1, s2 = mutate(s1), mutate(s2)
            q = "I" * rl
            f1.write(f"@synth.{i}/1\n{s1}\n+\n{q}\n")
            f2.write(f"@synth.{i}/2\n{s2}\n+\n{q}\n")

    meta = args.out_dir / "SYNTH_META.txt"
    meta.write_text(
        f"seed={args.seed}\nn_genes={args.n_genes}\nn_reads={args.n_reads}\n"
        f"read_len={args.read_len}\ngenome_bp={len(chrom)}\n"
        f"fasta={fa}\ngtf={gtf}\nreuse_genome={args.reuse_genome}\n"
    )
    print(f"Wrote {fa} ({len(chrom)} bp), {gtf}, {r1_path}, {r2_path}")


if __name__ == "__main__":
    main()
