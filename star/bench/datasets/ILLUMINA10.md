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

### Graded read subset (locked 2026-09-09)

For each Suite B sample, evaluate on the **first 800 paired-end records** (3200 FASTQ lines per mate), written to `suiteB/<id>/fastq_sub800/`. Full teaching FASTQs remain in `fastq/` for larger-n mapping-only checks.

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

# genomeGenerate with stock 2.7.11b (default --genomeSAindexNbases 14 kept;
# STAR warns it is oversized for 10Mb — intentional for load-dominated regime)
STAR --runMode genomeGenerate --runThreadN 8 \
  --genomeDir "$DEST/genome" \
  --genomeFastaFiles "$DEST/ref/genome.fa" \
  --sjdbGTFfile "$DEST/ref/genes.gtf" \
  --sjdbOverhang 100

# i02–i04 FASTQs same BASE/FASTQ/; share i01 genome via symlink.
```

Fetch script: `star/bench/scripts/fetch_illumina10.sh` (fill URLs as mirrors confirmed).

**Reference:** use the matching species/region FASTA+GTF shipped with each teaching set (human chr1 10Mb for i01–i04; D. melanogaster for i05–i08; organism per nf-core for i09–i10). Speedups are reported **per dataset** with its own index; fairness is stock vs optimized on that same index.

## Suite A — synthetic Illumina-like (harness only)

`gen_illumina10.py` — 10 PE datasets, shared mini genome, different seeds. **Not** sufficient alone for Zhang’s “Illumina” wording; use for CI/dev.

## Protocol per dataset

1. `THREADS=1`, identical CLI for stock and optimized  
2. Wall-clock end-to-end + `compare_outputs.sh`  
3. Pass only if speedup ≥2× **and** output match on that dataset  
4. A-claim requires all ten Suite B datasets (unless Zhang agrees to an aggregate later)
