# Exact reference-incremental re-annotation: pinned-normalizer replay (pre-registered 2026-10-12)

Written **before** any run below. Locked text is never edited; later
changes are dated addenda. Base commit `2ca21e2`.

## Why this exists

`ref-merge` (REFERENCE_INCREMENTAL_PROTOCOL.md) is **bounded-approximate**:
a rescaled E-value cell is accepted within
half-ULP(stock) + half-ULP(emitted) + |φ|·half-ULP(source). It is not
byte-identical to a full run. iSeqSearch is approximate too (Kendall τ
0.48–0.57). The pivot claim is **exact**: the re-annotated output equals
a full stock run on the new release, byte for byte, on every body line.

## Idea under test (PROPOSED)

A fitted normalizer (here `entry_count`, i.e. HMMER's Z) is a value the
tool computes from the reference. If the tool exposes a knob that sets
that value, the wrapper can make the tool itself print the new-release
number instead of rescaling a printed one. The knob is declared by the
caller as data, like `--prep` (`--pin '-Z {entry_count}'`); no tool name
is compiled into `acts/`.

Exact re-annotation of records Q against new release R':

1. **Discover.** Run the tool on Q against the sub-reference of new or
   changed entries (strict entry hash), pinned to the R' normalizer.
2. **Candidates.** Per record: cached hits whose entry is unchanged in
   R', plus discovery hits.
3. **Replay.** Run the tool once on the records that have any candidate,
   against the union of candidate entries **in R' file order**, pinned.
4. **Emit** the replay's body lines. Per-key counts the tool derives from
   its own hit list (HMMER domZ) are produced by the tool, not by ACTS.

Soundness argument (assumptions, not a theorem): under `--cut_ga`
reporting is per-entry and score-thresholded, and the pipeline filters
are P-value thresholds that do not read Z (R2p, R3, R3c). So an entry not
reported for a record in a full run is not reported in a run on any
sub-reference containing it, and a reported one is. Replay reproduces the
reported set; the pin reproduces Z; the per-record reported set
reproduces domZ; R' order reproduces any position-based tie-break.
Precondition: E-value-thresholded reporting refuses (R2n), as today.

## Test E1 — mechanism (oracle candidates)

Queries: 300 proteins sampled from `data/recurrence/A/GCF_002853805.1_protein.faa.gz`,
`random.Random(20261012).sample` over record indices, written in original
order. Reference: Pfam 38.2 (`data/hmmer/Pfam-A.hmm.gz`, 30,134 models).
Argv: `hmmscan --cut_ga --noali --cpu 4 --tblout T --domtblout D <ref> <q>`.

- **S**: stock full run.
- **R**: replay on the records with a hit in S, against the union of S's
  hit models in 38.2 order, with `-Z 30134` added.
- **Rn** (negative control): R without `-Z`.

Checks, body lines only (every line not starting with `#`), both tables:

1. R body == S body, byte for byte.
2. Rn body != S body (the pin is load-bearing).

**Kill rule E1:** check 1 fails → exact replay is dead for HMMER; ship
stays `ref-merge`, labelled approximate. Check 2 holding is required for
the result to mean anything.

## Test E2 — end to end (38.1 cache → 38.2)

Same queries. Cache: S₁ = stock run on Pfam 38.1. Changed/new = 38.2
entries whose strict hash (`acts/entry_hash.py`) is not in 38.1. Run
steps 1–4. Compare to S (stock on 38.2) as in E1.

**Kill rule E2:** any body-line difference → exact mode refuses for this
tool. Report candidate counts, discovery/replay entry counts, and walls
(MEASURED, VM: 4 cores, aarch64, HMMER 3.4 built from source). These
walls are indicative only; the graded timing stays on CARC.

## Footer

`#` lines carry the date, paths, and the option line (which will show
`-Z`). They are tool metadata, not results. ACTS regenerates them; MATCH
is body bytes plus the column header block. Stated, not hidden.

## Not in scope

E-value-thresholded reporting (refuses). Releases where the normalizer
shrinks (Z_new < Z_old with E-thresholds; not reachable under
`--cut_ga`). DIAMOND/BLAST pins (`--dbsize` / `-dbsize`) are a later
addendum; the BLAST boundary result (`different_hsp`) says replay may
not hold there.

## Addendum 2026-10-12 — E1 and E2 outcomes (results; rules unchanged)

Pre-registration was not committed before the runs: git in the session
could not delete its own lock files. Its SHA-256 and UTC time were
recorded first: `results/exact_replay/PREREG_HASH.txt`
(`d55ca345…`, 2026-10-12T23:09:34Z). The locked text above is that file.

Host: 4-core aarch64 VM, HMMER 3.4 built from source. Driver
`scripts/exact_replay_hmmscan.py`. File `results/exact_replay/e1_e2.json`.

**E1 — PASS.** 275 queries with a hit, 452 models replayed, `-Z 30134`.
tblout 534/534 and domtblout 545/545 body lines byte-identical to S.
Rn (no pin) differs on every body line (534/534, 545/545): the pin is
load-bearing. Not killed.

**E2 — PASS.** 4,052 changed or new models (equals R1). Candidates 534
pairs (= S's rows exactly), 452 replay models. Body byte-identical to S on
both tables. Not killed. Walls, single run, indicative: stock S 64.73 s;
discovery scan 7.22 s, replay scan 1.17 s, sub-reference builds 2.30 s,
release diff 14.69 s (Python, paid once per release, not per genome).

## Addendum 2026-10-12 — shipped exact mode and S3 (post-hoc; not a gate)

`acts/reference_run.py`: `--pin` (caller data, inserted after the tool
name; placeholders `{entry_count}`, `{total_entry_length}`). On a SHIP
contract: refuse `REFUSE_PIN` if a fitted normalizer member is not set by
the pin; once per (namespace, pin) run the in-situ E1 on the probe sample
and store the outcome in the contract; replay candidates (cached rows of
unchanged entries + rows from new/changed entries) on the union in release
order; tripwire on any non-candidate row; `--verify full` compares bodies
to a full run, `--verify audit` compares the audited records' body lines.
MATCH is body bytes; `#` lines are tool metadata.

Engineering found by Amdahl on S3 (MEASURED before/after, same slice):
stable entries were rewritten to the cache every release
(`cache_store_s` 12.01 → 0.001); coverage was stored per (record, entry)
pair, ~records × entries rows (the 31.9 GB CARC cache), now (entry,
record-set) with legacy rows still read; rows were loaded with one query
per entry per table, now one scan (`cache_load_s` 0.53 → 0.0008). A call on
the full reference uses the caller's own prepared file and falls back to a
written, prepared copy if the tool fails on it.

**S3** (`results/exact_replay/s3_cli_slice.json`): seeded 3,000-model
slice, 300 queries, `--verify audit`. 38.2 release run `SHIP`, body
byte-identical to an independent stock run (54 tblout, 77 domtblout rows).
Wall 2.76 s vs stock 5.25 s at this toy size, where parsing (1.23 s) and
the audit dominate. Not a speedup claim. The graded number stays the
pre-registered CARC re-annotation, now to be run with `--pin`.

## Addendum 2026-10-12 — Test E3, E-value reporting (pre-registered)

Written **before** any E3 run. The text above is unchanged. No E3 number
below is a result.

### Why

E1/E2 used `hmmscan --cut_ga`. That mode thresholds on bit score, so
changing Z never moves a hit across the reporting line. Default
reporting is E-value: `-E 10 --domE 10`, and E = P·Z. When Z changes,
hits cross the line. The fitter refuses that case today (R2n: union of
halves is a strict superset of the full run). E3 decides whether exact
mode extends to it.

### Mechanism under test (assumptions, not a theorem)

HMMER's pipeline filters (F1/F2/F3) are P-value gates. They do not read
Z. Only the reporting and inclusion E-values do. Per-model P is treated
as a function of that model and the query alone. domZ (the c-Evalue
normalizer) is, per query, the number of targets HMMER reported in that
run. Replay must make HMMER recompute it. A c-Evalue mismatch is a body
mismatch and a kill, not a tolerance. ACTS does not rescale any printed
cell.

- **Z grows** (a release adds models). Every cached hit's E rises, so an
  unchanged model that failed the old threshold cannot newly pass.
  Candidates = cached hits on unchanged models, plus discovery hits on
  new or changed models. Pinned replay (`-Z Z_new`) lets HMMER drop the
  hits that cross out and recompute domZ. Slack factor s = 1. Expected
  exact.
- **Z shrinks** (a release removes models). Hits whose old E lies in
  (10, 10·Z_old/Z_new] cross in and were never cached. Fill the cache
  at relaxed reporting thresholds `-E 10·s --domE 10·s` with
  s ≥ Z_old/Z_new, and keep those rows as candidates only. Replay uses
  the original thresholds and `-Z Z_new`. If Z_old/Z_new > s, the run
  is a refusal (full run), not a replay. From the stated sizes,
  30134 > 27481 and 30134 ≤ 2·27481, so s = 2 covers 38.2 → 38.1 and
  s = 1 does not. That inequality is arithmetic on the stated sizes,
  not a measurement.
- **Discovery** runs on the sub-reference **unpinned**. Z_sub < Z_new,
  so at a fixed reporting threshold the sub-reference is a superset;
  replay filters. Discovery uses the same slack thresholds as the cache
  fill. At s = 1 those thresholds are `-E 10 --domE 10`.

Inclusion thresholds (`--incE`, `--incdomE`) stay at HMMER's defaults.
They are not slack-widened. A difference they cause is a kill.

### Locked procedure

Tool, every scan, thresholds always on the command line, no `--cut_ga`:

```
hmmscan --noali --cpu 4 --tblout T --domtblout D -o /dev/null \
  -E Erep --domE Erep [-Z Z] <pressed-ref> <queries>
```

`--cpu 4` matches E1. This host has 14 cores; 4 is still the locked
width. HMMER 3.4 (`hmmscan` on `PATH`).

Queries, from `pipeline/data/recurrence/A/GCF_002853805.1_protein.faa.gz`.
Draw record indices with `random.Random(seed).sample(range(n), k)`,
sort the indices, write the records in that file order.

- Q300: seed `20261012`, k = 300. The E1 sample.
- Q1000: seed `20261013`, k = 1000. An independent draw. Used only if
  E3c on Q300 does not differ from stock.

References:

- Pfam 38.1: `pipeline/data/hmmer/pfam38.1/Pfam-A.hmm.gz`, stated Z = 27,481.
- Pfam 38.2: `pipeline/data/hmmer/Pfam-A.hmm.gz`, stated Z = 30,134.

If the number of `//`-terminated model blocks is not the stated Z, that
arm is INCONCLUSIVE and the test stops. Strict hash is
`entry_content_hash(block, PROFILE_VOLATILE_TAGS)` (`acts/entry_hash.py`,
tags from `acts/reference_formats.py`). A hash that occurs twice inside
one release makes the test INCONCLUSIVE. Unchanged means the hash is in
both releases. Discovery models are target-release blocks whose hash is
absent from the source release, taken in target-file order. Table
identity uses the HMM `NAME` (target field 0). A cache hit is a
candidate only when its source model's hash equals exactly one target
model; the replay uses that target model's name and block.

Cache fill: full source release, no `-Z`, `-E 10·s --domE 10·s`.
Discovery: the discovery sub-reference, no `-Z`, the same slack
thresholds. Replay: queries that have at least one candidate, against
the union of candidate models in target-file order, `-E 10 --domE 10
-Z Z_target`. Stock, the comparison target: full target release,
`-E 10 --domE 10`, no `-Z`. Mini-references are extracted model blocks
in target order, then `hmmpress`. Uncompressed text is deleted after
`hmmpress`. Pressed files stay in the work directory, not in git.

### Arms (Q300 unless the control clause fires)

- **E3a** growth, 38.1 → 38.2, s = 1. Replay `-Z 30134`. Check: body of
  tblout and of domtblout byte-identical to stock 38.2.
- **E3b** shrink, 38.2 → 38.1, s = 2. Cache and discovery at
  `-E 20 --domE 20`. Replay `-Z 27481` with `-E 10 --domE 10`. Check:
  byte-identical to stock 38.1.
- **E3c** negative control, 38.2 → 38.1, s = 1. Same as E3b with no
  slack (`-E 10 --domE 10` on the cache and on discovery). Must differ
  from stock 38.1 by at least one body line. That is the evidence the
  slack is load-bearing.

Body = every line that does not start with `#`. Both tables. `#` lines
are tool metadata, as in E1.

### Counts (recorded, not extra pass rules)

Per arm: candidate pairs; replay models; replay queries; crossed-out
rows; crossed-in rows; walls per phase. A row's pair is (target `NAME`,
query name), field 0 and field 2 of tblout, field 0 and field 3 of
domtblout.

- Crossed-out: cache body lines on unchanged models whose pair is
  absent from the stock body. Count tblout and domtblout separately.
- Crossed-in: stock body lines whose pair is absent from the s = 1
  cache on unchanged models and present in this arm's slack cache.
  Zero by definition when s = 1.
- E3c band rows: stock body lines whose pair is absent from the s = 1
  candidate set. tblout and domtblout separately.

Walls, one run, indicative only: stock, cache fill, hash diff,
discovery press, discovery scan, replay press, replay scan. The JSON
records git hash, host, and the HMMER version line. Result file:
`pipeline/results/exact_replay/e3.json`.

### Kill rule

If E3a or E3b differs in any body line on either table, exact mode
stays `--cut_ga`-only. Write that down and stop. Do not retune s,
thresholds, hashes, or the candidate rule. Do not ship the caller
`--slack` path.

If E3c does not differ on Q300, the control is underpowered. Rerun
E3a, E3b, and E3c on Q1000 and record that fact. Do not change the
locked rules. If E3c also does not differ on Q1000, the slack control
is uninformative: do not ship, even if E3a and E3b matched.

E3c differing is required for the shrink result to mean anything. It
is not itself a kill of exact mode.

## Addendum 2026-10-12 — E3 outcomes (results; rules unchanged)

Pre-registration `4ae39ab`. Driver `scripts/exact_replay_evalue.py`.
File `results/exact_replay/e3.json` (`git_head` `894b7ca`). A path bug
stopped the first process before any body comparison; the fix is that
commit. Completed scans were reused from their stamps. No threshold,
sample, or hash rule was changed.

Host: Joshuas-MacBook-Pro-3.local, arm64, `--cpu 4`, HMMER 3.4 on
`PATH` (`# HMMER 3.4 (Aug 2023)`). Python 3.11.9. Model counts matched
the stated sizes (27,481 and 30,134). Q300 only: E3c differed, so the
Q1000 rerun did not run. Walls below are one run and indicative.

**E3a — PASS.** 38.1 → 38.2, s = 1, replay `-Z 30134`. Discovery 4,052
models. Candidates 1,375 pairs, 1,135 replay models, 288 queries.
tblout 1,361/1,361 and domtblout 2,729/2,729 body lines byte-identical
to stock 38.2. Crossed out (cached, absent from stock): 1 tblout, 4
domtblout. Crossed in: 0. Not killed.

**E3b — PASS.** 38.2 → 38.1, s = 2, cache and discovery at `-E 20
--domE 20`, replay `-E 10 --domE 10 -Z 27481`. Discovery 1,399 models.
Candidates 1,332 pairs, 1,091 replay models, 287 queries. tblout
1,300/1,300 and domtblout 2,532/2,532 byte-identical to stock 38.1.
Crossed out: 23 tblout, 70 domtblout. Crossed in: 1 tblout, 4
domtblout. Not killed.

**E3c — control holds.** Same shrink at s = 1. Replay 1,299 tblout
lines against stock 1,300, and 2,528 domtblout lines against 2,532.
Band rows (stock lines whose pair is absent from the s = 1 candidate
set): 1 tblout, 4 domtblout, the same counts as E3b's crossed-in
rows. Positional diffs are 1,006 and 2,027 because the missing line
shifts the file. The stored first domtblout mismatch is a c-Evalue
(`5.5e-195` vs `7.3e-195`) on a row whose score is `635.9` on both
sides. Q300 was enough.

Indicative walls, seconds. Hash diff 16.20 (both releases, once).
Full press: 38.1 decompress 2.75 + press 10.92; 38.2 decompress 4.73
+ press 10.53. E3a: stock 43.46, cache fill 36.54 (the 38.1 stock
scan), discovery press 6.81, discovery scan 5.84, replay press 5.49,
replay scan 2.81. E3b: stock 36.54, cache fill 41.03, discovery press
5.43, discovery scan 2.13, replay press 5.31, replay scan 2.91. E3c:
cache fill is the 38.2 stock scan (43.46); discovery press 5.37,
discovery scan 2.15, replay press 5.28, replay scan 2.89.

## Addendum 2026-10-12 — optional Q1000 power run (rules unchanged)

Written before any Q1000 scan. E3's Q300 PASS stands either way. This
run does not rewrite `results/exact_replay/e3.json` and does not change
the sample of record.

E3's locked definitions, argv, references, s values, and kill rule are
reused verbatim on the already-locked Q1000 sample: seed `20261013`,
k = 1000, an independent draw from the same FASTA, indices sorted,
records written in file order. The Q300 run is this design's pilot. It
showed the arms complete end to end, that rows exist, and that the
controls behave (E3c differed on 1 tblout and 4 domtblout band rows).

The driver file is not edited. An external runner calls
`scripts/exact_replay_evalue.py`'s `evaluate` on that seed and k only.
If `evaluate` returns early because an E3a or E3b body differed, the
arms it skipped are then called through the same `run_arm` arguments
`evaluate` uses, so E3c is still measured. No threshold, sample, hash,
or candidate rule changes. `--cpu 4`. Work directory outside the repo.
Uncompressed text is deleted after `hmmpress`, as the driver already
does. Result file: `results/exact_replay/e3_q1000.json` (git hash,
host, HMMER version, every count, walls). Walls stay one run and
indicative.

Before the arms: one stock 38.2 scan, twice, on the first 100 records
of the Q1000 file (`-E 10 --domE 10`, no `-Z`). Bodies (lines that do
not start with `#`) of tblout and of domtblout must be identical.
Otherwise stop. No arm runs. That check is recorded and is not an
E3a/E3b pass rule.

Report-only quantities, not extra pass rules:

- Band rows: stock body lines whose pair is absent from the s = 1
  candidate set, per table. The driver's E3c `band_rows` count.
- Crossed-in and crossed-out counts per arm, as E3 already defines
  them. Zero crossed-in when s = 1, by that definition.
- Per-query domZ changes caused by band rows. domZ for a query is the
  number of tblout body lines for that query (one reported target per
  line), the same normalizer named in the E3 mechanism section. For
  each query, band_tbl is how many of its stock 38.1 tblout lines are
  band rows under the E3c candidate set, and band_dom is the same count
  on domtblout. A query whose band_tbl is nonzero has a domZ change
  caused by band rows, of size band_tbl. Record each such query with
  stock domZ, E3c replay domZ (0 if that query is absent from the
  replay), band_tbl, band_dom, and whether stock domZ minus replay
  domZ equals band_tbl. Also record the number of queries with
  band_dom > 0 and band_tbl = 0: domain rows that do not change domZ.

Outcome rule. An E3a or E3b body difference on Q1000 is recorded as a
failure of exact E-value mode on a larger sample. E3's Q300 PASS stays
recorded alongside it. Do not retune. If E3c does not differ, write
"control not exercised at Q1000" (INCONCLUSIVE, not a kill). E3c
differing, with E3a and E3b byte-identical to stock, means the slack
band holds on this sample and is load-bearing.

## Addendum — E1-scale (pre-registered)

Written before any whole-proteome `--cut_ga` scan in this test. The text
above is unchanged. No number below is a measured result. Semantics:
`results/exact_replay/e1scale_semantics.md` (commit `9a0d176`). Pilot:
`results/exact_replay/e1scale_pilot.json` (commit `598e7cd`).

### What the pilot decided

The width question was reviewed before the pilot and then measured on the
Q1000 draw, which is now pilot data and is not reused here.

`GetMaxNameLength` walks every registered hit. Under `--cut_ga` a hit is
registered only when its bit score already passes that model's GA1, and
that same hit is marked reported. The pilot's comparisons were
byte-identical, not whitespace-only, so no width remedy is adopted. The
three remedies in the semantics note stay unadopted. This is the one
redesign this question is allowed, and it is not spent.

Pilot, reported as a pilot. Sample sha256 `ffaa279d…`, seed `20261013`,
k = 1000, from `GCF_002853805.1`. Stock-vs-stock on Pfam 38.2 was
byte-identical (152.4 s, 147.2 s, indicative). E1 and E2, driver, were
byte-identical to stock: 1,738 tblout and 1,757 domtblout body lines,
1,267 models, 908 queries. The shipped CLI
`python3 -m acts run --strategy reference --pin '-Z {entry_count}'`
filled on 38.1 and replayed on 38.2 (`--verify full`) and was
byte-identical to an independent stock scan; decision `SHIP`. The
original 300 (sha256 `3a6e6669…`) still passed: 534 tblout and 545
domtblout, both tables, E1 and E2. Deleting 63 of 1,267 candidate models
(5%, `random.Random(20261013)`) differed, and the classifier reported
missing rows (99 tblout keys, 93 domtblout keys) plus value-only on the
surviving domtblout rows. That is the domZ effect named in the semantics
note. The tblout class was missing only, which is what a pinned `-Z`
predicts.

Rn, the unpinned replay, was value-only. On the 300 it differed on every
body line. On Q1000 it differed on 1,735/1,738 tblout lines and
1,754/1,757 domtblout lines. The three lines that stayed equal on each
table print E-value `0`. A printed zero does not move when Z changes.
E1's check 2 (Rn body differs) still holds. "Every line" is not the
measured pass rule.

### Locked procedure

Question, judged alone: is `--cut_ga` pinned replay byte-identical to
stock on a whole proteome?

Same argv as E1. Same driver, `scripts/exact_replay_hmmscan.py`, unchanged.
`--cpu 4`. HMMER 3.4 on `PATH`. Pin `-Z` equal to the number of model
blocks in Pfam 38.2, which the semantics tree and the pilot press both
counted as 30,134. If a press reports another count, stop; the arm is
INCONCLUSIVE. No slack. No column-width pad. No token claim in place of
bytes.

Proteomes, from `pipeline/data/recurrence/A/*.faa.gz`, excluding
`GCF_002853805.1_protein.faa.gz` and `GCF_002090355.1_protein.faa.gz`.
Draw `random.Random(20261014).sample(sorted(pool), 3)` and then sort the
three names. The draw, recorded before the scans, is:

1. `GCF_013315695.1_protein.faa.gz`
2. `GCF_049201905.1_protein.faa.gz`
3. `GCF_059719525.1_protein.faa.gz`

Whole files. No second sample of records. The runner recomputes the draw
and stops if the sorted names differ, which happens if the directory
gained or lost a file.

Before any replay comparison: two stock 38.2 scans of proteome 1, no
`-Z`. Bodies of both tables must be byte-identical. If they are not,
stop. No proteome is scored. That check is determinism, not an exactness
pass.

Then, for each proteome, in the order above: stock 38.2, stock 38.1,
E1, E2, and Rn, through the driver. E1 and E2 are the pass rules. Rn is
the pin control: its body must differ from stock on each table. It is
not required to differ on every line. A byte-identical Rn makes that
proteome's match uninformative: record it, and do not call the proteome
EXACT.

Classification, both tables, body lines only. Byte equality and
`split()` token equality are both recorded.

- whitespace-only: bytes differ, tokens equal
- value-only: some shared row's tokens differ
- missing / extra: row-key multiset differs
- order: same keys, different sequence

tblout key is (target name, query name). domtblout key is (target name,
query name, hmm from, hmm to, ali from, ali to).

Per proteome:

- EXACT: E1 and E2 byte-identical on both tables, and Rn differs.
- TOKEN-EQUAL: E1 and E2 have no token difference, some bytes differ, and Rn differs.
- FAIL: any E1 or E2 token differs, or Rn is byte-identical.

Overall:

- EXACT only if every proteome is EXACT and the three stock 38.2 tblout
  bodies sum to at least 5,000 lines.
- TOKEN-EQUAL if no proteome is FAIL and at least one is TOKEN-EQUAL,
  with the same line floor.
- FAIL if any proteome is FAIL.
- INCONCLUSIVE if the tblout floor is not met. A byte match below the
  floor is not EXACT.

The CLI is not re-run. The pilot already compared it to stock on Q1000.
Walls are one run and indicative. Result file:
`results/exact_replay/e1scale.json` (git hash, host, HMMER version,
input md5s, per-proteome line counts, difference classes, candidate
counts, walls). Work directory `~/tmp/e1scale_work`, outside the repo.
Uncompressed scratch is deleted after the run.

## Addendum 2026-10-13 — E1-scale outcome (results; rules unchanged)

Pre-registration on this branch is `44f1766`. The run recorded
`git_head` `d5360fd`; rebase onto `origin/main` replayed that patch
unchanged as `44f1766`. Driver `scripts/exact_replay_hmmscan.py`,
unchanged. File `results/exact_replay/e1scale.json`.

Host: Joshuas-MBP-3.lan, arm64, `--cpu 4`, HMMER 3.4 on `PATH`
(`# HMMER 3.4 (Aug 2023)`). Pressed model counts 30,134 and 27,481.
Proteomes are the locked draw, whole files. Stock-vs-stock on proteome
1 was byte-identical (738.4 s and 720.6 s, indicative). Walls below are
one run and indicative.

**Overall EXACT.** Stock 38.2 tblout body lines sum to 26,127, above
the floor of 5,000. E1 and E2 are byte-identical to stock on both
tables for every proteome. No width remedy. The token check agreed
with the byte check on every E1 and E2 table: there was no
whitespace-only difference.

| Proteome | Records | tblout | domtblout | E1 models | Outcome |
|---|---:|---:|---:|---:|---|
| GCF_013315695.1 | 4,927 | 9,094 | 8,812 | 3,719 | EXACT |
| GCF_049201905.1 | 4,290 | 8,488 | 8,202 | 3,574 | EXACT |
| GCF_059719525.1 | 4,374 | 8,545 | 8,265 | 3,615 | EXACT |

E2 replayed the same model counts as E1. Changed or new models: 4,052
on each proteome. Candidate pairs equal the tblout line counts.

Rn, the unpinned replay, was value-only and not byte-identical. On
each proteome, 11 tblout lines and 11 domtblout lines stayed equal to
stock. Every one of those lines prints E-value `0`. The rest differ.
The pin control holds. It does not differ on every line, for the same
reason the pilot recorded.

Uncompressed Pfam text was deleted after the run. Pressed sidecars in
the work directory were deleted with it.

## Addendum — per-record replay (pre-registered)

Written after the pilot on `GCF_013315695.1` and before any scan of the
two proteomes named below. The text above is unchanged. Pilot file
`results/exact_replay/costpass_batch_pilot.json`. The baseline it is
compared with is `results/exact_replay/costpass_baseline.json`.

### Cost

A batching of the records that have candidates costs, in pair-scan units,

    T = α·k + π·Σ_b |U_b| + Σ_b |B_b|·|U_b|

where k is the number of batches, U_b is the union of the candidate sets
in batch b, α is the per-batch startup, and π is the per-entry build
cost. Both α and π are in pair scans. From the median-wall baseline
replay, s = 84.8388374170172 / (4555 × 3719) seconds per pair and the
build was 1.563109832990449 / 3719 seconds per entry, so π = 84. A
two-entry prep and a one-record scan measured 0.003 s each; α = 2000
pair scans is 0.01 s, which leaves margin for writing the batch.
Exactness does not depend on α or π.

Records are sorted by their rarest candidate (lowest frequency, then
id), then by input position. Equal contiguous chunks of that order are
scored on a grid (powers of two, then a step through the neighborhood
of the best). The chunk size with the lowest T is kept. A tie keeps the
smaller chunk. That is the minimum on the grid, inside this family of
partitions, not over every partition. Each chunk is searched in input
order, pinned to the full reference's normalizer, against the union of
its own candidates in release order. Bodies are merged back in input
order. No tool name is compiled into `acts/`.

### What the pilot showed

`GCF_013315695.1` is pilot data. It is not one of the two proteomes
below. Oracle candidates, 104 batches, both tables byte-identical to
stock (9,094 tblout, 8,812 domtblout) in 11.1 s. Deleting 186 of 3,719
candidate models (5%, `random.Random(20261013)`) was missing on tblout
and missing plus value-only on domtblout. The unpinned replay was
value-only on both tables. The shipped CLI, three runs restored from
the same 38.1 cache, was `SHIP` and byte-identical on both tables.
Median wall 798.1 s (791.8, 798.1, 802.8). Median replay phase 15.7 s,
of which the scan was 10.4 s and the build 5.0 s. Median discovery
97.5 s. The unconditional safety check was still 647 s. Loads are in
the pilot file. Walls are indicative.

### Locked procedure

Question, judged alone: is the batched `--cut_ga` replay byte-identical
to stock on a fresh whole proteome?

Same argv, pin, and body-line MATCH as E1-scale. HMMER 3.4,
`--cpu 4`. The runner is the shipped CLI for the 38.1 cache then the
38.2 replay, plus an oracle batched replay and an unpinned batched
replay driven from the stock 38.2 hit set.

Proteomes, from `pipeline/data/recurrence/A/*.faa.gz`, excluding

- `GCF_013315695.1_protein.faa.gz` (pilot, and E1-scale)
- `GCF_049201905.1_protein.faa.gz` (E1-scale)
- `GCF_059719525.1_protein.faa.gz` (E1-scale)
- `GCF_002853805.1_protein.faa.gz` (E1 queries)
- `GCF_002090355.1_protein.faa.gz` (E1-scale exclusion)
- `GCF_001515725.1_protein.faa.gz` (DX3)
- `GCF_001513615.1_protein.faa.gz` (DX3 rate)

Draw `random.Random(20261015).sample(sorted(pool), 2)` and then sort
the two names. The draw, recorded before the scans, is:

1. `GCF_016806025.1_protein.faa.gz`
2. `GCF_017165095.1_protein.faa.gz`

The runner recomputes the draw and stops if the sorted names differ.

Per proteome, one stock 38.2 scan, then the oracle batched replay (E1),
the unpinned batched replay (Rn), and the shipped CLI filled on 38.1
and replayed on 38.2 (E2). Classification is the E1-scale rule, both
tables, body lines only.

- EXACT: E1 and E2 byte-identical on both tables, and Rn differs.
- TOKEN-EQUAL: E1 and E2 have no token difference, some bytes differ, and Rn differs.
- FAIL: any E1 or E2 token differs, or Rn is byte-identical.

Overall EXACT only if both proteomes are EXACT. TOKEN-EQUAL if neither
is FAIL and at least one is TOKEN-EQUAL. FAIL if either is FAIL.
A `REFUSE` from the CLI is not EXACT. Walls are one run and indicative.
Result file `results/exact_replay/costpass_measured.json`.
