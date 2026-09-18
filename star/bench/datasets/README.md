# Datasets (not committed — large)

## Tiny / daily iteration (preferred)

- Genome: chromosome subset (e.g. chr22 or a small synthetic genome)
- Reads: 100k–1M paired-end RNA-seq reads from a public SRA sample, or simulated with `polyester` / `art`

Place files as:

```
bench/datasets/genome/     # STAR --genomeDir output
bench/datasets/reads_1.fastq.gz
bench/datasets/reads_2.fastq.gz
```

## Final claim set

Document the exact SRA accessions + STAR genome generate command in `../docs/SCOPE.md` after professor confirms.

## Generating a STAR genome index (example)

```bash
STAR --runMode genomeGenerate \
  --runThreadN 8 \
  --genomeDir bench/datasets/genome \
  --genomeFastaFiles chr22.fa \
  --sjdbGTFfile chr22.gtf \
  --sjdbOverhang 99
```
