# Agent prompt v2 — a real, verified ≥2× for STAR

This supersedes `PROMPT_2X.md`. Everything below the horizontal rule is the prompt.
Paste it into a fresh Cursor / Claude Code session opened at the repository root.

Unlike v1, this is not a list of hypotheses. The hot path was profiled, the fix was
written, built, and measured, and the ≥2× was reproduced on four Illumina datasets
with byte-identical BAM output. The prompt hands the agent the finished diff and
makes it re-derive, re-measure, and extend the result rather than search blindly.

---

# TASK

You are working in `star/` of this repository. Your job is to land a **reproducible
≥2× end-to-end wall-clock speedup of STAR 2.7.11b at one thread with byte-identical
output**, on ten Illumina short-read datasets, and to write it up for CSCI 270.

Read `AGENTS.md`, `STATUS.md`, and `star/docs/SCOPE.md` before you touch anything.

The optimization itself is already solved and verified. The remaining work is
(a) rebuilding the benchmark honestly, (b) re-deriving and re-verifying the patch
yourself instead of trusting this document, (c) extending from four datasets to ten,
and (d) the write-up. Do not treat any number in this document as a result you can
cite. Every number here must be reproduced by you, on your hardware, before it goes
into `STATUS.md` or the write-up.

---

# PART 0 — WHAT IS TRUE RIGHT NOW, AND WHAT IS ROTTEN

Read this whole part before running anything. It will save you a day.

## 0.1 The headline in STATUS.md is not real

`STATUS.md` currently claims 2.38×–2.76× on i01–i04. That number is an artifact of a
rigged benchmark and **must be deleted, not defended**. Three separate things were
wrong with it, and each one alone is enough to sink the grade.

**The index was deliberately built wrong.** The genome is human chr1:1–10 Mb, about
10 Mb of sequence. STAR's `genomeGenerate` printed this warning, which is recorded in
`star/bench/datasets/suiteB/i01/genomeGenerate.log`:

```
!!!!! WARNING: --genomeSAindexNbases 14 is too large for the genome size=10000000,
which may cause seg-fault at the mapping step. Re-run genome generation with
recommended --genomeSAindexNbases 10
```

The warning was overridden on purpose, and `ILLUMINA10.md` recorded the override as
"intentional for load-dominated regime". Keeping 14 inflates the `SAindex` file from
about 6 MB to about 1.5 GB. The entire measured "speedup" was the optimized binary
skipping the load of that artificially huge file. Rebuild the same index at the
recommended `--genomeSAindexNbases 10` and the same patch measures about **1.05×**.

**The read count was tuned until the bar was cleared.** `bench/datasets/suiteB/i01/`
contains read subsets at 100, 200, 500, 600, 800, 1000, 1200, 1500, 2000 and 5000
pairs. The locked workload is 800. Measured on the oversized index, the speedup decays
with read count and crosses below 2× at roughly 2,000 reads. 800 is simply the largest
round subset that still passes. A subset chosen that way will not survive one question
from Zhang.

**Stock STAR on a correct index beats the "optimized" build on the rigged one.** At
800 read pairs, stock on the `Nbases 10` index runs in about 0.174 s; the patched
binary on the `Nbases 14` index takes about 0.193 s. Anyone who reruns with STAR's
recommended settings gets a faster result with no patch at all.

Delete the bake-off table from `STATUS.md`, delete
`bench/results/illumina10_table_partial.md`, and record in `PROFILING_LOG.md` that the
old numbers were withdrawn and why. Do this before you generate any new numbers, so
there is no chance of the two sets being confused.

## 0.2 The mmap patch is fine engineering but is not the 2×

The working tree carries an mmap patch in `star/upstream/source/Genome_genomeLoad.cpp`,
`Genome.cpp` and `Genome.h` that memory-maps `SA` and `SAindex` instead of reading them
into the heap. It is correctly written, correctly guarded against the sjdb-insert paths
that write into the index, and produces byte-identical output.

It is also worth about **1.05× on an honestly built index**, because on a correct index
there is very little index to load. Its apparent 2.5× came entirely from the 1.5 GB
`SAindex` described above.

Keep it or drop it, your call, but decide by measurement on the corrected benchmark and
report it as its own line in the ledger. It is not the source of the speedup and must
never be presented as such.

## 0.3 Two dead ends already measured, so you do not repeat them

**Word-at-a-time suffix-array compare.** An earlier attempt rewrote the byte loop in
`compareSeqToGenome` (`SuffixArrayFuns.cpp`) to compare eight bytes at a time. Measured
0.96×, i.e. a slight regression. The reason is in the profile below: seed search is
only about 7% of mapping time, so even a perfect win there is capped at a few percent.
It is currently reverted. Leave it reverted.

**Branch-and-bound pruning of the stitching recursion.** An exact upper-bound prune was
implemented and instrumented. It removed **377,429 of 52,382,046 internal nodes, i.e.
0.7%**, and produced no measurable time change. The bound is provably safe but the
recursion simply is not score-limited in practice — almost every subtree can still
reach a recordable score. Do not build this. If you want the instrumented counter
harness to confirm it yourself, it is described in Part 3.5.

---

# PART 1 — THE RULES, WHICH OVERRIDE EVERYTHING ELSE

These come from `star/docs/SCOPE.md` and Zhang's four conditions. A change that
violates any of them scores zero, so revert it the moment you notice, even if it is fast.

1. **Byte-identical output.** With `@PG` and `@CO` header lines stripped, the
   `samtools view -h` stream of the optimized BAM must be byte-identical to stock's.
   `SJ.out.tab` must match too, and `Log.final.out` must match apart from timestamps
   and the derived speed field. Compressed BAM bytes may differ; decompressed records
   may not.
2. **Identical flags, identical thread count.** Both sides run the same command with
   `--runThreadN 1`. The only difference between the two command lines is the path to
   the binary. Never change `--outBAMcompression`, `--readFilesCommand`, seed
   parameters, sort mode, `--genomeLoad`, or anything else on one side only.
3. **Wall-clock, end to end**, process start to final BAM on disk. Mean of at least
   three timed runs after one discarded warm-up run, per dataset, per binary.
4. **Ten Illumina datasets.** The synthetic set in `bench/datasets/` is for iteration
   only and never appears in the graded claim.
5. **The index is built the way STAR tells you to build it.** If `genomeGenerate`
   prints a parameter warning, you fix the parameter. Suppressing STAR's own advice to
   manufacture a slow baseline is the exact failure this project already made once.

A useful sanity test for any future idea: *if the optimized binary vanished, would the
baseline still be the number a competent user would get?* If not, the baseline is rigged.

---

# PART 2 — REBUILD THE BENCHMARK HONESTLY

## 2.1 Rebuild the i01 index at the recommended setting

Keep the old index directory if you like, but move it aside so it cannot be used by
accident. Build the graded index like this, from the repository root:

```bash
star/src/STAR_stock_mac --runMode genomeGenerate --runThreadN 8 \
  --genomeDir star/bench/datasets/suiteB/i01/genome_nb10 \
  --genomeFastaFiles star/bench/datasets/suiteB/i01/ref/genome.fa \
  --sjdbGTFfile star/bench/datasets/suiteB/i01/ref/genes.gtf \
  --sjdbOverhang 100 \
  --genomeSAindexNbases 10 \
  --outFileNamePrefix star/bench/datasets/suiteB/i01/genomeGenerate_nb10_
```

Confirm that the `genomeGenerate` log contains **no** `genomeSAindexNbases` warning,
and that `SAindex` is now about 6 MB rather than about 1.5 GB. Record the exact command
and the resulting file sizes in `ILLUMINA10.md`, replacing the old block.

## 2.2 Use the full read sets, not a tuned subset

Delete the `fastq_sub*` directories, or at minimum stop referencing them. The graded
workload is the **complete** teaching FASTQ for each sample: i01–i04 are 47,861 /
48,216 / 49,712 / 46,995 read pairs. They run in a few seconds each at one thread, so
there is no reason to subset at all. Update the "Graded read subset" section of
`ILLUMINA10.md` to say the full files are used.

Removing the subset removes the entire question of whether the subset was chosen to
flatter the result. Do not reintroduce one.

## 2.3 Fix the harness

`bench/scripts/run_timed.sh` and `run_illumina10.sh` still default to `THREADS=8`
in places and point at the old paths. Rewrite them so that:

- `THREADS` defaults to 1 and the graded path never overrides it.
- One warm-up run is executed and discarded, then `RUNS` (default 3) timed runs.
- The genome directory, both FASTQs, and the binary are parameters.
- Every timed run is followed by an output comparison, and the CSV records the
  comparison verdict alongside the wall time. A timing row with no verdict is worthless.
- `--readFilesCommand` is chosen once and used on both sides. On macOS use `gzcat`,
  on Linux `zcat`. Never let the two sides differ.

Install `samtools` wherever you benchmark. `compare_outputs.sh` exits 2 without it,
and the old harness treated that as a pass.

---

# PART 3 — MEASURE BEFORE YOU CHANGE ANYTHING

Do all of Part 3 against **stock** STAR, before applying any patch. You are confirming
the diagnosis independently, not taking this document's word for it.

## 3.1 Build a clean stock binary

Work from a pristine copy of the upstream source so the working-tree mmap patch does
not contaminate the baseline:

```bash
mkdir -p /tmp/starwork && cp -a star/upstream/source /tmp/starwork/stock
cd /tmp/starwork/stock
for f in Genome.cpp Genome.h Genome_genomeLoad.cpp BAMbinSortByCoordinate.cpp SuffixArrayFuns.cpp; do
  git -C "$OLDPWD/star/upstream" show HEAD:source/$f > $f
done
find . -name '*.o' -delete && find . -name '*.a' -delete && rm -f STAR Depend.list
make -C htslib lib-static -j8
make STARforMacStatic -j8 CXX=g++-16 CXXFLAGS_SIMD=""
```

On Linux use `make STAR -j8 CXXFLAGS_SIMD=""` instead of the Mac target, and drop
`CXX=g++-16`.

Two build hazards that already cost time here, so guard against both:

- **Stale objects across architectures.** The bundled `htslib/` has a `cram/`
  subdirectory whose objects are not removed by `make clean`. If you build on macOS and
  then in a Linux container over the same tree, the link fails with undefined references
  to `pool_alloc` and friends. Always `find . -name '*.o' -delete` and
  `find . -name '*.a' -delete`, not `make clean`.
- **Stale objects across edits.** STAR's `Depend.list` is generated once and does not
  always pick up header edits. After editing `Transcript.h` or `stitchWindowAligns.h`,
  delete the affected `.o` files or the whole set. A build that silently links an old
  object will give you a wrong timing and a wrong output-match verdict, and you will
  chase it for an hour. If a measurement surprises you, suspect a stale object first.

## 3.2 Get the phase breakdown

STAR writes phase timestamps to stdout: `started STAR run`, `loading genome`,
`started mapping`, `finished mapping`, `started sorting BAM`, `finished successfully`.
`bench/scripts/phase_breakdown.py` already parses these. Run stock on full i01 with the
corrected index and record the split.

On the corrected benchmark the expected shape is: genome load is negligible, BAM sort
and compression are a small percentage, and **mapping dominates**. This is the opposite
of the regime the old work optimized for, and it is why the mmap patch stops mattering.

## 3.3 Profile the mapping phase

You need a real profile, not a guess.

- **On Linux (preferred):** build with `-g -fno-omit-frame-pointer`, then
  `perf record -F 2000 -g -e cpu-clock -- ./STAR ...` and
  `perf report --children --sort sym --stdio -g none`. Inside a container you need
  `--privileged` and the `linux-perf` package; check `/proc/sys/kernel/perf_event_paranoid`.
- **On macOS:** `sample <pid>` works only outside a sandbox and often returns zero
  samples against a short-lived process; `xctrace` is not present on this machine.
  Prefer the Linux container, or use the instrumented timers in 3.4.
- **Exact instruction counts anywhere:** `valgrind --tool=callgrind` plus
  `callgrind_annotate`. Slow, but deterministic and it attributes to source lines.
  Read only the **self** (`--inclusive=no`) table; callgrind's inclusive table is
  meaningless for a deeply recursive function like this one, and will show absurd
  percentages in the millions.

What the profile should show you, and what you must confirm before proceeding:

| Symbol | Inclusive | Self |
|---|---|---|
| `stitchWindowAligns` | ~80% | ~8% |
| `Transcript::Transcript(const Transcript&)` | ~50% | ~24% |
| `memcpy` | ~23% | ~23% |
| `stitchAlignToTranscript` | ~16% | ~12% |
| `extendAlign` | ~8% | ~8% |
| `compareSeqToGenome` | ~4% | ~4% |

Roughly **half of total runtime is copying `Transcript` objects**, and essentially all
of it is inside the `stitchWindowAligns` recursion. Seed search, BAM sorting, and I/O
are rounding errors by comparison. If your profile does not look like this, stop and
work out why before continuing — most likely the index or the read set is still wrong.

## 3.4 Optional: per-phase timers inside `oneRead`

If you want the split without a profiler, add a small timer struct and instrument
`ReadAlign::oneRead`, `ReadAlign::mapOneRead`, and `ReadAlign::stitchPieces`, printing
at the end of `ReadAlignChunk::processChunks`. Print from a normal function called
there, not from a static destructor — STAR's `main` tears down `P.inOut` and can exit
before a static destructor runs, so the output disappears.

The expected result on full i01, one thread:

| Phase | Share of `oneRead` |
|---|---|
| stitching recursion | 78.5% |
| assigning seeds to windows | 10.7% |
| seed search | 7.3% |
| read loading | 1.1% |
| output | 0.9% |

## 3.5 Optional: count the recursion

To see the shape of the problem, add counters to `stitchWindowAligns` for roots,
internal nodes, and leaves. On full i01 (47,861 read pairs) you should see roughly:

| Quantity | Count |
|---|---|
| roots, i.e. windows stitched | 289,991 |
| internal nodes | 52,382,046 |
| leaves | 6,085,937 |

That is about 1,100 recursion nodes per read pair, and stock copies a `Transcript` at
essentially every one of them.

Also instrument the return code of `stitchAlignToTranscript`. You should find that
**39.0 million of the 52.4 million calls return `-1000001`**, the very first early
return in the function, which fires when the new align ends at or before the current
transcript's read end. That is 74% of all stitch attempts failing on a comparison of
two integers, after a full `Transcript` copy has already been paid for. Rung 3 below
exploits exactly this.

---

# PART 4 — THE OPTIMIZATION

## 4.1 The diagnosis in one paragraph

`stitchWindowAligns` is STAR's recursive alignment stitcher. It explores, for each
window, the powerset of candidate seeds: at each node it recurses once with the current
align included and once with it excluded. It takes its working transcript **by value**:

```cpp
void stitchWindowAligns(uint iA, uint nA, int Score, bool WAincl[], uint tR2, uint tG2,
                        Transcript trA, ...)
```

and it makes a second copy at the top of every internal node:

```cpp
Transcript trAi=trA;
```

`Transcript` is large. Its five per-exon arrays alone are fixed at `MAX_N_EXONS` = 20
rows regardless of how many exons the transcript actually has:

| Member | Bytes |
|---|---|
| `exons[20][5]` of `uint` | 800 |
| `shiftSJ[20][2]` of `uint` | 320 |
| `canonSJ[20]` of `int` | 80 |
| `sjAnnot[20]` of `uint8` | 20 |
| `sjStr[20]` of `uint8` | 20 |
| **total per-exon arrays** | **1,240** |

plus scalars and six STL containers, for roughly 1.6 KB per object. A typical
paired-end transcript has two or three exons, so **over 90% of every copy is untouched
padding**. Two copies at each of 52 million nodes is where half the runtime goes.

Three changes remove almost all of it, in increasing order of subtlety. Implement and
measure them **in order, one commit each**.

## 4.2 Rung 1 — copy only the exon rows that exist

Split `Transcript`'s members into the per-exon arrays and everything else, then give the
class a copy constructor and assignment operator that copy only `nExons + 1` rows of
each per-exon array instead of all 20.

Why `nExons + 1` and not `nExons`: STAR writes into a "pending" slot one past the last
exon. `stitchAlignToTranscript` sets `canonSJ[nExons-1]`, `sjAnnot[nExons-1]`,
`sjStr[nExons-1]` and `shiftSJ[nExons-1]` *before* incrementing `nExons`, and writes the
new exon at `exons[nExons]`. Copying one extra row keeps that slot live across a copy.

**The subtlety that will bite you.** `Transcript::reset()` in `Transcript.cpp` never
assigns `nExons`. A default-constructed `Transcript` therefore holds an indeterminate
`nExons`. Stock STAR is immune because it copies all 20 rows unconditionally; a bounded
copy is not. If `nExons` happens to be `UINT64_MAX`, then `nExons + 1` wraps to 0 and
you copy **nothing**, leaving the destination's exon rows stale. You must clamp both
ends:

```cpp
uint n = t.nExons + 1; if (n==0 || n>MAX_N_EXONS) n=MAX_N_EXONS;
```

Do not skip this. Without it you have a latent, input-dependent, non-deterministic
wrong-output bug that the four-dataset check will very likely miss.

The change to `Transcript.h`:

```cpp
#include <cstring>

struct TranscriptExonArrays {
    uint exons[MAX_N_EXONS][EX_SIZE];
    uint shiftSJ[MAX_N_EXONS][2];
    int canonSJ[MAX_N_EXONS];
    uint8 sjAnnot[MAX_N_EXONS];
    uint8 sjStr[MAX_N_EXONS];
};
struct TranscriptScalars {
    // every remaining member of the original class, verbatim and in the original order:
    // cigar, intronMotifs, sjMotifStrand, sjYes, nExons, readLengthOriginal, readLength,
    // Lread, readLengthPairOriginal, iRead, readNmates, readName, iFrag, rStart, roStart,
    // rLength, gStart, gLength, cStart, Chr, Str, roStr, haploType, primaryFlag, nMatch,
    // nMM, mappedLength, extendL, maxScore, nGap, lGap, nDel, nIns, lDel, lIns, nUnique,
    // nAnchor, varInd, varGenCoord, varReadCoord, varAllele, alignGenes
};

class Transcript : public TranscriptExonArrays, public TranscriptScalars {
public:
    Transcript(const Transcript &t) : TranscriptScalars(t) { copyExonRows(t); };
    Transcript& operator=(const Transcript &t) {
        if (this!=&t) { TranscriptScalars::operator=(t); copyExonRows(t); };
        return *this;
    };
    inline void copyExonRows(const Transcript &t) {
        //NOTE: Transcript::reset() never assigns nExons, so a default-constructed
        //Transcript can hold a garbage nExons. Stock copied all MAX_N_EXONS rows
        //unconditionally and so was immune; a bounded copy must clamp defensively
        //(n==0 catches nExons==UINT64_MAX).
        uint n = t.nExons + 1; if (n==0 || n>MAX_N_EXONS) n=MAX_N_EXONS;
        memcpy(exons,   t.exons,   n*sizeof(exons[0]));
        memcpy(shiftSJ, t.shiftSJ, n*sizeof(shiftSJ[0]));
        memcpy(canonSJ, t.canonSJ, n*sizeof(canonSJ[0]));
        memcpy(sjAnnot, t.sjAnnot, n*sizeof(sjAnnot[0]));
        memcpy(sjStr,   t.sjStr,   n*sizeof(sjStr[0]));
    };

    Transcript();   // the rest of the class is unchanged from here down
    ...
};
```

Keep the member order inside `TranscriptScalars` identical to the original class. Other
translation units read these members by name, so order does not affect correctness, but
keeping it identical makes the diff reviewable.

This rung alone measured about **1.6×**. Verify output, commit, move on.

## 4.3 Rung 2 — stitch in place and undo, instead of copying per node

Now remove the copy entirely from internal nodes. Change the signature to take a
reference, mutate that transcript in place for the include branch, then restore it
before taking the exclude branch. Only the leaf, which finalizes and records a
transcript, still needs its own copy.

In `stitchWindowAligns.h` and the definition in `stitchWindowAligns.cpp`:

```cpp
void stitchWindowAligns(uint iA, uint nA, int Score, bool WAincl[], uint tR2, uint tG2,
                        Transcript &trAin, ...)
```

At the top of the leaf branch, take the one copy that is still needed:

```cpp
if (iA>=nA) {//no more aligns to add, finalize the transcript
    Transcript trA(trAin); //leaf works on its own copy
    ...
```

In the internal-node body, replace `Transcript trAi=trA;` with an in-place alias plus an
undo record:

```cpp
Transcript &trW = trAin;
const Transcript &trA = trW;

//snapshot every live field a successful stitch (or the first-align init) can modify
struct StitchUndo {
    uint nExons; uint exRow[EX_SIZE];
    uint rStart,gStart,nMatch,nMM,nGap,lGap,nDel,lDel,nIns,lIns,nUnique,nAnchor;
    intScore maxScore;
} u;
u.nExons=trW.nExons; if (u.nExons>0) memcpy(u.exRow, trW.exons[u.nExons-1], sizeof(u.exRow));
u.rStart=trW.rStart; u.gStart=trW.gStart; u.nMatch=trW.nMatch; u.nMM=trW.nMM;
u.nGap=trW.nGap; u.lGap=trW.lGap; u.nDel=trW.nDel; u.lDel=trW.lDel;
u.nIns=trW.nIns; u.lIns=trW.lIns; u.nUnique=trW.nUnique; u.nAnchor=trW.nAnchor;
u.maxScore=trW.maxScore;

int dScore=0;
Transcript &trAi = trW; //stitched in place
```

and immediately before the exclusion branch, restore:

```cpp
trW.nExons=u.nExons; if (u.nExons>0) memcpy(trW.exons[u.nExons-1], u.exRow, sizeof(u.exRow));
trW.rStart=u.rStart; trW.gStart=u.gStart; trW.nMatch=u.nMatch; trW.nMM=u.nMM;
trW.nGap=u.nGap; trW.lGap=u.lGap; trW.nDel=u.nDel; trW.lDel=u.lDel;
trW.nIns=u.nIns; trW.lIns=u.lIns; trW.nUnique=u.nUnique; trW.nAnchor=u.nAnchor;
trW.maxScore=u.maxScore;

if (WA[iA][WA_Anchor]!=2 || trW.nAnchor>0) {
    WAincl[iA]=false;
    stitchWindowAligns(iA+1, nA, Score, WAincl, tR2, tG2, trW, ...);
};
```

**Why the undo record is complete.** You must be able to defend this, so derive it
yourself by reading `stitchAlignToTranscript.cpp` end to end and listing every write
through the `trA` pointer. The argument is:

- *Scalars.* A successful stitch modifies `nMatch`, `nMM`, `nGap`, `lGap`, `nDel`,
  `lDel`, `nIns`, `lIns`, and via `trA->add(&trExtend)` also `maxScore` and `nUnique`.
  The caller additionally increments `nUnique` and `nAnchor`. The first-align branch in
  `stitchWindowAligns` sets `rStart`, `gStart`, `nExons`, and `nMatch`. All are in the
  record.
- *The last exon row.* A stitch can extend the current last exon in place
  (`exons[nExons-1][EX_L] += ...`) and set its `EX_iFrag` and `EX_sjA`. That single row
  is saved in `exRow` and restored.
- *Rows past the last exon.* New exons are appended at index `nExons` and beyond. After
  `nExons` is restored, those rows are unreachable, so leaving them dirty is harmless.
- *The pending junction slot.* The writes to `canonSJ[nExons-1]`, `sjAnnot[nExons-1]`,
  `sjStr[nExons-1]` and `shiftSJ[nExons-1]` use the *old* `nExons`, so they land in the
  slot describing the junction *after* the current last exon. Every reader of these
  arrays iterates `for (iex = 0; iex < nExons-1; iex++)` or reads at most index
  `nExons-2`, so that slot is dead storage for a transcript with `nExons` exons. It does
  not need restoring. Confirm this by grepping for `canonSJ[` and `sjAnnot[` across the
  source and checking every index bound.
- *Everything else.* `Score`, `tR2`, `tG2` are passed by value and need no undo.
  `WAincl[]` is already saved and restored by the original algorithm.

This rung takes the total to roughly **2.0×**.

## 4.4 Rung 3 — skip stitches that provably cannot succeed

74% of `stitchAlignToTranscript` calls fail on one of its first two tests. Both are
cheap integer comparisons, and both are decidable in the caller. When the test says the
stitch must fail, the include branch is dead and the exclude branch is a tail call, so
the whole thing collapses into a loop.

The two early returns being replicated, from `stitchAlignToTranscript.cpp`:

```cpp
if (rBend<=rAend) return -1000001;
if (gBend<=gAend && trA->exons[trA->nExons-1][EX_iFrag]==iFragB) return -1000002;
```

with `rAend == tR2` and `gAend == tG2` at the call site. Insert this immediately after
`trW` is bound and before the undo snapshot:

```cpp
if (trW.nExons>0) {
    const uint lastFrag = trW.exons[trW.nExons-1][EX_iFrag];
    while (iA<nA) {
        if (WA[iA][WA_iFrag]!=lastFrag) break;   //mate stitching: not covered by this test
        uint rBend = WA[iA][WA_rStart]+WA[iA][WA_Length]-1;
        uint gBend = WA[iA][WA_gStart]+WA[iA][WA_Length]-1;
        if (rBend>tR2 && gBend>tG2) break;       //stitch may succeed: handle normally
        if (WA[iA][WA_Anchor]==2 && trW.nAnchor==0) return; //exclusion of last anchor disallowed
        WAincl[iA]=false;
        iA++;
    };
    if (iA>=nA) {//everything remaining was skipped: finalize
        stitchWindowAligns(iA, nA, Score, WAincl, tR2, tG2, trW, Lread, WA, R, mapGen, P, wTr, nWinTr, RA);
        return;
    };
};
```

**Why this is exact, and why the sjdb fast path cannot sneak past it.**
`stitchAlignToTranscript` has an earlier branch that returns a positive score for an
annotated-junction stitch. You must prove that branch is unreachable whenever your test
fires. It requires `rBstart==rAend+1`, hence `rBend = rAend + L ≥ rAend + 1 > rAend`, so
it cannot coexist with `rBend<=rAend`. It also requires `gAend+1 < gBstart`, hence
`gBend ≥ gBstart > gAend`, so it cannot coexist with `gBend<=gAend`. The
`nExons>=MAX_N_EXONS` guard returns `-1000010`, which is also below the `-1000000`
acceptance threshold, so aligns hitting it merely take the normal path — a missed
optimization, never a wrong answer.

This rung takes the total to roughly **2.1×**.

## 4.5 Optional rung 4 — build flags and PGO

Purely a build change, no source edits, output unaffected:

```
CXXFLAGSextra="-O3 -march=<your target> -flto -fno-plt -fno-semantic-interposition"
LDFLAGSextra="-flto"
```

then a PGO cycle: build with `-fprofile-generate -fprofile-update=single`, run once on
one dataset, rebuild with `-fprofile-use -fprofile-partial-training -fprofile-correction`.

Measured worth about another 2–4% on top of rungs 1–3. Two cautions. Do not use
`-mcpu=native` inside a container whose assembler is older than the detected CPU; it
fails with `selected processor does not support 'eor3'` during LTO. And if you use these
flags, you must **also** report a stock binary built with the same flags, so the write-up
separates compiler gains from algorithmic gains.

## 4.6 Rungs that were tried and rejected

Record these in the ledger as measured negatives, with numbers. They are part of an
honest write-up.

| Rung | Result | Verdict |
|---|---|---|
| Splitting the scalars further into a POD block and an STL-container block, skipping container copies when both sides are empty | about 4% **slower** than rung 1 alone | dropped |
| Branch-and-bound pruning of the recursion | prunes 0.7% of nodes, no measurable time change | dropped |
| Word-at-a-time `compareSeqToGenome` | 0.96× | dropped |
| mmap of `SA`/`SAindex` | about 1.05× on a correct index | keep only if measured, never as the headline |

---

# PART 5 — VERIFICATION, WHICH IS THE ACTUAL DELIVERABLE

A speed number without a passing equivalence check is worth nothing. Run all of this
after **every** rung, not just at the end.

## 5.1 Per-rung ledger

After each rung: rebuild from clean objects, verify output, time three runs after a
warm-up, and append one row to `star/docs/PROFILING_LOG.md`:

```
| rung | change | output match | stock mean s | ours mean s | cumulative speedup | keep? |
```

Keep a rung only if output matches and it gains at least 2%. Revert otherwise.

## 5.2 The equivalence check

For each dataset and each rung:

```bash
samtools view -h stock.bam | sed -E '/^@PG/d;/^@CO/d' > a.sam
samtools view -h opt.bam   | sed -E '/^@PG/d;/^@CO/d' > b.sam
cmp -s a.sam b.sam && echo OUTPUT_MATCH || echo OUTPUT_DIFF
cmp -s stock_SJ.out.tab opt_SJ.out.tab && echo SJ_MATCH || echo SJ_DIFF
diff <(grep -vE 'on \||speed' stock_Log.final.out) \
     <(grep -vE 'on \||speed' opt_Log.final.out) >/dev/null \
     && echo LOGFINAL_MATCH || echo LOGFINAL_DIFF
```

## 5.3 The flag matrix — do not skip this

Byte-identical output on the default flags is not sufficient evidence. The recursion
behaves differently under different scoring and filtering options, and a broken undo
record can pass the default path and fail elsewhere. Run stock against optimized on a
few thousand reads under **all** of these, and require a match on every one:

| Name | Flags |
|---|---|
| default | *(none)* |
| all attributes | `--outSAMattributes NH HI AS nM NM MD jM jI MC ch` |
| many multimappers | `--outFilterMultimapNmax 100 --outSAMprimaryFlag AllBestScore` |
| end-to-end | `--alignEndsType EndToEnd` |
| SAM output | `--outSAMtype SAM` |
| two-stage SJ filter | `--outFilterType BySJout` |
| PE overlap merge | `--peOverlapNbasesMin 10` |
| chimeric detection | `--chimSegmentMin 12 --chimOutType WithinBAM` |
| two-pass | `--twopassMode Basic` |
| non-default scoring | `--scoreGap -2 --scoreGapNoncan -10 --scoreDelOpen -3 --scoreInsOpen -3 --scoreGenomicLengthLog2scale -0.25` |
| intron/overhang limits | `--alignIntronMin 30 --alignIntronMax 100000 --alignMatesGapMax 100000 --alignSJoverhangMin 8 --alignSJDBoverhangMin 3` |
| on-the-fly junctions | `--sjdbGTFfile <gtf>` |
| quantification | `--quantMode TranscriptomeSAM GeneCounts` |

Compare `Aligned.*`, `SJ.out.tab`, `ReadsPerGene.out.tab`, `Aligned.toTranscriptome.out.bam`
and `Chimeric.out.junction` wherever each is produced. The non-default scoring row and
the chimeric row are the ones most likely to catch a bad undo record; the two-pass and
on-the-fly-junction rows exercise the sjdb insertion path that the mmap patch guards.

**One stock STAR bug you will hit here.** Combining `--sjdbGTFfile` at mapping time with
`--quantMode TranscriptomeSAM` fails **non-deterministically in stock STAR 2.7.11b**,
about half the time, with:

```
Transcriptome.cpp:18: could not open input file /geneInfo.tab
```

The cause is in `Transcriptome::Transcriptome`:
`trInfoDir = P.pGe.sjdbGTFfile=="-" ? P.pGe.gDir : P.sjdbInsert.outDir;` — when the GTF
is supplied at mapping, it looks in `P.sjdbInsert.outDir`, which is empty unless
`--sjdbInsertSave` is set. Measured over five repetitions, stock exited 0, 109, 109, 0,
109 on identical input. **This is not your patch.** Run that combination with
`--sjdbInsertSave All`, or test the two flags separately, and note the stock bug in the
write-up. Do not spend hours bisecting your own code for it, and do not let a flaky
stock baseline convince you that a correct patch is broken.

## 5.4 The determinism check

Run the optimized binary on the same input five times and confirm the BAM is
byte-identical every time. The bounded copy touches uninitialized memory if the clamp in
4.2 is wrong, and that shows up as run-to-run variation rather than a clean failure.

---

# PART 6 — THE TEN-DATASET RUN

Only start this once rungs 1–3 are in, every check in Part 5 passes, and the cumulative
speedup on i01 is comfortably above 2×. Aim for at least 2.2× on your development
dataset so that dataset-to-dataset variation does not drop one of the ten below the bar.

## 6.1 Fetch the remaining six

`ILLUMINA10.md` lists i05–i08 (Drosophila, GSE49587: SRR948304–SRR948307) and i09–i10
(nf-core rnaseq test data). `bench/scripts/fetch_illumina10.sh` is referenced but **does
not exist** — write it. For each dataset record the exact source URL, the checksum of
each FASTQ, the reference FASTA and GTF, and the exact `genomeGenerate` command, in
`ILLUMINA10.md`. Each organism needs its own index, built at the `genomeSAindexNbases`
value STAR recommends for that genome size, with no warnings in the log.

## 6.2 The graded run

For each of the ten: one warm-up, three timed runs, stock and optimized, one thread,
identical flags. Produce `bench/results/illumina10_table.md`:

| ID | organism | read pairs | stock mean ± sd | opt mean ± sd | speedup | output | SJ | Log.final |
|----|----------|-----------|-----------------|---------------|---------|--------|----|-----------|

The claim passes only if **all ten** show ≥2.0× and every equivalence column passes. If
one dataset comes in at 1.9×, say so and report it. Do not adjust the workload to fix it.

## 6.3 Hardware

The graded numbers should come from a single fixed machine. CARC Discovery via `carc/`
is the intended target and needs Josh for VPN and Duo. If CARC stays unavailable, a
native build on the local machine is acceptable provided the write-up states the
hardware plainly. What is **not** acceptable is Docker `linux/amd64` on Apple Silicon,
which is x86 emulation; every number from that setup is meaningless and the earlier
3.3 s baselines in `STATUS.md` came from exactly there.

If you benchmark inside a container, use a native-architecture image, pin the CPU count,
and run nothing else on the machine. Two of the runs recorded during this investigation
were corrupted by a concurrent build, one showing 973 s for a 6 s workload. Re-run
anything that looks anomalous rather than averaging it in.

---

# PART 7 — THE WRITE-UP

Fill in sections 6–8 of `star/writeup/WRITEUP.md`.

State plainly:

- **What the bottleneck was.** Half of STAR's single-threaded runtime on this workload is
  spent copying a 1.6 KB `Transcript` through a recursion that visits about 1,100 nodes
  per read pair, when a typical transcript uses under 10% of that structure.
- **What the fix is.** Bound the copy to the exons that exist; mutate in place with an
  undo record instead of copying per node; skip stitches that two integer comparisons
  prove will fail.
- **What it is worth**, per dataset, with the equivalence verdicts beside the times.
- **What it is not.** This is a constant-factor engineering win on the stitching hot
  path. It does not change STAR's algorithm, its output, or its asymptotic behaviour, and
  it will matter less on workloads where mapping is not the bottleneck.
- **The correction.** Say that an earlier version of this project reported 2.4–2.8× from
  an oversized suffix-array index and an 800-read subset, that those numbers were
  withdrawn, and that the current result is measured on a STAR-recommended index with
  complete read sets. Owning this is worth more than hiding it, and it is the difference
  between a defensible A and a claim that collapses under one question.

Also include, for the record: the profile table, the rung ledger with the rejected rungs
and their numbers, and the stock-STAR `--quantMode` flakiness you documented in 5.3.

---

# PART 8 — REFERENCE: THE VERIFIED DIFF

A working version of rungs 1–3 has already been built and measured. It touches exactly
three files: `Transcript.h`, `stitchWindowAligns.h`, `stitchWindowAligns.cpp`. Nothing
in `ReadAlign.h`, `ReadAlign_stitchPieces.cpp`, `stitchAlignToTranscript.cpp` or
`extendAlign.cpp` changes.

The full unified diff is committed at `star/src/star-2x-verified.patch`, against tag
2.7.11b. Use it to check your work **after** you have written your own version, not
instead of writing one. You have to be able to defend every line of this in the
write-up, and you cannot defend code you pasted.

Measured on a fixed machine at one thread, full read sets, STAR-recommended indexes,
mean of three timed runs after a discarded warm-up. Every row passed `OUTPUT_MATCH`,
`SJ_MATCH` and `LOGFINAL_MATCH`:

| dataset | read pairs | stock | rungs 1–3 | speedup |
|---|---|---|---|---|
| i01 | 47,861 | 5.83 s | 2.77 s | 2.11× |
| i02 | 48,216 | 6.07 s | 2.94 s | 2.07× |
| i03 | 49,712 | 5.49 s | 2.53 s | 2.17× |
| i04 | 46,995 | 6.42 s | 2.98 s | 2.15× |

Rung 4 (LTO plus PGO) moved these to 2.07×, 2.06×, 2.36× and 2.23× — that is, it helped
on two datasets, was flat on one, and was slightly negative on another. Treat it as
optional and noisy, not as a reliable 2–4%.

An independent earlier run of a near-identical build measured 2.13×, 2.06×, 2.00× and
2.10× on the same four datasets. The spread between the two runs, about 0.15× on the
same code, is ordinary machine noise and is exactly why Part 6 tells you to reach 2.2×
on your development dataset before starting the graded ten. At 2.0× exactly, one noisy
afternoon puts a dataset under the bar.

---

# WORKING RULES

- One rung, one commit, one ledger row. Never batch two rungs into one measurement.
- Delete `.o` files before every timed build. A stale object will hand you a wrong number
  and a wrong verdict.
- Never report a timing without the matching equivalence verdict in the same row.
- If a result surprises you, suspect the harness first: stale objects, a busy machine, a
  wrong index, a wrong read set, mismatched `--readFilesCommand`.
- If you get blocked on something only Josh can do — CARC VPN, Duo, a dataset that needs
  credentials — write the exact blocker and the exact command into `STATUS.md` and carry
  on with everything that does not depend on it.
- Update `STATUS.md` at the end of every session: what you measured, what you kept, what
  you rejected and why, and what is next.
- Do not touch `archive/`. It is the RM-decay research track and is not part of this
  deliverable.
