# Unrelated ship: semantics recheck (2026-10-20, WA2)

Dated addendum before the measured_v2 pre-registration. No pfscan
process was started for this recheck. Round-1 semantics live in
`UNRELATED_SHIP_SEMANTICS.md`; this file only re-judges the two
contract decisions that the v2 draw will reuse.

## Claim under recheck

On the locked command

```
pfscanV3 --matrix-only --nthreads 1 --output-method 7 --fasta \
  {reference} {input}
```

TARE's exact path should authorize a PROSITE matrix update
2026_02 → 2026_03 under the **identity** normalizer with **no pin**.

## Identity normalizer — still holds

Source re-read (pftools3 profile format, SIB docs; Debian `pfscan(1)`
for the classical tool; Schuepbach et al., Bioinformatics 2013 for the
V3 heuristic):

- Normalization coefficients live on the profile (`LINEAR`,
  `GLE_ZSCORE`, `GLE_ZSCAVE`). None take the library size, the residue
  total of the profile file, or a rank among profiles.
- Cut-off level defaults to the profile's own level-0 threshold, not an
  E-value times database size.
- Method-7 TSV columns 0–9 are entry-local or sequence-local. No column
  is a function of how many matrix entries are in the reference file.

Round-1 pilot and measured contracts recorded every numeric column as
`identity`, every byte column as `byte`, `inferred_pin` null, and why
`exact replay under identity normalizer`. Nothing in the format or the
locked argv has changed since that measurement. The v2 draw does not
re-fit the contract; it reuses it.

## No-pin decision — still holds

There is still no size pin in pfscanV3's usage for matrix search. Mode
(`--mode`) selects a normalization function already stored on the
profile; it does not freeze a database size. Inventing a pin would be a
second design of the same question. Refuse paths that need a pin
(hhsearch E-value, MMseqs2 / Foldseek prefilter) stay refused; they are
not this ship.

## What changes in v2 (design, not semantics)

| Item | Round 1 | Round 2 (this file's follow-on protocol) |
|---|---|---|
| Measured seed | 20261102 | 20261272 (WA block) |
| n genomes | 10 | 20 |
| Exclusions | pilot only | pilot + round-1 measured + build smoke |
| Per-genome floor | 1906 | 1906 (unchanged) |
| Pooled floor | none | 38120 (= 20 × 1906) |
| Negative control | pilot known-bad (20261103) | re-run on a v2 SHIP genome (20261273) |

No third redesign of the semantic question. The fresh draw is a new
measured sample under the same locked command and the same contract.

## Non-claims

- Laptop times are not speed evidence.
- Pattern search (`PROSITEPATTERNS`) is out of scope (`--matrix-only`).
- Multi-thread print order is not the claim (`--nthreads 1`).
