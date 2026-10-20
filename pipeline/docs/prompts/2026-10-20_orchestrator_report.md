# TARE orchestrator report — round 2 (2026-10-20)

**PAUSED 2026-10-20T17:48Z** — Josh stopped all local agents. CARC jobs left running (not cancelled). Resume by reattaching worktrees and polling those job IDs.

Orchestrator branch: `exp/orchestrator-report-r2`. Round-1 tips: `2026-10-19_orchestrator_report.md` on `exp/orchestrator-report`.

## Scoreboard (at stop)

| WS | Branch | Tip | Status | In-flight CARC / notes |
|---|---|---|---|---|
| W13 | `exp/w13-bounded-headline` | `36017cd` | STOPPED | pre-registered; job `13259408` headline_bounded_pilot |
| W6c | `exp/w6-row-keys` | `2be1e06` | **DONE** | 6/6 HMMER SHIP; BLAST measured NOT_SHIP |
| W8 | `exp/w8-release-chain` | `ea33413` | STOPPED | measured array `13259414_{0,1,2}` PENDING |
| W12a | `exp/w12a-expert-script` | `b9ed4b8` | STOPPED | pilot `13241867` (was RUNNING) |
| W5x | `exp/w5x-baselines-x86` | `8f94718` | STOPPED | resubmitted pilot `13259326` PENDING |
| W12b | `exp/w12b-iseqsearch` | `5b949cf` | STOPPED | confirm `13259333` (dup `13259402` cancelled earlier) |
| WA2 | `exp/a-unrelated-ship` | `9a36ec0` / agent said `83f9bf5` | STOPPED | `13259447` array + `13259448` agg |

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
