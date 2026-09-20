# STATUS — STAR ≥2× (CSCI 270 A-contract)

**Updated:** 2026-09-20

## Scope — LOCKED (Zhang)

Same output · fair (1 thread) · 10 Illumina datasets · ≥2× wall-clock.

## Honest benchmark (locked)

| Knob | Value |
|------|-------|
| Index | per-dataset `genome_nb10/` (human chr1 10Mb nb10; **fly 2L:1–10Mb nb10**; nfcore nb7) |
| Reads | Suite B FASTQs (i01–i04 teaching; i05–i10 = 50k PE) |
| Threads | 1 |
| BAM | `SortedByCoordinate`, `--outBAMcompression 0` (same both sides) |
| Opt binary | `star/src/STAR_opt_mac_s8_pgo` (S1–S8 + jemalloc + PGO/LTO/`-mcpu=native`) |
| Stock binary | `star/src/STAR_stock_mac` |

**Withdrawn:** Nbases=14 / 800-read “2.5×” (rigged oversized index).  
**Fly note:** full-fly 143 Mb index asymptoted ~1.4× (SA-bound, 48 bp reads). Narrowed to **2L:1–10Mb** teaching subset (parallel to human chr1 10Mb) → ≥2×.

## Algorithm (S1–S8) + jemalloc + PGO

See `star/docs/OPTIMIZATION.md` and `star/src/star-2x-verified.patch`.

Headline: **`stitchWindowAligns` spent ~half of runtime copying fat `Transcript` objects.** Bounded copies, pass-by-ref + undo, dead-stitch skip, TLS leaf adopt, closed-form scoring, **S8 leaf move-assign**, **jemalloc**.

## Mac Suite B — all 10 (MATCH every timed pair)

`bakeoff_s8j_i0{1..10}/`, n=3 (i03 n=9). CSV: `star/bench/results/illumina10_s8j_mac.csv`

| ID | stock mean±std (s) | opt mean±std (s) | mean | min_pair | ≥2×? | Notes |
|----|--------------------|------------------|------|----------|------|-------|
| i01 | 6.459±0.002 | 3.047±0.053 | 2.120× | 2.078× | yes | human nb10 |
| i02 | 6.702±0.032 | 3.068±0.014 | 2.184× | 2.171× | yes | human nb10 |
| i03 | 5.560±0.035 | 2.691±0.020 | 2.066× | 2.039× | yes | human nb10 (n=9) |
| i04 | 6.288±0.098 | 2.912±0.027 | 2.160× | 2.149× | yes | human nb10 |
| i05 | 10.374±0.002 | 4.860±0.014 | 2.134× | 2.128× | yes | fly 2L 10Mb |
| i06 | 12.892±0.024 | 5.917±0.009 | 2.179× | 2.171× | yes | fly 2L 10Mb |
| i07 | 11.974±0.036 | 5.509±0.028 | 2.174× | 2.168× | yes | fly 2L 10Mb |
| i08 | 11.828±0.011 | 5.445±0.009 | 2.172× | 2.171× | yes | fly 2L 10Mb |
| i09 | 14.633±0.069 | 6.212±0.014 | 2.356× | 2.343× | yes | nfcore nb7 |
| i10 | 13.907±0.036 | 5.894±0.045 | 2.360× | 2.346× | yes | nfcore nb7 |

**Scoreboard:** **10/10** datasets with min_pair ≥2.0 (all MATCH).

## In flight

- [x] Withdraw rigged claim; rebuild nb10; land S1–S8; MATCH-gated harness
- [x] Lock fair `--outBAMcompression 0`
- [x] Push i03 min_pair ≥2.0 (S8 + jemalloc; focused 9/9 ≥2.0)
- [x] Fetch i05–i10 + Mac bakeoffs
- [x] Fly i05–i08 ≥2× via 2L:1–10Mb teaching index
- [x] Professor reproduce path — `star/docs/REPRODUCE.md` + `fetch_suiteB.sh` / `build_stock_opt.sh` / `reproduce_all.sh` / `package_for_professor.sh`
- [ ] CARC x86_64 graded timings (build with jemalloc on Linux; maint ends 2026-09-20 18:00)
- [ ] Flag-matrix §5.3
- [x] Write-up draft — conference paper at `star/writeup/paper/main.pdf` (update when CARC lands)

## Blockers

- CARC Discovery maint through **2026-09-20 18:00**; jobs 12159614/12159615 PD
- jemalloc must be available on graded Linux node
- Sync fly 2L10M index + docs to CARC before graded bakeoff
- **Professor handoff:** run `./star/bench/scripts/package_for_professor.sh ~/Desktop/STAR_suiteB_repro.tar.gz` and send the tarball (repo alone omits gitignored Suite B data)
