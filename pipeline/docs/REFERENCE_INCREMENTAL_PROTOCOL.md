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
