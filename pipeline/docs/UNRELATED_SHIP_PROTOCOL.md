# Unrelated ship: measured-run protocol

Locked after the pilot and before the measured run. The pilot JSON is
`pipeline/results/unrelated_ship/pilot.json` (outcome PASS, code
`6b9632b`). This file is the pre-registration. The measured process
must not start until this file is in the tree it runs.

## What is being measured

TARE, package `acts`, strategy `reference`, `--pin` with no template.
The tool is pfscanV3 from the approved archive `pftools3-v3.2.13.zip`
(44,209,720 bytes). `CMakeLists.txt` in that archive says
`SET(VERSION "3.2.12")`. The binary built on CARC prints
`Version 3.2.12 built on Oct 18 2026 at 02:26:00.` No other source
was fetched.

Locked command, one thread:

```
pfscanV3 --matrix-only --nthreads 1 --output-method 7 --fasta {reference} {input}
```

References are the matrix entries only, written by the generalized-profile
parser. PROSITE 2026_02 has 1,434 matrix entries. PROSITE 2026_03 has
1,441. Patterns are not in the file. Archives are
`prosite2026_02.tar.bz2` (11,287,183 bytes) and
`prosite2026_03.tar.bz2` (11,352,723 bytes).

Each genome is a fill on 2026_02 and then an update to 2026_03, same
cache. The body compared with stock is the update, against one stock
scan of that proteome on 2026_03.

## Where it runs

Correctness ran, and this measured run runs, on CARC. The laptop
cannot compile this source: Apple clang rejects `-msse` for
`arm64-apple-darwin27.0.0` (`pipeline/docs/UNRELATED_SHIP_BUILD.md`).
The pilot node was `b22-07`, AMD EPYC 7542, with SSE2 and SSE4.1.
The job is non-exclusive, 4 CPUs, 16G. There is no timing claim.
Wall times are not evidence.

## Contract the pilot recorded

Both pilot genomes fitted the same contract and shipped with
`exact replay under identity normalizer`. No pin was inferred
(`inferred_pin` null). No column member is `entry_count` or
`total_entry_length`.

| Column | Role | Member |
|---|---|---|
| 0 | byte | byte (profile `AC\|ID`) |
| 1 | numeric | identity |
| 2 | numeric | identity |
| 3 | byte | byte (sequence id) |
| 4–7 | numeric | identity |
| 8–9 | byte | byte |

Record column 3, entry column 0. Every body line in the pilot had
ten whitespace fields. Sequence headers were unique. stderr did not
contain `xalip`.

On the first pilot genome the 2026_03 update reused 1,434 stable
matrix entries and scanned 7 fresh ones. That is the whole release
delta of the matrix file. The body was byte-identical to stock
(1,906 lines, 0 differing).

## Pilot controls

Seed `20261101`, two proteomes from `pipeline/data/recurrence/A`
(the e1scale set, 100 files):

1. `GCF_059615465.1_protein.faa.gz` — 4,377 records, 1,906 body lines
2. `GCF_003018555.1_protein.faa.gz` — 5,211 records, 2,039 body lines

Stock versus stock at `--nthreads 1` was byte-identical on both.
TARE update versus stock was byte-identical on both (0 differing
lines). Both decisions were SHIP.

Power floor: 1906

That is the smaller stock body. A measured genome with fewer than
1906 stock body lines is INCONCLUSIVE. It is not a failure of the
method, and TARE is not run on it.

Known-bad, seed `20261103`, on the first shipped genome. 332 candidate
profiles, 17 dropped (5%). 55 cached rows for those profiles were
deleted and coverage was left in place. The rerun decided REFUSE,
reason `IC2 neighbor stdout: pad_hit`. The control passed.

A second pair at `--nthreads 2` on the first genome had the same
1,906 lines in a different order (489 positions, class `order`).
That pair is not the locked command and is not a pass gate.

The heuristic note scanned the first matrix entry, `PS01031|SHSP`,
against the first 8 sequences, with and without `--no-heuristic`.
Both runs printed 0 lines, and the one-profile warning was present.
The note did not observe a heuristic miss. It was not repeated on
another profile.

## Measured draw

Seed `20261102`, 10 proteomes from the same directory, excluding the
two pilot names. `random.Random(20261102).sample` of the remaining
98, in this order:

1. `GCF_049949335.1_protein.faa.gz`
2. `GCF_002357915.1_protein.faa.gz`
3. `GCF_025782825.1_protein.faa.gz`
4. `GCF_054902895.1_protein.faa.gz`
5. `GCF_055398225.1_protein.faa.gz`
6. `GCF_013085185.1_protein.faa.gz`
7. `GCF_005389605.2_protein.faa.gz`
8. `GCF_030717825.1_protein.faa.gz`
9. `GCF_002090355.1_protein.faa.gz`
10. `GCF_977065495.1_protein.faa.gz`

## Pass rule

For each genome, record stock body lines, TARE body lines, the number
of differing body lines, the difference classes, the decision, the
checks, and the contract. Also record `n_stable` and `n_fresh` from
the update decision text.

- SHIP and 0 differing body lines: pass for that genome.
- Stock body under the power floor: INCONCLUSIVE.
- Any other decision, or a SHIP whose body differs: fail for that genome.

The run is PASS only if all 10 are SHIP with 0 differing lines.
One INCONCLUSIVE genome makes the run INCONCLUSIVE.
One failure makes the run FAIL.

Output: `pipeline/results/unrelated_ship/measured.json`.
The JSON records the git head of the code that ran.
