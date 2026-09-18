# Agent prompt — get STAR to ≥2× wall-clock at identical output

Paste everything below the line into a fresh agent session (Cursor or Claude Code) opened at the repo root.

---

You are working in `star/` of this repo. Read `AGENTS.md`, `STATUS.md`, and `star/docs/SCOPE.md` first. Your single job: make our build of STAR 2.7.11b run in **≤ half the wall-clock** of the stock STAR 2.7.11b binary, at **1 thread**, with **identical CLI flags** and **identical alignment output**, on the ten Illumina datasets in `star/bench/datasets/ILLUMINA10.md`. Nothing else counts. Do not stop at "faster"; stop at "≥2.0× on every dataset, output match on every dataset", or at a documented blocker only Josh can clear.

## Hard rules (Zhang's grading contract, non-negotiable)

1. **Same output.** After `samtools view -h` with `@PG`/`@CO` header lines stripped, stock and optimized BAM streams must be byte-identical. `star/bench/scripts/compare_outputs.sh` does this check. Compressed BAM bytes may differ; decompressed records may not. `Log.out` / `Log.progress.out` may differ.
2. **Same flags, same threads.** Both sides run the exact command in `run_baseline.sh` with `--runThreadN 1`. Never change `--outBAMcompression`, seed parameters, `--readFilesCommand`, sort mode, `--genomeLoad`, or anything else on only one side. The only difference between the two commands is the binary path.
3. **Wall-clock end to end**, process start to final BAM. Mean of ≥3 timed runs after one discarded warm-up run, per dataset, per binary.
4. **Ten Illumina datasets.** The synthetic set in `bench/datasets/` is for iteration only. The claim is made on Suite B.

Anything that violates a rule is worth zero, so revert it immediately even if it is faster.

## What is already known (do not rediscover this)

- **Every timing number in `STATUS.md` so far is invalid for the claim.** They came from Docker `linux/amd64` on an Apple M4 Pro, which runs x86 under emulation. Emulated timings do not transfer, and hardware `perf` counters are unavailable there. Graded numbers must come from a real x86_64 Linux node (CARC Discovery via `carc/`), or at minimum a native build on this Mac clearly labeled as non-graded.
- **The synthetic benchmark hides the real hot path.** Its genome is 327 kb with `--genomeSAindexNbases 8`, so the whole suffix array sits in L2 cache and genome load is ~0 s. That is why the word-at-a-time `compareSeqToGenome` patch in `upstream/source/SuffixArrayFuns.cpp` measured 0.96×. Do not iterate on that patch. Decide whether to keep it only after profiling on a real index.
- **The two existing patches** (`BAMbinSortByCoordinate.cpp` std::sort, `SuffixArrayFuns.cpp` word compare) are output-safe but gave no measurable win. Keep or drop them based on measurement, not sentiment.
- **The Suite B inputs are small** (tens of thousands to a few hundred thousand reads) while their indexes are real (human chr1 10 Mb subset, D. melanogaster). With the default `--genomeSAindexNbases 14` the `SAindex` file alone is ~1.5 GB and STAR loads `Genome`, `SA`, and `SAindex` eagerly with `new char[]` + `ifstream::read` in `Genome_genomeLoad.cpp`. On small inputs, startup and index loading can be a large fraction of wall-clock. That regime is where ≥2× is most reachable without touching alignment logic, and it is legitimate under the rules because both binaries pay it and the output is unchanged.

## Step 0 — build a measurement rig you can trust (do this before any optimization)

1. **Get one real Suite B dataset locally**: SRR1039508 chr1 subset plus its FASTA/GTF from the csoneson example-data repo listed in `ILLUMINA10.md`, or the nf-core rnaseq test data. Build its STAR index with the stock binary, using the same `genomeGenerate` command you will use for the graded run. Record the exact command in `star/bench/datasets/ILLUMINA10.md`.
2. **Install `samtools`** wherever you benchmark (Docker image, CARC conda env, or Homebrew locally). `compare_outputs.sh` exits 2 without it, and a speed number without an output match is worthless.
3. **Add phase timing to the harness.** STAR writes timestamps to `Log.out` for "loading genome", "started mapping", "finished mapping", "started sorting BAM", "finished successfully". Extend `compare_timings.py` (or add `phase_breakdown.py`) to report, per run: total wall, time before mapping starts, mapping time, sort+finish time. Commit the phase table for stock STAR on the real dataset to `star/docs/PROFILING_LOG.md` before changing any code.
4. **Profile stock STAR at 1 thread on the real dataset**, and separately on the synthetic one, and record the top 15 symbols by self time for each:
   - On CARC: build with `-O2 -g -fno-omit-frame-pointer`, then `perf record -g --call-graph dwarf` and `perf report --no-children --sort sym`.
   - In Docker on this Mac: `perf` will not work under emulation. Use `valgrind --tool=callgrind` + `callgrind_annotate`, accept the slowdown, and treat the result as instruction counts, not time.
   - Natively on this Mac: `make STARforMacStatic CXX=g++-16` (Homebrew gcc 16 is installed) and profile with `sample` or `xcrun xctrace record --template 'Time Profiler'`. Hot symbols are the same on arm64; absolute times are not graded.
5. **Decide the regime from the phase table**, then follow the matching ladder below. If startup + genome load is ≥40% of stock wall-clock on the real dataset, you are in Regime A. Otherwise Regime B. Most likely both ladders are needed to reach 2×; A first because it is cheaper and lower risk.

## The optimization ladder (stack them, measure each rung, keep a ledger)

Each rung must be an independent, revertible commit on `star/upstream/` (or a patch in `star/src/`). After each rung: rebuild, run `compare_outputs.sh` on the real dataset, time 3 runs at 1 thread, and append one ledger row to `PROFILING_LOG.md`:

```
| rung | change | output match | stock mean s | ours mean s | cumulative speedup | keep? |
```

Keep a rung only if output matches and it gains ≥2% on the real dataset. Revert otherwise. Stop adding rungs when cumulative speedup on the real dataset is ≥2.3× (margin for dataset variance), then move to the ten-dataset run.

### Regime A — startup and index loading dominate

A1. **mmap the index files instead of `new` + `ifstream::read`.** In `Genome_genomeLoad.cpp`, `Genome`, `SA`, and `SAindex` are read fully into heap buffers before mapping starts. Replace with read-only private `mmap` so only touched pages are faulted in. Gotchas: STAR needs `L` padding bytes before `G` (`G = G1 + L`, see the `new char[nGenome+L+L]` lines); reserve an anonymous region, map the file with `MAP_FIXED` at a page-aligned offset inside it so `G1 = mapped_start - L`, and never write into the mapped range (grep for writes to `G[`, `SA.charArray`, `SAi.charArray` after load; the sjdb-insert path with `--sjdbFileChrStartEnd`/`--sjdbGTFfile` at mapping time does write, so keep the old path when those flags are given). `PackedArray` just holds a `char*`, so pointing it at the mapping is fine. Add `madvise(MADV_RANDOM)` for `SA`/`SAindex` and `MADV_SEQUENTIAL`/`WILLNEED` for `Genome`.
A2. **Remove eager large allocations and zero-fills at startup** that scale with `limitBAMsortRAM`, `limitIObufferSize`, `limitOutSJcollapsed`, or chunk sizes. `calloc`/`memset` of hundreds of MB shows up as page-fault time in `perf`. Lazily allocate or leave uninitialized where the code never reads before write. Verify with `perf stat -e page-faults`.
A3. **Startup I/O**: `sjdbInfo.txt`, `exonInfo.tab`, `geneInfo.tab`, and `chr*.txt` are parsed with iostreams. Only bother if the phase table says pre-mapping time is still significant after A1/A2.

### Regime B — per-read mapping dominates

B1. **Build-level wins, zero code risk.** Add to `CXXFLAGSextra`: `-march=x86-64-v3` (or the exact CARC node arch), `-flto`, `-fno-plt`, `-fno-semantic-interposition`. Then PGO: build with `-fprofile-generate`, run once on the synthetic dataset, rebuild with `-fprofile-use -fprofile-partial-training`. Branchy code like STAR typically gains 10–30% from PGO alone. Confirm output match after PGO; floating-point reassociation is not enabled by these flags, so it should match.
B2. **Allocator.** Statically link mimalloc or jemalloc. `stitchWindowAligns.cpp` and `ReadAlign_outputAlignments.cpp` allocate per read. Output cannot change.
B3. **FASTQ parsing.** STAR reads a chunk into `chunkIn[]` in `ReadAlignChunk_processChunks.cpp`, wraps it in an `istringstream`, and `readLoad.cpp` then does `getline` + `istringstream` + `operator>>` per read. Replace the per-read parse with a hand-rolled pointer scanner over the chunk buffer that produces byte-identical `readName`, `iReadAll`, `readFilter`, `readFilesIndex`, `readNameExtra`, `Seq`, `Qual`, and `clippedInfo`. Keep `istream` as the interface if that is less invasive by subclassing `streambuf`, but the per-read iostream formatting must go.
B4. **Suffix-array search memory behavior** (`suffixArraySearch1`, `maxMappableLength`, `compareSeqToGenome`, `findMultRange` in `SuffixArrayFuns.cpp`; `PackedArray::operator[]`). On a real index this is a cache-miss-bound binary search. Safe transforms: software prefetch of the next `SA` midpoint, hoisting `PackedArray` unpack math out of the loop, caching the `SAindex` lookup for repeated prefixes within a read. Not safe: changing search order, tie-breaking, or `maxL` results. Assert equality against the old function under a debug build on the synthetic set before trusting it.
B5. **Per-read reset and stitching** (`ReadAlign_mapOneRead.cpp` `resetN()`, `ReadAlign_stitchPieces.cpp`, `stitchWindowAligns.cpp`, `extendAlign.cpp`). Look for `memset` or loops that clear arrays sized by `alignWindowsPerReadNmax`/`seedPerWindowNmax` every read; clear only the used prefix. The recursion in `stitchWindowAligns` is expensive but its enumeration order determines output ties, so do not memoize or reorder it.
B6. **Output path** (`ReadAlign_outputAlignments.cpp`, `ReadAlign_alignBAM.cpp`, `ReadAlign_outputTranscriptSAM.cpp`). Remove `to_string`/`ostringstream` in the per-alignment path; write into a preallocated buffer. Bytes must match exactly.
B7. **BAM compression and sort at 1 thread.** The bundled `htslib/` has no configure and no libdeflate hook. Options: static-link zlib-ng in zlib-compat mode (deflate output bytes differ, decompressed records identical, allowed by rule 1), or replace the bundled htslib with a current release built `--with-libdeflate`. `BAMbinSortByCoordinate.cpp` writes bins to `_STARtmp` and re-reads them; on inputs that fit in `--limitBAMsortRAM`, keep bins in memory. The sort key already includes read order, so order is deterministic.

## Fairness and reporting rules

- **Primary baseline** is the distributed static binary `upstream/bin/Linux_x86_64_static/STAR` (what users actually run). **Secondary row**: stock source rebuilt with the same compiler flags as ours but none of our code changes, so the write-up separates compiler gains from code gains. Report both.
- Report per-dataset: stock mean ± std, ours mean ± std, speedup, output-match verdict, and the phase breakdown. The claim passes only if all ten datasets show ≥2.0× and match.
- State the regime honestly in `writeup/WRITEUP.md`: if most of the win comes from index loading on small inputs, say so, and include one larger-input run showing what the mapping-only speedup is.

## Never do these

- Change any CLI flag or thread count on one side only.
- Claim a number from Docker on Apple Silicon.
- Claim 2× from the synthetic dataset alone.
- Skip `compare_outputs.sh` on any timed run.
- Touch `archive/` or anything RM-decay related.

## Deliverables when done

1. Patches in `star/upstream/` committed per rung, plus `star/src/star-2x.patch` as a single squashed diff against tag 2.7.11b.
2. `star/src/STAR_optimized` built on the graded machine, with the build command in `star/docs/BUILD.md`.
3. `star/docs/PROFILING_LOG.md` with the stock profile, the phase table, and the full rung ledger.
4. `star/bench/results/illumina10_table.md` with the ten-dataset table produced by `run_illumina10.sh`.
5. `STATUS.md` updated with the final numbers, and `writeup/WRITEUP.md` sections 6–8 filled in.

Work in the order: Step 0 → Regime A rungs → Regime B rungs → ten-dataset run → write-up. Update `STATUS.md` at the end of every session. If a rung needs Josh (CARC VPN, Duo, a dataset download that needs credentials), record the exact blocker and command in `STATUS.md` and continue on rungs that do not depend on it.
