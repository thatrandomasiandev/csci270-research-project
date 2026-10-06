# Reference-side incrementality: kill tests (pre-registered 2026-10-03)

Written **before** either test runs. Locked text below is never edited;
later changes are dated addenda.

## Idea under test (PROPOSED)

ACTS reuses results when **records** recur. Many tools take a second input,
a **reference** (Pfam, UniProt, an Ensembl release), and a new reference
release currently forces full re-annotation. The proposal: infer from the
outside how a tool's output decomposes over the reference, including global
normalizers (HMMER: E-value = Z·P, Z = number of models), so a new release
needs only its new or changed entries. Hand-built precedents: iBLAST
(Dash et al., PLoS ONE 2021), iSeqSearch (PeerJ 2025).

Two tests can kill it before anything is built.

## Test R1 — reference churn (is there anything to reuse?)

Data: Pfam-A 38.2 (`data/hmmer/Pfam-A.hmm.gz`, already used) and the
immediately preceding public release on the EBI FTP
(`/pub/databases/Pfam/releases/`). One download (< 1 GB).

Per model, keyed by Pfam accession without version (`PFxxxxx`):

- **strict hash**: the full model block except `DATE` and other lines that
  cannot affect `hmmscan --tblout` output (`DATE`, `BM`, `SM`, `COM`).
  NAME, ACC, DESC, GA/TC/NC, and the model body are all included, since each
  can change a tblout line.
- **body hash**: from the `HMM` line to `//` plus GA (what `--cut_ga`
  scores against).

Report: models in each release, added, removed, and unchanged under each
hash; Z for each release.

**Kill rule R1:** if fewer than **50%** of models in the newer release are
unchanged under the strict hash, reference-side reuse is not worth building.

## Test R2 — decomposition and normalizer (can reuse be exact?)

Local, small: 300 proteins from collection-A genome 1 (`GCF_002853805.1`,
fixed seed 20261003) and 400 Pfam models drawn from 38.2 (fixed seed). Split
the 400 models into two random halves R₁, R₂ (fixed seed). Run
`hmmscan --cut_ga --noali --tblout` on the full set R and on each half.

Checks, per (query, model) hit:

1. **Hit set:** hits(R) = hits(R₁) ∪ hits(R₂) exactly.
2. **Unnormalized columns:** every tblout column other than the two E-value
   columns (full-sequence and best-domain) is identical between the full run
   and the half that contains the model.
3. **Normalizer:** with Z = number of models in the database searched, each
   E-value satisfies E_R ≈ E_half · Z_R / Z_half. A value counts as
   reproduced if the rescaled printed value, re-printed at the same
   precision as HMMER's output, equals the printed full-run value
   (**byte-reproducible**). Also reported: the fraction within the printing
   tolerance (half a unit in the last printed digit, i.e. **consistent**).

**Kill rule R2:** if check 1 or check 2 fails for any hit, the tool is not
reference-decomposable under `--cut_ga`, and the idea dies for HMMER.

Check 3 decides the **form** of the claim, not its life:

- byte-reproducible for all hits: exact reuse is possible from printed
  output alone;
- consistent but not byte-reproducible: reuse is exact for hits, scores and
  counts, but normalized fields need recomputation from unrounded values the
  black box does not print. The paper would claim exactness for the hit
  set and unnormalized fields only.

## Ship controls

Nothing here changes `acts/`. The committed generic-path results (SnpEff
MATCH 52,638; fill-tags 23,072 hits) are untouched. `bash run_tests.sh` must
still pass after any script is added.

## Not in scope

No CARC timing and no claim of speedup. R1's projected re-annotation saving
is a PROJECTION (changed fraction of models; `hmmscan` cost is dominated by
b·N, which scales with the number of models).

## Addendum 2026-10-03 — R2 as registered was underpowered; powered rerun

Written after the registered R2 ran and **before** the powered run below.

The registered R2 (400 random models, 300 proteins) produced only **5
hits** (`results/reference_kill_r2_underpowered.json`): hit set equal, 0
unnormalized mismatches, E-values 10/10 consistent and 5/10
byte-reproducible. With 5 hits it cannot support a conclusion, so it is
kept as recorded and not counted.

**Powered R2 (R2p).** Same checks and kill rule. Changes:

- Models: every Pfam 38.2 model that hit genome 1 in the CARC stock run
  (`results/reference_kill_g1_hit_models.txt`: 3,871 names, from
  `savings_failed_20260928/tblout/A_hmmscan_01_stock.tbl` on CARC) plus
  1,000 random other models (seed 20261003). Total Z_R = 4,871.
- Split: two random halves of those 4,871 (seed 20261003).
- Proteins: the same 300-protein sample as R2.

Selecting models that hit is deliberate: decomposition can only fail on
hits. It does not bias checks 1–2, which compare runs on identical inputs.

## Addendum 2026-10-03 — outcomes of R1 and R2p (results; rules unchanged)

**R2p** (`results/reference_kill_r2p.json`, `afcb119`): 578 hits. The
union of hits from the two halves equals the full run (check 1). There are
0 mismatches outside the E-value columns (check 2). All 1,156 E-values are
consistent with E_full = E_half · Z_full / Z_half within print rounding,
and 724 (62.6%) are byte-reproducible (check 3). **Not killed.** By the
pre-registered branch for check 3, the claim form is: reuse is **exact for
the hit set and all unnormalized columns**. Normalized fields are
consistent with the inferred normalizer only up to HMMER's printed
precision; exact values need the unrounded P-values the black box does not
print. Fixing Z on the command line (`hmmscan -Z`) would make E-values
release-stable, but that is a user choice of flags, not something ACTS
infers. It is reported as an option, not as the method.

**R1** (`results/reference_kill_r1.json`): Pfam 38.1 → 38.2. Z goes from
27,481 to 30,134 models (2,674 added, 21 removed). **86.6%** of the newer
release's models are unchanged under the strict hash (87.1% body-only).
**Not killed** (threshold 50%).

**Projection (PROJECTED, not measured).** Re-annotating a proteome after
this release needs hmmscan only against the 4,052 new or changed models
(13.4% of Z_new). Assume hmmscan cost scales with the number of models
searched (b·N dominates, as measured in `headline_screen.json`) and per-model
cost is uniform. Then cost falls to about 13.4% of a stock run, plus the
merge and rescale, which gives about **7.4×** per re-annotation. Per-model
cost is not uniform, so a measured re-annotation across 38.1 → 38.2 is
required before any number is claimed.

## Addendum 2026-10-03 — scope, negative control, domtblout, MATCH type

Written **before** R2n and R3 run. It follows a soundness review by the
parallel ACTS session.

### Scope of the R2p result

R2p's hit-set equality holds **because `--cut_ga` thresholds on bit
score**, which does not depend on database size. Under HMMER's default
E-value reporting thresholds (`-E 10`, `--domE 10`), a smaller database
(smaller Z) gives smaller E-values and admits extra hits near the
boundary. The claim is therefore scoped to **score-thresholded modes**.

### R2n — negative control (must FAIL check 1)

Identical to R2p (same 300 proteins, same 4,871 models, same split), but
**without `--cut_ga`**, i.e. default E-value thresholds. **Expected:**
check 1 fails, with the union of the halves' hits a strict superset of the
full run's hits. If R2n *passes* check 1, the decomposition test cannot
tell a coupled normalizer from an uncoupled one, and R2p's pass carries no
weight.

### R3 — per-domain output (`--domtblout`), two candidate normalizers

R2p tested `--tblout` only. R3 runs `hmmscan --cut_ga --domtblout` on the
R2p inputs and checks, per domain line (query, model, domain index):

1. The domain-line set of the full run equals the union of the halves.
2. Every column other than the domain E-value columns (c-Evalue, i-Evalue)
   is identical.
3. For each domain E-value column, two candidate normalizers are tested
   from the data, without assuming HMMER's documentation:
   - **Z**, the number of models in the database searched;
   - **domZ**, the number of targets reported for that query in that run
     (data-dependent, recomputed from the merged hit set).

   A column is assigned the normalizer under which all its values are
   consistent within print tolerance. If neither fits, that column is
   **not reusable** and must be recomputed.

**Kill rule R3:** if check 1 or 2 fails, domtblout is not
reference-decomposable, and the claim is restricted to `--tblout`.

### MATCH type for reference-side reuse (declared)

**`ref-merge`**: byte-identical for the hit set and every unnormalized
column; normalized columns (`tblout` E-values, and any domtblout column
assigned a normalizer in R3) are equal **within the printed precision**
after rescaling. It is a distinct, weaker relation than `byte`, `order` or
`multiset`. No reference-side result may be described as byte-identical.

## Addendum 2026-10-03 — outcomes of R2n and R3 (results; rules unchanged)

**R2n negative control** (`results/reference_kill_r2n.json`): without
`--cut_ga`, the union of the halves has **3 hits not in the full run**
(1,085 vs 1,082; strict superset), plus 100 unnormalized mismatches
(inclusion/domain counts under E-value thresholds). Check 1 **fails as
required**. The decomposition test therefore distinguishes a Z-coupled
threshold from a score threshold, and R2p's pass carries weight. Scope
stays: score-thresholded modes only.

**R3 domtblout** (`results/reference_kill_r3.json`): 560 domain lines;
the union equals the full run; 0 mismatches outside the domain E-value
columns. **Not killed.** Normalizers assigned from the data:

| Column | Fits Z | Fits domZ (targets reported per query) | Assigned |
|---|---|---|---|
| full-sequence E-value | 560/560 | 150/560 | **Z** |
| i-Evalue | 560/560 | 150/560 | **Z** |
| c-Evalue | 151/560 | 504/560 | **not reusable** (recompute) |

The review that prompted this addendum expected i-Evalue to scale with
domZ; the data assign it Z. c-Evalue mostly tracks a per-query count but
not the pre-registered domZ definition. Trying other definitions now would
be post hoc. It is left as an exploratory follow-up and is not claimed.

**`ref-merge` claim, consolidated:** under `--cut_ga`, hit sets, domain
sets and all unnormalized columns are byte-exact. tblout E-values, domtblout
full-sequence E-values and i-Evalues are equal within printed precision
after rescaling by Z. domtblout c-Evalues must be recomputed.

## Addendum 2026-10-03 — c-Evalue: exploratory finding and confirmatory test R3c

**Which domZ R3 tested:** the number of distinct targets with at least one
line in that run's **domtblout** for the query. HMMER's domZ counts targets
that pass the **per-sequence** reporting threshold, and a target can pass it
while reporting no domain line, so R3's definition can undercount.

**Exploratory (post hoc, not a result):** on the same R3 files, recomputing
domZ from **tblout** (per-sequence reported targets per query) makes c-Evalue
consistent on **560/560** lines. Because it was found after seeing R3, it
does not change R3's pre-registered assignment (c-Evalue: not reusable).

**R3c (confirmatory, pre-registered here, fresh data):** a new 300-protein
sample from genome 1 and a new random split of the same 4,871 models, both
with seed **20261004**. Run `hmmscan --cut_ga` with both `--tblout` and
`--domtblout` on the full set and on each half. Checks:

1. The domain-line set of the union equals the full run's.
2. 0 mismatches outside the domain E-value columns.
3. c-Evalue rescaled by domZ_full/domZ_half, **with domZ = per-sequence
   reported targets for the query from tblout**, is consistent within print
   tolerance on **every** line; full-sequence E-value and i-Evalue are
   consistent rescaled by Z.

**Rule:** if check 3 holds for all lines, c-Evalue is reclassified as
reusable with the tblout-domZ normalizer, which is data-dependent and
recomputed from the merged per-sequence hit set. If any line fails,
c-Evalue stays not reusable.

## Addendum 2026-10-03 — R3c outcome (result; rule applied as registered)

`results/reference_kill_r3c.json` (fresh seed 20261004): 511 domain lines;
the union equals the full run; 0 unnormalized mismatches. **511/511**
consistent for full-sequence E (Z), i-Evalue (Z), and c-Evalue
(domZ = per-sequence reported targets for the query, from tblout). Per the
R3c rule, **c-Evalue is reclassified as reusable** with that data-dependent
normalizer, recomputed from the merged per-sequence hit set.

`ref-merge` now covers every domtblout column: domain sets and unnormalized
columns byte-exact; full-sequence E and i-Evalue rescaled by Z; c-Evalue
rescaled by per-query domZ. All three are within printed precision.

## Addendum 2026-10-06 — prior-art verdict (no new test)

The kill rule for novelty, the search log, and the readings are in
[`REFERENCE_PRIOR_ART.md`](REFERENCE_PRIOR_ART.md). Verdict: **NARROW**.
iBLAST, iSeqSearch, and GeStore's BLAST plugin hand-build reference
incrementality and E-value repair for specific search tools. GeStore's
HMMER plugin does not rescale. KumQuat infers input-stream combiners
and does not fit a normalizer. Nothing read infers both decomposition
over reference entries and a fitted column normalizer for an unmodified
CLI with no per-tool plugin. The R1–R3c results are unchanged. They
show the property for `hmmscan --cut_ga`; they are not that inference
procedure. A hand-coded HMMER plugin would not meet the surviving claim.

## Addendum 2026-10-06 — generic fitter pre-registration

Written **before** any fitter implementation. No `acts/` code is added
with this addendum, and no tool is run for it. Locked text above is
unchanged. The family in §3 is closed here. Extending it after seeing
any tool's output requires a new dated addendum whose title contains
**post-hoc**. A member that names a tool is not a member of this family.

The R1–R3c files remain what they were: evidence that one argv has the
property. They are not evidence that a generic fitter found it. This
addendum is the procedure that would have to find it, and the tests
that accept or reject that procedure.

### 1. Abstraction

The tool is an unmodified function of two argv-named inputs:

\[
F(\text{records}, \text{reference}).
\]

`records` is the stream Survivor 1 already memoizes. `reference` is the
other argv-named input (a database, a profile file, a sequence file).
The fitter does not read environment variables, unnamed paths, or a
tool's source. Fault class F6 stays outside the guarantee.

A **per-format entry parser** splits `reference` into entries. Parsers
in scope now:

| Format | Entry | Length (format data) | Volatile-tag list |
|---|---|---|---|
| HMMER3 profile text | bytes up to and including the `//` line | the integer on the `LENG` line | `DATE`, `BM`, `SM`, `COM` |
| FASTA | one record (`>` header through the next header) | residue count, whitespace ignored | empty |
| `entryline` (fixtures only, §4 T3) | one line `ID LENGTH` | the integer `LENGTH` | empty |

Length is format data sitting next to that parser. It is not computed
by the fitter and it is not looked up in a tool manual at fit time.
HMMER3 length is model length (`LENG`), not the number of lines in the
block. FASTA length is residues, not header characters.

**Volatile lines.** A line is volatile when its first
whitespace-delimited token is in that format's tag list. The tags
above are data for the HMMER3 parser. The fitter never contains the
list. `DATE`, `BM`, `SM`, and `COM` are the same four lines R1 excluded
from the strict hash; the rule here is the generic form of that
exclusion (first token, not a tool predicate).

**Entry identity.** SHA-256 of the entry bytes after volatile lines are
dropped, remaining lines kept in order with their newlines. An entry
whose identity hash is unchanged across a reference release is the unit
of reuse. FASTA, with an empty tag list, hashes the whole record, so a
header edit is a changed entry.

The fitter refuses if the named reference format has no parser, or if
a HMMER3 entry has no `LENG` line. It does not guess a length.

### 2. Decomposition probe (a)

Parameters, fixed now:

| Parameter | Value |
|---|---|
| Parts \(k\) | 2 |
| Probe record count \(n_p\) | 300 |
| Split and sample seed | 20261006, except T1 and T2, which use the historical R2p/R3c/R2n inputs |

**Partition.** Let the entries be in file order, \(n = |R|\). Draw

```
rng = random.Random(seed)
idx = list(range(n))
for i in range(n - 1, 0, -1):          # Fisher–Yates
    j = int(rng.random() * (i + 1))    # random.Random.random, not shuffle
    idx[i], idx[j] = idx[j], idx[i]
```

Cut the shuffled index list into \(k\) contiguous parts whose sizes
differ by at most one: base \(= n // k\), remainder \(= n \% k\); the
first `remainder` parts have size `base + 1`, the rest have size
`base`. For \(k = 2\) and even \(n\) the parts are equal. Parts are
non-empty, disjoint, and cover \(R\). If \(n < 2\), REFUSE.

This Fisher–Yates is the spec, not `random.Random.shuffle` (CPython
3.11's `shuffle` is a different stream). Guard, derived from this
algorithm at seed 20261006 and \(n = 4\): the shuffled index list is
`[0, 3, 2, 1]`. An implementation whose partitioner disagrees on that
input is wrong. T3 uses this partitioner. T1 and T2 do **not**: they
reuse the halves already drawn by `scripts/reference_kill_tests.py`
(its `Random.shuffle`, seeds 20261003 and 20261004). Regenerating those
files, if they are not on disk, must call that script. It must not
re-split them with the Fisher–Yates above.

**Probe records.** A second `random.Random(seed)`, not the partition
stream. `sample` of size \(\min(n_p, |records|)\) from the record input
in file order. Fixtures smaller than 300 use every record.

**Runs.** Invoke \(F\) on the probe records with the whole reference
and with each part. Same argv otherwise. \(k + 1\) invocations.

**Row key.** The format's output parser exposes, on each data row,
`record_key`, `entry_key`, and an optional `row_index` (domain index
is the HMMER3 domtblout case of `row_index`; the fitter does not know
the word "domain"). The row key is that triple. Comment lines are not
rows.

**Decision.** Fit §3 first, on rows whose key appears in the whole and
in exactly one part. Then **ship (a) only if** the union of the part
outputs matches the whole under the locked `ref-merge`:

- the set of row keys is equal (a key in two parts, or in only one
  side, fails);
- non-numeric columns are byte-identical on aligned rows;
- a numeric column assigned `identity` is byte-identical;
- a numeric column assigned a linear member matches within the
  half-ULP predicate of §3 after rescaling by that member.

Shipping (a) without a completed (b) is not allowed. `ref-merge` is
otherwise unchanged: normalized columns are not called byte-identical.

**Failure.** Any failure in this addendum — including a column with no
unique member — is **REFUSE** for this argv. The caller runs one full
\(F(\text{records}, \text{reference})\) and does not splice probe rows,
part rows, or a partially fitted column into the user-facing output.
No silent reuse. A fit is per argv: `--cut_ga` and the default
threshold are different contracts, and a fit on one is not a fit on
the other.

### 3. Normalizer family (b), closed

A column is **numeric** when every aligned printed token parses as a
finite float. A mixed column REFUSEs the argv.

Printed-precision predicate, the same one R2p/R3c already implement.
For a printed token, let `dec` be the number of digits after the
decimal point in the mantissa (0 if there is no decimal point). If the
token contains `e` or `E`, let `exp` be the integer exponent;
otherwise `exp = 0`.

\[
\mathrm{half\text{-}ULP}(\text{printed}) = 0.5 \times 10^{-\mathrm{dec}} \times 10^{\mathrm{exp}}.
\]

A part value \(v\) rescaled by a finite factor \(\phi\) is consistent
with a whole value \(w\) when

\[
|v \phi - w| \le \mathrm{half\text{-}ULP}(w_{\text{printed}}) + \mathrm{half\text{-}ULP}(v_{\text{printed}}) \cdot |\phi|.
\]

**Members.** A numeric column is assigned a member only when the rule
below leaves exactly one distinct candidate. The candidates are:

1. **`identity`.** The printed token is unchanged across the partition
   (byte-identical on every aligned row). Factor \(\phi = 1\).
2. **`entry_count`.** \(\phi = |R| / |R_{\text{part}}|\), where
   \(R_{\text{part}}\) is the unique part containing the row's entry.
   Size measure: number of entries.
3. **`total_entry_length`.** \(\phi = L(R) / L(R_{\text{part}})\).
   \(L\) is the sum of per-format lengths from §1. Residues for FASTA,
   `LENG` for HMMER3 profiles, the `LENGTH` field for `entryline`.
4. **`per_key_row_count` of an output table \(T\) of the same run.**
   \(\phi = c(\text{record\_key}, T, R) / c(\text{record\_key}, T, R_{\text{part}})\),
   where \(c\) is the number of data rows in \(T\) with that record
   key. One candidate per output table the argv wrote, not per tool.
   A zero denominator means this candidate does not fit.

No candidate's definition contains a tool name, a flag, or the letters
Z or domZ. HMMER's database size and its per-sequence reported-target
count are what `entry_count` and `per_key_row_count` recover **if**
the probe says so. They are not inputs to the fitter.

A candidate **fits** when every aligned row is consistent under its
\(\phi\). `identity` fits only on byte-identical tokens, which implies
the half-ULP test at \(\phi = 1\).

**Distinctness.** Two fitting candidates are the same candidate when
each one's prediction is consistent with the other's on every aligned
row. An all-zero column makes every linear factor predict zero; those
predictions are not distinct from `identity`. If the only distinct
fitting candidate is `identity`, or every fitting candidate is
observationally equivalent to `identity`, assign `identity`.

**Ties.** If two or more distinct candidates fit the primary probe,
run the disambiguating probe below. Do not pick a favorite. If it
leaves exactly one distinct candidate, assign that one. If it leaves
none, or still leaves two or more, REFUSE the column.

**A column that no candidate fits:** REFUSE the whole
reference-incremental path for this argv. Do not drop the column, do
not recompute just that column, do not reuse the others. This is
stricter than R3's "not reusable, recompute this column," and it is
the rule for the fitter. R3's sentence is not edited.

**Disambiguating probe, pre-registered.** One partition, built from
the reference only, used for every tie. It does not depend on which
candidates tied and it is not redesigned after a tool run.

Order entries by per-format length descending, breaking ties by
content-hash ascending. Walk that order and fill part \(L\) until
\(2 \sum_{e \in L} \mathrm{length}(e) \ge L(R)\) and \(L\) is a proper
subset. Part \(S\) is the complement. Both parts must be non-empty;
if the walk cannot make two non-empty parts, the tie stands and the
column REFUSEs. Integer comparison only (`acc * 2 >= total`).

Re-run the same probe records on \(L\) and on \(S\). Reuse the
whole-reference output from the primary probe when the reference bytes
and the probe records are unchanged. A tied candidate survives only if
it still fits every aligned row. Distinctness is applied again.

Why this partition exists: a primary split that balances both entry
count and total length gives \(\phi = 2\) for both size measures, so
they tie even when only one is the true law. Loading the longest
entries until half the total length makes the count ratio and the
length ratio disagree whenever lengths are unequal. When every entry
has the same length the two ratios agree on every partition, the probe
cannot break the tie, and the column REFUSEs. That refusal is correct:
the two members are the same function on that reference.

The family is not Karlin–Altschul effective length, not a bit-score
correction, and not a polynomial search over arbitrary coefficients
(Zhang, Chen, Hao, Xiong, Xie, Zhang, and Mei, ASE 2014, search linear
and quadratic relations for scalar library functions; this family is
four named measures, not that search). Spouge rescaling as written in
iBLAST is hand-derived for BLAST; it is credited, and it is not a
member. Adding effective length, or any fifth measure, after a BLAST
or HMMER run is a **post-hoc** addendum or it is not part of the claim.

### 4. Acceptance tests

Pass/fail is fixed here. The implementation session does not get to
loosen a line after a run. Future code lives in `acts/`. Scripts call
it. A HMMER-named branch, a column-name map from `evalue` to
`entry_count`, or a constant \(Z\) inside the fitter fails the suite
even if T1's numbers come out right.

**T1 — recover the measured hmmscan contract, with no HMMER normalizer code.**
Data: `hmmscan --cut_ga` tblout as in R2p (`results/reference_kill_r2p.json`,
seed 20261003, 300 queries, 4,871 models) and tblout + domtblout as in
R3c (`results/reference_kill_r3c.json`, seed 20261004, same model set,
fresh 300 queries and a fresh split). Pass only if the fitter ships
(a) and assigns:

| Columns | Member |
|---|---|
| tblout full-sequence E-value and best-domain E-value (kill-test indices 4 and 7); domtblout full-sequence E-value and i-Evalue (indices 6 and 12) | `entry_count` |
| domtblout c-Evalue (index 11) | `per_key_row_count` of the **tblout** table of the same run (one row per reported entry; the quantity R3c called tblout domZ) |
| every other numeric column in those tables | `identity` |

R2p already measured 1,156/1,156 E-values consistent with entry count
and 0 mismatches elsewhere. R3c measured 511/511 for full-sequence E
and i-Evalue against entry count, and 511/511 for c-Evalue against
tblout per-query row count, with 0 unnormalized mismatches. Those
files did **not** compare `total_entry_length`, and they did not run
the disambiguating partition. If the primary halves tie entry count
with length, or tie tblout row-count with domtblout row-count, T1
passes only when the disambiguating probe of §3 leaves the assignment
in the table. If the tie survives, T1 fails. That failure is a result,
not a license to edit this table.

**T2 — R2n negative control must REFUSE.**
Same inputs as R2p without `--cut_ga`
(`results/reference_kill_r2n.json`). Measured: union 1,085 hits, full
run 1,082, 3 hits only in the union, so the row-key sets differ.
Pass iff the fitter REFUSEs this argv. Shipping a normalizer, or
reusing the overlapping rows, fails T2.

**T3 — synthetic fixtures.** Pure Python function \(F\), format
`entryline`, column printed `{:.6f}` (half-ULP \(= 5 \times 10^{-7}\)).
Not HMMER-shaped: no profile text, no tblout header, no `LENG`. The
numeric column is named `evalue` on purpose. Seed 20261006, \(k = 2\),
the Fisher–Yates partitioner of §2.

Shared reference for A and B, file order `e0 e1 e2 e3`, lengths 1, 2, 1, 2 (total length 6,
four entries). Content hashes are SHA-256 of `b"{id} {length}\n"`.
Primary parts from the pinned shuffle `[0, 3, 2, 1]`:
\(\{e0, e3\}\) and \(\{e2, e1\}\), each of count 2 and length 3, so
entry-count, total length, and a one-row-per-hit row count all have
\(\phi = 2\). Disambiguating part \(L = \{e1, e3\}\) (the two length-2
entries; hash order puts `e1` first), length 4, count 2; part
\(S = \{e0, e2\}\), length 2, count 2. Records `r0` and `r1` with
payloads \(p = 0.5\) and \(p = 0.25\). Hits are only `e1` and `e3`
(one output row per hit per record).

| Fixture | Law for `evalue` | Primary probe | Required decision |
|---|---|---|---|
| A | \(\|entries\| \cdot p\) | entry-count, length, and per-key row count tie (\(\phi = 2\)); identity does not fit | **ship**, member `entry_count`, and only after the disambiguating probe (on \(L\), length factor 1.5 and row-count factor 1 both miss; entry-count factor 2 hits) |
| B | \(L(R) \cdot p\) | same three-way tie | **ship**, member `total_entry_length`. The same disambiguating probe must reject `entry_count` (predicted 4.0 and 2.0 against whole 3.0 and 1.5 for \(p = 0.5, 0.25\)) |
| C | per-key row count in the only output table, times \(p = 0.5\). File order `c0 c1 c2 c3`, all length 1. `q0` hits `c0`, `c1`, `c2`; `q1` hits all four. Primary parts \(\{c0, c3\}\) and \(\{c2, c1\}\) | row-count fits every row; entry-count and length predict factor 2 and miss `q0` (part value 0.5 rescales to 1.0, whole is 1.5) | **ship**, member `per_key_row_count` of that table |
| D | 1-based rank of the entry by content hash among the entries of **this** run. File order `d0 d1 d2 d3`, all length 1, one record, one row per entry | rank is not byte-identical and is not a constant multiple of entry count, length, or row count (`d2`'s part rank 2 against whole rank 3 on the pinned split) | **REFUSE** |
| E | one row per unordered pair of entries, four entries, value `1.000000`, row key includes both entry ids | each half emits one pair; the whole emits six; key sets differ | **REFUSE** because decomposition fails |

Derived checks the test must assert, not thresholds to tune: on A and
B the primary probe is a tie, and the disambiguating probe is what
separates them. A fitter that skips the tie-break and guesses
`entry_count` fails B. A fitter that hard-codes the column name
`evalue` fails B the same way.

**T4 — ship controls, unchanged.** After the fitter lands,
`pipeline/run_tests.sh` still passes, and the existing contracts are
untouched: SnpEff reassembly MATCH on 52,638 records
(`results/inference_checks.json`, `n_reassembled` = `n_stock` = 52638,
`bodies_equal` true) and `bcftools +fill-tags` widened to `SAMPLES`
with 23,072 hits on HG00099 (same file). This addendum does not
re-run them and does not change their expected numbers.

### 5. Red-team

Three attacks, given the NARROW verdict in
[`REFERENCE_PRIOR_ART.md`](REFERENCE_PRIOR_ART.md). Each names the
experiment that defeats it. None of these experiments has been run;
T1–T3 are the defeats, pre-registered above, not results.

**Attack 1. "This is GeStore with inference."**
GeStore (Pedersen, Willassen, Bongo, Euro-Par HiBB 2013, §2.2 and §3)
incrementalizes an unmodified binary with a hand-written plugin.
The BLAST plugin corrects E-values from Turcu, Nestorov, and Foster;
the HMMER plugin only generates input files and treats every Pfam
change as significant. iBLAST writes the Spouge formula in
BLAST-specific code. Defeat: the fitter module contains no per-tool
branch, and T3's oracles are not those tools. A plugin that special-cases
HMMER can be adjusted until T1 passes and still fails T3-B (length, not
entry count), T3-D (rank), and T3-E (pairs). T1 plus T3 together are
the bar. Either one alone is GeStore or is an untested family.

**Attack 2. "The family is tuned to HMMER."**
The four members were chosen with R2p/R3c and the Spouge/iBLAST formula
already in view. That is true, and hiding it would be a worse paper.
The algebra is not the claim. The claim is that a closed family,
written down before the fitter runs, is fitted or refused with no
per-tool code. Defeat, in three parts:

- No member's definition names a tool (§3). A fifth member needs a
  **post-hoc** addendum, and results measured before that addendum
  cannot be cited as confirmation of the extended family.
- T3 is not HMMER-shaped. B must ship `total_entry_length` on a column
  named `evalue`. D and E must REFUSE. A family or a code path that
  only knows "E-value scales with the number of models" fails those
  three.
- T1 failing closed is a successful kill of this attack's cousin, "it
  will fit HMMER because we built it to." If the disambiguating probe
  cannot separate entry count from total length on the R2p/R3c
  halves, the fitter REFUSEs and the HMMER contract does not ship.

**Attack 3. "The probe costs more than the savings at low churn."**
Low churn is the large-savings side, not the dangerous side. One
re-annotation of \(n\) query records against a reference whose changed
fraction is \(c\), under the model \(T = a + b n\):

\[
T_{\text{stock}}(n) = a + b n, \qquad T_{\text{inc}}(n, c) = a + c\, b n, \qquad S(c) = (1 - c)\, b n.
\]

Assumptions, all stated, none of them a new measurement: \(a\) does not
shrink on a smaller reference; \(b\) scales linearly with the fraction
of entries searched; the \(k = 2\) parts partition the entries, so
their per-record costs sum to \(b n_p\); merge and rescale are ignored
next to these terms. The measured wrapper \(w = 0.019\) s
(`results/headline_screen.json`) is \(3.6 \times 10^{-5}\) of the
primary probe below, so it is left out. Per-entry cost is **not** uniform; the
R1 outcome addendum already says a timed 38.1 → 38.2 run is required
before any speedup is claimed. This paragraph does not claim one.

Probe cost. Each of the \(k + 1\) invocations pays \(a\). The whole
reference contributes \(b n_p\), and the parts together contribute
another \(b n_p\):

\[
P = (k + 1)\, a + 2\, b\, n_p = 3a + 2 b n_p \quad (k = 2).
\]

The disambiguating probe reuses the whole run and adds two invocations
on a partition of the same reference, costing \(2a + b n_p\). Both
together:

\[
P_{\text{both}} = 5a + 3 b n_p.
\]

Break-even churn on **one** later re-annotation (the harsh case; more
releases only amortize \(P\)):

\[
c^\* = 1 - \frac{P}{b n}, \qquad \text{provided } b n > P.
\]

Savings exceed the probe when \(c < c^\*\). They fall short when churn
is high.

Inputs, MEASURED: \(a = 31.959641573764316\) s and
\(b = 0.7228553909794854\) s/record at \(n = 4192\), hmmscan
`--cut_ga`, full Pfam, `results/headline_screen.json`. So
\(b n = 3030.2097989860026\) s. R1 changed-model fraction
\(c_{\mathrm{R1}} = 4052 / 30134 = 0.134466\)
(`results/reference_kill_r1.json`: \(z_{\text{new}} = 30134\),
unchanged strict \(= 26082\)). \(n_p = 300\) from §2.

PROJECTED, from the formulas and those inputs:

| Probe | \(P\) (s) | \(c^\*\) | \(S(c_{\mathrm{R1}})\) (s) | \(S / P\) |
|---|---|---|---|---|
| Primary only | 529.592 | 0.8252 | 2622.749 | 4.95 |
| Primary plus tie-break | 810.368 | 0.7326 | 2622.749 | 3.24 |

\(c_{\mathrm{R1}}\) is below both thresholds, so on this workload one
re-annotation's projected savings cover the probe, including the
tie-break. The attack would land if a release had \(c > c^\*\), or if
the linear-\(b\) assumption is badly wrong. Neither is answered by
this arithmetic. The 7.4× sentence in the R1 outcome addendum stays a
separate projection and is not updated here.

## Addendum 2026-10-06 — fitter build and T1–T4 outcome

Written after the library in `db16609` and the measurements cited
below. Locked text above is unchanged. No fifth normalizer. No new
probe. The procedure is the one pre-registered above; this addendum
records what shipped and what the tests did.

### Shipped algorithm

`F(records, reference)` is `acts/reference_run.py`. The reference is
the argv-named file that is not the record input and parses as
entries, unless `--reference` names it. Per-format parsers cover
profile text (the on-disk header token `HMMER3/f`), FASTA, and the
`entryline` fixtures. Length and the volatile-tag list are data on
those parsers. The strict entry hash is `acts/entry_hash.py`;
`scripts/reference_kill_tests.py` calls it.

The strategy's probe is the pre-registered one: \(k = 2\),
\(n_p = 300\), seed `20261006`, Fisher–Yates on
`random.Random.random`. T1 and T2 do not use it. They reuse the
historical `Random.shuffle` halves from
`scripts/reference_kill_tests.py` (seeds `20261003` and `20261004`).
The closed family is identity, `entry_count`, `total_entry_length`,
and `per_key_row_count`. Two or more non-identity members that both
fit are a tie even when their primary factors coincide. The
disambiguating partition is the pre-registered length-descending
split. Cache rows are keyed by record key, entry content hash, and
argv with the reference path removed. A later reference reuses
unchanged entries, scans new or changed entries as a sub-reference,
drops removed entries, rescales fitted columns, recomputes per-key
counts from the merged row set, and re-renders. `--verify full` runs
the tool on the full reference and compares under ref-merge. Audit
samples \(q = 0.02\). `--baseline gestore` runs the decomposition
probe and refuses any numeric column that is not identity.

### Index step

Sidecars are built by a caller-declared `--prep` command, not by
tracing. `acts/trace.py` is Linux-only and records reads. The index
has to exist before the tool runs, on every sub-reference, including
on a Mac. The command is data. No tool name is compiled into `acts/`.

### Refusal

One full run, no partial reuse, and a stated reason, when any of
these hold: fewer than two entries; empty record input; a column is
mixed or matches no member; a non-numeric column is not
byte-identical; the disambiguating partition is empty or still leaves
two or more non-identity members; primary row-key sets differ; prep
or the tool fails. A tool or prep failure is not cached. A gestore
baseline also refuses when a numeric column is not identity.
`--verify full` mismatch is `REFUSE_MATCH`. Audit mismatch is
`REFUSE_AUDIT`.

### Amdahl

The dominant term of one incremental re-annotation is
\(b \cdot n_{\text{changed}}\). PROJECTED speedup, the
pre-registered break-even model, not a new fit:

\[
\mathrm{speedup}(c) = \frac{a + b n}{a + c\, b n}
\]

with \(a = 31.959641573764316\) s,
\(b = 0.7228553909794854\) s/record, \(n = 4192\), MEASURED in
`results/headline_screen.json`. The table above stands: primary
\(P = 529.592\) s and \(c^\* = 0.8252\); primary plus tie-break
\(P = 810.368\) s and \(c^\* = 0.7326\);
\(S(c_{\mathrm{R1}}) = 2622.749\) s. The wrapper and the merge stay
out of the model. The probe is paid once. Nothing in the build
micro-optimizes them.

### T1 — PASS

`results/reference_fitter_t1.json`. Historical halves, 2435 and 2436
entries, \(Z = 4871\). R2p is `--cut_ga` tblout, 578 rows. R3c is
tblout plus domtblout, 511 domain rows. Both `SHIP`.

Assignments, with no normalizer code for this tool: tblout columns 4
and 7, and domtblout columns 6 and 12, `entry_count`. Domtblout
column 11, `per_key_row_count` of the tblout table. Every other
numeric column, identity.

R2p's primary partition left `entry_count` and `total_entry_length`
tied on columns 4 and 7 (578/578 each). The disambiguating probe kept
`entry_count` and dropped total length. Tie-break residuals, both
candidates:

| Column | Candidate | Consistent | Fits | Max abs residual |
|---|---|---|---|---|
| tblout 4 | `entry_count` | 578/578 | yes | \(6.65754174650969 \times 10^{-7}\) |
| tblout 4 | `total_entry_length` | 17/578 | no | \(2.4029899858449707 \times 10^{-5}\) |
| tblout 7 | `entry_count` | 578/578 | yes | \(0.004008486175745979\) |
| tblout 7 | `total_entry_length` | 19/578 | no | \(1.401697018993092\) |

R3c did not tie. The same historical halves already rejected total
length, so the disambiguating probe was not run. Primary-partition
residuals for both candidates are in the same JSON under
`primary_residuals`: tblout 4, total length 436/528; tblout 7,
449/528; domtblout 6, 424/511; domtblout 12, 435/511.
`entry_count` is 528/528 and 511/511 on those columns. Domtblout 11
fits only `per_key_row_count` of tblout (511/511); `entry_count` is
119/511 and total length is 104/511.

### T2 — PASS

`results/reference_fitter_t2.json`. R2n `REFUSE`: tblout column 16
matches no normalizer. No reuse.

### T3 — PASS

`pipeline/tests/test_reference_fitter.py`, fixtures under
`pipeline/tests/fixtures/reference_fitter/`. A ships `entry_count`.
B ships `total_entry_length`, separated from A by the tie-break. C
ships `per_key_row_count`. D and E `REFUSE`. The gestore baseline
refuses law A.

### T4 — PASS

The same module reads `results/inference_checks.json`: SnpEff
`n_reassembled` = `n_stock` = 52638 and bodies equal; fill-tags
widening is the HG00099 case (23072 hits, cache key includes
`SAMPLES`). `pipeline/run_tests.sh` is the gate for this commit.

### Smoke, not a gate

`results/reference_fitter_smoke.json`. The model list in
`scripts/repro_savings_desc_stop.py` has 73 names, not 78; all 73
were used. Seven description edits plus one cloned entry is 8/74 of
the release. Forty records. The second run `SHIP`s under
`--verify full`, 10 of 11 rows reused. Indicative Mac wall times:
first reference \(0.310\) s, release \(0.122\) s. Not a speedup
claim. At this size the \(b \cdot n_{\text{changed}}\) term is not
what the clock shows.

Provenance on the result files: git `db16609` at measurement time,
host `Joshuas-MacBook-Pro-3.local`, CPython 3.11.9, HMMER 3.4 (Aug
2023). The work tree was dirty from files this session did not own.
Those files were not edited here.

Next measurement, not done here: a timed Pfam 38.1 → 38.2
re-annotation on CARC, submitted with `ssh discovery sbatch`, not run
on a login node.

## Addendum 2026-10-06 — timed 38.1→38.2 re-annotation

Written after the length-weighted churn below and **before** any timed
arm. Locked text above is unchanged. No fifth normalizer. The gate is
the primary formula. The secondary number is reported and is not the
gate.

### Workload

Collection A, seed-20260926 order, positions 1–5. Same proteomes as
`docs/SAVINGS_PROTOCOL.md`:

| Pos | Index | Accession | Proteins |
|---|---|---|---|
| 1 | 9 | `GCF_002853805.1` | 5117 |
| 2 | 5 | `GCF_002090355.1` | 4091 |
| 3 | 2 | `GCF_001650275.1` | 5176 |
| 4 | 75 | `GCF_052050745.1` | 4197 |
| 5 | 29 | `GCF_016659085.1` | 4191 |

Protein counts are the FASTA record counts on the Mac copies. The
timed job recounts them and stops if a file disagrees.
`hmmscan --cut_ga --noali --cpu 32`, writing tblout and domtblout.
The index step is the declared prep `hmmpress -f {reference}`.

### Files

| Release | SHA-256 | Version file |
|---|---|---|
| 38.1 | `d3d30c8e6801bfedecf783408ecc98916f8f1dda8974c6e51036fcbdd765f591` | Pfam 38.1, 27481 families, 2025-09 |
| 38.2 | `2d82087b6c5c60d762cc767f98e8260b273134c215ab7efccf7440614a4e5dab` | Pfam 38.2, 30134 families, 2026-01 |

38.2 bytes are the CARC file
`/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/hmmer/Pfam-A.hmm.gz`,
copied to the Mac. 38.1 is `pipeline/data/hmmer/pfam38.1/Pfam-A.hmm.gz`.
The timed job re-hashes both and stops on a mismatch.
`results/reference_reannot_churn.json`.

### Length-weighted churn (model files only, before timing)

Unchanged means the content hash is in 38.1. That hash is the strict
hash R1 used. The cross-check matches R1: 30,134 models in 38.2,
26,082 unchanged.

\[
c_{\mathrm{length}} = 600557 / 4754065 = 0.12632494507332145.
\]

Count churn stays \(c = 4052 / 30134 = 0.13446605163602576\). Changed
and new models are shorter than the average model, so the length
weight is below the count weight.

### What is not run

A whole-invocation cache keys the reference bytes. The reference
changed, so that cache has zero hits. It is not run.

### Setup, untimed, reported

Per genome, one reference-incremental run on 38.1 fills the cache.
The probe and fit run once, on genome 1's fill. Its wall is \(P\).
The new release is pressed once before any stock arm. That press is
not charged to arm (i). The gestore probe runs once, on genome 1
against 38.2. Its wall is reported separately and is not \(P\).

### Arms

Each genome, three repeats, one genome per invocation, on one
exclusive `epyc-7542` node. Order inside a genome:
`(i), (ii), (iii)` and then the next repeat. Genomes follow the
table above.

- **(i)** stock `hmmscan` on the pressed 38.2.
- **(ii)** reference-incremental on 38.2, warm from that genome's
  38.1 cache. The wall includes parsing, the diff, the sub-reference
  build, prep, the tool on changed and new models, merge, rescale,
  and render. It does not include a second full scan.
- **(iii)** shipped `--baseline gestore`. It does not infer a
  normalizer. Columns whose values depend on reference size cannot
  be reused, so the fit refuses and the timed call scans every 38.2
  entry, including prep of that copy. Expected: wall at least that
  of (i), larger by the full-release prep, and not the incremental
  speedup. A decision other than `REFUSE` is `STOP_GESTORE`.

### Preflight

The layout pin landed at `9c9f51a`. Its library check,
`preflight_stock_outputs`, is the record-memo savings contract.
This experiment's MATCH is `ref-merge`, so the preflight is that
relation: after genome 1's cache fill, one stock run and one
incremental run on 38.2, every row of both tables. Those two runs
are not repeats. A mismatch is `STOP_MATCH` and no repeat starts.

### MATCH

Every timed (ii) is `ref-merge`d against that repeat's (i), both
tables, every row. A mismatch stops the remaining repeats, records
the reason, and no speedup is claimed.

### Predictions

\[
\mathrm{speedup}(c, n) = (a + b n) / (a + c\, b n)
\]

with \(a = 31.959641573764316\) s and
\(b = 0.7228553909794854\) s/record from
`results/headline_screen.json`.

**Primary.** \(c = 4052/30134\). At \(n = 4192\) this is
\(6.968662141244353\times\). The five genomes are not all 4,192
proteins, so the comparison value is the unweighted mean of the five
per-genome primaries, \(6.99924607283027\times\):

| Accession | Primary | Secondary |
|---|---|---|
| `GCF_002853805.1` | 7.048181565546971 | 7.4733276423250805 |
| `GCF_002090355.1` | 6.9579639131287525 | 7.371035883891939 |
| `GCF_001650275.1` | 7.052346971503922 | 7.478054963227952 |
| `GCF_052050745.1` | 6.969179352246338 | 7.383742308241676 |
| `GCF_016659085.1` | 6.968558561725364 | 7.3830389153098235 |

**Secondary.** The same formula with \(c_{\mathrm{length}}\). The
unweighted mean is \(7.417839942599294\times\). At \(n = 4192\) it is
\(7.383156276518736\times\).

**Gate.** Let \(S(g)\) be mean wall of (i) divided by mean wall of
(ii) for genome \(g\), repeats only, probe excluded.
\(\bar S\) is the unweighted mean of the five \(S(g)\).
**CONFIRMED** if there is no stop and
\(|\bar S - 6.99924607283027| / 6.99924607283027 \le 0.25\).
**REFUTED** otherwise. Report the result either way.

Also report, and do not use as the gate: \(\bar S\) against the
secondary mean; speedup including measured \(P\),
\(\bar T_i / (\bar T_{ii} + P)\) and
\(5 \bar T_i / (5 \bar T_{ii} + P)\), where \(\bar T\) is the
unweighted mean of the per-genome mean walls.

### Amdahl, to be measured on arm (ii)

For each timed (ii) repeat the clocks are:

- `prep_s`: the declared prep on the sub-reference
- `tool_s`: the tool on changed and new models. This is the measured
  stand-in for \(a + b \cdot n_{\mathrm{changed}}\)
- `merge_s`: rescale plus render
- `w`: end-to-end wall minus prep, tool, and merge

\(a\) is not separable from one invocation. The report uses the
headline intercept above and sets
\(b \cdot n_{\mathrm{changed}} = \mathrm{tool\_s} - a\), under the
assumption that \(a\) does not shrink. If `tool_s` is below \(a\),
that assumption fails and `tool_s` is the dominant measured term.
The means of these clocks are the measured decomposition. Nothing
here is a license to micro-optimize a term before the means exist.

### Resources

One exclusive `epyc-7542`, 32 CPUs, 128 GB, 48 h requested.
PROJECTED occupancy is about 30–40 h (five cache fills, the probe,
three repeats of a ~50 min stock scan, a shorter incremental scan,
and a gestore scan that also presses a full copy). That projection
is not a result. The job is `jobs/reference_reannot.job`, own tree
`reference_reannot/` on CARC, own `GIT_HASH`. It does not write
`results/savings/`.
