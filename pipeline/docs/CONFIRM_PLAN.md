# Confirmatory hmmscan CARC plan — 2026-09-27

Written **after** `results/confirm_predictions.json` was locked and
**before** any sbatch. Not a timing claim. **Do not sbatch from the
session that adds this file.** No SSH, no `sbatch`, no `scp`.

Protocol: `docs/CONFIRM_PROTOCOL.md`.
Predictions: `results/confirm_predictions.json`.
Jobs: `jobs/confirm_scan.job` via `scripts/submit_confirm.sh --dry-run`.

Account **`biyik_1165`**, partition `main`, exclusive
`--constraint=epyc-7542`, `--cpus-per-task=32`, `--mem=64G`. Same node
for stock sample and cached (savings addendum 2026-09-27). HMMER 3.4,
Pfam-A 38.2, `probe_n = 8`. PRIMARY = **hmmscan `--cut_ga`**. hmmsearch
is not submitted.

`--time` uses `predict_hmmer_speedup.ceil_hours`: **1.5 × (cached +
stock-sample predicted wall) + 1 h setup**, snapped up.

Nothing in this file is a measured speedup.

---

## What this is not

- Not a submit. Not permission to open SSH or Duo.
- Not a rewrite of `docs/SAVINGS_PROTOCOL.md` or of
  `jobs/hmmer_savings.job` / `scripts/run_hmmer_savings.py`.
- Not hmmsearch (secondary / not scored).
- Not collections A or B.

---

## Locked predictions (hmmscan PRIMARY)

Per-genome `N_i` from the downloaded proteomes. *a*, *b*, *w* from
`results/headline_screen.json`. *P* = singleton_8 (412.4 s). `m(k)`
along the locked run order.

| Arm | m(k=1) | m(k=10) | m(k=29) | cum speedup | with *P* | cached/stock | cached wall | stock sample | combined |
|-----|--------|---------|---------|-------------|----------|--------------|-------------|--------------|----------|
| confirm_E | 0.718 | 0.057 | 0.234 | 2.99× | 2.96× | 0.334 | 9.66 h | 5.74 h | 15.40 h |
| confirm_C | 0.620 | 0.154 | 0.352 | 3.19× | 3.12× | 0.313 | 5.08 h | 3.26 h | 8.34 h |

confirm_E `--time` snaps **36:00:00** because 1.5×15.40 h + 1 h = 24.10 h
and `ceil_hours` jumps 24 → 36. Combined wall itself is 15.4 h.

---

## Jobs (not submitted)

| Job name | Collection | Mode | Pred. wall (cached + stock) | `--time` | Est. actual |
|----------|------------|------|------------------------------|----------|-------------|
| `conf_E_scan` | confirm_E | hmmscan PRIMARY | 15.40 h | **36:00:00** | **15.4 h** |
| `conf_C_scan` | confirm_C | hmmscan PRIMARY | 8.34 h | **16:00:00** | **8.3 h** |

JSON after every genome under `results/confirm/`. Resumable.

**Requested exclusive node-hours (sum of `--time`): 52.**
**Predicted exclusive wall, both jobs: ~23.7 h.**

**Josh: approve 52 exclusive node-hours on `biyik_1165` before any
sbatch.** Do not submit if the allocation cannot absorb 52 h. After
approval, from the Mac: `bash pipeline/scripts/submit_confirm.sh --submit`
(this file's commit only ran `--dry-run`).

Reuse Pfam-A already on
`/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/hmmer/` if the
savings jobs have staged it. confirm_E FASTAs rsync from
`pipeline/data_confirm/E/` (gitignored). confirm_C FASTAs rsync from
`pipeline/data/recurrence/C/` (already on disk; do not rewrite).

---

## Confirmation criteria (verbatim from the protocol)

Evaluated at k = 30 on hmmscan only, separately per arm:

1. Cumulative measured speedup (with *P*) is within ±20% of predicted:
   `|meas / pred − 1| ≤ 0.20`.
2. Cached below 50% of stock by k = 30: `cached_frac < 0.50`.
