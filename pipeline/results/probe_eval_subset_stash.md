# Probe eval — batched vs singleton (pre-merge stash snapshot)

**Not the committed main eval.** Source: `stash@{0}` = `f723379`
(`backup/pre-merge-stash`), untracked parent `stash@{0}^3`.
Main keeps `probe_eval_subset_batched.json` /
`probe_eval_subset_singleton.json` from `agent/probe` (`e24370f`).
See `docs/PROBE_COST_RECONCILE.md`.

Protocol addendum: `docs/INFERENCE_PROTOCOL.md` (commit `427fcbb`).
`--verify audit`, seed 20260927. This snapshot’s in-scope = not F6-env /
F6-file (**56 cells per `probe_n`**, **224** total) — the locked audit
denominator. Main’s JSON uses **256**.

JSON: `probe_eval_subset_compare_stash.json`.
Figures: `22_probe_eval_subset_batched_stash.png`,
`23_probe_eval_subset_singleton_stash.png`.

## In-scope unsafe-ship (stash)

| `probe_n` | batched | singleton |
|-----------|---------|-----------|
| 50 | 3/56 | 3/56 |
| 200 | 1/56 | 1/56 |
| 500 | 0/56 | 0/56 |
| 2000 | 0/56 | 0/56 |

Overall in-scope: **4/224** both. False-refuse: **0/20** both.
F3 probe-caught: 4, 7, 7, 7 of 8 at those sizes — **identical**.
The four in-scope misses are F4 (field-role) plus one F3 at `probe_n=50`,
*p*=0.01 — not a subset-mode gap.

All-cell unsafe-ship is 67/288 batched vs 68/288 singleton; the extra
cell is F6-env (out of scope).

## Tool calls (first infer, stash)

All-cell means include early refuses (determinism at 2 calls).
Complete = input-1 finished infer (`SHIP` / `REFUSE_AUDIT` / `REFUSE_MATCH`).

| `probe_n` | batched all / complete / max | singleton all / complete / max |
|-----------|------------------------------|--------------------------------|
| 50 | 14.2 / 18.6 / 24 | 39.5 / 54.6 / 60 |
| 200 | 12.6 / 19.1 / 24 | 121.9 / 205.1 / 210 |
| 500 | 12.3 / 19.2 / 24 | 280.3 / 505.2 / 510 |
| 2000 | 11.6 / 19.5 / 24 | 1024.2 / 2005.5 / 2010 |

Batched max stays 24 at every `probe_n`. Singleton complete path is
`≈ 4 + probe_n`.
