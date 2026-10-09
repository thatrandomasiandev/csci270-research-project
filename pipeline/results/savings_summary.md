# HMMER accumulated-savings analysis

Protocol: `pipeline/docs/SAVINGS_PROTOCOL.md`.
Analyzer: `pipeline/scripts/analyze_savings.py`.
Analyzed: 2026-10-08T01:19:00.770615+00:00.

**Primary / `paper_uses`:** hmmsearch. **hmmscan is post-hoc** and is not promoted after seeing numbers.

Probe cost *P* uses **singleton_8** (`probe_n = 8`, 12 calls): `P = Σ (a + b · n_j)`, `cum_cached = P + Σ cached_i`. This is the queued-job account, not `batched_500`.

hmmsearch is the locked primary (paper_uses). hmmscan is post-hoc. Part 2 predictions used N = 4,192 for every genome; measured stock uses each proteome's N_i. Probe cost P uses singleton_8 (12 calls) because that is what the queued jobs ran.

## Correctness gates

No MATCH / audit / STOP failures in the dumps that were present.

## A · diverse E. coli (30) — hmmsearch (PRIMARY)

Source `/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/results/savings_20261006/A_hmmsearch.json` · 30/30 genomes with cached wall · resumed=False.

| Metric | Stock | Cached (no P) | Cached + P |
|--------|------:|--------------:|-----------:|
| wall hours | 5.3477 | 1.9516 | 2.3948 |
| CPU hours | 16.1569 | 6.2874 | — |
| cum. speedup (wall) | 1 | 2.740× | 2.233× |

Stock wall = measured at sampled positions [1, 2, 5, 10, 20, 30] plus `a + b·N_i` elsewhere (a=132.558, b=0.118895). Unsampled stock wall is a + b·N_i. Unsampled stock CPU is imputed from the sampled CPU/wall ratio times that wall (3.0198 CPU-s/wall-s).
Part 2 predicted cum. speedup at this prefix (N=4192 stand-in, no P): 2.111×. singleton_8 predicted (with P): 1.792×.
P = 1595.447 s (0.4432 h) from 12 calls [8, 8, 8, 8, 1, 1, 1, 1, 1, 1, 1, 1].

**Fit error > 10% at sampled points (do not replace the fit):**
- genome 1: |error|/measured = 0.406 (measured 526.950s, predicted 740.945s)
- genome 2: |error|/measured = 0.351 (measured 458.126s, predicted 618.958s)
- genome 5: |error|/measured = 0.642 (measured 384.227s, predicted 630.848s)
- genome 10: |error|/measured = 0.772 (measured 392.364s, predicted 695.408s)
- genome 20: |error|/measured = 0.726 (measured 411.576s, predicted 710.508s)
- genome 30: |error|/measured = 0.759 (measured 397.437s, predicted 698.975s)

## B · O157:H7 (40) — hmmsearch (PRIMARY)

Source `/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/results/savings_20261006/B_hmmsearch.json` · 40/40 genomes with cached wall · resumed=False.

| Metric | Stock | Cached (no P) | Cached + P |
|--------|------:|--------------:|-----------:|
| wall hours | 7.6401 | 1.1159 | 1.5591 |
| CPU hours | 22.9548 | 5.7739 | — |
| cum. speedup (wall) | 1 | 6.847× | 4.900× |

Stock wall = measured at sampled positions [1, 2, 5, 10, 20, 40] plus `a + b·N_i` elsewhere (a=132.558, b=0.118895). Unsampled stock wall is a + b·N_i. Unsampled stock CPU is imputed from the sampled CPU/wall ratio times that wall (3.0034 CPU-s/wall-s).
Part 2 predicted cum. speedup at this prefix (N=4192 stand-in, no P): 4.077×. singleton_8 predicted (with P): 3.242×.
P = 1595.447 s (0.4432 h) from 12 calls [8, 8, 8, 8, 1, 1, 1, 1, 1, 1, 1, 1].

**Fit error > 10% at sampled points (do not replace the fit):**
- genome 1: |error|/measured = 0.462 (measured 506.925s, predicted 741.183s)
- genome 2: |error|/measured = 0.457 (measured 498.410s, predicted 726.202s)
- genome 5: |error|/measured = 0.793 (measured 407.652s, predicted 730.839s)
- genome 10: |error|/measured = 0.766 (measured 406.056s, predicted 717.285s)
- genome 20: |error|/measured = 0.718 (measured 424.176s, predicted 728.818s)
- genome 40: |error|/measured = 0.807 (measured 399.806s, predicted 722.278s)

## 3×
- hmmsearch cumulative wall is 6.85× (primary).

## What this is not

- Not permission to promote hmmscan to `paper_uses`.
- Not `probe_n = 500` and not the batched-18 deployable probe.
- Not invented numbers: every total comes from a job dump plus the locked fit.

