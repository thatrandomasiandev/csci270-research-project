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

## Timing (pre-registered) — 2026-09-24

Written from `results/snpeff_timing_fit.json` **before** any cached-path MATCH or timing. Do not edit this section after seeing Part B.

Tool: SnpEff 5.4c, GRCh38.86, flags `-noStats -noLog` (same as `scripts/run_snpeff_identity.py`). Sample 3 = HG00099 chr22 `joint_called_c1`, N = 52,638 records. Machine: same as the fit; nothing else heavy during the 15 stock runs + 3 wrapper runs. JVM / database load time: **not logged** (`-noLog`; `jvm_or_db_load_s` is null).

### Fit `t = a + b*n`

Nested prefixes of HG00099, 3 runs each. OLS on per-size **mean** wall times.

| n | run1 s | run2 s | run3 s | mean s | stdev s |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 8.468642708001425 | 8.504416708001372 | 8.590933874998882 | 8.52133109700056 | 0.06287570912372939 |
| 1,000 | 8.955383333999634 | 8.47388391700224 | 8.540532417002396 | 8.656599889334757 | 0.2608910993928792 |
| 5,000 | 9.654292374998477 | 10.042541124999843 | 10.369244333000097 | 10.022025944332805 | 0.3579172111549521 |
| 20,000 | 10.746701874999417 | 10.346336000002339 | 11.070879874998354 | 10.721305916666703 | 0.3629389380092583 |
| 52,638 | 14.186916499998915 | 12.793811250001454 | 12.711970124997606 | 13.230899291665992 | 0.828945818137097 |

- a = **8.905257133314686** s (fixed / startup)
- b = **8.425687600843582e-05** s/record

### miss_n and wrapper w

```
miss_n = records of HG00099 not in HG00096 ∪ HG00097
       = 11,191
       ≈ 0.212603062426384 × 52,638
       ≈ 0.213 × 52,638
```

w = wrapper overhead (split + cache lookup + reassembly) with SnpEff replaced by `cat`, same HG00099 input, same 96∪97 key set, 3 runs: 0.04844520799815655, 0.04264554199835402, 0.041588874999433756 s. **w = 0.04422654166531478** s.

### Predicted speedup (locked)

```
predicted speedup = (a + b*N) / (a + b*miss_n + w)
                  = 13.34037057264673 / 9.892402374390407
                  = 1.3485471039049597
```

### ~1× case (stated in advance)

a is 8.91 s of a predicted 13.34 s stock run. If the measured cached/stock ratio is ~1×, that is Amdahl: startup dominates, the overlap is not thereby fake. A ~1× result does not license rewriting miss_n or the fit.
