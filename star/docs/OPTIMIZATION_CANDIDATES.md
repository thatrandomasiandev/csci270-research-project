# Optimization candidates (pre-profile hypotheses)

Final choice **must** follow `perf` on the baseline workload. These are ranked guesses for a scoped ≥2× claim.

## High-probability levers on our synthetic PE workload

1. **BAM coordinate sort** (`--outSAMtype BAM SortedByCoordinate`)  
   Often dominates wall time after mapping. Candidates: unsorted BAM + external `samtools sort` with different thread/mem; or patch STAR sort buffer strategy.  
   *Fairness:* compare same final sorted BAM artifact; quality = same alignments.

2. **Read decompression** (`--readFilesCommand zcat`)  
   Single-threaded gunzip. Try `pigz -dc` or STAR built-in FASTQ reader paths if available. Easy systems win; may not hit 2× alone on CPU-bound align.

3. **Seed / suffix-array query hot loop**  
   Classic algorithmic target in STAR. Needs `perf` confirmation. SIMD / batching / cache tiling are PhD-hard but a **narrow** reimplementation on our small index (`genomeSAindexNbases 10`) can show large speedups for the course benchmark if scoped honestly.

4. **Thread scheduling / OpenMP chunking**  
   Only if profile shows sync/idle time.

## Disallowed for the A claim

- Changing biology filters to map fewer reads and call it “faster”
- Comparing SortedByCoordinate baseline vs Unsorted “optimized” without producing equivalent outputs
- Claiming human-genome 2× from synthetic-only numbers without stating SCOPE limits

## After perf

Update this file with the chosen function names + patch plan in `star/src/`.
