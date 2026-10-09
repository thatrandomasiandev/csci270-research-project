# HMMER accumulated-savings experiment (pre-registered)

Written **before** any savings run. Do not edit the locked sections after
a job starts. No CARC job in the commit that adds this file.

Predecessor screen: `results/headline_screen.json` (job 12377262).
Reuse test: commit `7eeb40e` / `results/inference_fasta_reuse.json`.
Predictions: `results/hmmer_predicted_speedup.json`.
Cache key: `docs/CACHE_KEY_PROTOCOL.md` (addendum 2026-09-27).

This measures **accumulated** stock vs cached wall and CPU over a
realistic collection, in order. It is not a single-pair ceiling.

---

## Deviation from HEADLINE_SCREEN.md (stated)

`docs/HEADLINE_SCREEN.md` locked `paper_uses = hmmsearch` if both modes
ADVANCE. Both did.

The Part 2 model (`results/hmmer_predicted_speedup.json`) shows
**hmmsearch is startup-capped** (≤ 4.8× even at the K-12 `m`; on
collection A it stays ~2.1–2.5× at k = 10 and 30). **hmmscan scales
with recurrence** (A: 2.96× at k = 10, 4.10× at k = 30; B: 36.7× at
k = 10, 50.7× at k = 39).

**Both modes are run.**

- **hmmsearch** stays the **pre-registered primary** (the locked
  `paper_uses` choice).
- **hmmscan** is a **post-hoc selection**. It is justified by the
  model above, and by the official EBI `pfam_scan.pl`:
  `https://ftp.ebi.ac.uk/pub/databases/Pfam/Tools/PfamScan.tar.gz`
  (retrieved 2026-09-27; `Last-Modified` 2017-03-01).
  `PfamScan.pm` line 78 sets the binary to `hmmscan`; lines 138 / 145
  start the argv with `'hmmscan'`; lines 428–429 push `'--cut_ga'`
  unless the user set an E-value or bit-score cutoff. See
  `results/headline_screen.md`.

A 3× claim on hmmsearch from this experiment is not licensed by the
model on collection A. Do not promote hmmscan to primary after seeing
the numbers.

---

## MATCH (from `7eeb40e`)

HMMER `--tblout` pads columns and right-aligns numbers. The paper
claims **token identity**, **not** byte identity.

| Mode | MATCH | Source |
|------|--------|--------|
| hmmscan `--cut_ga` | **order** + whitespace-normalized (`split()`) | `inference_fasta_reuse.json` → `scan_cut_ga` (`match=order`, `match_ws=true`) |
| hmmsearch `-Z 1e6 --domZ 1e6` | **multiset** + whitespace-normalized | same file → `search_fixed_Z` (`match=multiset`, `match_ws=true`) |

Do not require byte-identical tblout. Do not silently switch MATCH
after a mismatch.

---

## Workloads (locked)

Same order for stock and cached. Orderings are
`recurrence_curves.json` → `orderings[0]`, seed **20260926**.
Accessions are `recurrence_accessions.json`.

### Collection B — O157:H7, all 40

Full collection, seed-20260926 order (index into the accession list):

```
4, 2, 1, 14, 32, 11, 38, 7, 23, 15,
24, 35, 27, 28, 39, 22, 31, 13, 37, 9,
17, 6, 36, 5, 18, 29, 12, 21, 8, 16,
10, 25, 3, 33, 0, 26, 30, 34, 19, 20
```

First / last: `GCF_001651945.2` (FRIK2533) … `GCF_013167595.1` (F8952).

### Collection A — diverse *E. coli*, first 30 of the first ordering

Seed-20260926 order, **stop after genome 30**:

```
9, 5, 2, 75, 29, 64, 23, 80, 4, 14,
47, 63, 31, 28, 16, 52, 6, 39, 69, 78,
25, 74, 76, 57, 20, 24, 15, 67, 41, 44
```

First / last of this prefix: `GCF_002853805.1` (14EC029) …
`GCF_024298565.1` (EC21Z-014). Do not run genomes 31–100 in this
experiment.

Collection C is not in this run.

---

## Cached path (locked)

Sequential over the collection. **One persistent cache file per mode**
(not per genome). Namespace per `CACHE_KEY_PROTOCOL.md`: kind + argv
strings + content hash of the HMMER binary + content hash of every
argv-named path (Pfam-A). `{input}` is not fingerprinted.

Same flags as the screen (`headline_screen.json` argv templates):
`--cpu 32`, `--noali`, `--tblout`. hmmscan: `--cut_ga`. hmmsearch:
`-Z 1000000 --domZ 1000000`.

Per genome, log:

- wall (perf_counter)
- CPU (user+sys, `RUSAGE_CHILDREN`)
- hits, misses
- **EMPTY hits** (cached row, no domain lines)
- **NON-EMPTY hits** (cached row with ≥1 hit line)

`7eeb40e` reused 202 overlapping proteins but almost all of those hits
were EMPTY (192 scan / 190 search). NON-EMPTY reuse was only 10 / 12
rows. This collection run is the real NON-EMPTY test.

JSON is **written after every genome**, not only at the end. A killed
job must still have a prefix.

---

## Stock baseline (locked)

A full stock run of every genome is ~10 min (hmmsearch) and ~51 min
(hmmscan) at the screen `N = 4,192`. That is the reason we sample.

Measure stock on these 1-based positions, **same order as cached**:

| Workload | Stock genomes |
|----------|----------------|
| A (30) | 1, 2, 5, 10, 20, 30 |
| B (40) | 1, 2, 5, 10, 20, 40 |

For every other genome *i*, predict stock wall from the screen fit
and that proteome’s own `N_i`:

```
stock̂_i = a + b · N_i
```

`a`, `b` from `headline_screen.json` (per mode). Report measured vs
predicted at every sampled point. **If any sampled |error| / measured
exceeds 10%, flag it** in the result JSON and the write-up. Do not
quietly replace the fit.

---

## Correctness (locked)

1. **MATCH** (table above) on every genome that has a stock run.
   Fail → STOP and report. Do not continue the collection.
2. **Dune-style audit** on genomes without a stock run: re-run a
   random **2% of cache hits** for that genome through the stock tool
   (same argv, that protein only), fixed seed **20260927**. Draw at
   least **20 NON-EMPTY hits** per genome when that many exist; if
   fewer NON-EMPTY hits exist, audit all of them. Compare with the
   same MATCH. Any mismatch → STOP and report.

EMPTY hits may be in the 2% draw; they do not count toward the
20 NON-EMPTY floor.

---

## Headline metrics (locked)

Per workload and per mode:

- Cumulative **CPU-hours** and **wall-hours**, stock vs cached, over
  the collection (stock uses measured points + `a + b·N_i` for the
  rest; say so).
- Per-genome speedup vs *k* (genome *k*+1 given the first *k*).
- Measured vs Part 2 predicted speedup
  (`results/hmmer_predicted_speedup.json`; that file used screen
  `N = 4,192` for every genome).

No 3× sentence unless the measured cumulative numbers say so, and
then only for the mode it is true of. hmmscan 3× on A, if it appears,
is post-hoc.

---

## Kill rule (locked)

If, at the end of collection A, **cumulative cached wall is not below
50% of cumulative stock wall for hmmscan**, report that the
**diverse-collection headline fails**. Stop talking about 3× on A.
Collection B may still be reported as the clonal / surveillance case.

The Part 2 median model puts A / hmmscan cached at 31,288 s vs stock
91,865 s (34% of stock, cum ~2.94×). That is a prediction, not a
result. The kill rule is on the **measured** totals.

---

## CARC (locked ops; jobs not submitted in this commit)

- Account **`biyik_1165`**, partition `main`, **exclusive** node,
  `--cpus-per-task=32`, `--mem=64G`.
- Submit from the Mac: `carc-transfer` rsync, then `ssh discovery sbatch`
  (same path as `scripts/submit_headline_hmmer.sh`).
- One job per (workload, mode, path). Eight jobs. JSON after every
  genome.
- HMMER 3.4, Pfam-A 38.2, same as job 12377262.

### Predicted exclusive-node wall (N = 4,192 stand-in)

From `hmmer_predicted_speedup.json` → `savings_budget`:

| Job | Pred. wall | `--time` request |
|-----|------------|------------------|
| A cached hmmscan (30) | 8.69 h | **16:00:00** |
| A cached hmmsearch (30) | 2.49 h | **06:00:00** |
| B cached hmmscan (40) | 1.85 h | **04:00:00** |
| B cached hmmsearch (40) | 1.72 h | **04:00:00** |
| A stock sample hmmscan (6) | 5.10 h | **10:00:00** |
| A stock sample hmmsearch (6) | 1.05 h | **03:00:00** |
| B stock sample hmmscan (6) | 5.10 h | **10:00:00** |
| B stock sample hmmsearch (6) | 1.05 h | **03:00:00** |

`--time` = 1.5× predicted wall + 1 h setup, snapped up.

**Predicted exclusive wall, all eight jobs: ~27.2 h.**
**Requested node-hours (sum of `--time`): 56.**

**Josh: approve 56 exclusive node-hours on `biyik_1165` before any
sbatch.** Real `N_i` will move the wall; the 1.5× pad is the slack.
Do not submit if the allocation cannot absorb 56 h.

---

## What this is not

- Not a CARC submit and not a timing run in the commit that adds this
  file.
- Not permission to promote hmmscan to `paper_uses`.
- Not byte-identical tblout.
- Not collection C, and not A genomes 31–100.
- Not STAR.

---

## Addendum 2026-09-27 — same node for stock and cached

Written **before** the paired CARC submit. Do not edit the locked
sections above. This addendum only changes **how** the already-locked
stock samples and cached collection are executed.

**Why.** Separate stock and cached jobs can land on different nodes.
That confounds the speedup with hardware. Stock and cached for the
same workload and mode must share one exclusive node.

**Jobs.** Four jobs, not eight. One job per (collection, mode):

| Job | Collection | Mode | Pred. wall (cached + stock sample) | `--time` |
|-----|------------|------|-------------------------------------|----------|
| `sav_A_scan` | A | hmmscan | 8.69 h + 5.10 h = 13.79 h | **22:00:00** |
| `sav_A_search` | A | hmmsearch | 2.49 h + 1.05 h = 3.54 h | **07:00:00** |
| `sav_B_scan` | B | hmmscan | 1.85 h + 5.10 h = 6.95 h | **12:00:00** |
| `sav_B_search` | B | hmmsearch | 1.72 h + 1.05 h = 2.77 h | **06:00:00** |

`--time` = 1.5× (cached + stock-sample predicted wall) + 1 h setup,
snapped up. Requested node-hours: **47** (under the approved 56).

**Interleave.** For each genome *k* in the locked order: if *k* is a
stock-sample position, run **stock immediately before** the cached
run for that same genome. Other genomes: cached only (predicted stock
as locked). MATCH and the Dune-style audit are unchanged and still
STOP the job.

**Node.** Exclusive `main`, account `biyik_1165`,
`--constraint=epyc-7542` (b22, EPYC 7542 — same model as screen job
12377262 on `b22-16`). Record hostname and `lscpu` in every job
output.

**Resume.** JSON after every genome. Restart skips complete genomes
and reloads the persistent cache. A timeout loses at most one genome.

Everything else in the locked text is unchanged.

---

## Addendum 2026-09-27 — probe_n gap and probe cost P

Locked sections above are unchanged. The queued jobs are not rewritten.

The runner that was submitted uses `PROBE_N = 8`
(`scripts/run_hmmer_savings.py:37`) and the **singleton** subset-invariance
probe that was on disk when those jobs were queued (`427fcbb`, before
batched subset-invariance was implemented). That is **not** the
`probe_n = 500` size that first reaches 0/56 in-scope unsafe-ship in
`results/probe_eval_audit.json`, and it is not the batched probe
pre-registered in `docs/INFERENCE_PROTOCOL.md` (addendum 2026-09-27).

After `agent/probe` landed, the default inference path is batched
(**18** FASTA→table calls: 4 full-probe + 2 halves + 4 quarters + 8
singletons; no alignment extras on tab-delimited tblout). At
`probe_n = 8` singleton is cheaper (12 vs 18). The queued jobs do not
silently pick up that default.

### What the paper reports

1. The jobs used `probe_n = 8`. Report that number next to the probe-eval
   miss rates at the same size (audit mode, in-scope = not F6-env / F6-file).
2. Cumulative savings **without** probe cost *P* (the locked formula:
   sum of per-genome cached times) **and** **with** *P*:

```
P = Σ_j (a + b · n_j)
cumulative cached = P + Σ_i cached_i
```

   *P* is paid once per namespace (once per HMMER mode). `a`, `b` are the
   screen fits. `n_j` is the record count of inference tool call *j*.
3. Source for the with-*P* numbers on **main**:
   `results/hmmer_predicted_speedup_with_probe.json`
   (keys `singleton_8`, `batched_500`, …).
   Do not overwrite `results/hmmer_predicted_speedup.json`.

Two accounts in that file:

| Account | What it models | Calls (main) |
|---------|----------------|--------------|
| `singleton_8` | The queued jobs | 12 |
| `batched_500` | Recommended deployable probe | 18 |

Do not claim the jobs used `probe_n = 500`. Do not silently drop *P*
from a cumulative headline that includes first-infer time.

A pre-merge duplicate prediction (20 batched / 14 singleton-8 calls,
because it added FASTA alignment extras) is archived as
`results/hmmer_predicted_speedup_with_probe_stash.json`
(stash `f723379` / `backup/pre-merge-stash`). See
`docs/PROBE_COST_RECONCILE.md`.

---

## Addendum 2026-09-27 — analysis code pre-committed

Locked sections above are unchanged. This records that the analyzer
existed **before** any savings job dumps or `results/savings_summary.*`.

`scripts/analyze_savings.py` was committed at **`00f9403`**
(`00f9403e55b94dcb16576ef7f63990b0bc64b318`) before any savings
results existed. Tests: `tests/test_analyze_savings.py` (synthetic
runner-schema fixtures only; explicit tmp output paths).

Any later change to that script is a **declared deviation** from this
pre-registration. Do not silently edit the analyzer after job JSON
lands and then treat the new numbers as the locked analysis.

---

## Addendum 2026-09-27 — hmmscan `--tblout` byte MATCH

Locked sections above are unchanged. The queued A/B savings jobs are
not rewritten. This records what `agent/bytes` (`b85859e`) measured
**after** those jobs were queued.

The locked MATCH table claimed **token identity**, not bytes, because
`7eeb40e` / `results/inference_fasta_reuse.json` could not reproduce
HMMER column padding after name substitution.

`results/inference_fasta_reuse_bytes.json` (same 6 Pfam models, N=500,
seed 20260927, renamed genomes) re-ran that reuse under a **generic**
column-layout probe (`docs/INFERENCE_PROTOCOL.md` addendum 2026-09-27):

| Mode | Layout | MATCH now | `byte_match` |
|------|--------|-----------|--------------|
| hmmscan `--cut_ga` | **pinned**, scope **fixed**; names left `fixed_min` 20; numeric columns right | **order**, `match_ws=false` | **true** |
| hmmsearch `-Z 1e6 --domZ 1e6` | **unpinned** (mixed-sample short-name widths are not per-row, per-query, or per-file) | **multiset** + whitespace (`7eeb40e` fallback) | **false** |

Do **not** claim byte identity for hmmsearch `--tblout`. Do **not**
change MATCH on the already-queued A/B jobs after they finish; those
ran on pre-`b85859e` code and stay token identity.

Future runs that import current `acts.fasta_memo` (confirmatory
hmmscan, comparison scoring of new patches) use **byte MATCH for
hmmscan `--cut_ga`** when the layout stays pinned. Whitespace
normalized remains the fallback whenever the probe cannot pin a
layout.


## Addendum 2026-10-03 — first run halted by its own MATCH gate; fix and rerun

Locked sections above are unchanged. This addendum is written **before**
any rerun result exists.

### What happened

All four jobs submitted 2026-09-27 (12394300, 12394301, 12394503,
12394504; git `dc5ead9`) ended FAILED with exit 2 on 2026-09-28. The
record is `results/savings_failed_20260928/` (per-run JSON, `STOP.json`,
Slurm logs, `genome5_diff_summary.json`).

- `A_hmmsearch` (primary) passed MATCH on genomes 1–2 and the audit on
  3–4, then **failed cached MATCH at genome 5** (`GCF_016659085.1`):
  73 of 19,889 `--tblout` lines differed, all only in the trailing
  target-description tokens (index ≥ 18). The gate worked as designed:
  nothing was reported from that run.
- `A_hmmscan` had passed MATCH on its sampled genomes 1, 2, 5, 10, 20 and
  reached genome 22, but stopped because the runner used **one shared
  `STOP.json`** for all four runs. Both B jobs read that file and exited
  in 25 s.

### Root cause (generic; no HMMER-specific code involved)

1. **Description echo misclassified.** `hmmsearch --tblout` echoes each
   FASTA record's description as several whitespace tokens at the end of
   the line. The field-role probe perturbed descriptions to single tokens
   (`DESC_i`), so multi-token descriptions were never exercised, and a
   fallback classified those tokens as PRODUCED. Cached rows replayed the
   description of the genome that first produced them. RefSeq renames
   proteins between annotation releases (e.g. `WP_001278994.1`: cached
   "MULTISPECIES: aldolase", genome 5 "MULTISPECIES: 3-oxo-tetronate
   4-phosphate decarboxylase").
2. **Description never stored.** The cache payload did not record the
   record's description, so description substitution could not run.
3. **STOP not scoped** per (collection, mode).
4. Found while verifying the fix (latent, did not fire on CARC): rows
   rebuilt through the layout path were padded to the contract's widest
   row after a late-key probe, adding trailing spaces under byte MATCH.

### Fix (`acts/fasta.py`, `acts/infer_fasta.py`, `acts/fasta_memo.py`,
`scripts/run_hmmer_savings.py`)

- Perturbed descriptions are multi-word with varying word counts, and one
  in four is empty, so description spans and empty markers are probed.
- Whitespace tables: an echoed description is detected as a span,
  collapsed to one cell for classification and layout, stored with each
  cached record, and replaced from the new input at reassembly (last
  occurrence; the trailing field keeps the inferred byte layout). Tab
  tables replace the description cell by position.
- **New class-level guard at inference:** reassembling every probe record
  from its cached payload with the *perturbed* name and description must
  reproduce the tool's perturbed output, or the tool is refused. This
  catches any field-role misclassification before caching.
- Rows rebuilt through the layout path keep their own width.
- STOP files are `STOP_<collection>_<mode>.json`.
- Guard tests: `test_trailing_multiword_desc_is_passthrough`,
  `test_tab_desc_cell_replaced_on_reuse`,
  `ReassembleCellsWidthTests`, `tests/test_savings_runner_stop.py`.

### Verification before rerun (local, real data, correctness only)

`scripts/repro_savings_desc_stop.py`: collection-A genomes 1–5 in the
locked order, the 78 Pfam models behind the 73 differing lines, each
genome subset to the renamed proteins plus 300 random ones, `verify=full`
on every genome. Results `results/repro_savings_desc_stop_hmmsearch.json`
and `results/repro_savings_desc_stop_hmmscan.json`: all five genomes SHIP
with MATCH in both modes (hmmsearch whitespace multiset; hmmscan byte,
order). Timing on the Mac is not a result.

### Rerun (unchanged protocol except the fix)

- Same workloads, order, flags, stock-sample genomes, audit, kill rule,
  `--time`, exclusive `epyc-7542` nodes, and the analysis code locked at
  `00f9403`.
- Probe pinned to the pre-registered `probe_n = 8` with **singleton**
  subset checks (`SUBSET_MODE`), matching what `analyze_savings.py` prices
  as P. (The library default had become batched after the first
  submission.)
- MATCH types: hmmsearch whitespace multiset (token identity), as locked;
  hmmscan byte when the layout stays pinned (addendum above).
- Fresh caches and output directory. The 2026-09-28 directory on CARC is
  moved aside to `results/savings_failed_20260928/`; no row from the
  failed run is combined with the rerun. The failed run stays in the
  record and is reported as a halted run.
- Already visible in the failed run and flagged here before the rerun:
  stock wall time on genome 1 of A/hmmsearch was 523 s against a model
  prediction of 741 s (42% error; the screen fit used BW25113 at
  N = 4,192). The locked >10% flag applies and will be reported, not
  refit.

---

## Addendum 2026-10-06 — rerun halted by a stale MATCH gate; gate fix

Locked sections above are unchanged. This addendum is written **before**
any rerun result exists. The four jobs below are a halted run. They are
not analyzed here.

### What happened (MEASURED)

Jobs 12629413 (`sav_A_scan`), 12629414 (`sav_A_search`), 12629415
(`sav_B_scan`), and 12629416 (`sav_B_search`) ran at git `f8e3685`
(`f8e36856607547a551391c94c919e29700824b54`) and all ended FAILED, exit
2, on 2026-10-05 (`sacct`: partition `main`, exclusive, constraint
`epyc-7542`; time limits 22 h, 7 h, 12 h, 6 h). Each log
(`results/savings_failed_20261005/logs/sav_*-<jobid>.out`) prints
`inferring table contract (probe_n=8)` and then `STOP_CONTRACT`. The
per-run JSON decision is `STOP_CONTRACT` and `"genomes": []`. The
record is `results/savings_failed_20261005/`.

Each inferred contract
(`results/savings/cache/{A,B}_{hmmscan,hmmsearch}/cache.jsonl.contract.json`
on CARC, left in place) has `decision` OK, reason `probe passed`,
`match` equal to the locked type (order for hmmscan, multiset for
hmmsearch), `layout.pinned` true, and `match_ws` false. The sqlite
caches have **0** rows in `records` (input fingerprints only). No genome
was timed.

### Why `match_ws` false under a pinned layout is still the locked MATCH

`tables_match` (`acts/table.py`) with `match_ws` false compares body
lines for byte equality: list equality when `match` is order
(`bodies_equal`), `Counter` equality when `match` is multiset
(`bodies_multiset_equal`). With `match_ws` true it applies `ws_line`
(`" ".join(line.split())`) first and then the same list or `Counter`
comparison.

`ws_line` is a function of one body line. Therefore:

- equal body-line lists stay equal after `ws_line` (order);
- equal body-line multisets stay equal after `ws_line` is applied
  elementwise (multiset). Two distinct lines that collapse to one
  whitespace-normalized line can only make the whitespace relation
  *weaker*. They cannot make a true byte comparison fail the whitespace
  comparison of the same type.

The converse is false, and it is not claimed: whitespace equality does
not imply byte equality. The two match types are not interchangeable.
Order byte equality does not imply multiset whitespace equality of a
*different* pair of texts, and a wrong `match` value is still refused.

Inference sets `match_ws = (delim != "tab") and not layout.pinned` when
the description is absent or a trailing span (`acts/infer_fasta.py`).
A pinned layout is exactly the case that demands the stricter byte
check. The probe on these four contracts passed that check, so the
locked whitespace-normalized MATCH of the same type holds on the probe
as well.

### Cause

The gate in `scripts/run_hmmer_savings.py` (and the same condition in
`scripts/confirm_run.py`) stopped unless `contract.match_ws` was true.
That condition is the pre-`b85859e` whitespace-only MATCH. The
2026-09-27 byte-MATCH addendum above already said a pinned layout uses
byte MATCH. The gate was not updated, so it rejected a contract that is
stricter than the locked whitespace MATCH. The Mac repro
(`scripts/repro_savings_desc_stop.py`) never calls this gate.

### Fix

One predicate, `acts.infer_fasta.contract_satisfies(contract, expected_match)`,
is true iff `contract.match == expected_match` and (`contract.match_ws`
or the layout is pinned). Both runners call it. They do not keep a
second copy of the condition. Guard: `tests/test_contract_gate.py`,
including the trimmed CARC hmmsearch contract from job 12629414
(`tests/fixtures/savings/A_hmmsearch.contract.json`; `traced_files`
paths removed).

hmmsearch now runs under **byte MATCH** when its contract is pinned.
On this rerun all four cached contracts are pinned, so both modes run
under byte MATCH. The paper still claims only **token identity** for
hmmsearch unless byte MATCH holds on every genome. Do not describe the
hmmsearch `--tblout` result as byte-identical from the contract alone.

### Pre-registered for the rerun

- Same workloads, order, flags, stock-sample genomes, audit, kill rule,
  `--time`, exclusive `epyc-7542` nodes, partition `main`, and the
  analysis code locked at `00f9403`. No savings numbers are computed in
  the session that resubmits.
- The contracts and their sqlite files stay. They were inferred at
  `f8e3685` and the inference code is unchanged since that commit, so
  they are reused. `ensure_contract` loads the cached contract and does
  not probe again. MEASURED job elapsed on 2026-10-05, which ended at
  the contract gate with no genome rows: hmmsearch A `00:27:12`,
  hmmsearch B `00:27:25` (`sacct`). The resubmit skips that probing,
  about 27 minutes on each hmmsearch job.
- If a pinned contract fails byte MATCH mid-run, the run halts with
  `STOP_MATCH`. It is not retried under whitespace. Any rerun that
  would proceed with an **unpinned** contract requires a new addendum
  before it is submitted. No silent fallback.
- The halted JSON, `STOP_*.json`, logs, and `GIT_HASH` are archived
  under `results/savings_failed_20261005/` and are not combined with
  the rerun. The failed run stays in the record.

---

## Addendum 2026-10-06 — hmmscan byte layout refuted by archived full outputs; pin only unique width rules

Locked sections above are unchanged. This addendum is written **before**
the hmmscan resubmit. It does not use any output of jobs 12739162,
12739229, 12739228, or 12739230.

### Cause

`acts.table` layout inference pinned a width rule the probe did not
uniquely identify. When `fixed_min`, per-query `max_value`, and
per-file `max_value` all explained a column, it kept `fixed_min`.

HMMER `p7_tophits_TabularTargets` sets the target-name width to
`ESL_MAX(20, p7_tophits_GetMaxNameLength(th))` on the hit list it is
given (`src/p7_tophits.c`). hmmscan calls that once per query, so the
width is per query. The cached hmmscan contracts
(`results/savings/cache/{A,B}_hmmscan/cache.jsonl.contract.json` on
CARC, inferred with `probe_n` 8, scope `fixed`, column 0 `fixed_min`
20) never saw a model name longer than 20, so every rule fit and the
code pinned the floor.

### Evidence (archived 2026-09-28 stock, not this run)

Re-rendered on the Mac with `acts.table.render_table` and the cached
A hmmscan layout. Bodies only. Counts are MEASURED and recorded in
`results/hmmscan_layout_preflight.json`.

| File | Rows | Byte mismatches under the pinned floor |
|------|------|----------------------------------------|
| `results/savings_failed_20260928/tblout/A_hmmscan_01_stock.tbl` | 9,397 | 22 |
| `A_hmmscan_02_stock.tbl` | 8,177 | 22 |
| `A_hmmscan_05_stock.tbl` | 8,333 | 20 |
| `A_hmmscan_10_stock.tbl` | 9,098 | 21 |
| `A_hmmscan_20_stock.tbl` | 9,251 | 37 |

On genome 1 the 22 rows are 11 queries. Every query's target-name
field width equals `max(20, longest target name in that query)`
(0 exceptions on that file).

The same check on `A_hmmsearch_{01,02,05}_stock.tbl`, split with the
cached contract's `n_cols` so the description is one cell, is **0
mismatches over 62,262 rows**. hmmsearch keeps that pinned contract.

### Rule

A whitespace/tab layout is pinned only when every column's width rule
is the only rule the probe does not refute. Two rules that render the
same bytes on every extension the probe's groups allow (a max-value
rule whose groups never contain two cell lengths, against `fixed_min`
with the same floor) are one rule. If more than one rule still fits,
the layout is unpinned and the reason is stored on the contract.
MATCH is then the whitespace-normalized relation of the locked match
type (`order` for hmmscan).

hmmscan therefore uses its **locked whitespace MATCH** (order +
`split()`) unless a probe uniquely identifies the layout. It does not
keep the byte MATCH from the 2026-09-27 addendum when the probe cannot
tell a fixed floor from a per-query max. hmmsearch is unchanged: its
cached pinned contract stays, and this resubmit does not touch it.

Re-inferring the layout from the five archived A hmmscan bodies leaves
it unpinned (the accession column is still explained by more than one
rule). Preflight under that contract's whitespace MATCH is 0, 0, 0, 0,
0 mismatches. That check is `acts.infer_fasta.preflight_stock_outputs`,
called from `scripts/run_hmmer_savings.py` after the contract gate and
before any genome run. A mismatch stops with `STOP_PREFLIGHT`.

### Resubmit

Cancel the held hmmscan jobs only. Archive the old hmmscan contracts
under `results/savings_failed_20261005/`, then delete only
`results/savings/cache/{A,B}_hmmscan/`. Stage this commit on a separate
CARC code path. Do not replace the checkout, `results/savings/GIT_HASH`,
or caches that 12739228 and 12739230 read. Resubmit A and B hmmscan
with the same resources (exclusive `epyc-7542`, 22 h and 12 h). Set
`ACTS_GIT_HASH_FILE` per job. Point preflight at the archived tblout
directory.

---

## Addendum 2026-10-08 — hmmsearch outcome

Locked sections above are unchanged. This records jobs 12739228 and
12739230 after they finished. The analyzer is still the copy locked at
`00f9403`; it was not edited to produce these numbers.

### Locked analyzer

Inputs: `results/savings_20261006/A_hmmsearch.json` (job 12739228,
`b22-04`, exclusive `epyc-7542`, elapsed 03:39:04, exit 0) and
`results/savings_20261006/B_hmmsearch.json` (job 12739230, `b22-05`,
exclusive `epyc-7542`, elapsed 03:15:02, exit 0). Both ran git
`5245c29a64896e14cdb8ba3b2a0e94166cb5ae38`, Python 3.11.9, and HMMER
3.4 built on the node with gcc 13.3.0. Logs:
`results/savings_20261006/sav_A_search-12739228.{out,err}` and
`sav_B_search-12739230.{out,err}`.

`scripts/analyze_savings.py --jobs` those two files wrote
`results/savings_summary.json`, `results/savings_summary.md`, and
figures 25–28. The run found no MATCH, audit, or STOP failures. A is
30/30 and B is 40/40. The kill rule is A/hmmscan and was not evaluated;
hmmscan dumps were not in this analysis.

Locked cumulative wall speedup, sampled stock measured and every other
genome imputed as `a + b·N_i`:

| Collection | Without P | With singleton_8 P |
|------------|----------:|-------------------:|
| A | 2.740× | 2.233× |
| B | 6.847× | 4.900× |

The analyzer printed a 3× sentence for hmmsearch because the B total is
6.847×. A is 2.740×. That sentence describes the locked imputed total.
It is not the paper number.

### Fit-error flag

The locked >10% flag fired at every sampled genome. Measured stock wall
was 384–527 s. `a + b·N_i` predicted 619–741 s. The flag stands. The
fit is not replaced.

### POST-HOC sensitivity

Computed after seeing the fit-error flag, by
`scripts/savings_sensitivity.py`, which reads only the two run JSONs.
Output: `results/savings_sensitivity.json`. This is not the locked
analysis.

Formula: `r = sum(sampled measured stock) / sum(sampled fitted stock)`.
Sampled stock stays measured. Unsampled stock becomes `r` times its
fitted value. Cached wall and singleton_8 `P` stay as in the locked
analyzer. Assumption: the sampled ratio represents the unsampled
genomes.

| Collection | r | Without P | With P |
|------------|--:|----------:|-------:|
| A | 0.627662232339967 | 1.8561541144638773× | 1.5126488173514772× |
| B | 0.6052815600933489 | 4.4038095881881× | 3.1519938702250814× |

Rounded as 1.86× (1.51× with P) and 4.40× (3.15× with P).

The paper's headline will use measured stock wherever a measurement
exists. It will not use the locked imputation unless this correction is
printed beside it.

### Pre-registered stock completion

Written before the stock-completion submit. Report the result whatever
it is.

Measure stock hmmsearch on every genome in
`results/hmmsearch_stock_tasks.json` (58 tasks: A positions that were
not sampled, then B; indexes 0–57). Same stock argv as
`scripts/run_hmmer_savings.py`: `--cpu 32 --noali -Z 1000000 --domZ
1000000 --tblout`. Same HMMER 3.4 build method (gcc 13.3.0, SSE, prefix
install on the node) and the same Pfam-A file the savings jobs staged
from `pipeline/data/hmmer/` on the data tree. Same node class:
exclusive `epyc-7542`, partition `main`, account `biyik_1165`, 32 CPUs,
64 GB.

One genome per array task. A build job on the same node class installs
HMMER and presses Pfam once; the array starts `afterok` that job so
the 58 tasks do not each compile. Code and `ACTS_GIT_HASH_FILE` live
on `/project2/biyik_1165/jjt_373/csci270-star/acts-hmmsearch-stock-20261008/`,
not in the savings checkout and not in `results/savings/GIT_HASH`.
Each task writes `results/hmmsearch_stock/{collection}_{position}.json`
with `kind = hmmsearch_stock_completion`. A finished successful JSON is
not overwritten.

Requested time: build `01:00:00`, each genome `00:45:00` (44.5
node-hours requested). The sampled measurements in the two run JSONs
are 384–527 s, so the expected measurement is about 6–9 node-hours plus
one build. The pad is the slack. Do not change the node type in the
queue without a later addendum.

When all 58 JSONs exist, `scripts/analyze_savings_measured.py` replaces
each imputed stock wall with the new measurement and reports cumulative
speedup with and without singleton_8 `P`. That fully measured pair is
the paper number. No threshold is applied after the run.

### Submit record

The text above was committed at `465edf5` before `sbatch`. Submitted
2026-10-08 from the Mac onto
`/project2/biyik_1165/jjt_373/csci270-star/acts-hmmsearch-stock-20261008/`.
`GIT_HASH` there is `465edf548ca68e3e6a72824b8bac056b2c5300c1`.

| Job | Name | State at submit | Start |
|-----|------|-----------------|-------|
| 12862906 | `stock_hmm_build` | PENDING, Reason=Priority | Unknown |
| 12862907, tasks 0–57 | `stock_hmm_measure` | PENDING, `afterok:12862906` | Unknown |

`squeue --start -A biyik_1165` gave no start time for either job. Another
pending job on the account, 12850670, was estimated at
2026-10-11T04:28:41. The node type was not changed.
