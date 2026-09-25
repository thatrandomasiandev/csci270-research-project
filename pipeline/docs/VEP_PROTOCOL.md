# VEP / per-variant protocol (locked 2026-09-24)

Pre-registered **before** any VEP or SnpEff run. Do not change after seeing numbers.

Order: **identity first**, then overlap on added samples. A header-only `cmp` fail is not a finding.

STAR is closed. Do not hunt another aligner.

## MATCH (decided now)

**Primary MATCH is the record body**, not the whole file.

- Drop every line that starts with `#` (VCF/VEP header, including date, cmdline, cache version).
- Compare the remaining lines as a multiset keyed by `CHROM POS REF ALT` (full ALT field).
- Stock-vs-stock on the *same* input is rung 0. If the **body** differs, REFUSE_IDENTITY (non-deterministic). If only the header differs, that is expected; records-only MATCH stands.

Erratum 2026-09-24: the implementation used a dict (collapsing duplicate keys) and first-ALT keys; fixed to a line multiset and full-ALT keys before any timing run. The SnpEff 200/200 identity result was produced by the old code and must be re-run.
- Full-file `cmp` is logged and must not be the accept/reject rule.

## Overlap (how not to fake 1.0)

Joint-called multi-sample VCFs (1000 Genomes) share a site list by construction. **Never** compute `recall_in_new` on that site list.

1. `bcftools view -s SAMPLE -c1` — keep sites where that sample carries an alternate allele.
2. Overlap those per-sample extracts. Label the table `joint_called_c1`.
3. Separately-called per-sample VCFs (the realistic “add sample 1,001”) are a later rung if we get them. Do not treat `-c1` as that workflow.

## Independence (locked flags)

Default VEP is per-variant. These couple neighbors — **forbidden** on the locked run:

- the `haplo` / Haplosaurus binary
- haplotype / codon-combining plugins
- `--check_svs` (needs DB; overlaps SVs)

Locked VEP argv (when the binary exists):

```
vep --offline --cache --vcf --no_stats --fork 1 --force_overwrite
```

chr22 only. No plugins until independence SHIPs.

**Catch:** annotate the file, shuffle record order, annotate again, compare bodies by variant key. If a variant’s annotation depends on its neighbors, REFUSE_IDENTITY. The fixture `annotate_neighbors` must fail this test; `annotate_1to1` must pass.

## Setup cost

- Do **not** download the full human VEP cache (tens of GB) from this protocol.
- chr22 VCF is ~177 MB (1000G GRCh38 phased). Fetch only with `--fetch-vcf`.
- SnpEff is the lighter second tool if VEP cache is the blocker. Same MATCH and `-c1` rules.

## What is on this machine (2026-09-24, later)

- `bcftools` 1.24 (Homebrew). SnpEff 5.4c + GRCh38.86 under `pipeline/tools/` (gitignored). VEP still absent; full VEP cache not downloaded.
- 1000G chr22 joint VCF + HG00096/97/99 `-c1` extracts under `pipeline/data/vep_chr22/` (gitignored).
- Identity: `results/snpeff_identity/report.json` — body MATCH, shuffle MATCH, full-file DIFF on `##SnpEffCmd`.
- Overlap: `results/vep_chr22_overlap.json` — CEU pairwise recall 0.62–0.64; growing cohort 0.787.

```
python3 scripts/run_snpeff_identity.py
python3 scripts/run_c1_overlap.py
```
