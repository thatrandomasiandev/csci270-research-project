# Reference boundary: NCBI BLAST+ blastp (pre-registered 2026-10-09)

Written **before** any `blastp` invocation for this experiment. Locked text
below is never edited. Later changes are dated addenda. This is a
correctness and fit experiment. It is not a timing run and it does not
claim a speedup.

The fitter under test is the one shipped in `acts/reference_fit.py` and
`acts/reference_run.py`: `k = 2`, seed `20261006`, Fisher–Yates on
`random.Random.random`, and the length-descending tie-break. No member
is added to the closed family. No per-tool branch is added. The driver
calls `probe_fit`. A refusal is a result.

## Pin

| Item | Value |
|---|---|
| Tool | NCBI BLAST+ `blastp` |
| CARC module | `blast-plus/2.14.1` |
| Source tarball | `https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.14.1/ncbi-blast-2.14.1+-src.tar.gz` |
| Bytes | 28,258,487 |
| SHA-256 | `712c2dbdf0fb13cc1c2d4f4ef5dd1ce4b06c3b57e96dfea8f23e6e99f5b1650e` |
| Check on the node | `blastp -version` and `makeblastdb -version` must contain `2.14.1`. Any other string stops the job before a search. |
| Environment | `OLD_FSC` is unset. The job does not export it. |

Line numbers below are from that tarball.

## What this binary computes

Two formulas are in the source. This job runs the default one.

**Length adjustment.** `BLAST_ComputeLengthAdjustment`
(`c++/include/algo/blast/core/blast_stat.h:746-751`, same comment at
`c++/src/algo/blast/core/blast_stat.c:4991-4996`) is the fixed point of

```
f(ell) = beta + (alpha/lambda) * (log K + log((m - ell)*(n - N ell)))
```

with `m` the query length, `n` the database length, and `N` the number
of database sequences. The search-space code then sets

```
effective_db_length = db_length - ((Int8)db_num_seqs * length_adjustment);
effective_search_space = effective_db_length * (query_length - length_adjustment);
```

(`c++/src/algo/blast/core/blast_setup.c:836-843`). That effective database
length is `n′ = n − N·ℓ`. It is a combination of total length and entry
count, with a per-query `ℓ`. `BLAST_KarlinStoE_simple` multiplies that
search space into the E-value
(`c++/src/algo/blast/core/blast_stat.c:4139-4153`):

```
return (double) searchsp * exp((double)(-Lambda * S) + kbp->logK);
```

`Blast_HSPListGetEvalues` uses that Karlin call only when `sbp->gbp` is
null (`c++/src/algo/blast/core/blast_hits.c:1886-1890`).

**Default reported E-value.** `BlastScoreBlkNew` allocates the Gumbel
block unless the environment variable `OLD_FSC` is set
(`c++/src/algo/blast/core/blast_stat.c:921-923`):

```
use_old_fsc = getenv("OLD_FSC");
if (!use_old_fsc) sbp->gbp = s_BlastGumbelBlkNew();
```

With `gbp` set, the same function calls `BLAST_SpougeStoE`
(`blast_hits.c:1872-1878`). The only database-size factor in that
function is

```
double db_scale_factor = (gbp->db_length) ?
        (double)gbp->db_length/(double)n_ : 1.0;
...
e_value = area * k_ * exp(-lambda_ * y_) * db_scale_factor;
```

(`c++/src/algo/blast/core/blast_stat.c:5168-5170` and `5212`). `n_` is
the subject length passed by the caller. `gbp->db_length` is the
sequence-source total length (`blast_setup.c:914-922`). `area` depends
on the query length, the subject length, and the score. For a fixed
alignment, the reported E-value is proportional to database length.
That is the closed-family member `total_entry_length` when the
sequence-source length equals the FASTA residue sum from
`parse_fasta_entries`. A mismatch is recorded. It does not add a member.

**Composition mode.** `blastp` constructs `CCompositionBasedStatsArgs`
with no override (`c++/src/algo/blast/blastinput/blastp_args.cpp:110`).
The default string is `"2"` (`cmdline_flags.cpp:144`). Case `'2'` sets
`eCompositionMatrixAdjust` (`blast_args.cpp:849-850`). Unified p-values,
which would fold `eff_searchsp` back into the printed E-value
(`blast_kappa.c:149-177`, `unified_pvalues.c:245-251`), are enabled
only when the second character of the flag is `u`
(`blast_args.cpp:873-876`). B1 does not pass `-comp_based_stats`, so
the mode stays 2 and unified p-values stay off.

**Bit score.** After the score is rescaled,
`c++/src/algo/blast/core/blast_kappa.c:111-113`:

```
hsp->score = BLAST_Nint(((double) hsp->score) / scoreDivisor);
hsp->bit_score = (hsp->score*lambda*scoreDivisor - logK)/NCBIMATH_LN2;
```

Database length is not an input. On a row that survives in a part and
in the whole, `bitscore` is predicted to be `identity`.

**Print format** for the tabular E-value and bit score,
`c++/src/objtools/align_format/align_format_util.cpp:841-869`. E-values
below `0.0009` use `%3.0le` (one significant digit). E-values at or
above `10` use `%2.0lf`. Bit scores at or below `99.9` use `%4.1lf`.
The fitter's half-ULP predicate is applied to those printed tokens.

**Global cuts.** The default expect cutoff is `10`
(`blast_options.h:158-159`, `BLAST_EXPECT_VALUE`) and the default
hit-list size is `500` (`blast_options.h:160-161`, `BLAST_HITLIST_SIZE`,
the `-max_target_seqs` cap). Both are database-size-dependent: the
E-value compared with the cutoff scales with database length, and the
cap keeps a fixed number of database sequences per query.

## Queries and reference

Queries are 20 proteins from collection A genome 1,

`/project2/biyik_1165/jjt_373/csci270-star/pipeline-ref-second/pipeline/data/recurrence/A/GCF_002853805.1_protein.faa.gz`.

The draw is the shipped sampler `sample_record_indices(n, 20, 20261006)`.
File order is preserved. Those 20 records are the record input. `probe_fit`
keeps its defaults (`k = 2`, `n_p = 300`, seed `20261006`, `sample=True`).
With 20 records and `n_p = 300` the sampler keeps every record. The
partition of the reference uses the same seed on its own `Random`
instance, which is the locked partitioner.

Reference, reused, not downloaded:

`/project2/biyik_1165/jjt_373/csci270-star/pipeline-ref-second/data/swissprot/uniprot_sprot_2026_03.fasta.gz`

(93,801,562 bytes on disk, 2026-10-06). Entries and lengths come from
`parse_reference`. Prep is caller data:

```
makeblastdb -in {reference} -dbtype prot -out {reference}
```

`-parse_seqids` is absent so `sseqid` stays the FASTA first token, which
is the entry key the shipped alias map stores.

## B1 argv

Score and hit-list cuts are pushed out so a surviving row is as close
as this program allows to "every alignment the database contains."
They are not removed. `-evalue 1000` replaces the default `10`.
`-max_target_seqs 100000` replaces the default `500`. Swiss-Prot has
on the order of 5.7×10⁵ sequences, so 100000 is still a cap. `-evalue`
still couples the hit set to database size, because the printed
E-value scales with `db_length` and the cutoff is an absolute number.

```
blastp
  -query {input}
  -db {reference}
  -out {output}
  -outfmt "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore"
  -max_target_seqs 100000
  -evalue 1000
  -num_threads 4
```

Not passed, and not to be added after a run: `-comp_based_stats`,
`-max_hsps`, `-task`, `-matrix`, `-gapopen`, `-gapextend`, `-seg`,
`-soft_masking`, `-dbsize`, `-searchsp`, `-sum_stats`. `OLD_FSC` stays
unset. `-num_threads 4` matches the non-exclusive allocation. This is
not an exclusive `epyc-7542` job.

Multiple HSPs per query–subject pair are left at the program default.
The shipped row key is `(qseqid, sseqid)` plus one index column when a
pair has more than one row. `qstart` is the column the fitter can use
when it is unique inside the pair. A failure to find that column is a
REFUSE with the fitter's own reason and is reported as that reason.

## Predictions

Fixed now.

**B1-rows.** The row-key sets of the halves and the whole are predicted
not to match. Direction: `only-union > 0` and `only-whole = 0`, unless
the 100000 cap binds. A hit kept on a half has a smaller `db_length`,
so its Spouge E-value is smaller than the same alignment on the whole.
The cutoff is 1000 on every run. A hit with E just under 1000 on a half
can sit over 1000 on the whole and appear only in the union. The whole
is the larger search, so it does not keep a hit the half dropped for
this reason. If some query has more than 100000 hits with E ≤ 1000, the
cap can also drop keys, and that can put keys in `only-whole`. That
second mechanism is named here. The predicted primary mechanism is the
E-value cutoff.

**B1-fit.** This applies to aligned rows, the rows whose key is in the
whole and in exactly one part. It is predicted even if the key sets
then fail.

- `evalue` (column 10) fits `total_entry_length`. The reported formula's
  database factor is `gbp->db_length`. `identity` does not fit.
  `entry_count` does not fit once the length ratio and the count ratio
  differ by more than the printed half-ULP. On the primary halves those
  two ratios are both near 2, so a tie is allowed. The tie-break is the
  locked longest-first partition, and it is predicted to leave
  `total_entry_length`.
- `bitscore` (column 11) is `identity`.
- `pident`, `length`, `mismatch`, `gapopen`, `qstart`, `qend`,
  `sstart`, and `send` are `identity` on aligned rows. The matrix
  adjustment in mode 2 depends on the query and the subject, which are
  the same pair in the part and in the whole.
- `per_key_row_count` is not the E-value factor.

The Karlin combination `n − N·ℓ` would fit no member, or would tie and
then fail the tie-break. That is the `OLD_FSC` path. This job does not
take it. A column residual that matches no member falsifies B1-fit and
is reported.

**Overall.** REFUSE. The predicted reason is the fitter's row-key
message, with `only-union` greater than zero. The fitter checks column
failure before key-set failure, so a B1-fit miss surfaces as
`matches no normalizer` (or a tie-break elimination) and the JSON still
carries the key-set counts.

## What each outcome means

- **REFUSE on row keys, as predicted.** The closed family is a model of
  a column on a decomposed hit set. A database-size-dependent global
  cut changes which rows exist. The fitter refuses that argv instead of
  splicing a partial hit set. The family has not been stretched to
  "anything that scales."
- **SHIP.** The cutoff and the cap left the row keys equal on these 20
  queries, and `evalue` matched `total_entry_length` within half-ULP.
  The explanation, already fixed here, is that 2.14.1's default
  reported E-value is the Spouge `db_length` factor and that no hit sat
  between the half-database cutoff and the whole-database cutoff. That
  is reported. It is not a fit of the Karlin combination, and it is not
  a license to add a member.
- **Rows match, `evalue` fits no member.** The length adjustment, or a
  gap between sequence-source length and FASTA residue length, is above
  print precision. REFUSE. Reported. This is the outcome a Karlin-only
  reading expects. It falsifies B1-fit and confirms that the family
  stops at a combination.
- **Any other reason** (`duplicate rows have no row-index column`, a
  version mismatch, a tool failure) is reported with that reason. It is
  not rewritten into the predicted sentence.

## Job

Account `biyik_1165`, partition `main`, one ordinary node, 4 CPUs,
16 GB, 12 hours. Not exclusive. No `epyc-7542` constraint. Scratch is
node-local `SLURM_TMPDIR` or `/tmp`. The result file is
`results/reference_boundary_blast.json` and contains the decision, the
reason, per-column member residuals, the key-set counts, and
`acts.provenance` (git hash, host, Python, BLAST version). Code and
`ACTS_GIT_HASH_FILE` live under

`/project2/biyik_1165/jjt_373/csci270-star/acts-reference-boundary-20261009/`.

Submit with `ssh discovery sbatch` after `rsync` through `discovery`.
No login-node search.

## Addendum 2026-10-09 — outcome

Job `12864923` on `a01-16`, elapsed 21m48s, exit 0. Git
`2ea39e2b93df41aea17c6663bafb00b7a40d7c54`. `blastp` and `makeblastdb`
reported `2.14.1`. `OLD_FSC` was unset. The measured file is
`results/reference_boundary_blast.json`.

**Overall.** REFUSE, as predicted. The reason string is
`out: column 2 matches no normalizer`. Column 2 is `pident`. The locked
text said a B1-fit miss would surface as that sentence, and that the
JSON would still carry the key-set counts. Both happened. The fitter
stops at the first column failure, so the row-key sentence was not the
recorded reason.

**B1-rows.** Confirmed. Whole 15,125, union 28,937, only-union 13,812,
only-whole 0, in-two-parts 0. The halves keep rows the whole drops. The
100000 cap did not place any key only in the whole.

**B1-fit, as locked, on the fitter's aligned keys.** Falsified.
Identity holds for `pident` on 15,124 of 15,125 aligned keys. The miss
is query `WP_000153074.1`: part `21.875`, whole `33.333`. That same key
is the sole miss for `length`, `mismatch`, `gapopen`, `qend`, `send`,
and `bitscore`, and the sole miss for `evalue` against
`total_entry_length` (15,124 of 15,125). `qstart` and `sstart` are
identity on all 15,125. The sentence "on aligned rows, `evalue` fits
`total_entry_length` and `bitscore` is identity" is false for the
fitter's own aligned set, because of this one key. `pident` was
predicted to be identity. It is the column the fitter named.

### Post-hoc

The outputs of job `12864923` lived on node-local scratch and were
gone. Job `12897373` re-ran the same argv and the same probe on
`d05-41` (partition `debug`, 59-minute cap) and wrote the three tables
under `/tmp/acts_ref_bdiag_12897373/call{1,2,3}/out`. Those files are
`results/reference_boundary_tables/{whole,part0,part1}.tsv`. Their key
sets match job `12864923`. The fitter was not modified. The job was
cancelled after the copy, while `column_residuals` was still scanning.
Classification and the same-HSP residuals below were computed from the
copied tables with the shipped `consistent` / `half_ulp` predicate.
Details are in `results/reference_boundary_diagnosis.json`.

`infer_key_columns` selects `sstart` (column 8). `length`, `mismatch`,
`gapopen`, `qstart`, and `qend` are integers and are not unique inside
`(qseqid, sseqid)`. The whole table has 15,078 pairs, 32 of them with
more than one row. `index_rows` accepts every table: there is no
duplicate `(qseqid, sseqid, sstart)`.

One joined key fails the alignment body. It is one pair, and each
table has one row for it:

```
whole  WP_000153074.1 sp|A0KJE6|LOLA_AERHH 33.333 36 23 1 3 37 1 36 205 25.0
part0  WP_000153074.1 sp|A0KJE6|LOLA_AERHH 21.875 128 72 5 3 105 1 125 180 24.3
```

Both rows start at query residue 3 and subject residue 1. The intervals
differ (`qend`/`send` 37/36 against 105/125). The whole interval is
absent from the part. Classification: `different_hsp`. Counts:
`same_hsp` 15,124, `different_hsp` 1, `misaligned_row_key` 0,
`same_interval_different_score` 0, duplicate row keys 0.

On those 15,124 joins the alignment body is byte-identical, and the
shipped predicate gives:

- `pident`, `length`, `mismatch`, `gapopen`, `qstart`, `qend`,
  `sstart`, `send`, and `bitscore` are identity (15,124/15,124).
- `evalue` fits `total_entry_length` (15,124/15,124). `identity` fits
  77. `entry_count` fits 14,183. `per_key_row_count` fits 88.
- The worst `evalue` residual under `total_entry_length` is
  1.489 on `WP_029396194.1` (`245` × 1.99791 against printed `488`).
  The half-ULP tolerance on that row is 1.499, so the predicate
  accepts it.

Where the reported HSP is the same alignment, the 2.14.1 reading
holds: printed E-value tracks database length, and bit score has no
database factor. The REFUSE is the one pair whose reported HSP changes
between the half and the whole. That single `pident` change is enough
for column 2 to match no member. The hit-set cut is also present
(only-union 13,812) and would have been the refusal if column 2 had
fitted. Both are reported. No member was added.
