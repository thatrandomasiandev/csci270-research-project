# Survivor 1 measurements (2026-09-24)

Reconstruct:

```
cd pipeline && PYTHONPATH=$PWD python3 -m acts probe-suiteB
cd pipeline && PYTHONPATH=$PWD python3 -m acts overlap --suiteb
```

Key is the paired sequence `(R1, R2)`, not the read name.

## Within-file uniqueness

| ID | n | unique | unique_frac | max × if per-record |
|----|---|--------|-------------|---------------------|
| i03 (best) | 49712 | 43124 | 0.867 | 1.15 |
| i01, i02, i04, i06, i09, i10 | ~47–50k | — | 0.91–0.94 | 1.06–1.09 |
| i05, i07, i08 | 50000 | — | ≥0.976 | ≤1.03 |

## Cross-sample overlap (incremental headline)

`recall_in_new` = fraction of sample B’s distinct pairs already seen in sample A.

| Group | prev → new | shared | recall_in_new |
|-------|------------|-------:|--------------:|
| human_airway | i01 → i02 | 3550 | 0.078 |
| human_airway | i02 → i03 | 2896 | 0.067 |
| human_airway | i03 → i04 | 4739 | **0.108** |
| fly | i05 → i06 | 920 | 0.020 |
| fly | i06 → i07 | 836 | 0.017 |
| fly | i07 → i08 | 894 | 0.018 |
| nfcore | i09 → i10 | 3984 | 0.087 |

Best incremental pay-off on these reads is ~11% of the next sample already cached — about 1.12× **if** STAR were per-read. It is not. Fly is overlap-rare.

RNA-seq reads are the wrong instance. Variants are not.

## SnpEff identity (chr22, 200 variants, HG00096 `-c1`)

`results/snpeff_identity/report.json` — SnpEff 5.4c, GRCh38.86, `-noStats`.

| Check | Result |
|-------|--------|
| stock-vs-stock body | MATCH (200/200) |
| shuffled-input body | MATCH |
| full-file `cmp` | DIFF — only `##SnpEffCmd` (input path) |

Header volatility is real and was the reason MATCH is the body. Neighbors do not leak under these flags. Identity is **n=200**, not the full 51k.

## 1000G chr22 overlap (`joint_called_c1`)

Carried ALTs only. CEU: HG00096/97/99. Not separately-called.

| prev → new | n_prev | n_new | shared | recall_in_new |
|------------|-------:|------:|-------:|--------------:|
| HG00096 → HG00097 | 51086 | 52269 | 32428 | 0.620 |
| HG00097 → HG00099 | 52269 | 52638 | 33527 | 0.637 |
| HG00096 → HG00099 | 51086 | 52638 | 33302 | 0.633 |
| HG00096∪97 → HG00099 | 70927 | 52638 | 41447 | **0.787** |

Recomputed 2026-09-24 with full-ALT keys (`scripts/run_c1_overlap.py`). `n_multiallelic` = 0 on all three extracts — this 1000G release is already split into two-allele records — so the numbers match the first-ALT table exactly.

After two samples, the third is 79% already seen (miss_frac 0.21). That is the incremental headline on variants. It is not a timed speedup. It is not VEP. It is not separately-called.

STAR identity refuse: `star_identity_refuse.txt`.
JSON: `vep_chr22_overlap.json`.
