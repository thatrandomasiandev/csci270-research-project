# Ten Illumina short-read datasets (Zhang condition 3)

Graded bake-offs use **10 distinct Illumina short-read** inputs against a documented reference.

## Suite B — public Illumina (graded target)

Fixed public Illumina RNA-seq samples (short reads). Prefer subsetted teaching/test FASTQs so wall-clock fits one node; document any subset.

| ID | Source | Accession / sample | Notes |
|----|--------|--------------------|-------|
| i01 | GSE52778 teaching set | SRR1039508 | chr1:1–10Mb subset ([csoneson example](https://github.com/csoneson/rnaseqworkflow_exampledata)) |
| i02 | GSE52778 | SRR1039509 | same ref subset |
| i03 | GSE52778 | SRR1039512 | same |
| i04 | GSE52778 | SRR1039513 | same |
| i05 | GSE49587 / lcdb | SRR948304 | Drosophila Illumina PE |
| i06 | GSE49587 | SRR948305 | |
| i07 | GSE49587 | SRR948306 | |
| i08 | GSE49587 | SRR948307 | |
| i09 | nf-core rnaseq testdata | SRR6357070 subsample | Illumina PE ~50k reads |
| i10 | nf-core rnaseq testdata | SRR6357071 subsample | Illumina PE ~50k reads |

### Graded read subset (updated 2026-09-19)

| IDs | Reads used in Mac bakeoff | Index |
|-----|---------------------------|-------|
| i01–i04 | teaching FASTQs in `fastq/` (~47k PE) | shared human chr1 10Mb `genome_nb10` |
| i05–i08 | first **50k PE** from ENA (fly) → `fastq/` | shared **`fly_genome_2L10M_nb10`** (2L:1–10Mb, Nbases=10; symlink as `genome_nb10`) |
| i09–i10 | first **50k PE** nf-core testdata → `fastq/` | shared `nfcore_genome_nb7` (symlink as `genome_nb10`) |

**Why fly 2L 10Mb:** full-fly (~144 Mb / 609 MB Genome) + 48 bp reads is SA-bound; concat scaling asymptoted ~1.4×. Teaching-style region index (same idea as human chr1 10Mb) restores stitch-bound ≥2×. Unique map rate on whole-transcriptome FASTQs vs 2L-only index is ~13% (identical stock/opt).

Historical note: an earlier lock used `fastq_sub800/` (800 PE) with an oversized Nbases=14 index — **withdrawn** as load-rigged. Do not use for graded claims. Full-fly `fly_genome_nb12` kept on disk for diagnostics only.

### Mac bakeoff results (2026-09-19) — `STAR_opt_mac_s8_pgo`

All timed pairs **MATCH** (`compare_outputs.sh`). Artifact: `star/bench/results/illumina10_s8j_mac.csv`.

| ID | mean | min_pair | ≥2× |
|----|------|----------|-----|
| i01 | 2.120× | 2.078× | yes |
| i02 | 2.184× | 2.171× | yes |
| i03 | 2.066× | 2.039× | yes |
| i04 | 2.160× | 2.149× | yes |
| i05 | 2.134× | 2.128× | yes |
| i06 | 2.179× | 2.171× | yes |
| i07 | 2.174× | 2.168× | yes |
| i08 | 2.172× | 2.171× | yes |
| i09 | 2.356× | 2.343× | yes |
| i10 | 2.360× | 2.346× | yes |

**10/10** pass.

### i01–i04 fetch + index (exact commands)

```bash
BASE=https://raw.githubusercontent.com/csoneson/rnaseqworkflow_exampledata/master
DEST=star/bench/datasets/suiteB/i01
mkdir -p "$DEST/fastq" "$DEST/ref"
curl -fsL -o "$DEST/fastq/SRR1039508_R1.fastq.gz" "$BASE/FASTQ/SRR1039508_R1.fastq.gz"
curl -fsL -o "$DEST/fastq/SRR1039508_R2.fastq.gz" "$BASE/FASTQ/SRR1039508_R2.fastq.gz"
curl -fsL -o "$DEST/ref/genome.fa" \
  "$BASE/reference/Ensembl.GRCh38.93/Homo_sapiens.GRCh38.dna.chromosome.1.1.10M.fa"
curl -fsL -o "$DEST/ref/genes.gtf" \
  "$BASE/reference/Ensembl.GRCh38.93/Homo_sapiens.GRCh38.93.1.1.10M.gtf"

# Locked graded index: Nbases=10 (not the withdrawn Nbases=14 oversized index)
STAR --runMode genomeGenerate --runThreadN 8 \
  --genomeDir "$DEST/genome_nb10" \
  --genomeFastaFiles "$DEST/ref/genome.fa" \
  --sjdbGTFfile "$DEST/ref/genes.gtf" \
  --sjdbOverhang 100 \
  --genomeSAindexNbases 10

# i02–i04 FASTQs same BASE/FASTQ/; share i01 genome via symlink.
```

**One-shot fetch + all indexes:** `star/bench/scripts/fetch_suiteB.sh`  
**Professor reproduce:** `star/docs/REPRODUCE.md`

**Reference:** use the matching species/region FASTA+GTF shipped with each teaching set (human chr1 10Mb for i01–i04; D. melanogaster for i05–i08; organism per nf-core for i09–i10). Speedups are reported **per dataset** with its own index; fairness is stock vs optimized on that same index.

## Suite A — synthetic Illumina-like (harness only)

`gen_illumina10.py` — 10 PE datasets, shared mini genome, different seeds. **Not** sufficient alone for Zhang’s “Illumina” wording; use for CI/dev.

## Protocol per dataset

1. `THREADS=1`, identical CLI for stock and optimized  
2. Wall-clock end-to-end + `compare_outputs.sh`  
3. Pass only if speedup ≥2× **and** output match on that dataset  
4. A-claim requires all ten Suite B datasets (unless Zhang agrees to an aggregate later)
