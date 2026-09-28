# Probe miss-rate (measured)

Protocol `docs/PROBE_EVAL_PROTOCOL.md` (`b4c878f`). Seed 20260927. `N_rec`=2500. JSON: `probe_eval.json`. Figure: `figures/12_probe_eval_catch.png`.

This is a measurement, not a method. Closest priors: Chen/Segura metamorphic testing; Dune `cache-check-probability`; vCache (LLM δ). F6 is outside the guarantee (argv-named inputs only).

## Headline

| Metric | Value |
|--------|-------|
| Unsafe-ship | **33 / 256** (0.129) |
| Unsafe-ship excluding F6 | **1 / 224** (0.0045) |
| False-refuse (C1–C5 × 4 `probe_n`) | **0 / 20** |
| Smallest *p* reliably caught (locked: F1–F5, F7, F8, both formats refuse) | **none** at every `probe_n` (F4/F5 VCF *widen and SHIP*) |
| Same, refuse-or-bust classes only (F1–F3, F7, F8) | `probe_n`=50 → 0.1; 200/500/2000 → 0.01 |

The one in-scope miss: **vcf F4, *p*=0.01, `probe_n`=50**. No live record in the 50-prefix, so ID was not widened; input 2 MATCH’d (same IDs); input 3 changed IDs and replay ≠ stock.

## Per class (32 cells = 2 formats × 4 *p* × 4 `probe_n`)

| Class | Input-1 refuse | First probe (count) | Unsafe-ship | Notes |
|-------|----------------|---------------------|-------------|-------|
| F1 | 32/32 | determinism 25, MATCH 7 | 0 | MATCH catches when the prefix has no live record |
| F2 | 29/32 | shuffle 25, MATCH 4 | 0 | 3 silent cells at *p*=0.001 (no live neighbor on input 3) |
| F3 | 27/32 | subset 23, MATCH 4 | 0 | 5 cells SHIP then input-2 MATCH fails (miss-batch *N* ≠ file *N*) |
| F4 | 16/32 | perturbation 15, MATCH 1 | **1** | FASTA refuses; VCF widens ID and SHIPs (correct) except the *p*=0.01/`n`=50 miss |
| F5 | 17/32 | perturbation 10, MATCH 7 | 0 | VCF late-key / widen ID; FASTA MATCH or perturbation |
| F6 | 0/32 | — | **32** | Undetectable by design |
| F7 | 32/32 | determinism 24, MATCH 8 | 0 | Same pattern as F1 |
| F8 | 32/32 | shuffle 26, MATCH 6 | 0 | |

## Catch rate by frequency (excl. F6)

| *p* | Input-1 refuse |
|-----|----------------|
| 1.0 | 0.857 (48/56) |
| 0.1 | 0.857 (48/56) |
| 0.01 | 0.839 (47/56) |
| 0.001 | 0.750 (42/56) |

The 0.857 ceiling is F4/F5 VCF: perturbation *widens* and SHIPs, which is the pre-registered success for those classes, not a miss.
