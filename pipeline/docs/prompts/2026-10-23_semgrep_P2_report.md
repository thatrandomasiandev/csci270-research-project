# Semgrep P2 report: pilot (2026-10-23)

## Final SHA

`e74286be48512153cdb8d6d54a8ed2fd4be68729` (branch tip). Results commit `15bf913`. Worktree: `../ACTS-semgrep`. Base `origin/main` = `b3cd9ad`.

## GATE R

**PASS.** No shared-path revert.

| File | Kind | Result |
|---|---|---|
| `pipeline/tests/fixtures/savings/A_hmmscan_01_widen.tbl` | HMMER tblout | identical |
| `pipeline/results/reference_boundary_tables/part0.tsv` | DIAMOND/BLAST+ outfmt 6 | identical |
| `pipeline/results/reference_boundary_tables/part1.tsv` | DIAMOND/BLAST+ outfmt 6 | identical |
| `pipeline/results/reference_boundary_tables/whole.tsv` | DIAMOND/BLAST+ outfmt 6 | identical |
| `pipeline/results/infernal/inputs.tsv` | Infernal **inputs manifest** (not cmscan tblout) | identical |
| `pipeline/fixtures/llm_arm/data/{smoke,dev,test}.tsv` | non-tool TSV | identical |
| live `stock_old.tbl` / `stock_old.dom` | HMMER tblout + domtblout | identical |
| HMMER e2e fill+update bodies (main `b3cd9ad` vs branch) | decision stripped + tblout/domtblout body sha256 | identical (`# Date:` only full-file diff) |

**Not committed in repo:** Infernal cmscan/cmsearch tblout, pfscanV3 output, HMMER domtblout fixtures.

## Prompt-1 gates re-run

| Gate | Result |
|---|---|
| G-a full pytest | **PASS** — 426 passed / 1 skipped (after pilot json-records tests) |
| G-b regression corpus | **PASS** |
| G-c microbenchmark | **PASS** (all within `max(1%, 50µs)`) |
| G-d default isolation | **PASS** |

## Pilot checks

| # | Check | Outcome |
|---|---|---|
| 1 | Stock vs stock (newer) | **PASS** (only `time`) |
| 2 | Positive control fill→update | **FAIL** (limitation after one fix): full OWASP pair update `REFUSE` IC2 `missing_candidate`; min-delta (seed 20261324) `REFUSE_MATCH` non-candidate pair. Hand-fixture v1→v2 still SHIPs. |
| 3 | Negative control (drop finding hook) | **PASS** — refuse, row-key sets differ |
| 4 | Inference | **PASS** — identity normalizer, no pin; volatile `time` |
| 5a | Cross-rule dedup plant | **INCONCLUSIVE** (0 findings on plant); cross-rule signal = min-delta non-candidate refuse |
| 5b | nosemgrep | **PASS** (correct id → 0 findings) |
| 5c | taint | **PASS** (59 taint rules present; no shipped mismatch) |
| 5d | Result order | **PASS** (stock-vs-stock) |
| 6 | Errors dependence | **rate 0.7** (7/10 half-rule subsets); expect envelope **REFUSE** when errors differ |
| 7 | Shape timings (laptop) | stock ~76–78s; fill ~670–690s; refused update ~124–212s — **not evidence** |

## Power

3269 findings on newer concat / 1000 files (floor 500). Seed 20261322.

## Errors-dependence rate

**0.7** (seed 20261325). Full run had 2 errors (syntax + Timeout). Half-rule subsets often drop the Timeout tied to `hardcoded-token`.

## Shape timings

See `pipeline/results/nonbio/semgrep_pilot.json` → `checks.7_shape_timings_laptop_not_evidence`.

## Proposed pre-registration

See `pipeline/docs/SEMGREP_PILOT.md`: fresh corpus, three consecutive releases, `r=3` alternating stock/TARE on exclusive EPYC 7542, SHIP+non-volatile match pass rule, power ≥500, errors policy locked before timing. **Do not start CARC** until a laptop pair SHIPs an update under IC2, or the claim is refuse-not-speedup.

## Code fixes this pilot

- `acts/table_json.py` — column lock across probe parts; sanitize newlines/tabs in scalar cells  
- `acts/reference_run.py` — lock json-records header per output  
- `tests/test_semgrep_domain.py` — `LineTableSanityTests`

## Priorities in time box (~1h wall)

| Priority | Status |
|---|---|
| 1 GATE R + G-a..G-d | **done** |
| 2 pilot data | **done** |
| 3 pilot checks | **done** (positive control recorded as limitation) |
| Deliverables + push | **this commit** |
