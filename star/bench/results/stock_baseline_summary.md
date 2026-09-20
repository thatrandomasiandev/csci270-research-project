# Stock STAR baseline (dev Mac — non-graded)

**Date:** 2026-09-09 ~18:33 PDT  
**Hardware:** Apple M4 Pro arm64, macOS 25.6  
**Binary:** `star/src/STAR_stock_mac` (STAR 2.7.11b, native Mac build)  
**Protocol:** `--runThreadN 1`, BAM SortedByCoordinate, `limitBAMsortRAM=4e9`, `gzcat`  
**Timing:** 1 warmup discarded + 5 timed runs (800 PE) / 3 timed (full i01)  
**Index:** human chr1 1–10Mb, `--genomeSAindexNbases 14` (shared via symlink for i02–i04)

## Graded workload lock — first 800 PE

| ID | stock mean±std s (n=5) | uniquely mapped % | multi % | input reads |
|----|------------------------|-------------------|---------|-------------|
| i01 | 0.476±0.009 | 95.00 | 4.75 | 800 |
| i02 | 0.475±0.013 | 96.50 | 3.50 | 800 |
| i03 | 0.452±0.007 | 98.00 | 1.88 | 800 |
| i04 | 0.484±0.005 | 95.38 | 4.50 | 800 |

Raw timings: `stock_baseline_suiteB_i01_i04.csv`  
Mapping rates: `stock_baseline_suiteB_mapping.csv`

## Mapping-bound reference — full i01 FASTQ

| ID | stock mean±std s (n=3) | uniquely mapped % | input reads |
|----|------------------------|-------------------|-------------|
| i01 full | 5.793±0.044 | 95.17 | 47861 |

Raw: `stock_baseline_i01_full_timings.csv`

## Figures

All under `star/bench/results/figures/`.

### Honest (use these)

Regenerate: `python3 star/bench/scripts/plot_bakeoff.py`

| File | Content |
|------|---------|
| `honest_stock_vs_opt_wall.png` | Stock vs opt wall (bakeoff_lock i01–i04) |
| `honest_speedup.png` | Mean speedup + min-pair tick vs 2× |
| `honest_per_pair_speedup.png` | Per-pair scatter (paper appendix) |
| `honest_s8j_wall_and_speedup.png` | STATUS S8+jemalloc i01–i03 |

### Withdrawn / directional (800 PE, Nbases=14)

| File | Content |
|------|---------|
| `stock_baseline_wall_800pe.png` | Stock mean±std wall time, i01–i04 |
| `stock_baseline_mapping_800pe.png` | Unique / multi / other mapping fractions |
| `stock_baseline_runs_800pe.png` | Per-run scatter + mean |
| `stock_i01_800_vs_full.png` | 800 PE vs full i01 stock wall time |
| `bakeoff_stock_vs_opt_800pe.png` | Stock vs A1 mmap paired bars |
| `bakeoff_speedup_800pe.png` | Speedup vs 2× claim line |

## Notes

- Mac numbers are **dev / directional only**; graded claim needs CARC x86_64 Linux.
- Phase parser returns NA on sub-second STAR log timestamps (second resolution); wall clock from Python `time.time()` is authoritative.
- STAR `Could not ls` warnings on paths with spaces are cosmetic; reads still map.
