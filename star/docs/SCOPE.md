# SCOPE — locked with Zhang (2026-09-08)

## Professor confirmation (verbatim conditions)

Zhang confirmed an **A** if all four hold:

1. **Same output as STAR** — our program’s output must match STAR’s (not merely “similar mapping rate”).
2. **Fair comparison** — same machine, same thread count (he suggests **1 thread** each).
3. **Ten Illumina short-read datasets** — evaluate on **10 different** Illumina short-read datasets.
4. **≥2× wall-clock** — total runtime from receiving input to producing output.

## Graded claim

On a fixed machine **M**, with **`--runThreadN 1`**, our optimized STAR build achieves **≥2×** lower wall-clock than stock STAR **2.7.11b** on each of **10 Illumina short-read datasets**, with **byte-equivalent or alignment-equivalent output** as defined below.

## Output equivalence (how we prove “same as STAR”)

Primary check (preferred): after forcing identical CLI flags (including BAM compression),

- Compare coordinate-sorted BAM via `samtools view` / `cmp` on uncompressed SAM records **or** `diff` of `samtools view -h` streams (header `@PG`/`@CO` lines that embed binary path/version may be normalized).

Fallback if BAM tooling differs only in headers: same number of alignments, same QNAME→(RNAME,POS,CIGAR,FLAG,MAPQ,SEQ) tuples for every read.

**Disallowed for the graded claim:** changing defaults that alter alignments or BAM payload (e.g. different `seedSearchStartLmax`, `outBAMcompression`, unsorted vs sorted).

## Fairness protocol

| Item | Rule |
|------|------|
| Threads | Identical; default graded runs use **1** |
| Machine | Same node / VM for stock and optimized |
| Flags | Identical CLI except binary path |
| Input | Same FASTQs + same prebuilt genome index |
| Timing | Wall-clock of full STAR process (input → final BAM) |
| Warmup | Optional discard of first cold run; report mean of ≥3 timed runs per dataset |

## Datasets

Ten Illumina short-read RNA-seq (or DNA SE/PE Illumina) sets — see `star/bench/datasets/ILLUMINA10.md`. Prefer public SRA/ENA with fixed accessions; subsets allowed if documented and fixed.

## In scope

- Internal speedups that preserve STAR’s output under the same flags
- Harness, timings CSV, output-diff checks, course write-up

## Out of scope

- Claiming 2× via more threads than stock
- “Faster but different BAM compression / seed density” as the A claim
- RM-decay / RL archive work

## Confirmed by Zhang

- **Date:** 2026-09-08  
- **Notes:** Four conditions above; single-thread example; 10 Illumina short-read datasets; wall-clock end-to-end.
