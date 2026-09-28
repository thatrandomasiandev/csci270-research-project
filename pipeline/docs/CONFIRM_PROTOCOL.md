# Confirmatory hmmscan run (pre-registered)

Written **2026-09-27, before any new FASTA download and before any
timing**. Do not edit the locked sections after seeing
`results/confirm_predictions.json` or any job dump. No CARC job in the
commit that adds this file. No local HMMER timing as a substitute.

Predecessor: `docs/SAVINGS_PROTOCOL.md` (hmmscan chosen after the
headline screen — a **declared deviation** from
`docs/HEADLINE_SCREEN.md` `paper_uses = hmmsearch`). This file turns
that post-hoc selection into a **confirmed prediction** on data that
was never used to pick the mode.

Locked inputs (read, not rewritten):

- `results/headline_screen.json` — *a*, *b*, *w* per mode. No refitting.
- `results/recurrence_accessions.json` — collections A, B, C accessions.
- `results/recurrence_curves.json` — collection C seed-20260926 ordering.
- `results/hmmer_predicted_speedup_with_probe.json` — probe-cost *P*
  formula (`singleton_8`).
- `scripts/predict_hmmer_speedup.py`, `scripts/predict_hmmer_probe_cost.py`
  — formulas, imported, not edited.
- `scripts/run_hmmer_savings.py` — MATCH / audit / `probe_n` / JSON
  schema, imported, not edited.

---

## Why this exists

`docs/SAVINGS_PROTOCOL.md` runs hmmscan as **post-hoc** on collections
A and B. A 3× sentence on those collections is not a confirmation.

This experiment pre-registers **hmmscan `--cut_ga` as PRIMARY** on a
**new *E. coli* draw** (never in A or B) and on the already-locked
**collection C prefix**. Predictions are locked from MD5 `m(k)` plus
the screen fit **before** any stock or cached wall is measured.

---

## Primary (locked)

**Primary = hmmscan `--cut_ga`.** That is the point of this
confirmation.

- hmmsearch is **not** primary here and is **not scored**.
- Do not add hmmsearch as a co-primary after seeing numbers.
- If hmmsearch walls are recorded at all, label them
  `secondary / not scored`. This protocol does **not** submit
  hmmsearch jobs.

Same hmmscan flags as the screen and the savings runner
(`headline_screen.json` argv template; `scripts/run_hmmer_savings.py`):
`--cpu 32`, `--cut_ga`, `--noali`, `--tblout`. HMMER 3.4, Pfam-A 38.2
(job 12377262).

---

## Collection confirm_E — new diverse *E. coli* (locked)

Thirty random RefSeq complete *E. coli* genomes. **Seed `20260927`.**
That is **not** the recurrence seed `20260926`.

Eligibility, strain collapse, and protein-FASTA rule are **the same
as collection A** in `docs/RECURRENCE_PROTOCOL.md` (Eligible row +
strain name + protein URL + size cap). Cite that file; do not
reinvent the filters. In brief, a row is eligible when:

- `assembly_accession` starts with `GCF_`
- `version_status` = `latest`
- `assembly_level` = `Complete Genome`
- `genome_rep` = `Full`
- `ftp_path` is not `na` / empty
- protein FASTA is present (HTTP HEAD of
  `{ftp_path}/{basename}_protein.faa.gz` succeeds; rewrite `ftp://` →
  `https://`)

**Exclusions** (drop before sampling):

1. Every accession in `results/recurrence_accessions.json`
   collections **A** and **B**.
2. The K-12 / BW25113 cluster, same regex as
   `docs/RECURRENCE_PROTOCOL.md`:
   `(?i)(k-?12|mg1655|w3110|bw25113)` on `organism_name`, strain, or
   isolate.

**One per strain**, same collapse as A (`one_per_strain` in
`scripts/run_recurrence_curves.py`): among rows that share a
normalized strain, keep the lexicographically smallest accession;
empty-strain rows stay unique.

Then:

1. Sort the remaining unique-strain list by `assembly_accession`.
2. Draw 30 **without replacement** with
   `random.Random(20260927).sample(list, 30)`.
3. Re-sort the sample by accession for a stable on-disk order
   (same as A).
4. If a sampled protein URL fails HEAD, replace from the remaining
   pool in accession order (smallest first) until 30 succeed or the
   pool is exhausted. Exhaustion → STOP and ask Josh. Do not shrink
   *K*.
5. **Run order** (the confirmatory ordering, one permutation):
   `random.Random(20260927).sample(range(30), 30)` into the
   accession-sorted sample.

Prefer the existing *E. coli* assembly summary at
`data/recurrence/assembly_summary_ecoli.txt` (read-only via the
`data/` symlink). Do not re-fetch the summary if that file is
present. New protein FASTAs go under `pipeline/data_confirm/`
(gitignored). Never write into `data/`.

**Size cap.** Sum HTTP `Content-Length` (unknown → 2 MiB, same as
`docs/RECURRENCE_PROTOCOL.md`). If the planned **new** download would
exceed 1 GiB, **stop and ask Josh**. Do not continue.

---

## Collection confirm_C — *S. aureus* prefix (locked)

Not a new sample. Collection C is the locked *S. aureus* set in
`results/recurrence_accessions.json` (`id = C_saureus`).

**Run order:** the first **30** indices of
`results/recurrence_curves.json` → `collections.C.orderings[0]`
(seed-**20260926** ordering, the first of the 20). Locked prefix:

```
4, 2, 1, 37, 14, 32, 11, 40, 48, 7,
23, 31, 15, 45, 8, 26, 3, 19, 12, 18,
44, 24, 36, 22, 5, 6, 33, 16, 10, 43
```

Do not re-sample C. Do not use a 20260927 permutation of C. FASTAs
already on disk under `data/recurrence/C/` are **read**, not copied
into `data_confirm/` unless a file is missing (missing → STOP and
ask; do not write into `data/`).

---

## MATCH, audit, probe, stock sample, CARC (cited, not redefined)

All of the following are **the same objects** as
`docs/SAVINGS_PROTOCOL.md`. This file does not change them.

| Object | Lock | Source |
|--------|------|--------|
| MATCH, hmmscan `--cut_ga` | **order** + whitespace-normalized (`split()`) | SAVINGS_PROTOCOL.md “MATCH”; `inference_fasta_reuse.json` → `scan_cut_ga` |
| MATCH, hmmsearch (secondary only) | **multiset** + whitespace-normalized | same table; not scored here |
| Dune-style audit | seed **20260927**, 2% of cache hits, ≥ **20 NON-EMPTY** per genome when that many exist (else all); EMPTY hits do not count toward the floor; mismatch → STOP | SAVINGS_PROTOCOL.md “Correctness” |
| `probe_n` | **8** | `scripts/run_hmmer_savings.py` (`PROBE_N = 8`); SAVINGS_PROTOCOL.md addendum 2026-09-27 |
| Stock-sample positions (30-genome collection) | **1, 2, 5, 10, 20, 30** (1-based, same order as cached) | SAVINGS_PROTOCOL.md “Stock baseline”, workload A |
| Stock for other genomes | `stock̂_i = a + b · N_i` from locked screen fit; flag if any sampled \|error\| / measured exceeds 10% | same section |
| Cached path | one persistent cache file per mode; namespace per `docs/CACHE_KEY_PROTOCOL.md`; JSON **after every genome** | SAVINGS_PROTOCOL.md “Cached path” |
| Same node | stock sample immediately before cached for that genome; exclusive node | SAVINGS_PROTOCOL.md addendum 2026-09-27 |
| CARC | account **`biyik_1165`**, partition `main`, **exclusive**, `--constraint=epyc-7542`, `--cpus-per-task=32`, `--mem=64G` | SAVINGS_PROTOCOL.md; copy style from `jobs/hmmer_savings.job` (do not edit that file) |

Resume: JSON after every genome; restart skips complete genomes and
reloads the persistent cache. Collection ids in dumps are
`confirm_E` and `confirm_C` so they cannot be confused with A/B.

---

## Prediction procedure (locked; no refitting)

Compute `m(k)` on each confirmatory collection **along the locked run
order** (one permutation, not the 20-ordering median). Key is the
same as `docs/RECURRENCE_PROTOCOL.md`:

> MD5 of uppercase AA, whitespace ignored, `*` stripped, headers ignored.

`m(k)` is the miss of genome *k*+1 given genomes `1…k` of that order
(sets of distinct keys). Genome 1 is all misses.

Then predicted per-genome and cumulative speedup from the **locked**
*a*, *b*, *w* in `results/headline_screen.json` and probe cost *P*,
**no refitting**. Formulas are those in
`scripts/predict_hmmer_speedup.py` and
`scripts/predict_hmmer_probe_cost.py` /
`results/hmmer_predicted_speedup_with_probe.json`:

```
stock_i     = a + b · N_i
cached_1    = stock_1
cached_{i>1}= a + b · m(i-1) · N_i + w
P           = Σ_j (a + b · n_j)     # singleton_8: 12 calls, probe_n = 8
                                    # sizes (8,8,8,8,1,1,1,1,1,1,1,1)
cum_stock(k)         = Σ_{i=1..k} stock_i
cum_cached(k)        = Σ_{i=1..k} cached_i
cum_cached_with_P(k) = P + cum_cached(k)
cum_speedup(k)       = cum_stock(k) / cum_cached(k)
cum_speedup_with_P(k)= cum_stock(k) / cum_cached_with_P(k)
```

`N_i` is the proteome record count of genome *i* (same object as
`N_i` in `scripts/run_hmmer_savings.py`). *a*, *b*, *w* are the
hmmscan screen fit. Do not refit. Do not silently drop *P*.

Also record the screen-N = 4,192 stand-in series (the Part 2
convention) as a sidecar; the **confirmation uses per-genome `N_i`**.

Lock all of the above in `results/confirm_predictions.json` **before
any timing**. Commit message: `Lock confirmatory predictions.`

---

## Confirmation criteria (stated now, before seeing numbers)

Evaluated at **k = 30** on **hmmscan** only, separately per arm
(`confirm_E`, `confirm_C`). hmmsearch is not scored.

Let `pred` be the locked `cum_speedup_with_P` at k = 30.
Let `meas` be the measured
`cum_stock / (P + Σ cached_i)` at k = 30, using the same locked *P*
(not a new probe-time measurement).
Let `cached_frac = (Σ cached_i) / cum_stock` at k = 30
(collection run only; *P* is not in this fraction — same object as
the savings kill rule).

**The confirmation succeeds on an arm if and only if both hold:**

1. **Cumulative measured speedup (with *P*) is within ±20% of
   predicted:** `|meas / pred − 1| ≤ 0.20`.
2. **Cached below 50% of stock by k = 30:** `cached_frac < 0.50`.

Fail either → that arm is **not confirmed**. Do not loosen the band.
Do not drop *P* from criterion 1 after seeing numbers. Do not promote
a passing secondary hmmsearch number into the confirmation.

---

## Outputs (locked)

| Path | When | Contents |
|------|------|----------|
| `docs/CONFIRM_PROTOCOL.md` | this commit | this file |
| `results/confirm_predictions.json` | after FASTAs + `m(k)`, before timing | accessions, run order, `m(k)`, locked *a,b,w,P*, per-genome and cumulative predictions, criteria |
| `docs/CONFIRM_PLAN.md` | after predictions, before sbatch | node-hour estimates for Josh |
| `jobs/confirm*.job`, `scripts/submit_confirm.sh` | same | exclusive epyc-7542 jobs; `--dry-run` default |
| `results/confirm_*` job dumps | CARC, later | JSON after every genome; ids `confirm_E` / `confirm_C` |

FASTAs under `data_confirm/` stay gitignored.

---

## What this is not

- Not a CARC submit and not a timing run in the protocol commit.
- Not local HMMER wall as a stand-in for the exclusive-node job.
- Not permission to keep hmmsearch as primary, or to add it as
  co-primary.
- Not collections A or B, and not a redraw of C.
- Not a refit of *a*, *b*, *w*.
- Not STAR.

---

## Jobs (ops lock; not submitted in this commit)

One paired job per arm, hmmscan only, same interleave as the savings
addendum (stock sample immediately before cached on the same exclusive
`epyc-7542` node). Copy style from `jobs/hmmer_savings.job`. Reuse
`scripts/run_hmmer_savings.py` by **import**. Do not edit that file.

`--time` = 1.5× (cached + stock-sample predicted wall) + 1 h setup,
snapped up, same helper as `predict_hmmer_speedup.ceil_hours`.
Concrete hours go in `docs/CONFIRM_PLAN.md` after
`results/confirm_predictions.json` exists.

**Do not sbatch until Josh approves the node-hours in that plan.**
