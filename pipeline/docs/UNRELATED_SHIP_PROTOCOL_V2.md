# Unrelated ship: measured_v2 pre-registration (2026-10-20)

Locked after the WA2 semantics recheck
(`UNRELATED_SHIP_SEMANTICS_V2.md`) and **before** any measured_v2
process. This file is the pre-registration. The measured_v2 job must
not start until this file is in the tree it runs, and the freeze
commit that contains it is recorded in `GIT_HASH` / the result JSON.

Round-1 measured JSON (`measured.json`, outcome INCONCLUSIVE) is not
rewritten. Output of this run: `pipeline/results/unrelated_ship/measured_v2.json`.

## What is being measured

Same tool, same locked command, same contract as round 1:

```
pfscanV3 --matrix-only --nthreads 1 --output-method 7 --fasta {reference} {input}
```

- Archive: `pftools3-v3.2.13.zip` (44,209,720 bytes); binary prints
  `Version 3.2.12 …`.
- References: matrix-only PROSITE 2026_02 (1,434) → 2026_03 (1,441).
- Contract: identity normalizer, no pin, record col 3, entry col 0
  (pilot-locked; semantics recheck 2026-10-20 still holds).

Each genome: fill on 2026_02, update to 2026_03, same cache. Body
compared to one stock scan of that proteome on 2026_03.

## Power floors

| Floor | Value | Rule |
|---|---|---|
| Per-genome | 1906 | Stock body lines on that proteome. Below → genome `INCONCLUSIVE`; TARE is not run. Not a method failure. |
| Pooled | 38120 | Sum of stock body lines over genomes that meet the per-genome floor. Below → run `INCONCLUSIVE`. Equals 20 × 1906. |

## Measured_v2 draw

Seed `20261272`. Pool: `pipeline/data/recurrence/A` (e1scale, 100
`.faa.gz`). Excluded (not eligible for this draw):

- Pilot (seed 20261101): `GCF_059615465.1_protein.faa.gz`,
  `GCF_003018555.1_protein.faa.gz`
- Round-1 measured (seed 20261102): the ten names in
  `UNRELATED_SHIP_PROTOCOL.md`
- Build smoke: `GCF_001513615.1_protein.faa.gz`

`random.Random(20261272).sample(remaining, 20)` in this order:

1. `GCF_004377995.2_protein.faa.gz`
2. `GCF_055556535.1_protein.faa.gz`
3. `GCF_002853805.1_protein.faa.gz`
4. `GCF_904866455.1_protein.faa.gz`
5. `GCF_052050745.1_protein.faa.gz`
6. `GCF_032384295.1_protein.faa.gz`
7. `GCF_048568975.1_protein.faa.gz`
8. `GCF_041235215.1_protein.faa.gz`
9. `GCF_048404355.1_protein.faa.gz`
10. `GCF_003722195.1_protein.faa.gz`
11. `GCF_018415995.1_protein.faa.gz`
12. `GCF_900196535.2_protein.faa.gz`
13. `GCF_002058765.1_protein.faa.gz`
14. `GCF_036498065.1_protein.faa.gz`
15. `GCF_015571655.1_protein.faa.gz`
16. `GCF_037231045.1_protein.faa.gz`
17. `GCF_024918035.1_protein.faa.gz`
18. `GCF_001900595.1_protein.faa.gz`
19. `GCF_049354865.1_protein.faa.gz`
20. `GCF_057812745.1_protein.faa.gz`

The pool is **not** filtered by prior stock-line counts before the
draw. No post-hoc redraw.

## Pass rule

For each genome record stock lines, TARE lines, differing lines,
difference classes, decision, checks, contract, `n_stable` /
`n_fresh`.

- `SHIP` and 0 differing body lines: pass for that genome.
- Stock body under the per-genome floor: `INCONCLUSIVE` for that genome.
- Any other decision (including any `UNSAFE` / `REFUSE` / `FAIL`), or a
  `SHIP` whose body differs: fail for that genome.

Run outcome:

- `PASS` only if all 20 are `SHIP` with 0 differing lines **and** the
  pooled stock-line sum (genomes meeting the per-genome floor) is
  ≥ 38120 **and** the injected-drop control refused.
- One `INCONCLUSIVE` genome, or pooled floor miss → run `INCONCLUSIVE`.
- One failure → run `FAIL`.

## Injected-drop negative control

Seed `20261273`. On the first genome in draw order that `SHIP`s with
byte-identical body: drop 5% of candidate profile keys from the cache
rows (coverage left in place), rerun update. Must `REFUSE`. A drop that
still matches stock fails the control.

## Where it runs

CARC, non-exclusive, EPYC-7542, correctness only. Array: one proteome
per task, ≤20 tasks (`--array=0-19`), then one aggregate task for the
pooled check, known-bad control, and `measured_v2.json`. Wall times in
the correctness JSON are diagnostics, not a timing claim.

## Timing (only if measured_v2 PASS)

If and only if `measured_v2.json` outcome is `PASS`: time 5 genomes
from the draw (seed `20261274`, `random.Random(20261274).sample(drawn, 5)`),
r=3 paired stock vs TARE update walls, exclusive node. Lowest priority
behind W13, W8, W12a, W5x, W12b. Output:
`pipeline/results/unrelated_ship/timing_v2.json`.

## Seeds in the WA block

| Seed | Use |
|---|---|
| 20261271 | reserved (unused; round-1 pilot already locked under 20261101) |
| 20261272 | measured_v2 draw |
| 20261273 | injected-drop control |
| 20261274 | timing genome sample (only if PASS) |
| 20261275–20261279 | reserved |
