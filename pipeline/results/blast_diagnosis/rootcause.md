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

`-dbsize` set to the whole reference's residue count is the
TARE-expressible correction. It pins `n` and leaves `N` equal to the
half's sequence count. The script
`pipeline/scripts/blast_hsp_diagnosis.py` reruns the locked probe,
checks stock against stock, then pins `-dbsize`, `-searchsp`,
`-comp_based_stats 0/1/2`, `-max_hsps 1`, and `-ungapped` together with
`-comp_based_stats 0` (the binary rejects ungapped composition
adjustment) one at a time.

## Evidence

Measured on CARC job `13223561` (host `b09-03`), BLAST+ 2.14.1+, git
`10c3c81acf67eca1d427ea9afc04cec9d170b646` (dirty false). Numbers are
`results/blast_diagnosis/rootcause.json`. The binary is the spack
module used for B1. `OLD_FSC` was unset. Threads in the probe were 4,
matching B1.

Stock versus stock on the 20-query probe is byte-identical: 15,125
lines, MD5 `e1792cd30e1b67f1c9a0227f31a24f19`. The partition matches B1
(575,748 sequences, 209,017,843 letters, part lengths 104,399,849 and
104,617,994). The one joined disagreement is the published line, and
no other joined line disagrees:

```
whole  WP_000153074.1  sp|A0KJE6|LOLA_AERHH  33.333  36  23  1  3  37  1  36  205  25.0
part0  WP_000153074.1  sp|A0KJE6|LOLA_AERHH  21.875  128 72  5  3 105 1 125  180  24.3
```

Key sets match the published diagnosis: whole 15,125, union 28,937,
only_union 13,812, only_whole 0, in_two_parts 0. Classification
`different_hsp`. 12/36 is 33.333 percent. 28/128 is 21.875 percent.
The pairwise report of the same binary, preserved under
`/scratch1/jjt_373/tare_e/blast_pairwise_preserve/`, shows the same two
alignments: both are "Compositional matrix adjust," both start at
query 3 and subject 1, and the long one ends at query 105 and subject
125.

One option reproduces the unpinned whole line, including the E-value
and the bit score. `-dbsize 209017843` on the half that contains
`A0KJE6` prints

```
WP_000153074.1  sp|A0KJE6|LOLA_AERHH  33.333  36  23  1  3  37  1  36  205  25.0
```

The same flag on the whole database leaves that line unchanged
(853 lines on the one-query file either way). On the full 20-query
probe, each pinned half is the whole table restricted to subjects in
that half: part 0 has 7,498 rows, part 1 has 7,627, the sum is 15,125,
and each half has zero missing and zero extra against the whole
(`full_probe_confirmation.reproduces_whole` is true). A check on those
same files, after the job, found the half's lines equal to the
filtered whole lines in whole-file order, not only as a multiset.

The other pins do not reproduce the unpinned command.

| Pin on the half | Line for A0KJE6 | Equals unpinned whole |
|---|---|---|
| none | 21.875, length 128, E 180, bits 24.3 | no |
| `-dbsize 209017843` | 33.333, length 36, E 205, bits 25.0 | yes |
| `-searchsp 5214656096` | same interval, E 161, bits 25.0 | no |
| `-comp_based_stats 0` | same short interval, E 242, bits 23.9 | no |
| `-comp_based_stats 1` | the long interval, E 152, bits 24.6 | no |
| `-comp_based_stats 2` | the long interval, E 180, bits 24.3 | no |
| `-max_hsps 1` | the long interval | no |
| `-ungapped -comp_based_stats 0` | the pair is absent | no |
| `-num_threads 1` | the long interval | no |

`-searchsp 5214656096` is the effective search space the binary printed
for this query (`report_stats`). It selects the short HSP and the bit
score 25.0, and it also changes the whole-database E-value from 205 to
161. The printed E-value follows `db_length` (Spouge), which
`-searchsp` does not set. It is also one number per query, and TARE
has no per-query placeholder.

Mode 0 reports the short interval on both databases, at bit score 23.9
instead of 25.0, so the database-size split goes away and the stock
score goes away with it. Mode 1 reports the long interval on both
(E-values 152 and 304). Default mode 2 is the only mode in which the
half and the whole disagree about which alignment to print. Culling
the HSP list to one, and running on one thread, leave the
disagreement in place. The stock pair being byte-identical already
says the disagreement is not a thread race.

## Mechanism

`-dbsize` writes `BlastEffectiveLengthsOptions.db_length`
(`blast_options.h:482-491`; a zero value means "use the real length,"
`BLAST_FillEffectiveLengthsOptions` at `907-922`). That length is `n`
in `BLAST_ComputeLengthAdjustment` (`blast_stat.h:771-785`) and the
database factor in the printed E-value (`BLAST_SpougeStoE`). The score
cutoff that decides which initial hits are kept takes the effective
search space (`BLAST_Cutoffs`, `blast_stat.h:577-578`). Mode 2, the
blastp default, then redoes the alignment with a composition-adjusted
matrix and keeps the Smith-Waterman result only when its E-value,
computed from `eff_search_space`, is under the `-evalue` cutoff
(`redo_alignment.c`, `Blast_RedoOneMatchSmithWaterman`; the line
numbers of that keep test are the public toolkit source, not a
re-count of the 2.14.1 tarball). The composition used for the adjusted
matrix is taken from the preliminary alignment's window, so a cutoff
that changes with database length can change which adjusted alignment
is reported.

The sweep names that path. Mode 2 is required for the two databases to
disagree. Pinning `db_length` to the whole reference's residue count
puts the half back on the whole database's alignment, including the
E-value. Pinning the search-space product fixes the alignment and not
the printed E-value. No blastp flag pins the sequence count `N`. On
these halves that remainder did not move a printed cell.

`infer_knobs` will not discover the flag. The help bracket is
`<Int8>`, and `int8` is not in `_PLACEHOLDER_NAMES`. A declared pin
can still set it: `--pin '-dbsize {total_entry_length}'`. The value
on this release is 209,017,843.

## What this does not change

The gate is untouched. An explicit pin is applied only after the
unpinned fit returns SHIP (`reference_run.py`, the refusal return
before `_run_exact`). This file does not claim that
`python3 -m acts run` emits SHIP for blastp. That is the pilot in
`docs/BLAST_PIN_PROTOCOL.md`.

## Deviation

Two earlier jobs, `13223485` and `13223517`, omitted `-outfmt 6`.
blastp wrote the pairwise report. The harness then treated two empty
tabular joins as a match and wrote a `SHIP_CANDIDATE` JSON that is
void. Those jobs are not this result. Job `13223561` is the tabular
rerun: the published lines are present, the joins are nonempty, and
the confirmation above is that file. The pairwise text is kept only as
a picture of the two alignments.
