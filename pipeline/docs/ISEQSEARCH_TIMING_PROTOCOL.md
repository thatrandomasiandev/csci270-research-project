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

## Addendum 2026-10-19 — pilot outcome, before the measured job

Pilot job `13241869` on `a03-17` (AMD EPYC 7513, not the measured
constraint), 4 CPUs, 32 GB, non-exclusive, code
`cefc427dfc6fb27cfdcd0bfa22cca4653e158666`. Elapsed 2 min 45 s. File
`pipeline/results/iseqsearch_timing/pilot.json`. Verdict `COMPLETE`.
These walls are not a speed claim.

The first submission, job `13241864`, used `--nice=10000` and sat at
priority 1. It was cancelled before it started and resubmitted without
that nice. No pilot wall comes from `13241864`.

What the pilot observed:

- Delta FASTA 10239 entries, MD5 `6d9202d47413f295fcc15b7159f2bd1e`,
  the same file as the laptop dx_i delta. `l_old` 208482574. `l_delta`
  4056372. `l_sum` 212538946.
- Query name hash matches the locked pilot draw. 50 queries, disjoint
  from the 300.
- Stock vs stock: 3962 body rows, identical. Known-good passed.
- iSeqSearch fresh merge: 3982 rows, not body-identical. 37 of 3962
  shared rows byte-identical, 3925 same HSP with a different value, 0
  different HSP, 20 extra rows. Known-bad (drop last line) passed.
  This is the 50-query pilot, not the figure's 407 of 31377.
- Cold TARE and the timed TARE arm both returned `REFUSE_PIN`, reason
  `total_entry_length: no knob`. `returned_stock` is false. No body
  file was written. The timed arm's phase clock is parse 13.21 s,
  prep 1.42 s, tool 13.31 s, probe 0 s.

The locked limit treated only the stock blast and the iSeqSearch delta
blast as query-scaled. The pilot shows TARE's `tool_s` is also a
DIAMOND search of the query file, and the cold invocation (62.31 s) is
inside `once_s`. Scaling those as well, and scaling the warm search
and the stock-vs-stock pair, gives

```
once = 26.596 + 3.943 + 5.094
     + 6 * (warm + 17.513 + 62.309)
pass = 6 * 8.735
     + (0.807 - 0.218 + 6 * 0.218)
     + (29.081 - 13.314 + 6 * 13.314)
limit_s = 1.5 * (once + 3 * pass)
```

`warm` is the residual of `once_s` after diff, both full builds,
stock-vs-stock, and cold: 124.817 - 26.596 - 3.943 - 5.094 - 17.513 -
62.309 = 9.362. Then `once` = 570.8 s, one scaled pass = 149.9 s,
`limit_s` = 1531 s. Slurm's time unit is one minute, so the measured
job asks for 30 minutes. That is above 1531 s and below the 8 hour
cap. The job still exits when the run finishes.

The pilot JSON key `exclusive` is the Slurm partition name (`main`).
Job `13241869` was not exclusive. The driver no longer writes that key.
A measured run records `exclusive_requested` from `TARE_EXCLUSIVE=1`.

## Addendum 2026-10-19 — declared `--dbsize` pin

The bare `--pin` pilot is a separate arm. Its walls, including the
29.081 s timed `REFUSE_PIN`, do not enter the measured speed claim.
`bare_pin_in_speed_claim` is false. The 30 minute measured limit above
was scaled from that bare-pin pilot. It is withdrawn and is not a
submit authorization.

The timed TARE arm uses the paper command in
`pipeline/scripts/exact_replay_dx2.py` `run_cli`:

- `--pin` and `--dbsize {total_entry_length}` as two argv elements
- `--slack` and `--evalue 0.002` as two argv elements
- the blastp argv from that file's `tool_argv`, including `--evalue 0.001`
- the job's thread count in place of that file's `THREADS = "8"`

Stock DIAMOND and iSeqSearch stay on the dx_i argv, which has no
`--evalue`. The TARE difference class is against a stock blast of the
declared tool argv, not against the dx_i body. The old-release declared
fill is untimed. Each timed repeat restores that cache and runs the
declared command on 2026_03. A speed number exists only if that
exclusive measured run finishes. `REFUSE_PIN` before replay is not the
timed outcome this arm is allowed to report as a pass.

### Confirmation, before the exclusive job

One non-exclusive run, 4 threads, seed `20261252`, 50 records drawn
from the complement of the dx_i 300. It does not reuse the pilot 50
(seed `20261251`). Name SHA-256
`c18503df0fcac4afa24ada20fc5125629783ffb750da1961a6b5660025a3d7e4`.
First index 209, last index 4946.

Pass, all of these:

- `decision` starts with `REFUSE` and is not `REFUSE_PIN`
- `why` does not contain `no knob`
- the phase record shows the tool ran before the check refused
  (`replay_s` > 0, or an `ic2_*` phase > 0)
- a replay body exists, and its difference class against the declared
  stock blast is recorded

Fail that rule and the exclusive job stays unsubmitted. The confirmation
wall is not a speed number. After a pass, this addendum records the
decision, the why, the phases, and the difference class, and replaces
the measured `#SBATCH --time` from that wall before the single measured
`squeue` check. Query-reading DIAMOND steps scale by 300/50. Parse,
makedb, and the iSeqSearch merge do not. Three alternating repeats, then
×1.5, rounded up to a minute, and not submitted if that limit exceeds
8 hours.

## Addendum 2026-10-20 — confirm FAIL_CONTROL, pin placement

Job `13259333` (`tare-w12b-confirm`) on `a01-09` (AMD EPYC 7513), 4
threads, non-exclusive, frozen code `9d57c81`, seed `20261252`, file
`pipeline/results/iseqsearch_timing/confirm.json`. Verdict
`FAIL_CONTROL`. `confirmation_pass` false. Exclusive measured job not
submitted.

What failed: both the 2026_01 fill and the 2026_03 update returned
`REFUSE_PIN` with
`why: pin check failed: tool failed (1): Error: Invalid command: dbsize`.
No replay body. `difference_class` null. `post_replay_refuse` false.

Root cause (CARC diamond 2.2.5, MD5 `7de14b7f9f4c440ddfb5142ad96b1d8b`):
TARE inserted pin tokens after argv[0], yielding
`diamond --dbsize <N> blastp …`. That binary's syntax is
`diamond COMMAND [OPTIONS]`; the same argv prints
`Invalid command: dbsize`. `diamond blastp --dbsize <N> …` accepts the
flag. Mac dx2 used a different diamond build and is not this host.

Fix (not a redesign of the timing question): `reference_run._pinned` and
probe extras now merge pin tokens with `apply_extra_argv`, the same
helper probe already used for diamond scripts, so `--dbsize` lands on
the blastp argv. Unit test
`test_pin_argv_lands_after_diamond_subcommand`. Re-confirm with the
same locked seed `20261252` after that commit is frozen into
`GIT_HASH`. The exclusive job still waits on a confirmation pass and on
the capped-node check.



## Addendum 2026-10-20 — laptop-offline CARC chain

Measured (and W12b confirm) jobs were submitted before the laptop went offline,
with SLURM `--dependency=afterok` on the pilot/prior exclusive stage and an
in-job pilot-pass guard that exits unless the pre-registered pass rule holds.
Exclusive arrays use `%2`–`%3` throttles. No laptop action is required to start
a dependent stage.


### Declared-pin argv fix (same day)

Confirm job 13259333 FAILED: `--pin` / `--slack` values beginning with `-` were
swallowed by argparse (`nargs='?'` on `--pin`), so diamond saw a bare `dbsize`
subcommand. The driver now passes `--pin=--dbsize {total_entry_length}` and
`--slack=--evalue 0.002`. Confirm is re-submitted; measured waits on it.
Measured `--time` is 12:00:00 for the offline chain (bare-pin 30 min withdrawn).

## Addendum 2026-10-22 — confirm pass rule (refusal without body)

Job `13260166` (after the `--pin=` argv fix) ended `FAIL_CONTROL` with
`decision=REFUSE` / `why=IC2 neighbor out: pad_hit`. Provenance showed
`post_replay_refuse=true`, `replay_s>0`, and `ic2_neighbor_s>0`, but
`replay_body=false` and `difference_class=null` because a REFUSE does not
write `tables/out`. The old pass rule required all three of
`post_replay_refuse`, `replay_body`, and `difference_class`, so a correct
declared-pin refuse was scored as failure.

Fix (not a redesign of the timing arms): `confirmation_declared_pass`
returns true when `post_replay_refuse` holds and the arm did not SHIP a
body. Unit tests: known-good refusal (pad_hit, no body) and known-bad
SHIP. Confirm is **not** resubmitted while the exclusive-node freeze
(W13/W8/W5x) is in force; resubmit only after those jobs finish.

## Addendum 2026-10-23 — resubmit after freeze lift

Freeze on W13/W8/W5x lifted for new W12b submissions. Resubmitted the
confirm → measured chain on CARC staged tree `tare-w12b` with code tip
`d396b2b` (confirm pass-rule fix above). This is a **script pass-rule
bug fix**, not a method failure and not a redesign of the locked arms.

| Job | ID | Role |
|---|---|---|
| Confirm | `13347607` | `iseqsearch_timing_confirm.job` |
| Measured | `13347608` | `iseqsearch_timing_measured.job`, `Dependency=afterok:13347607` |

Staged `iseqsearch_timing.py` md5 `93f59ca93ea982d689218536d6c278b5`
(matches worktree); `GIT_HEAD` written as `d396b2b` before sbatch.

## Addendum 2026-10-24 — queued W12b job moved to biyik_1173 (queue priority only)

Queued CARC job `13347608` (W12b iSeqSearch measured; confirm `13347607` already completed) was
moved from Slurm account `biyik_1165` to `biyik_1173` on 2026-10-24. Queue priority / fairshare
only: identical hardware constraints and limits (`--exclusive`, `--mem=0`, `--constraint=epyc-7542`,
same wall and exclusive node caps). No cancel, resubmit, or redesign; job IDs unchanged.
