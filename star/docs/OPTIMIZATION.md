# Optimization design — same-output only (Zhang lock)

## Hard constraints
- Output must match stock STAR under **identical CLI flags**
- Fair: same machine, same threads (graded default: **1**)
- ≥2× **wall-clock** end-to-end
- Evaluate on **10** Illumina short-read datasets
- Index built at STAR-recommended `--genomeSAindexNbases` (no oversized-index tricks)

## Graded CLI lock (both binaries)
```
--runThreadN 1
--outSAMtype BAM SortedByCoordinate
--limitBAMsortRAM 4000000000
--readFilesCommand gzcat   # or zcat on Linux
--outBAMcompression 0      # identical on both; shrinks shared BAM zlib fixed cost
```
Only the binary path differs.

## Algorithmic stack (in `star/src/star-2x-verified.patch`)

| Rung | Change | Why |
|------|--------|-----|
| S1 | Bounded `Transcript` exon-row copy (`nExons+1`, clamped) | Stock copied 20 unused padding rows every time |
| S2/S3 | `stitchWindowAligns` takes `Transcript&`; in-place stitch + undo | Removes per-node full object copies |
| S3b | Pre-skip stitches that hit −1000001/−1000002 | ~74% of stitch attempts die on two integer compares |
| S4 | TLS leaf + `adoptStitchState` (no empty STL clone) | Leaf finalize avoids vector/set copy traffic |
| S5 | `stitchAlignToTranscript` does not write before early returns | Enables clean fail paths |
| S6 | Exclude-on-fail as a loop | Cuts tail-recursion overhead |
| S7 | Closed-form `L * scoreMatch` | `scoreMatch` is constexpr 1; stock looped |
| S8 | Leaf insert via `std::move` into window slot | Avoids cloning STL containers on every recorded transcript |

## Build extras (opt binary)
PGO + LTO + `-mcpu=native`, trained on i01–i04; **jemalloc** linked (`-ljemalloc`). Report allocator separately from pure algorithm if asked. On CARC/Linux, install jemalloc or static-link it.

## Rejected / withdrawn
| Idea | Result |
|------|--------|
| Nbases=14 oversized `SAindex` + mmap “2.5×” | **Withdrawn** — rigged baseline |
| Word-at-a-time `compareSeqToGenome` | 0.96× |
| Branch-and-bound stitch prune | 0.7% nodes, no time win |
| mmap SA/SAi on nb10 warm SSD | ~no gain |
| S9 SA→genome `__builtin_prefetch` | No gain / slight loss on small nb10 index (fits cache) |
