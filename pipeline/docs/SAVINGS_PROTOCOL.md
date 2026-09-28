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

