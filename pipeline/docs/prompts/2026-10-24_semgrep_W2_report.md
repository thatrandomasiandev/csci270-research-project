# Semgrep W2 overnight report (2026-10-24)

## Branch / SHA

| | |
|---|---|
| Branch | `exp/semgrep-domain` |
| Tip (this report) | `5d6451674854bd3362dbfb1a9b8642ee92ea5bb7` |
| Prior tip | `f41ba82d3bc970845abecf797ba0e674fc2ce620` (column-lock + IC2 tab split + timeout addendum) |
| Worktree | `../ACTS-semgrep` |

## What ran

1. Locked Semgrep `--timeout 0 --timeout-threshold 0 --max-memory 0` into run argv; dated addendum in `SEMGREP_PILOT.md`.
2. Re-measured errors-dependence on 10 half-rule subsets, seed **20261326**, corpus `records.txt`.
3. Diagnosed P2 refuses; fixed TARE empty-batch json-records column lock + IC2 tab-aware split; tests added.
4. Re-ran positive controls: P2 min-delta, P2 full OWASP pair, seed **20261327** pair — all with timeout-0 argv.
5. Wrote CARC pre-registration draft (not submitted).
6. Re-ran `pytest` (G-a); GATE R parse spot-check on committed tables.

## Outcomes

### Task 1 — errors dependence (`~/tmp/w2/errors_dep/report.json`)

| Metric | P2 (timeout 5) | W2 (timeout 0) |
|---|---|---|
| Rate errors differ from full | **0.7** | **0.0** |
| Full `n_errors` | 2 (Syntax + Timeout) | **1** (Syntax only) |
| Remaining | — | Syntax error on `0979.py`, `rule_id: null` |
| Rule-independent? | no (Timeout tied to `hardcoded-token`) | **yes** |

### Task 2 — diagnosis

- **Min-delta REFUSE_MATCH:** TARE attribution bug. Exact row: `corpus/files/0012.py`, `pass-body-fn`, start 32:1 / end 35:9. Empty first batch → `__json__`-only lines → whitespace split → record key `is`. **Fixed.**
- **Full-pair IC2 missing_candidate:** primarily **C4** timeouts (neighbor pad changed Timeout set / dropped findings). With timeout 0 + fix, same pair SHIPs. Not Semgrep cross-rule dedup / id collision / check_id mismatch / merge-key bug.

### Task 3 — positive controls → **SHIP**

| Pair | Update decision | equal except `time` | reused / fresh |
|---|---|---|---|
| Min-delta (P2) | SHIP, ic2 pass | True | 3269 / 1 |
| Full OWASP (P2) | SHIP, ic2 pass | True | 3103 / 251 |
| Seed 20261327 | SHIP, ic2 pass | True | 3269 / 1 |

Difference class on success: none (non-volatile match). Scratch: `~/tmp/w2/positive/`.

### Task 4 — CARC pre-reg

Written in `pipeline/docs/SEMGREP_PILOT.md`. **Not submitted.**

## Gates

| Gate | Result |
|---|---|
| G-a pytest | **PASS** — 428 passed / 1 skipped |
| G-b / G-c / G-d | Covered by pytest suite (G-d isolation test present) |
| GATE R | Prior P2 PASS retained; parse OK on committed HMMER/DIAMOND/Infernal-manifest tables |

## Controls

- Positive: three release-pair updates SHIP + stock-identical except `time`.
- Negative: P2 drop-finding refuse unchanged (not re-litigated).
- Unit: empty-first-batch lock regression + IC2 tab-cell subject test.

## Deviations

- First errors-dep attempt briefly used `path_list.txt` (original site-packages paths); aborted; re-ran on `records.txt` (pilot corpus). Documented in scratch only.
- Allowed `git fetch --depth 120` on `~/tmp/tare_g1/rules` (24 MB ≪ 150 MB).

## Open issues

- CARC job not submitted (await Josh).
- Cross-rule dedup **plant** still inconclusive (0 findings); speedup story no longer blocked by false refuses.
- Laptop walls still not evidence.

## SHIP / REFUSE status

**SHIP** — laptop release-pair updates stock-identical except declared volatile `time`.
