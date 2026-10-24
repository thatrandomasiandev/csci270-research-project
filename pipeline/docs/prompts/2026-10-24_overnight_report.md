# Overnight orchestrator report — 2026-10-24

**Orchestrator window:** ~2026-10-24 07:38 UTC → 09:47 UTC (Josh asleep).  
**Repo:** `/Users/joshuaterranova/Desktop/CSCI270/ACTS` and named worktrees.  
**Report branch:** `exp/overnight-report` (this file).  
**Disk:** started ~72 GB free → dipped ~35 GB mid-W1 → ended ~47 GB. Pause threshold (15 GB) never hit.

All four workstreams finished **DONE**. W13/W12a/W12b still **PENDING** on CARC — no W13 macro fill tonight.

---

## W1 — Shared contract P2d (verification false rejection)

| | |
|---|---|
| Status | **GO** |
| Branch / tip | `exp/shared-contract` @ **`1c5d57c`** (report content SHA `d6cb014`) |
| Worktree | `ACTS-sharedcontract` |
| Report | `pipeline/docs/prompts/2026-10-23_shared_contract_P2d_report.md` |

**Root cause:** Layer-C called `verify_stored_fit([one_table])`, so `per_key_row_count` with `count_table='tbl'` lacked sibling tbl counts → φ=NaN → false reject of a contract identical to each genome’s own.

**Fix:** Full-contract verification (probe-equivalent); `CONFIRM_N=10` on full Pfam; regression test; GATE R **PASS**; pytest **429** passed.

**Pilot (N=5, full Pfam, seed 20261336):** q=**1.0**; all outputs stock-identical; projected **ρ(20)=1.85** (≤2.5). Laptop V/L shape only.

**Open:** Layer-A scratch still holds ~6–9 GB prepared Pfam under `~/tmp/tare_sharedcontract_p2d/`. **Not folded into `main.tex` tonight** (orchestrator rule).

---

## W2 — Semgrep diagnose refusals

| | |
|---|---|
| Status | **SHIP** (laptop release-pair updates stock-identical except volatile `time`) |
| Branch / tip | `exp/semgrep-domain` @ **`b23c62f`** (content tip frozen in report as `5d64516`) |
| Worktree | `ACTS-semgrep` |
| Report | `pipeline/docs/prompts/2026-10-24_semgrep_W2_report.md` |

**Timeouts:** Locked `--timeout 0 --timeout-threshold 0 --max-memory 0`. Errors-dependence rate **0.7 → 0.0** (seed 20261326). Remaining: one rule-independent Syntax error on `0979.py`.

**Diagnosis:** Min-delta `REFUSE_MATCH` was a **TARE bug** (empty first batch → `__json__`-only lines → bad record key on `0012.py` / `pass-body-fn`). Full-pair IC2 `missing_candidate` was primarily **C4 timeouts**. Not Semgrep cross-rule dedup.

**Positive controls → SHIP:** P2 min-delta, P2 OWASP (3103 reused / 251 fresh), seed 20261327. Pytest **428** passed / 1 skipped.

**CARC pre-reg:** drafted in `SEMGREP_PILOT.md` — **not submitted**. **Not folded into `main.tex` tonight.**

---

## W3 — Paper fold-in (only `main.tex` editor)

| | |
|---|---|
| Status | **DONE** (Steps 1–4 + W4 scale sentence) |
| Branch / tip | `hub/submission-ready` @ **`3851284`** |
| Worktree | `ACTS-hub` |

| Step | SHA | Notes |
|---|---|---|
| 1+2 W8/W5x | `9aa316f` | Measured release chain; matched Table 4 (INCR 1.50× / ProcessCache 14.49× / `\sys` 4.20×; Riker blocked) |
| 3 Formal core | `7df6e7f` | C0–C4; exact-merge prop; R1–R6; imprecision fixes noted in formal-core report |
| 4 Cross-field | `867f617` | IR / MS / Gaia cites verified (Staudinger = SIGIR-AP 2024) |
| Scale sentence | `e7ae203` (artifacts `92d2ec2`) | PROJECTED 143 vs 34 core-years/release; validation caveat omitted for space |
| Report stamps | `3851284` | |

**Gates (final tip):** checker **0** mismatches (PENDING W13/W12a/W12b/WA2 OK); body **≤12** pp (refs p13); anonymity OK; pytest **412** passed / 1 skipped (`tests/`); finalize.sh: W8/W5x **COLLECTED**, W13/W12a/W12b **STILL RUNNING**.

**Reports:** `2026-10-23_paper_w8_w5x_report.md`, `2026-10-23_formal_core_report.md`, `2026-10-23_crossfield_paragraph_report.md`, `2026-10-24_scale_projection_paper_report.md`.

**Not done:** W13 macro fill / `finalize.sh` paper rebuild (jobs incomplete). No Semgrep or shared-contract prose.

---

## W4 — Impact at real scale (projection)

| | |
|---|---|
| Status | **DONE** |
| Branch / tip | `exp/scale-projection` @ **`2cbd8ae`** (also cherry-picked onto hub as `92d2ec2`) |
| Worktree | `ACTS-scale` |
| Artifacts | `pipeline/scripts/scale_projection.py`, `pipeline/results/scale/projection.json`, `pipeline/docs/SCALE_PROJECTION.md` |

**NCBI:** assembly_summary.txt 242,166,326 B; sha256 `7034587b…c626`; download 2026-10-24T07:39:25Z→07:40:51Z.  
**Counts:** 2,179,028,082 proteins / 544,814 assemblies (127 blank excluded); 22,893 reference; **0** representative in this snapshot.

**PROJECTED (widened; validation median abs wall error 26.3% > 25%):**

| Scope | Stock / release | `\sys` typical update | `\sys` rebuild (~93%) |
|---|---:|---:|---:|
| All RefSeq bacteria | **143** core-years (105–324) | **34** (22–78) | **≈143** |
| Reference genomes | **6.0** | **1.4** | **≈6.0** |

Per year (8 releases / 25 mo; rebuild fraction 1/7 pairs): stock **548** vs `\sys` historical mix **189** (widened 132–434).

---

## CARC timeline (read-only)

| Time (UTC) | Observation |
|---|---|
| 07:38 | Baseline: W13 `13260162_0` RUNNING ~4h01m on b22-07; `_1.._8` PENDING; W12a `13347581` / W12b `13347608` PENDING; confirm `13347607` COMPLETED. Untouched: `12864756_*`. |
| ~08:50 | `_0` COMPLETED (04:22:12); `_1` RUNNING. |
| 09:46 | `_0` COMPLETED; `_1` RUNNING ~1h15m; `_2.._8` still PENDING; W12a/W12b still PENDING. |

**Action taken:** none (no submit / cancel / modify). **W13 macros left PENDING** — not all nine tasks COMPLETE; W3 not asked to run `finalize.sh` paper rebuild.

Hourly log: `~/tmp/overnight_carc_watch.log`.

---

## FOR JOSH IN THE MORNING

1. **Merge / collect order:** `hub/submission-ready` @ `3851284` has W8/W5x + formal core + cross-field + scale sentence. Decide when to merge to `main` (orchestrator did not).
2. **W13 / W12a / W12b:** still queued/running. When all nine W13 tasks COMPLETE with controls, run collect + fill PENDING macros on hub (or relaunch W3 with that instruction only).
3. **Shared-contract CARC:** P2d is **GO** (q=1.0, ρ(20)=1.85). Approve submitting the realistic CARC run, or fold the laptop GO narrative into the paper first?
4. **Semgrep CARC:** pre-reg is drafted in `SEMGREP_PILOT.md` on `exp/semgrep-domain` @ `b23c62f`. Submit or revise? (Laptop SHIP only; walls not evidence.)
5. **Scale caveats:** NCBI snapshot has **zero** `representative genome` rows (reference-only “reps”); validation MAE 26.3% — widen stays in JSON/docs, not in the paper sentence. Confirm whether that framing is OK.
6. **Disk cleanup (optional):** `~/tmp/tare_sharedcontract_p2d/` (~9 GB) and leftover `p2c` scratch are safe to prune after you no longer need Layer-A repro files.
7. **Do not touch** job `12864756` (still pending Priority).
