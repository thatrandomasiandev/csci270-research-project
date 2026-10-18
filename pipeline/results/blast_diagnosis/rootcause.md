# BLAST+ HSP diagnosis

Semantics review first. The measured pin sweep is separate and is cited
only from `rootcause.json` once that file exists. Nothing below is a
claim that a pin works.

Locked inputs, from `docs/REFERENCE_BOUNDARY_PROTOCOL.md` and
`results/reference_boundary_blast.json` (git `2ea39e2`, job `12864923`):
NCBI BLAST+ `blastp` 2.14.1, Swiss-Prot 2026_03, 20 queries drawn by
`sample_record_indices(..., 20, 20261006)`, reference split by
`partition_indices(..., k=2, seed=20261006)`. The argv is

```
blastp -query {input} -db {reference} -out {output}
  -outfmt "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore"
  -max_target_seqs 100000 -evalue 1000 -num_threads 4
```

`OLD_FSC` is unset. No `-comp_based_stats`, `-dbsize`, `-searchsp`,
`-max_hsps`, or `-ungapped`.

## What a TARE pin can set

A declared `--pin` is caller data. `pin_tokens` expands only
`{entry_count}` and `{total_entry_length}` (`acts/reference_run.py`,
`PIN_PLACEHOLDERS`). The tokens are inserted after the program name.
`_batched_replay` and `_pin_check` pass `pin_values` of the full
reference, including when the sequences actually searched are a subset.
A literal flag with no placeholder can also be declared. Exact mode
compares that pinned subset with the unpinned stock command, so a flag
that changes the scoring mode is a pin only if the subset-plus-flag
output equals the unpinned whole output.

`infer_knobs` discovers a pin only for help-text options whose argument
bracket is a numeric placeholder (`integer`, `size`, `value`, and the
other names in `_PLACEHOLDER_NAMES`). A bracket spelled `String` is
invisible to inference. Declaration does not have that limit.

## What in blastp depends on the database as a whole

Line numbers in `blast_options.h` and `blast_stat.h` are from the
installed 2.14.1 headers next to the CARC binary
`/apps/spack/2406/apps/linux-rocky8-x86_64_v3/gcc-13.3.0/blast-plus-2.14.1-tdum24r/`.
The `.c` line numbers are the ones already audited against the 2.14.1
tarball in `docs/REFERENCE_BOUNDARY_PROTOCOL.md`, except the
Smith-Waterman keep test, which is quoted from the public
`redo_alignment.c` (NCBI C++ toolkit doxygen). That keep test is the
code path the pin sweep is aimed at; the run, not the line number, is
the evidence.

1. **Effective length and search space.** `BlastEffectiveLengthsOptions`
   (`blast_options.h:482-491`) holds `db_length`, `dbseq_num`, and
   `searchsp_eff` (one slot per query context).
   `BLAST_FillEffectiveLengthsOptions` (`blast_options.h:907-922`) says
   a zero length or sequence count means "use the real value."
   `-dbsize` is the command-line override of `db_length`. `-searchsp`
   is the override of `searchsp_eff`. The length adjustment is the
   fixed point

   ```
   f(ell) = beta + (alpha/lambda) * log(K * (m - ell) * (n - N * ell))
   ```

   (`BLAST_ComputeLengthAdjustment`, `blast_stat.h:771-785`). `n` is
   the database length and `N` is the number of sequences. `-dbsize`
   can pin `n` to `{total_entry_length}`. No blastp flag in the manual
   pins `N`, so a half database still contributes its own sequence
   count to the edge correction. `-searchsp` pins the product, but it
   is one number per invocation and the product depends on the query
   length. TARE has no per-query placeholder, so `-searchsp` is not a
   reference-only pin.

2. **Composition-based statistics.** `compositionBasedStats`
   (`blast_options.h:342`) defaults to mode 2 for `blastp` (protocol:
   `cmdline_flags.cpp` default `"2"`, `eCompositionMatrixAdjust`). The
   adjusted matrix is a function of the query composition and the
   subject composition, not of the other database sequences. The redo
   then computes a Smith-Waterman alignment and keeps it only when

   ```
   searchsp = query_info[query_index].eff_search_space
   newSwEvalue = searchsp * exp(-(Lambda * score) + logK)
   alignment_is_significant = newSwEvalue < cutoff_e
   ```

   (`redo_alignment.c`, the `Blast_RedoOneMatchSmithWaterman` loop).
   `cutoff_e` is the `-evalue` setting (`s_GetAlignParams` sets
   `cutoff_e = hitParams->options->expect_value`). Mode 2 can therefore
   replace the preliminary alignment, and the keep decision sees the
   search space. A declared pin can pass `-comp_based_stats 0`, `1`, or
   `2`. That changes the matrix on the subset. It reproduces the
   unpinned whole run only if the experiment says so.

3. **Karlin-Altschul parameters.** For the default matrix the ungapped
   parameters and the gapped Gumbel block (`Blast_GumbelBlk`,
   `blast_stat.h:92-112`, `db_length` at line 108) come from the matrix
   and from precomputed tables, not from the residue composition of
   this FASTA. With `OLD_FSC` unset, `gbp` is allocated and the printed
   E-value is `BLAST_SpougeStoE` (`blast_stat.h:497`), whose database
   factor is `gbp->db_length / n_` (protocol, `blast_stat.c:5168-5212`).
   On a fixed alignment the printed E-value is proportional to database
   length. The bit score is `(score * lambda - log K) / ln 2` after
   rescaling and has no database factor (protocol, `blast_kappa.c:111-113`).
   A pin cannot edit lambda or K except by changing the matrix or the
   composition mode.

4. **X-drop and the score cutoffs.** Ungapped, gapped, and final
   X-drop are stored in bits (`blast_options.h:302`, `336-337`). Those
   bit values do not depend on the database. The raw-score cutoff that
   decides which initial hits are saved does: `BLAST_Cutoffs`
   (`blast_stat.h:577-578`) takes the effective search space. A larger
   database raises the score required to meet the same E-value.
   `-evalue 1000` is still that cutoff. There is no flag for the
   internal score cutoff itself. `-dbsize` and `-searchsp` are how a
   pin would feed it a whole-database search space. `-evalue` is a
   reporting threshold; TARE treats that as slack, not as the
   normalizer.

5. **`-max_target_seqs`, `-max_hsps`, culling.** `hitlist_size`
   (`blast_options.h:400`) is `-max_target_seqs`, default 500. B1 sets
   100000. The manual breaks ties by database order. `max_hsps_per_subject`
   (`blast_options.h:445`) defaults to "all HSPs that meet the expect
   value," and the manual ranks the kept HSPs by expect value. Expect
   values move with the search space, so a ranking can change, but only
   among HSPs the search actually produced. Culling is off unless
   `-culling_limit` is set. A declared pin can set `-max_hsps`. The
   published key sets have `only_whole = 0`, so the 100000 cap did not
   drop a whole-database row that a half kept.

6. **Order and ties.** The composition redo sorts by E-value and breaks
   ties by the subject's index in the database (public `blast_kappa.h`
   comment on `Blast_RedoAlignmentCore`). A half database renumbers
   those indices. The published pair is not a tie: the intervals and
   the bit scores both differ. Output order is not the fitter's row
   identity. The diagnosis compares sorted line multisets, and reports
   raw byte identity separately.

7. **Threads.** B1 passes `-num_threads 4`. That flag is already in the
   argv. It is not a size correction. Two stock runs of the same
   database are the determinism control. If their hit multisets differ,
   the pin sweep stops.

## The published line, and the hypothesis the sweep tests

`results/reference_boundary_diagnosis.json` classified one joined row
as `different_hsp` and 15,124 as `same_hsp`:

```
whole  WP_000153074.1  sp|A0KJE6|LOLA_AERHH  33.333  36  23  1  3  37  1  36  205  25.0
part0  WP_000153074.1  sp|A0KJE6|LOLA_AERHH  21.875  128 72  5  3 105 1 125  180  24.3
```

Both start at query residue 3 and subject residue 1. The ends differ.
On the other 15,124 joins the alignment body and the bit score are
identical, and the E-value fits `total_entry_length`. The closed family
already describes the printed E-value of a fixed alignment. The refusal
is the one alignment that was replaced.

Hypothesis, not a result: the half database's smaller search space
either saves a seed the whole database's cutoff drops, or keeps a
composition-adjusted Smith-Waterman alignment whose E-value is under
1000 only on the half. `-dbsize` set to the whole reference's residue
count is the TARE-expressible correction. It pins `n` and leaves `N`
equal to the half's sequence count, so it may be short of
`-searchsp`. The script `pipeline/scripts/blast_hsp_diagnosis.py`
(frozen at the commit recorded in `rootcause.json`) reruns the locked
probe, checks stock against stock, then pins `-dbsize`, `-searchsp`,
`-comp_based_stats 0/1/2`, `-max_hsps 1`, and `-ungapped` together with
`-comp_based_stats 0` (the binary rejects ungapped composition adjustment)
one at a time.

## Evidence

Not measured in this file yet. The CARC job is
`pipeline/jobs/blast_hsp_diagnosis.job`. It was not submitted while
tasks of job `13208152` were still `PENDING`.
