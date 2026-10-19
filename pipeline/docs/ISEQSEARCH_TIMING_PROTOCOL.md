# iSeqSearch timing (pre-registered 2026-10-19)

Written before the pilot and before the measured run. Locked text is not
edited. Later changes are dated addenda. The system is TARE. The Python
package is `acts`. This file does not claim a speedup.

Workstream W12b. Code commit at protocol time:
`1c65571538afcc139af560156147e4276905f9b4`. Driver:
`pipeline/scripts/iseqsearch_timing.py`. Result directory:
`pipeline/results/iseqsearch_timing/`.

## Question

Figure 9 reports that 407 of 31,377 shared rows from iSeqSearch are
byte-identical to a full DIAMOND run, and the caption says TARE was not
timed against iSeqSearch. On the same Swiss-Prot 2026_01 → 2026_03 update
and the same 300 queries as `dx_i`, what is the end-to-end wall of

1. stock DIAMOND 2.2.5 on 2026_03,
2. iSeqSearch's incremental update, including the delta database build,
3. TARE on DIAMOND through the refusal path,

each on one exclusive `epyc-7542`, alternating, three repeats?

Laptop walls are not evidence for that comparison.

## What was read before any timing run

- `pipeline/results/reference_diamond/dx.json` (`dx_i`, S1 argv, input
  checksums). The saved search files were classified again with the
  current `correlation` in `scripts/exact_replay_diamond.py`. Integer
  classes match the JSON: `shared_rows` 31377, `shared_byte_identical`
  407, `same_hsp_different_value` 30968, `different_hsp` 2, `row_extra`
  133, `row_missing` 0, `bodies_equal` false. The Pearson value is not
  a locked digit: `correlation` walks a `set`, so the sum order moves
  the last bits (stored JSON 0.9999991687961751; recomputes land within
  1e-12 of it). Kendall τ on this file reproduced
  0.9999939628622326. The integer classes are the figure's claim.
- iSeqSearch commit `7e862bf3afa52b65b3cca4255de66ab4cb764fe3`,
  `source/main.py` MD5 `2c0762059f0229add06bf351edb2f979` (2477 bytes),
  on the laptop at
  `pipeline/builds/Incremental-Protein-Search` and on CARC at
  `/project2/biyik_1165/jjt_373/csci270-star/pipeline-ref-second/iseq/Incremental-Protein-Search`.
  `source/merger.py` was read. No download.
- DIAMOND 2.2.5: laptop binary 22031624 bytes, MD5
  `711d4c7b29e24c3fd6ec6a288ec1d326` (the dx_i host binary); CARC binary
  `/project2/biyik_1165/jjt_373/csci270-star/pipeline-ref-second/bin/diamond`,
  28553136 bytes, prints `diamond version 2.2.5`. The measured run uses
  the CARC binary. Its MD5 is checked in the job against
  `7de14b7f9f4c440ddfb5142ad96b1d8b`.
- Swiss-Prot FASTAs, both machines: 2026_01 is 93457057 bytes, MD5
  `5245b19456d9a063b13c46602269bc5f`; 2026_03 is 93801562 bytes, MD5
  `bc9d398533e6df582b563c6c03093bd0`.
- Queries `GCF_002853805.1_protein.faa.gz`, 1074926 bytes, MD5
  `b170d133266427c46d87d99284e1fda3`, 5117 records.
- `acts/reference_run.py` refusal path (`--pin` with an empty template,
  `_take_inferred_pin`, `REFUSE_PIN` return). D2's stored decision is
  `SHIP` with `evalue` fitted to `total_entry_length`. `dx_k` on a
  constructed sample returned pin `no knob`, `tool_calls` 2,
  `help_candidates` 0.

## Semantics that can move a number for a reason other than speed

1. iSeqSearch does not run DIAMOND. `main.py --default OLD DELTA OUT
   L_old L_delta` rescales column `[-2]` by `(L_old + L_delta) / L_part`
   and prints `str(float(...))`. With the S1 12-column row, `[-2]` is
   `evalue`. Byte identity fails on a rescaled E-value even when the
   alignment is unchanged. That is the published 30,968
   `same_hsp_different_value` class, not a timer bug.
2. Dedup keeps one row per `(qseqid, sseqid)`, the lower E-value after a
   stable sort. Hits to sequences the new release removed are kept.
   `row_extra` is that design, not a crashed merge.
3. `L_old` and `L_delta` are `diamond dbinfo` letter counts of the old
   database and of the delta database. Their sum is the denominator the
   code uses. It is not replaced by the 2026_03 letter count.
4. The merger imports Biopython and tqdm at import time. CARC Python
   3.11.9 already has Biopython 1.85 and tqdm 4.67.1 in the user site.
   Those are the pins in `requirements-diamond.txt`. They are not the
   1.79 / 4.64.0 pins in iSeqSearch's own `requirements.txt`. No new
   install. A missing import is a failed arm, not a reimplementation.
5. `csv.writer` ends lines with `\r\n`. Classification splits lines and
   fields, so the line ending is not a difference class.
6. A short row raises `IndexError` inside the merger. The arm is then
   `ran: false` with the traceback tail. The merger is not rewritten.
7. DIAMOND S1 is sensitive to the database, `-k 0`, `--min-score 40`,
   `-b 2.0`, `--comp-based-stats 1`, and `--threads`. The measured argv
   is the `dx_i` argv with `--threads 32`. The pilot uses the same flags
   with `--threads 4`. A thread-count change can change tie order. The
   pilot's walls are not the measured walls, and a pilot row-count is
   not required to equal 407.
8. TARE's exact-mode CLI is `python3 -m acts run --strategy reference
   --pin` with no template. The namespace hashes the command with the
   reference path removed, so a contract stored on 2026_03 applies to a
   later call with the same argv. `probe_fit` runs only when that
   contract is absent. D2 shipped, so the expected next step is pin
   inference, not the approximate rescaling path. `infer_knobs` is called
   on one half of the reference and on the whole reference.
   `dx_k` found no help-text candidate and returned `no knob` after two
   calls. On `no knob`, the current code returns `REFUSE_PIN` and does
   not call `_dump_raw`. It does not write a stock body. The sentence
   "TARE returns the stock run" is a hypothesis this run tests. It is
   not enforced by deleting output or by appending a stock search the
   code did not run.
9. `no knob` is not stored on the contract, so each timed TARE repeat
   repeats pin inference. The cold `probe_fit` is not repeated. Repeats
   restore the post-probe contract so later repeats do not pay the probe
   again and do not reuse rows a previous repeat stored.
10. Stock-vs-stock: two S1 searches of the same database and queries can
    disagree if DIAMOND breaks ties by thread schedule. The pilot and
    the measured run both do this pair before the clock. Disagreement
    stops the alternating block. Verdict `INCONCLUSIVE`. Difference
    class is recorded. That is not a kill of iSeqSearch.

## Samples

Measured queries are not redrawn. They are
`sorted(random.Random(20261017).sample(range(5117), 300))` on
`GCF_002853805.1`, written in that order. Name list SHA-256
`b7ed150e41d88cb6eccea223fd6c2bb52c2b6a2478092ec443f8595148d915b5`.
The existing `q300.faa` is 114470 bytes, MD5
`a703200e3967517b57f8f7469bb1bd8c`, and its names match this draw.
The job regenerates the file and stops if either hash differs.

Pilot queries are 50 records drawn with `random.Random(20261251)` from
the complement of those 300 indices, then sorted. Name list SHA-256
`6d9cb4d8937d5b395b316175f16f996357b912f83e5625745db9f160467ad633`.
The job stops if the draw intersects the 300 or the hash differs.
Seed `20261251` is not used elsewhere in this repository. The block
`20261251`–`20261259` is reserved for this workstream. The measured run
uses no new seed.

## Arms

Untimed, before the clock, on the compute node, in this order:

1. Check input sizes and MD5s. A mismatch stops with `STOP_INPUTS`.
2. Build the 2026_01 database, the 2026_03 database, and the delta FASTA
   of 2026_03 entries whose content hash is absent from 2026_01. The
   delta entry count is recorded. The dx_i count is 10239. A different
   count stops with `STOP_INPUTS` before any timed arm: it is not the
   same update.
3. `diamond dbinfo` letter counts for the old database and, once the
   delta database has been built at least once inside a timed arm, for
   the delta. The prep records the old count. dx_i reports `l_old`
   208482574 and `l_delta` 4056372. A different old count stops.
4. One S1 search of the pilot or measured queries against 2026_01. This
   file is the previous result iSeqSearch merges. It is not inside an
   iSeqSearch wall.
5. Two S1 searches against 2026_03. Bodies must be identical. This is
   the stock-vs-stock control.
6. One cold TARE invocation (`--pin`, empty cache). Its wall is
   `tare_cold_wall_s`. The contract sqlite is snapshotted. This wall is
   not in the TARE mean.

Clocked repeats, one arm at a time:

| Repeat | Order |
|---|---|
| 1 | stock, TARE, iSeqSearch |
| 2 | TARE, iSeqSearch, stock |
| 3 | iSeqSearch, stock, TARE |

- **stock.** S1 `diamond blastp` on the prebuilt 2026_03 database.
  The full-database build stays in prep.
- **iSeqSearch.** Delete any delta `.dmnd`, `diamond makedb` on the
  delta FASTA, `dbinfo`, S1 `blastp` of the queries against that
  database, then `main.py --default` on the warm 2026_01 m8 and the
  new delta m8. All four steps are inside the wall. The delta FASTA
  itself stays in prep. Its wall is reported separately and is not
  added into the arm after the fact.
- **TARE.** Restore the post-probe contract. Run `python3 -m acts run
  --strategy reference --pin --verify full --audit-p 0` on 2026_03 with
  the S1 argv and `makedb` as `--prep`. The wall is the process wall.
  Nothing is subtracted. A second stock search is not appended if the
  process writes no body.

The pilot runs one pass of the three arms (`repeats` = 1), not the
three-repeat rotation. It is a functional pilot. Its walls are not
speed evidence. The measured run uses `repeats` = 3 and the rotation
above.

## Controls

| Control | Must |
|---|---|
| Classifier known-good | Classifying a stock body against itself yields `bodies_equal` true and `shared_byte_identical == shared_rows`. |
| Classifier known-bad | Dropping the last line of an iSeqSearch body yields `bodies_equal` false and `row_missing >= 1`. |
| Saved dx_i files | Already classified: 407 of 31377. Recorded in `reverify_saved.json`. Not re-searched. |
| Stock vs stock | The two untimed 2026_03 searches are body-identical. |
| iSeqSearch negative | The fresh merge is not body-identical to stock. If it is, the approximate-vs-exact contrast was not observed (`FAIL_CONTROL`). |
| TARE refusal | Decision is `REFUSE_PIN` or starts with `REFUSE`. Any other decision is `FAIL_CONTROL`. `returned_stock` is true only if a body file exists and its body equals the stock body. |
| Power | Pilot `stock_rows >= 100` and `query_n == 50`. Measured `stock_rows >= 1000` and `query_n == 300`. Below the floor the verdict is `INCONCLUSIVE`, not a kill. |

Difference classes on a failed body compare are the keys from
`classify_bodies`: `same_hsp_different_value`, `different_hsp`,
`row_missing`, `row_extra`, plus `line_order_only` and `bodies_equal`.

## Verdicts

- `COMPLETE` — every clocked arm ran, stock-vs-stock passed, both
  classifier controls passed, the iSeqSearch negative control passed,
  every TARE decision is a refusal, and the power floor is met.
  `COMPLETE` does not mean one arm is faster. The walls are the result.
- `FAIL_CONTROL` — the run finished but a control that must pass did
  not. Walls are still reported.
- `INCONCLUSIVE` — missing power, stock nondeterminism, a crashed arm,
  a signal, or a time limit. Partial JSON is still written. No imputed
  wall.
- `STOP_INPUTS` — checksum, query hash, or delta-count mismatch. No
  timed arm.

There is no third redesign. A failed control is reported, not repaired
by changing the merger or the refusal path.

## Time limit for the measured job

Set in an addendum after the pilot, before `sbatch` of the measured
job. The pilot records `once_s` (release diff, both full database
builds, the warm 2026_01 search, the two stock-vs-stock searches, and
the cold TARE invocation) and `pass_s` (the sum of the three clocked
arm walls). Inside that pass, `search_s` is the stock blast plus the
iSeqSearch delta blast, and only those two steps read the query file.

```
scaled_pass = pass_s - search_s + (300/50) * search_s
limit_s = 1.5 * (once_s + 3 * scaled_pass)
```

The measured run pays `once_s` once and the pass three times. The 1.5
factor is the backstop above that projection. The job exits when the
run finishes. If `limit_s` would exceed 8 hours, do not submit; report
the pilot and stop. The pilot's own Slurm limit is 4 hours,
non-exclusive, 4 CPUs, 32 GB. Full database files are built on scratch.
The shared Swiss-Prot directory is read, not rewritten.

## Host

Measured: one node, `--exclusive --mem=0 --constraint=epyc-7542`,
`--cpus-per-task=32`, job name starts with `tare-w12b`. Account
`biyik_1165`, partition `main`. Scratch
`/scratch1/$USER/tare-w12b/`. Staged tree
`/project2/biyik_1165/jjt_373/csci270-star/tare-w12b/`. Scratch must
not be tmpfs. A `SIGTERM` handler writes the partial JSON and sets
`INCONCLUSIVE`.

Before `sbatch`, the queue is counted with
`squeue -u $USER -h -t R,PD -o "%i %j %D %T"`. Submit only if the sum
of `%D` for job names matching `tare-w8|tare-w12a|tare-w5x|tare-w12b|tare-w6`
is at most 5. This workstream's budget is one exclusive node. The
pilot is not exclusive. Job `12864756` is never touched.

## Not claimed

A speedup, a reproduction of 407 on a freshly searched server output,
or that TARE returns a stock body. Those are outputs of the run, or
they are absent.
