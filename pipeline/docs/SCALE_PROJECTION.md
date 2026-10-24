# Scale projection: RefSeq bacteria × Pfam (PROJECTED)

Workstream W4 (`exp/scale-projection`). Reproduces from
`pipeline/scripts/scale_projection.py` + downloaded NCBI
`assembly_summary.txt` (sha256 pinned) + committed headline / W8 / release-chain
results. **No `main.tex` edits.** Paper-facing sentences use `\sys`; prose here
says TARE.

## Headline (PROJECTED)

Re-annotating **every RefSeq bacterial genome** against each new Pfam release
costs **~143 core-years** with a full stock `hmmscan`; with TARE it costs
**~34 core-years** on a typical update (headline median **4.24×**, 95% CI
4.17–4.68) and **≈143 core-years** on a rebuild-like release (~93% models
changed, as in 37.4→38.0).

At the paper’s Pfam cadence (eight releases in 25 months ≈ **3.84 releases/year**)
and the historical rebuild fraction among seven measured pairs (**1/7**):

| Scope | Stock / release | TARE typical update | TARE rebuild | Stock / year | TARE / year (historical mix) |
| --- | ---: | ---: | ---: | ---: | ---: |
| All RefSeq bacteria | 143 (widened 105–324) | 34 (22–78) | ≈143 | 548 | 189 (132–434) |
| Reference/representative only | 6.0 | 1.4 | ≈6.0 | 23.1 | 8.0 |

Widened bands are required: validating the headline per-protein model against
every measured genome (9 headline + 53 W8 with stock walls) gives **median
absolute relative error 26.3% > 25%** (W8 used `--cpu 8` on other CARC nodes).

## Data (NCBI assembly_summary)

| Field | Value |
| --- | --- |
| URL | https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/assembly_summary.txt |
| Download start (UTC) | 2026-10-24T07:39:25Z |
| Download end (UTC) | 2026-10-24T07:40:51Z |
| Bytes | 242,166,326 (HEAD `Content-Length` matched; ≤400 MB gate) |
| sha256 | `7034587bd874e2ef5ba670c6efd4a5f422dfd487fe4e6db1afb3f92288d4c626` |
| Scratch path | `~/tmp/tare_scale/assembly_summary.txt` (not in repo) |

Counts (column `protein_coding_gene_count`; blank/`na` **excluded**, never imputed):

| Set | Assemblies | With count | Missing/blank | Σ proteins |
| --- | ---: | ---: | ---: | ---: |
| All RefSeq bacteria | 544,941 | 544,814 | 127 | 2,179,028,082 |
| `reference genome` | 22,893 | 22,893 | 0 | — |
| `representative genome` | 0 | 0 | 0 | — |
| Reference **or** representative | 22,893 | 22,893 | 0 | 92,099,519 |

All rows have `version_status=latest` and `genome_rep=Full` in this snapshot.
This file’s bacteria table labels the curated subset as `reference genome` only
(zero `representative genome` strings); “representatives only” below means
`refseq_category ∈ {reference genome, representative genome}`.

## Cost model (MEASURED → rate)

**Rate (headline server).** For each EXACT headline genome:

`core_seconds_per_protein = stock_median_wall_s × n_cpus / n_records`

Sources: `pipeline/results/exact_replay/headline_carc.json` +
`headline_measured/*.json`. Stock walls are the scored A-arm medians; `n_cpus=4`
(`--cpu 4`); `n_records` from fill; node type AMD EPYC 7542 (e.g. `b22-30`).

| Quantity | Value | Source key |
| --- | --- | --- |
| Median core-s / protein | 2.065 | derived from nine EXACT genomes |
| Headline speedup median | 4.243 | `headline_carc.json` `headline_median` |
| 95% CI | 4.172–4.684 | `bootstrap_ci95.low/high` |
| First-run overhead | 1.321× | `first_run_overhead_median` |
| Break-even updates | 0.260 | `break_even_n_median` |

Per-release projection assumes a **warm** TARE cache (first-run 1.32× paid once;
break-even 0.26 updates). Update cost = stock / S. Rebuild releases
(`f_Δ ≥ 0.9`, measured 37.4→38.0 `f_Δ=0.931`) ≈ **one full stock rerun under TARE**.

**Pfam cadence.** Eight releases in 25 months → 3.84 releases/year (paper Fig. 1).
**Rebuild fraction.** 1 of 7 pairs in `pipeline/results/release_chain/pairs.json`.

## Validation

Calibrate on headline median rate; predict stock wall =
`n_proteins × rate / cpus` for every headline + W8 genome with a stock wall
(W8 `n_proteins` = `headers.fasta_records` when present, else NCBI count).

| Metric | Value |
| --- | --- |
| N genomes | 62 (9 headline + 53 W8) |
| Median \|pred−meas\|/meas | **0.263** |
| Widen gate (25%) | **triggered** |
| Observed core-s/protein (all) | min 2.017, p10 2.183, median 2.802, p90 4.698, max 5.591 |

Widened stock band = envelope of (point × (1±median abs err), csp p10/p90).

## Assumptions (would make the number wrong if false)

1. NCBI `protein_coding_gene_count` tracks hmmscan FASTA workload at catalog scale.
2. Headline EPYC 7542 / `--cpu 4` core-s/protein transfers to the deployment of interest (validation already shows ~26% median wall error on W8).
3. Future Pfam mix resembles the seven measured pairs (one rebuild-like).
4. Caches stay warm; refuse/verify tails do not force full reruns beyond the timed 13.4% pair.
5. Summing every assembly does not double-count unique protein work a curator would dedupe.

## Reproduce

```bash
# assembly_summary already at ~/tmp/tare_scale/ with the pinned sha256
nice -n 10 python3 pipeline/scripts/scale_projection.py \
  --assembly-summary ~/tmp/tare_scale/assembly_summary.txt \
  --expected-sha256 7034587bd874e2ef5ba670c6efd4a5f422dfd487fe4e6db1afb3f92288d4c626
# → pipeline/results/scale/projection.json
```

## Proposed paper sentences (W3 hand-off)

Use `\sys`. Each `% source:` path is relative to repo root; JSON paths are
dot-keys into `pipeline/results/scale/projection.json` unless noted.

1. Re-annotating every RefSeq bacterial genome against each new Pfam release is projected to cost 143 core-years for a full stock hmmscan of 2.18 billion proteins, versus 34 core-years with \sys on a typical update at the headline median 4.24× (≈143 core-years when a release rewrites ~93% of models, as in 37.4→38.0).
   `% source: PROJECTED pipeline/results/scale/projection.json projection.all_refseq_bacteria.stock_core_years_per_release.point=142.59979366110335 projection.all_refseq_bacteria.tare_core_years_per_typical_update.point=33.60663993313079 projection.all_refseq_bacteria.tare_core_years_per_rebuild_release.point=142.59979366110335 assembly_counts.all_bacteria.sum_protein_coding_gene_count=2179028082; MEASURED pipeline/results/exact_replay/headline_carc.json headline_median=4.243202948728078; MEASURED pipeline/results/release_chain/pairs.json pairs.4.f_delta=0.9311802701115678; HAS PROJECTED; HAS core-years`

2. Under Pfam’s recent cadence of eight releases in 25 months and a one-in-seven rebuild rate among measured consecutive pairs, the same catalog is projected at 548 stock core-years per year versus 189 core-years per year with \sys (widened 132–434 after a 26% median per-protein validation error against headline+W8 walls).
   `% source: PROJECTED pipeline/results/scale/projection.json projection.all_refseq_bacteria.per_year.stock_core_years=547.5832076586369 projection.all_refseq_bacteria.per_year.tare_core_years_historical_mix.point=188.84002738828147 projection.all_refseq_bacteria.per_year.tare_core_years_historical_mix.widened_lo=131.53446548020497 projection.all_refseq_bacteria.per_year.tare_core_years_historical_mix.widened_hi=433.87621321867397 projection.all_refseq_bacteria.per_year.pfam_releases_per_year=3.84 cost_model.rebuild.rebuild_fraction_among_measured_pairs=0.14285714285714285 validation.median_abs_rel_error_stock_wall=0.26284007645898827; NOMINAL eight=8; NOMINAL months=25`

3. Restricting to RefSeq reference genomes (22{,}893 assemblies; 92.1 million proteins in this snapshot) lowers the projected stock cost to 6.0 core-years per release and the \sys typical-update cost to 1.4 core-years.
   `% source: PROJECTED pipeline/results/scale/projection.json projection.representatives_only.stock_core_years_per_release.point=6.027169871823096 projection.representatives_only.tare_core_years_per_typical_update.point=1.420429318288858 assembly_counts.n_reference_or_representative=22893 assembly_counts.representatives_only.sum_protein_coding_gene_count=92099519; HAS reference`
