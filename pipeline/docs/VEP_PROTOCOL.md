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

## Alternating rerun (pre-registered) — 2026-09-24

Written **before** any alternating timed run. Do not edit the locked Timing section or `results/snpeff_timing_fit.json` (commit `701d24b`). Question: does the Part B 1.23× stand, and why did the same stock input mean 13.230899 s in the fit (19:42–19:44) vs 19.566053 s in Part B (19:46–19:48)? Inputs are already known byte-identical (`subsets/HG00099.n52638.vcf` == `cached_work/HG00099.vcf`); both used `run_snpeff` (`-Xmx4g -noStats -noLog`).

### Design

- One Python process. Same full-N file for every stock and cached timed run: `data/vep_chr22/subsets/HG00099.n52638.vcf`.
- Cache populated from HG00096 then HG00097 **before** timing. Populate wall is recorded, not used in r. Each cached timed run starts from a copy of that 96∪97 cache (SnpEff still sees miss_n = 11,191).
- 1 discarded warm-up of each path (stock, then cached). Not in r.
- Then **10 pairs**, order **ABBA** with A = stock, B = cached:

```
S C | C S | S C | C S | S C | C S | S C | C S | S C | C S
```

- Per-pair ratio `r_i = stock_i / cached_i`. Report **median r** and a bootstrap **95% CI** on the median (10,000 resamples, seed **20260924**).
- Every cached-path body must `bodies_equal` the stock body. Any fail → stop; do not time further.

### Decision rule

- CI lower bound **> 1.0** → speedup stands; report median r, **not** 1.23.
- CI **includes 1.0** → speedup **not established** on this machine.

### Explanation test (same session, after the pairs)

Locked from `snpeff_timing_fit.json` (do not rewrite): b = 8.425687600843582e-05 s/record, w = 0.04422654166531478 s, N = 52,638, miss_n = 11,191.

(a) Stock n=1 (`subsets/HG00099.n1.vcf`), 5 runs, same Python process → **a_now**.
(b) Stock full-N from a **plain shell loop** (`/usr/bin/time java -Xmx4g … -noStats -noLog`), 5 runs, timed by `/usr/bin/time`, not by Python `perf_counter`.

If run-to-run drift of the fixed cost is the cause of the 6 s shift:

```
r_from_a_now = (a_now + b*N) / (a_now + b*miss_n + w)
```

Compare r_from_a_now to measured median r. Also plot stock wall vs run index inside the session. If the 6 s gap remains after (a) and (b), say it is unexplained.

## Alternating rerun, CARC (pre-registered) — 2026-09-24

Written **before** the CARC job is submitted. Do not edit the locked Timing section, `results/snpeff_timing_fit.json` (commit `701d24b`), the Mac alternating section above, `results/snpeff_alternating.json`, or the Mac figures.

The Mac run (`ddf0807`, `results/snpeff_alternating.json`) met its decision rule (median r = 1.29, 95% CI [1.17, 1.33]) but broke the machine-idle precondition (load 5 → 27; Google Drive >100% CPU). The shell-loop and n=1-after-block conclusions in that report are **withdrawn**. This section re-runs the wall-time experiment on a dedicated CARC node.

### What stays (ddf0807)

- 1 discarded warm-up per path (stock, then cached). Not in r.
- Then **10 pairs**, order **ABBA** (A = stock, B = cached), one Python process.
- Same HG00099 full-N input: `data/vep_chr22/subsets/HG00099.n52638.vcf`.
- Cache pre-populated from HG00096 then HG00097. Populate is recorded, not timed in r. Each cached timed run starts from a copy of that 96∪97 cache (miss_n = 11,191).
- Every cached-path body must `bodies_equal` the stock body. Any fail → stop.
- Decision rule unchanged: bootstrap 95% CI of the per-pair **wall** ratio (10,000 resamples, seed **20260924**). Lower bound > 1.0 → the speedup stands; report the median. CI includes 1.0 → speedup not established on this machine.

### What changes

- **Machine:** one exclusive CARC `main` node (same account/partition as STAR jobs 12159614/12159615). Java major 21. Record `java -version`, `lscpu` model, hostname. Log `uptime` before every pair.
- **Secondary metric:** user+sys CPU seconds per timed run via `resource.getrusage(RUSAGE_CHILDREN)` deltas. Per-pair `r_cpu_i = stock_cpu_i / cached_cpu_i`. Report the median CPU-time ratio (same bootstrap) next to the wall-time ratio. The wall-time rule stays primary.
- **a_now:** stock n=1 (`subsets/HG00099.n1.vcf`), 5 runs, **interleaved** with the pairs — one n=1 run after each even-numbered pair (after pairs 2, 4, 6, 8, 10). Not after the block of 10 pairs. The Mac after-block n=1 and the shell loop are not repeated.

Output: `results/snpeff_alternating_carc.json` (numbers only; include a side-by-side with the Mac JSON, which is not edited).
