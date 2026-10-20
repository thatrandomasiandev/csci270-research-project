# TARE orchestrator report — round 2 (2026-10-20)

In progress. Final status only when every workstream is DONE, INCONCLUSIVE (with reason), or BLOCKED on Josh.

Orchestrator branch: `exp/orchestrator-report-r2`. Round-1 tips (authoritative at launch): see `2026-10-19_orchestrator_report.md` on `exp/orchestrator-report`.

## Scoreboard (live)

| WS | Branch | Worktree | Status | Notes |
|---|---|---|---|---|
| W13 | `exp/w13-bounded-headline` | `ACTS-w13r2` @ `0e92344` | LAUNCHED | Highest CARC priority; freeze at bounded-audit default |
| W6c | `exp/w6-row-keys` | `ACTS-w6` @ `2be1e06` | **DONE** | Needless HMMER 6/6 SHIP (incl. Drosophila); BLAST measured NOT_SHIP (`pident` col-2) |
| W8 | `exp/w8-release-chain` | `ACTS-w8` @ `53d6e58` | LAUNCHED | Pilot 13241855 COMPLETED; commit + measured |
| W12a | `exp/w12a-expert-script` | `ACTS-w12a` @ `b9ed4b8` | LAUNCHED | Pilot 13241867 still PENDING |
| W5x | `exp/w5x-baselines-x86` | `ACTS-w5x` @ `5965454` | LAUNCHED | Pilot 13241865 TIMEOUT; resubmit |
| W12b | `exp/w12b-iseqsearch` | `ACTS-w12b` @ `5b949cf` | LAUNCHED | Confirm then exclusive measured |
| WA2 | `exp/a-unrelated-ship` | `ACTS-exp-a` @ `258b20d` | LAUNCHED | Fresh draw seed 20261272 |

## CARC at launch (2026-10-20 ~10:35 PT)

| Job | Name | State | Elapsed / limit |
|---|---|---|---|
| 13241855 | tare-w8-pilot | COMPLETED | 05:39:03 / 16:00:00 |
| 13241901 | tare-w6-hmmer | COMPLETED | 07:03:31 / 18:00:00 |
| 13243768 | tare-w6-blast | COMPLETED | 09:39:23 / 12:00:00 |
| 13241865 | tare-w5x-pilot | TIMEOUT | 03:00:04 / 03:00:00 |
| 13241867 | tare-w12a-pilot | PENDING | Priority; leave queued |
| 12864756_* | scan_stock_measure | (others) | **DO NOT TOUCH** |

Result files confirmed on CARC (not yet committed):
- `/project2/biyik_1165/jjt_373/csci270-star/tare-w8/results/pilot_20261221.json`
- `/project2/biyik_1165/jjt_373/csci270-star/tare-w6/results/hmmer_GCF_000001215.4.json`
- `/project2/biyik_1165/jjt_373/csci270-star/tare-w6/results/blast_measured.json`

CARC exclusive priority: W13 > W8 > W12a > W5x > W12b > WA2 timing. Cap 6 exclusive EPYC.

---

## W6c — collect leftovers

**STATUS: DONE.** Tip `2be1e068c99516ca9350082bb75f0b4f68360925` on `exp/w6-row-keys`. No new CARC runs.

- Needless HMMER refusals fixed: **6/6** SHIP, bodies byte-identical (incl. Drosophila `GCF_000001215.4`).
- BLAST measured: **NOT_SHIP** — both releases `REFUSE` / `out: column 2 matches no normalizer`; fallback ordered-equal to stock (2,137,688 lines).
- Reports: `pipeline/docs/prompts/2026-10-20_w6c_report.md` (on that branch).

---

*(Sections below filled as workstreams finish.)*
