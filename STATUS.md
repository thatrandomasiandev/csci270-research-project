# STATUS — STAR ≥2× (CSCI 270 A-contract)

**Updated:** 2026-09-18 ~15:05 PDT

## Scope — LOCKED (Zhang)

Same output · fair (1 thread) · 10 Illumina datasets · ≥2× wall-clock.

## Honest benchmark (locked)

| Knob | Value |
|------|-------|
| Index | `genome_nb10/` (`--genomeSAindexNbases 10`, SAindex ≈ 5.8 MB) |
| Reads | **Full** Suite B FASTQs (i01–i04) |
| Threads | 1 |
| BAM | `SortedByCoordinate`, `--outBAMcompression 0` (same both sides) |
| Opt binary | `star/src/STAR_opt_mac_s8_pgo` (S1–S8 + jemalloc + PGO/LTO/`-mcpu=native`) |
| Stock binary | `star/src/STAR_stock_mac` |

**Withdrawn:** Nbases=14 / 800-read “2.5×” (rigged oversized index).

## Algorithm (S1–S8) + jemalloc + PGO

See `star/docs/OPTIMIZATION.md` and `star/src/star-2x-verified.patch`.

Headline: **`stitchWindowAligns` spent ~half of runtime copying fat `Transcript` objects.** Bounded copies, pass-by-ref + undo, dead-stitch skip, TLS leaf adopt, closed-form scoring, **S8 leaf move-assign**, **jemalloc**.

## Latest Mac results (MATCH every timed pair)

Focused cool i03 (9 pairs, `/tmp/starbench`, comp=0) — **S8 + jemalloc + PGO**:

| Metric | Value |
|--------|-------|
| mean speedup | **2.066×** |
| min_pair | **2.039×** (9/9 pairs ≥2.0) |
| output | MATCH |

Sanity (same binary):

| ID | n | mean | min_pair |
|----|---|------|----------|
| i01 | 3 | 2.120× | 2.078× |
| i02 | 3 | 2.184× | 2.171× |
| i03 | 9 | 2.066× | 2.039× |

Prior S7-only focused i03 was mean 2.019× / min 1.970× (8/9 ≥2.0).

**Verdict:** i03 min_pair margin restored past 2.0. Still need i05–i10 + CARC (link jemalloc there too).

## In flight

- [x] Withdraw rigged claim; rebuild nb10; land S1–S7; MATCH-gated harness
- [x] Lock fair `--outBAMcompression 0`
- [x] Push i03 min_pair ≥2.0 (S8 + jemalloc; focused 9/9 ≥2.0)
- [ ] Fetch i05–i10
- [ ] CARC x86_64 graded timings (build with jemalloc on Linux)
- [ ] Flag-matrix §5.3
- [x] Write-up draft — conference paper at `star/writeup/paper/main.pdf` (update when i05–i10 + CARC land)

## Blockers

- Josh: CARC VPN/Duo
- jemalloc must be available on graded Linux node (Homebrew/apt/`-static`)
