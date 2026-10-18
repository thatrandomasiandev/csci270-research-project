# TARE release chain (skeleton, 2026-10-18)

This file is the design and the semantics review. It is **not** the
measured-run pre-registration. No pilot has run. No measured wall below
is a result. The measured lock is a dated addendum written after the
pilot and before seed `20261122`. The pilot may change the harness. It
may not change the hash definition, the argv, the release order, or the
pass rules below.

Code under test, until a later addendum freezes another commit:
`507c45fcd2eb3c3e7850791cb2daf5e84400ffab` on `exp/c-release-chain`.
Do not rebase onto a main commit that adds the program-binary hash to
the reference cache key. At this commit the cache namespace hashes the
command line with the reference path removed and does not hash the
binary (`pipeline/paper/tare/main.tex` implementation section).

The system is TARE. The package on disk is still `acts`
(`python3 -m acts`, run from `pipeline/`).

## Question

Figure 1 stacks published family counts. Figure 5 draws earlier Pfam
releases as triangles from net additions, because the release notes do
not publish edits (`pipeline/docs/MOTIVATION_EVIDENCE.md`). Pfam keeps
every release, so the edit mass can be measured. Separately, the cost
model says the cache is cheaper than repeated full runs after
\(n \ge (F - T)/(T - U)\) releases, and the only measured HMMER pair is
38.1→38.2. A cache carried across several releases might drift.

Three questions, judged separately:

1. For each consecutive pair 37.0→37.1 … 38.1→38.2, what are
   unchanged, edited, new, removed, and \(f_\Delta\) under the strict
   hash?
2. On one genome, does a cache filled at 37.4 and updated through
   38.0, 38.1, and 38.2 stay byte-identical to stock at every release,
   and identical to a cache filled at 38.1 and updated only to 38.2?
3. On three further genomes, with three alternating runs at each step
   of the full chain, what is \(S_g\), what does the cost model predict
   from that step's \(f_\Delta\) using \(a\) and \(c\) from earlier data
   only, and when does fill-plus-updates cost less than repeated stock
   runs?

## Semantics review (no hmmscan, no new files)

Read before any pair census and before any scan. Sources:
`pipeline/scripts/reference_kill_tests.py` (`r1`),
`pipeline/acts/entry_hash.py`,
`pipeline/acts/reference_formats.py`,
`pipeline/results/reference_kill_r1.json`,
`pipeline/docs/EXACT_REPLAY_PROTOCOL.md` (E1, E1-scale, headline pilot,
headline measured addendum),
`pipeline/scripts/headline_carc_measured.py`,
`pipeline/acts/reference_run.py` (`_run_exact`, `_ic2`),
`pipeline/acts/exact_certificate.py`.

### Hash definition (the one `reference_kill_r1.json` used)

A block is the text from after the previous `//` through the line that
starts with `//`. The key is the first `ACC` token with the version
suffix removed (`PF00001.21` → `PF00001`). `r1` stores a dict, so a
repeated key keeps the last block and the earlier block disappears from
`z`. The strict hash is `entry_content_hash(block, PROFILE_VOLATILE_TAGS)`
with tags `DATE`, `BM`, `SM`, `COM`. Those four lines are dropped. The
remaining lines, including `NAME`, `ACC`, `GA`, `TC`, `NC`, `STATS`, and
the `HMM` body, stay in order.

`f_\Delta = (z_new - unchanged_strict) / z_new`. Unchanged means the key
is in both releases and the strict hashes are equal. Edited means the
key is in both and the hashes differ. New is `added`. Removed is keys
only in the old release. Removed families are not in the denominator.
The body hash in `r1` (the `GA` line plus the `HMM` section) is recorded
and is not \(f_\Delta\).

A version bump on `ACC` is the same key and a different hash, so it
counts as edited. A `DATE`-only change counts as unchanged. The first
model of the local Pfam 38.2 file has real `DATE`, `BM`, and `SM` lines
(`BM` is the `hmmbuild` command; `SM` is an `hmmsearch` command that
contains a `-Z` and a `--cpu`). Dropping them is the `r1` definition.
This census does not switch to raw bytes.

The paper's 86.6% is `unchanged_strict / z_new`, not raw-file identity
and not `unchanged_body`. The positive control is exact equality with
`reference_kill_r1.json` on: `z_old` 27481, `z_new` 30134, `added` 2674,
`removed` 21, `shared` 27460, `unchanged_strict` 26082,
`unchanged_body` 26253, `frac_new_unchanged_strict`
0.8655339483639742, `frac_new_unchanged_body` 0.8712086015796111.
Then \(f_\Delta = 4052/30134\). A mismatch means the script is wrong.
Do not publish `pairs.json`.

The shipped parser (`iter_profile_raw`) merges two adjacent blocks when
they share `NAME`/`ACC` and have different magics. The pin's
`{entry_count}` is the merged count. `r1` does not merge. If the merged
count, the `//` count, and the last-wins key count disagree, that
release's chain step is INCONCLUSIVE: the pin Z would not be the `r1`
model count. Duplicate keys, a block with no `ACC`, or a strict hash
that occurs twice in one release also make that release INCONCLUSIVE
for a chain step. The census still reports the last-wins numbers and
sets `inconclusive`.

Published family counts in `MOTIVATION_EVIDENCE.md` are CITED from the
38.2 relnotes (37.0 = 21979, 37.1 = 23794, 37.2 = 24076, 37.3 = 24424,
37.4 = 24736, 38.0 = 25545, 38.1 = 27481, 38.2 = 30134). They are a
sanity flag (`z_matches_relnotes`), not a substitute for the hash.

Net addition \(z_\text{new} - z_\text{old}\) is what Figure 5's triangles
use. It is smaller than edited+new whenever models are edited or the
adds and kills do not cancel. Report both. Do not replace \(f_\Delta\)
with the net fraction.

### hmmscan behaviors that can fail a check for a reason other than drift

Body lines are non-empty lines that do not start with `#`. `#` lines
carry the date, the paths, and the option line. They are not compared.

`--cut_ga` reports on the per-model bit-score threshold. Changing Z does
not move a hit across that line. Printed E-values still depend on Z, so
an unpinned replay is the pin control: its body must differ. It is not
required to differ on every line. A printed E-value of `0` does not move
when Z changes (E1-scale addendum).

domZ is the number of targets HMMER reported for that query. Dropping a
hit changes the conditional E-values of the hits that remain. A 5%
candidate drop is expected to show `missing` and, on domtblout, often
`value-only`. That is the drop, not a parser bug.

`GetMaxNameLength` walks registered hits. The E1-scale pilot was
byte-identical, not whitespace-only, so no column-width pad is added.
If a difference is bytes-unequal and tokens-equal, the class is
`whitespace-only`. It is a failure of byte identity.

Replay order is the target release's file order. A tie broken by a model
the replay omitted is a real `order` difference.

`--cpu 4` is part of the cache namespace. Every fill and update in one
chain uses `--cpu 4`. Stock uses `--cpu 4` as well. HMMER's threaded
output was byte-identical across stock repeats in the headline pilot.
This design still requires stock-vs-stock identity before any TARE
comparison. If two stock bodies differ, that genome stops as
INCONCLUSIVE. The difference is not charged to TARE.

`hmmpress -f` is the prep. Press time is not charged to either arm, as
in the headline job. A press failure is a harness failure.

The residue cap skips the random pads when one record holds more than
half the residues (`2 * length > total`). A bacterial proteome of many
proteins should not bind it. If it binds, the 5% drop control cannot
run, because that control is the random-pad layer. The neighbor pad does
not put a dropped candidate back. The pilot is then INCONCLUSIVE on the
negative control.

There is no CLI switch that drops candidates. The negative control is a
separate, untuned process. It is not part of the timed argv.

### Files already present (HEAD 2026-10-18, bodies not downloaded)

Laptop, read-only shared tree:

| Release | Path | Bytes |
|---|---|---:|
| 38.1 | `/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data/hmmer/pfam38.1/Pfam-A.hmm.gz` | 384357362 |
| 38.2 | `/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data/hmmer/Pfam-A.hmm.gz` | 418160514 |

CARC, listed once after `ssh -O check discovery` reported a master
(pid 73601). Same byte sizes:

| Release | Path | Bytes |
|---|---|---:|
| 38.1 | `/project2/biyik_1165/jjt_373/csci270-star/reference_reannot/data/pfam38.1/Pfam-A.hmm.gz` | 384357362 |
| 38.2 | `/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/hmmer/Pfam-A.hmm.gz` | 418160514 |

`find` under `/project2/biyik_1165/jjt_373/csci270-star` for
`Pfam-A.hmm.gz`, `Pfam37*`, `pfam37*`, `Pfam38.0*`, and `pfam38.0*`
returned only those two files. The laptop search under `CSCI270`,
`~/tmp`, and `~/Downloads` found the same two gzip files plus an
uncompressed pilot HMM at
`pipeline/data/reference_diamond_dx2/pilot/hmmer/Pfam-A.hmm` (2246909846
bytes). That file is not a release archive and is not an input.

HEAD of the six missing release URLs, `Content-Length` only, HTTP 200,
`Content-Type: application/x-gzip`, no body downloaded:

| File | URL | Bytes |
|---|---|---:|
| Pfam37.0/Pfam-A.hmm.gz | `https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam37.0/Pfam-A.hmm.gz` | 310495632 |
| Pfam37.1/Pfam-A.hmm.gz | `https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam37.1/Pfam-A.hmm.gz` | 331036725 |
| Pfam37.2/Pfam-A.hmm.gz | `https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam37.2/Pfam-A.hmm.gz` | 335484150 |
| Pfam37.3/Pfam-A.hmm.gz | `https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam37.3/Pfam-A.hmm.gz` | 341949642 |
| Pfam37.4/Pfam-A.hmm.gz | `https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam37.4/Pfam-A.hmm.gz` | 347150343 |
| Pfam38.0/Pfam-A.hmm.gz | `https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam38.0/Pfam-A.hmm.gz` | 355568131 |

The same HEAD on 38.1 and 38.2 returned 384357362 and 418160514, equal
to the local and CARC files. Those two are not in the approval request.

Job `13208152` still had a PENDING task at the one listing
(`13208152_9 PENDING`; tasks 4–8 RUNNING). No release-chain job is
submitted while any task of `13208152` is PENDING.

That same listing found no `Pfam-A.hmm.gz` under `/scratch1/jjt_373`.
Three uncompressed `Pfam-A.hmm` files in the 2026-10-08 and 2026-10-09
trees (`acts-baselines-20261009`, `acts-hmmscan-stock-20261009`,
`acts-hmmsearch-stock-20261008`) are not versioned release archives
and are not inputs.

## Part 1 — pair census

`pipeline/scripts/release_chain_pairs.py` imports `iter_models` and
`model_hashes` from `reference_kill_tests.py`. Invoke it with
`--release VER=PATH` repeated and `--out`. `--control` defaults to
`reference_kill_r1.json`. The 38.1→38.2 pair must match that file on
every `CONTROL_KEYS` field before any other pair is trusted. Until the
six missing releases exist, that one pair is written to
`pipeline/results/release_chain/control_38.1_38.2.json` and is not
`pairs.json`. `pairs.json` is written only when all eight releases are
passed and `complete` is true.

The script also records `hashset_fresh`: new-release strict hashes that
are absent from the old release's hash set. That is what the shipped
cache treats as fresh. \(f_\Delta\) stays the r1 ratio. If the two
counts differ, both are reported and the definition is not switched.

Each result JSON records git head, host, platform, Python, argv, wall
seconds, and each file's byte size and md5. The wall time of the hash
is not a speed claim. Laptop limits for that run: `nice -n 10`, one
process, scratch only if a temporary file is required (the script
streams).

`pipeline/paper/tare/figures/make_churn_pairs.py` reads `pairs.json` and
writes `churn_pairs.pdf` and `churn_pairs.png`. It exits if the seven
pairs are absent or out of order. Bars are the fraction of the new
release: unchanged `#bdbdbd`, edited `#9ecae1`, new `#2171b5`. Edited
and new are what TARE reruns. Serif, 7.5 pt, figure width 7.0 in.
The paper `main.tex` is not edited by this work.

## Part 2 — pilot, seed 20261121 (not run)

One genome. Chain, in order, no extra releases and no skips:
37.4 → 38.0 → 38.1 → 38.2. This shorter chain is the pilot named in
the task. The measured run uses the full consecutive chain. That
difference is intentional and stays disclosed.

### Draw

Pool: stems of `pipeline/data/recurrence/A/*_protein.faa.gz`, minus
`EXCLUDE_REASONS` and minus `DRAWS` in
`pipeline/scripts/headline_carc_measured.py` at this commit. The runner
stops unless `len(EXCLUDE_REASONS) == 50` and `len(DRAWS) == 10`. The
ten `DRAWS` are the headline measured sample (array `13208152`) and are
not reused here. On the laptop copy of `recurrence/A` (100 stems) that
pool has 40 stems. SHA-256 of the newline-joined sorted stems is
`40dc92dba7c117e9e9e435f61498fd255a08e6790789d7f861a64aa3a51a456c`.
Pilot genome =
`sorted(random.Random(20261121).sample(sorted(pool), 1))[0]`,
which on that directory is `GCF_057650775.1`.
The job recomputes the pool hash and the draw from the CARC directory
and stops if either differs. Whole file. No second subsample of
proteins. The measured draw is not locked here. On this same directory,
removing the pilot genome and drawing
`sorted(random.Random(20261122).sample(reduced, 3))` yields
`GCF_025259645.1`, `GCF_057098645.1`, and `GCF_900196535.2`
(reduced-pool sha256
`3cc3445dbbfd79ea11fa75f306c31e3032bf5b2e4d529b08b1ff7d23667f69e2`).
Those three names become the measured sample only in the post-pilot
addendum.

### Command

Same as the headline, from `pipeline/`:

```
python3 -m acts run --strategy reference \
  --pin '-Z {entry_count}' \
  --verify audit \
  --prep 'hmmpress -f {reference}' \
  --input QUERY --reference RELEASE --cache CACHE -o OUT -- \
  hmmscan --cut_ga --noali --cpu 4 \
  --tblout {output:tblout} --domtblout {output:domtblout} \
  -o /dev/null {reference} {input}
```

Stock, no pin:

```
hmmscan --cut_ga --noali --cpu 4 --tblout T --domtblout D -o /dev/null RELEASE QUERY
```

HMMER 3.4 is built from the tarball pinned in
`pipeline/jobs/headline_carc_pilot.job`
(`sha256 ca70d94fd0cf271bd7063423aabb116d42de533117343a9b27a65c17ff06fbf3`).
The module HMMER is not used. One `hmmscan` at a time. `--cpu 4` is the
width.

### Order of operations

1. Two stock scans on 37.4. Bodies of both tables must be byte-identical.
   If not, stop. No TARE result is scored.
2. One fill on 37.4 into an empty cache. Record decision, phases, wall,
   and cache bytes (`PRAGMA wal_checkpoint(TRUNCATE)` plus `-wal`/`-shm`,
   as `cache_bytes` in the headline runner). The emitted body must be
   byte-identical to the stock 37.4 body. If the decision is not `SHIP`,
   or the body differs, the pilot stops. Later updates are not run.
3. For each next release, in order: one stock scan, then one TARE update
   on the cache carried from the previous SHIP. Compare TARE body to that
   stock body. Record decision, phases, \(f_\Delta\) from the pair census,
   and cache bytes. A non-`SHIP` decision or any body difference stops
   the chain. The class list is still written.
4. Drift control, only after step 3 reaches 38.2 and passes. Fill a new
   cache at 38.1. Update that cache to 38.2. The chained 38.2 body, the
   direct 38.2 body, and the stock 38.2 body must be byte-identical on
   both tables. Three-way equality is the pass. Chained-equals-stock
   with direct different is a drift failure. Direct-equals-stock with
   chained different is an exactness failure already caught in step 3.
5. Negative control, once, on the first update only (37.4→38.0), and
   only after that update passed. It does not replace the carried cache.
   Candidate model names are the distinct tblout target names (field 0)
   of the stock body. \(k = \max(1, \mathrm{round}(0.05 N))\),
   `dropped = random.Random(20261123).sample(sorted(names), k)`.
   Pinned `hmmscan` (`-Z` = that release's entry count, `--cut_ga
   --noali --cpu 4`) runs on the complement in target-file order.
   The reduced body must differ from stock. The shipped random-pad
   judge (`acts.exact_certificate.judge`, seeds 20261031, 20261032,
   20261033, sample 50, the same predicate `_ic2` uses) must return
   `pass: false` on at least one pad and table. The reduced body is not
   written as the step's output.

   If the reduced body equals stock, or no sampled record lost a dropped
   model, the drop was not exercised: INCONCLUSIVE, one retry with seed
   `20261124` on the same candidate set. A second power miss is recorded
   and not tried again. If the body differs and the judge passes, the
   control failed. The measured run does not start.

### Pass, power, classes

A step passes only when the decision is `SHIP` and both bodies are
byte-identical to that step's stock. Minimum count: 1000 tblout body
lines and 1000 domtblout body lines. Below that, INCONCLUSIVE, not a
kill. Classes on a difference, from `headline_carc_measured.classify`:
`whitespace-only`, `value-only`, `missing`, `extra`, `order`. Both
tables. tblout key is (target name, query name). domtblout key is
(target name, query name, hmm from, hmm to, ali from, ali to).

Pilot walls are not a speed claim. The pilot file is
`pipeline/results/release_chain/pilot_20261121.json`.

## Part 3 — measured run, seed 20261122 (not locked, not run)

Do not start until all of these are true: the six archives are approved
and their md5s are in `pairs.json`; the 38.1→38.2 control matched; the
pilot file is committed; this document has a dated addendum that cites
the pilot and freezes the code commit; job `13208152` has no PENDING
task; the node is exclusive.

Three genomes, disjoint from the pilot genome.
`measured_pool = pilot_pool - {pilot genome}`.
`sorted(random.Random(20261122).sample(sorted(measured_pool), 3))`.
The runner stops if the recomputed names differ. Fresh files. No genome
from the pilot.

Full chain, no skips: 37.0 → 37.1 → 37.2 → 37.3 → 37.4 → 38.0 → 38.1 →
38.2. Fill once at 37.0. Then each later release is a step.

At the fill release: three stock scans, which must be byte-identical to
each other, then one fill, which must match that body and `SHIP`.
At each later release, alternating `A B A B A B` (stock, TARE), r = 3.
Restore the incoming cache snapshot before every B, so the repeats do
not advance the chain. The cache carried forward is the snapshot after
the first B if that B is `SHIP` and byte-identical to its paired A.
If B1 fails, that genome stops. Later steps are not imputed.

\(S_g\) at a step is the median of the three stock walls divided by the
median of the three TARE walls. Also report the median of \(S_g\) across
the three genomes, the geometric mean, and the range. CV is the sample
standard deviation over the mean, per arm. Flag CV > 0.05. Do not drop
the genome. A FAIL stays in the median.

### Prediction, earlier data only

For the first update (37.0→37.1) there is no earlier chain step.
Use the headline-pilot coefficients already printed in the headline
measured addendum of `EXACT_REPLAY_PROTOCOL.md`, from that pilot's three
paired B runs on one genome: \(a = 1.0146410126797523\),
\(c = 0.10846594102974193\). Label them `prior`, not a refit. They are
one genome and one pair, and that pilot's TARE CV was 5.78%.

For every later step, refit \(a\) and \(c\) from chain steps that have
already finished, on every genome and every paired repeat of those
earlier steps. Do not include the step being predicted.
\(a_i = \mathrm{discovery\_s} / (f_\Delta \cdot T_{\mathrm{paired}})\),
\(c_i = (U - \mathrm{discovery\_s}) / T_{\mathrm{paired}}\),
with \(f_\Delta\) the census value of that earlier step and
\(T_{\mathrm{paired}}\) the stock wall next to that B in the
alternation. \(a\) and \(c\) are the arithmetic means. State the step
ids that entered the mean.
\(S_{\mathrm{pred}} = 1 / (a f_\Delta + c)\) with this step's \(f_\Delta\).
Relative error \(|S_{\mathrm{pred}} - S_g| / S_g\) is reported. It is
not a pass rule.

### Payback

For genome \(g\), after \(m\) updates (m counts releases after the fill):

\[
C_{\mathrm{TARE}}(m) = F + \sum_{i=1}^{m} U_i, \qquad
C_{\mathrm{stock}}(m) = T_0 + \sum_{i=1}^{m} T_i
\]

\(F\) is the one fill wall. \(T_0\) is the median of the three stock
walls at the fill release. \(T_i\) and \(U_i\) are the medians at update
\(i\). The payback index is the smallest \(m\) with
\(C_{\mathrm{TARE}}(m) \le C_{\mathrm{stock}}(m)\). If none of m = 1…7
qualifies, the payback is null on that genome. The single-pair formula
\(n \ge (F - T) / (T - U)\) is the special case of one update and one
stock time. Report the cumulative sums, not only that special case.
Laptop times are not used.

### Exactness

Same body rule, same 1000-line floor, same classes as the pilot, at
every step including the fill. Stock-vs-stock is the three A bodies at
that step. The unpinned control is not repeated at every step. It runs
once, on the last release of genome 1: replay the stock hit set with
`-Z` omitted. Its body must differ. A byte-identical unpinned replay
makes that genome's matches uninformative: record it, do not call the
genome EXACT.

Node: AMD EPYC 7542, `--exclusive --mem=0`, scratch chosen as in
`pipeline/jobs/headline_carc_pilot.job` (`/tmp` when at least 40 GiB is
free, otherwise `/scratch1/$USER/`). A crash, signal, md5 mismatch, or
model-count mismatch writes a partial JSON and exits 2. A scored FAIL
exits 0. Result file
`pipeline/results/release_chain/measured_20261122_<genome>.json`
with git head, seed, HMMER version, host, argv, walls, phases,
decisions, cache bytes, and each release md5.

## Seeds

Block 20261121–20261129. None of these integers appear elsewhere in the
tree at this commit.

| Seed | Use |
|---|---|
| 20261121 | pilot genome draw |
| 20261122 | measured genome draw |
| 20261123 | first 5% drop |
| 20261124 | one power retry of that drop |
| 20261125–20261129 | unused |

The IC2 pad seeds 20261031–20261033 stay the shipped constants. They are
not drawn from this block.

## Controls

| Control | Must | If it does not |
|---|---|---|
| 38.1→38.2 strict census vs `reference_kill_r1.json` | equal on `CONTROL_KEYS` | do not write `pairs.json` |
| Stock vs stock before any TARE compare | byte-identical bodies | INCONCLUSIVE, stop that genome |
| Fill and each update vs stock | `SHIP` and byte-identical | FAIL, stop the chain |
| Drift, pilot only | chained 38.2 = direct 38.2 = stock | drift or exactness failure |
| 5% drop, pilot only | body differs and the shipped judge refuses | control failure; no measured run |
| Unpinned replay, measured genome 1, last release | body differs | do not call that genome EXACT |
| Line floor 1000 + 1000 | both tables | INCONCLUSIVE |

## Deviations so far

None of the pass rules have moved. The SSH note at the start of the
session said the ControlMaster was down. `ssh -O check discovery` found
a master (pid 73601), so CARC was listed once for existing files and
for `squeue -j 13208152`. No second ssh followed. No download. No
`sbatch`. `pipeline/paper/tare/main.tex` was not edited.

## Open, blocked on Josh or on the pilot

- Approval to download the six gzip files in the table above.
- The seven-pair `pairs.json` and `churn_pairs.pdf` / `.png`.
- The pilot, then the measured-run addendum, then the measured run.
- `13208152` still had a PENDING task at the one check.

## Addendum 2026-10-18 — 38.1→38.2 control

Written after the run. The rules above are unchanged. This is not the
seven-pair census and not a speed claim.

Code that produced the file: `d9a0103243dabf0e2eab944b8945cde89b0801fd`.
Output: `pipeline/results/release_chain/control_38.1_38.2.json`.
`control_pass` is true. Every `CONTROL_KEYS` field equals
`reference_kill_r1.json`. `f_delta` is 4052/30134. Edited is 1,378, new
is 2,674, removed is 21.

On this pair only, the shipped hash-set count equals the accession
count: `hashset_fresh` is 4,052. The shipped parser's entry count equals
`z` on both files (27,481 and 30,134), every block magic is `HMMER3/f`,
and there are no duplicate stems, empty accessions, or duplicate hashes.
The pin's Z is the r1 model count for these two releases. That equality
is not assumed for 37.0–38.0.

Both md5s equal the headline pins: 38.1
`dc814cc181ece09102c09c4e6c19f2fd`, 38.2
`7ab3c4e215d0daaea3004e37c4e24f8a`. `pairs.json` was not written. The
figure script was not run.
