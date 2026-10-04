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
