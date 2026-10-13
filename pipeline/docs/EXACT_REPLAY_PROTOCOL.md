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
