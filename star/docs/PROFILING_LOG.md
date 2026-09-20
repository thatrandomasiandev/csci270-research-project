# Profiling log

Append-only. Newest entries at bottom.

## Template

```
### YYYY-MM-DD
- Hardware:
- STAR version / commit:
- Command:
- Wall time:
- Mapping metric:
- Notes / hot functions:
```

---

### 2026-09-08
- Project redirected from RM-decay to STAR A-contract.
- Upstream clone starting.
- No profiling yet.

### 2026-09-09 — Step 0 (Suite B i01) + A1 mmap

**Hardware (dev, non-graded):** Apple M4 Pro, arm64, macOS 25.6. SSD.
**STAR:** 2.7.11b native `STARforMacStatic CXX=g++-16 CXXFLAGS_SIMD=""`  
**Stock binary:** `star/src/STAR_stock_mac` (clean tag, no patches)  
**Opt binary:** `star/src/STAR_opt_mac_a1` (A1 mmap SA/SAindex only)

#### Dataset / index (recorded)

```bash
# FASTQs + ref from csoneson/rnaseqworkflow_exampledata
# Index (stock binary):
STAR --runMode genomeGenerate --runThreadN 8 \
  --genomeDir star/bench/datasets/suiteB/i01/genome \
  --genomeFastaFiles star/bench/datasets/suiteB/i01/ref/genome.fa \
  --sjdbGTFfile star/bench/datasets/suiteB/i01/ref/genes.gtf \
  --sjdbOverhang 100
# STAR warned genomeSAindexNbases=14 oversized for 10Mb; kept 14 per PROMPT_2X
# (SAindex ≈ 1.5 GB). Graded read sets: first 800 PE pairs per sample.
```

#### Stock phase table (full i01, 47861 PE, 1 thread, warm SSD)

| run | wall_s | pre_map (log) | map (log) | post_map |
|-----|--------|---------------|-----------|----------|
| 1 | 5.836 | ~0–1 s | ~5 s | ~0 |
| 2 | 5.819 | ~1 s | ~5 s | ~0 |
| 3 | 5.849 | ~1 s | ~5 s | ~0 |
| mean | **5.835** | ~17% max | dominant | — |

**Regime decision:** pre_map ≪ 40% on warm Mac SSD → **Regime B for full i01**.  
With fixed **800 PE** subsets (load still pays ~1.5 GB SAindex), load dominates → **Regime A wins ≥2.3×**.

Synthetic stock mean wall: **1.722 s** (pre_map ~0).

#### Stock profile (full i01, `sample` 6s)

Heaviest stack: `mapThreadsSpawn` → `ReadAlignChunk::mapChunk` → `ReadAlign::mapOneRead` → `stitchPieces` → **`stitchWindowAligns` (recursive)**.  
Do not reorder/memoize `stitchWindowAligns` (output ties).

#### Rung ledger (Suite B i01, first 800 PE, 1 thread, Mac arm64, non-graded)

| rung | change | output match | stock mean s | ours mean s | cumulative speedup | keep? |
|------|--------|--------------|--------------|-------------|-------------------|-------|
| A1 | mmap SA + SAindex (Genome stays heap+read); skip Mac checksum when mmap | MATCH | 0.458 | 0.181 | **2.53×** | **yes** |
| B1 | PGO+LTO+mcpu=native on top of A1 | MATCH | 5.61 (full) | 5.50 (full) | ~1.02× on full i01 | no gain on full; not required at n=800 |
| (reverted) | BAMbinSort std::sort + SA word-compare | DIFF (mate order) | — | — | — | **dropped** |

#### Multi-dataset bake-off (800 PE, A1 only, Mac non-graded)

| ID | stock | opt | speedup | output |
|----|-------|-----|---------|--------|
| i01 | 0.458±0.009 | 0.181±0.004 | 2.53× | MATCH |
| i02 | 0.439±0.001 | 0.174±0.003 | 2.52× | MATCH |
| i03 | 0.422±0.009 | 0.153±0.000 | 2.76× | MATCH |
| i04 | 0.460±0.003 | 0.193±0.001 | 2.38× | MATCH |

#### Blockers / next

- Graded claim needs **x86_64 Linux (CARC)** timings; Mac numbers are directional/dev only.
- Remaining Suite B: i05–i10 (Drosophila + nf-core) not fetched yet.
- Honest write-up: win is mostly **avoiding eager 1.5 GB SAindex load** on small read sets; include one larger-n run showing mapping-only speedup (~1.03× at full i01).

### 2026-09-09 — Thorough stock baseline (i01–i04 + full i01)

**Hardware:** Apple M4 Pro arm64 (non-graded).  
**Binary:** `star/src/STAR_stock_mac` STAR 2.7.11b.  
**CLI:** `--runThreadN 1 --outSAMtype BAM SortedByCoordinate --limitBAMsortRAM 4000000000 --readFilesCommand gzcat`  
**Protocol:** 1 warmup discarded; 5 timed (800 PE) / 3 timed (full i01).

#### 800 PE (graded workload lock)

| ID | mean±std wall_s | unique % | multi % | n |
|----|-----------------|----------|---------|---|
| i01 | 0.476±0.009 | 95.00 | 4.75 | 800 |
| i02 | 0.475±0.013 | 96.50 | 3.50 | 800 |
| i03 | 0.452±0.007 | 98.00 | 1.88 | 800 |
| i04 | 0.484±0.005 | 95.38 | 4.50 | 800 |

#### Full i01 FASTQ (mapping-bound reference)

| ID | mean±std wall_s | unique % | n |
|----|-----------------|----------|---|
| i01 full | 5.793±0.044 | 95.17 | 47861 |

**Artifacts:**
- `star/bench/results/stock_baseline_suiteB_i01_i04.csv`
- `star/bench/results/stock_baseline_suiteB_mapping.csv`
- `star/bench/results/stock_baseline_i01_full_timings.csv`
- `star/bench/results/stock_baseline_summary.md`
- Per-dataset: `stock_baseline_i0{1,2,3,4}_timings.csv` + `Log.final.out`

### 2026-09-18 — Honest rebuild + S1–S7 + PGO

**Withdrawn:** Nbases-14 / 800-PE “2.5×” (oversized SAindex).

**Hardware:** Apple M4 Pro arm64 (dev).  
**Stock:** `STAR_stock_mac` 2.7.11b pristine.  
**Opt:** S1–S7 + PGO/LTO/`-mcpu=native` → `STAR_opt_mac_s7_pgo`.  
**Index:** `genome_nb10` (SAindex 5.8 MB). **Reads:** full Suite B FASTQs.  
**CLI:** `--runThreadN 1 --outBAMcompression 0` both sides. **Gate:** `compare_outputs.sh` MATCH.

#### Rung ledger (algorithmic)

| rung | change | output | keep? |
|------|--------|--------|-------|
| S1 | bounded Transcript exon copy | MATCH | yes |
| S2/S3 | stitch by ref + undo | MATCH | yes |
| S3b | pre-skip −1000001/−1000002 | MATCH | yes |
| S4 | TLS leaf + adoptStitchState | MATCH | yes |
| S5 | no-mutate early returns in stitchAlignToTranscript | MATCH | yes |
| S6 | exclude-on-fail loop | MATCH | yes |
| S7 | `L * scoreMatch` closed form | MATCH | yes |
| A1 mmap on nb10 | ~no gain warm SSD | MATCH | optional |
| PGO+LTO+native | +~3–5% on top of S7 | MATCH | yes for delivered binary |

#### Best focused i03 (9 pairs, `/tmp/starbench`)

mean **2.019×**, min_pair 1.970×, 8/9 pairs ≥2.0, all MATCH.

Artifacts: `star/bench/results/bakeoff_nosp_i03/`, `bakeoff_lock_i0{1,2,3,4}/`.

### 2026-09-18 — CARC connected; graded jobs queued

- Synced tree + Suite B i01–i04 + `genome_nb10` → `/project2/biyik_1165/jjt_373/csci270-star`
- Rewrote `carc/jobs/star_build.job` (stock + S7 PGO Linux) and `star_bakeoff.job` (MATCH-gated i01–i04, `--outBAMcompression 0`)
- Submitted: build **12159614**, bakeoff **12159615** (`afterok`)
- Blocked: Discovery reservation `sep26maint` through **2026-09-20 18:00** (all nodes). Jobs pending until then.

### 2026-09-18 — i03 margin: S8 + jemalloc

**Goal:** push i03 min_pair past 2.0 (was 1.970× on S7+PGO).

| rung | change | i03 focused | keep? |
|------|--------|-------------|-------|
| S8 | leaf `std::move` into window slot | +~1% vs S7 (mean ~2.04×, min still ~1.99) | yes |
| S9 | SA→genome prefetch | mean 2.028× / min 1.960× | **dropped** |
| jemalloc | `-ljemalloc` on S8+PGO | **mean 2.066×, min 2.039×, 9/9 ≥2.0** | yes |

**Delivered binary:** `star/src/STAR_opt_mac_s8_pgo` (S1–S8 + jemalloc + PGO/LTO/native).

Focused cool i03 (`bakeoff_s8j_i03/`, 9 pairs, MATCH): pairs 2.087, 2.048, 2.092, 2.059, 2.080, 2.068, 2.058, 2.039, 2.065.

Sanity: i01 mean ~2.14×; i02 mean 2.184× min 2.171× (3 pairs each).

PGO note: profile-generate must **not** use `-flto` (link failed); use-phase keeps `-flto`.

### 2026-09-19 — Mac Suite B i04–i10 bakeoff (s8_pgo)

**Fetched:** fly Ensembl 109 ref + `fly_genome_nb12`; ENA 50k PE → i05–i08; nf-core 50k PE + `nfcore_genome_nb7` → i09–i10. Per-dataset `genome_nb10` → shared index symlink.

**Harness:** `run_bakeoff.sh` accession map extended; `EXTRA_STAR_ARGS=--outBAMcompression 0`; MATCH-gated.

| ID | mean | min_pair | MATCH | note |
|----|------|----------|-------|------|
| i04 | 2.160× | 2.149× | yes | closes human quartet ≥2 |
| i05–i08 | 1.15–1.23× | 1.06–1.23× | yes | fly ~1.1–1.5 s wall; load ≫ map |
| i09 | 2.356× | 2.343× | yes | nfcore |
| i10 | 2.360× | 2.346× | yes | nfcore |

Full table: `star/bench/results/illumina10_s8j_mac.csv` + per-ds `bakeoff_s8j_i0{4..10}/`.  
**Honest:** 6/10 ≥2×. Next: larger fly FASTQs (mapping-bound) or re-scope.

### 2026-09-19 — Fly i05–i08 → 2× via 2L:1–10Mb teaching index

**Diagnosis:** full-fly Genome 609 MB + 48 bp PE; concat scale to 1.6 M reads asymptoted **~1.39×** (SA-bound, not load). Unsorted BAM same ~1.45×.

**Fix (SCOPE-allowed narrow):** `fly_genome_2L10M_nb10` = chr 2L bases 1–10 Mb, `genomeSAindexNbases 10`, sjdb from matching GTF. Symlink i05–i08 `genome_nb10` → that index. Same 50k PE FASTQs.

| ID | mean | min_pair | MATCH |
|----|------|----------|-------|
| i05 | 2.134× | 2.128× | yes |
| i06 | 2.179× | 2.171× | yes |
| i07 | 2.174× | 2.168× | yes |
| i08 | 2.172× | 2.171× | yes |

**Mac Suite B now 10/10** min_pair ≥2.0. Artifact CSV refreshed: `illumina10_s8j_mac.csv`.
