# Probe miss-rate at `probe_n = 8`

Addendum `docs/PROBE_EVAL_PROTOCOL.md` (2026-10-10), pre-registered at
`9e978af` before this run. Seed 20260927. `N_rec` = 2500. Subset mode
**singleton** (`scripts/run_hmmer_savings.py` `PROBE_N` / `SUBSET_MODE`).
JSON: `probe_eval_n8.json`.

Provenance in that JSON: git `9e978af`, `git_dirty` false, host
`Joshuas-MacBook-Pro-3.local`, Python 3.11.9, finished
`2026-10-10T20:42:27Z`. Mac. No `strace`. No CARC.

This is one new size. The locked sizes stay in `probe_eval.md` and
`probe_eval_audit.md`. Their canonical denominator stays **224**. This
file’s in-scope denominator is the same per-size slice, **56**
(7 × 4 × 2, excluding F6-env and F6-file).

Priced schedule, PROJECTED from `acts.predict.inference_call_sizes`:
`[8, 8, 8, 8, 1, 1, 1, 1, 1, 1, 1, 1]` (12 calls). Every control measured
`tool_calls = 12` with `subset_mode = singleton` and `probe_n = 8`.

## Next to the locked sizes

| `probe_n` | Full in-scope | Audit in-scope (*q* = 0.02) | Source |
|-----------|---------------|-----------------------------|--------|
| **8** | **2/56** | **4/56** | MEASURED, this file |
| 50 | 1/56 | 3/56 | `probe_eval.md`, `probe_eval_audit.md` |
| 200 | 0/56 | 1/56 | same |
| 500 | 0/56 | 0/56 | same |
| 2000 | 0/56 | 0/56 | same |
| locked total | **1/224** | **4/224** | those files; not recomputed here |

## Headline

| Metric | `--verify full` | `--verify audit` |
|--------|-----------------|------------------|
| Canonical in-scope unsafe-ship | **2/56** | **4/56** |
| Overall unsafe-ship | 10/72 | 20/72 |
| JSON `report.in_scope_*` (excl. F6-env only) | 2/64 | 12/64 |
| F6-env | 8/8 | 8/8 |
| F6-file | 0/8 | **8/8** |
| False-refuse | **0/5** | **0/5** |

The audit 12/64 is the four in-scope cells plus eight F6-file cells.
Canonical in-scope does not include F6-file.

Full cells: **vcf F4, *p* = 0.1** and **vcf F4, *p* = 0.01**. Audit cells:
those two, plus **vcf F3, *p* = 0.01** and **fasta F4, *p* = 0.001**.
Each SHIPed at `tool_calls = 12`, `subset_mode = singleton`, `probe_n = 8`.

## Per class (8 cells = 2 formats × 4 *p*)

### Full verification

| Class | Input-1 refuse | First probe (count) | Unsafe-ship |
|-------|----------------|---------------------|-------------|
| F1 | 8/8 | determinism 3, MATCH 5 | 0 |
| F2 | 7/8 | shuffle 6, MATCH 1 | 0 |
| F3 | 6/8 | subset 3, MATCH 3 | 0 |
| F4 | 4/8 | perturbation 2, MATCH 2 | **2** |
| F5 | 6/8 | MATCH 6 | 0 |
| F6-env | 0/8 | — | **8** |
| F6-file | 8/8 | MATCH 8 | 0 |
| F7 | 8/8 | determinism 3, MATCH 5 | 0 |
| F8 | 5/8 | shuffle 3, MATCH 2 | 0 |

vcf F3 at *p* = 0.01 and *p* = 0.001 SHIPed the probe and then input 2
returned `REFUSE_MATCH` (miss-batch *N* ≠ file *N*). They are not
unsafe ships.

### Deployed audit

| Class | Input-1 refuse | Extra catch | Unsafe-ship |
|-------|----------------|-------------|-------------|
| F1 | 3/8 | audit 3 | 0 |
| F2 | 6/8 | — | 0 |
| F3 | 3/8 | audit 1 | **1** |
| F4 | 2/8 | audit 1 | **3** |
| F5 | 3/8 | audit 3 | 0 |
| F6-env | 0/8 | — | **8** |
| F6-file | 0/8 | — | **8** |
| F7 | 3/8 | audit 2 | 0 |
| F8 | 3/8 | audit 1 | 0 |

F5’s input-1 refuses on the audit column are `REFUSE_MATCH` (the miss
path, not a full-file stock compare). Counted in the JSON `by_probe`
as `match`.

## What the empty-probe formula did

PROJECTED \((1-p)^8\) is 0 at *p* = 1, 0.4305 at 0.1, 0.9227 at 0.01,
0.9920 at 0.001. The outcome against that projection is the 2026-10-10
outcome addendum in `docs/PROBE_EVAL_PROTOCOL.md`. Short form: F4 is
the miss on both columns; the audit adds one F3 and one fasta F4; full
MATCH catches F6-file on this Mac and the audit does not.

Refuse contracts in `schedule.subset_mode_mismatches` are stamped
`batched` by `prepare_contract`’s default after a singleton infer.
SHIP contracts are not. vcf F3 at *p* = 1 metered 11 calls (eight
singletons after the three preamble runs).
