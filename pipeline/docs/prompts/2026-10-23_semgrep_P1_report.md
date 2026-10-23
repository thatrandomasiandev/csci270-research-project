# Semgrep P1 report: opt-in features, zero regression (2026-10-23)

## Branch / SHAs

| | |
|---|---|
| Branch | `exp/semgrep-domain` |
| Base (origin/main) | `b3cd9ad32269c01880f4e2819b26f7fdd8d14cf8` |
| Final HEAD | `43c857371cdf25f8d02aca4feaa785b18b1b0ea0` |
| Worktree | `../ACTS-semgrep` |

Commits: baseline → yaml-list/json-records/{inputs} → pin-path tab/coerce fixes.

## Gates

| Gate | Result | Numbers |
|---|---|---|
| **G-a** Full pytest | **PASS** | Baseline 412 passed / 1 skipped. Final **425 passed / 1 skipped** (13 new Semgrep-domain tests). 0 failures. |
| **G-b** Regression corpus | **PASS** | 4 format round-trips: output sha256 identical to baseline. Entryline e2e `decision.txt` identical after dropping `phases:` / `probe_phases:` wall-time lines (decision/why/verify/n_entries/program_binary unchanged: REFUSE on column tie). |
| **G-c** Microbenchmark | **PASS** | All six medians within `max(1%, 50 µs)` of baseline (~4–5 µs parse/detect; tol 50 µs). See `pipeline/results/nonbio/p1_gates.json`. |
| **G-d** Default path isolation | **PASS** | Subprocess: after `parse_reference_text` on entryline, `acts.reference_yaml` and `acts.table_json` are absent from `sys.modules`. |

## json-records byte identity

**Achieved** for non-volatile fields via Semgrep's compact form:

- `json.dumps(..., separators=(",", ":"), ensure_ascii=False)`
- Key order preserved from the tool output
- Row objects kept in `__json__` cells; render rebuilds `results` then sorts with Semgrep's ordering key (path, start, end, check_id, message)

**Where full-file byte identity is impossible without a volatile declaration:** the top-level `time` object. Two of fifteen G1 files fail exact `render(parse(x)) == x` because nested floats serialize differently (`9.112287734037329e-06` vs Python's `9.11228773403733e-06`). After stripping `time`, all 15 G1 outputs round-trip byte-identically on every other top-level field, including `results`.

## Decision on `time`

| Evidence | |
|---|---|
| Present with G1 argv (`--json`, no `--time`) | yes |
| Present with `--no-time` | yes (still a populated object) |
| Differs stock-vs-stock | yes (only field that differs at fixed f) |
| Float round-trip via `json.dumps` | not always |

**Ship rule:** caller must pass `--volatile-json-field time`. Recorded in `decision.txt` as `volatile_json_fields: ['time']`. Default remains empty (refuse near-matches that only differ on undeclared fields). Avoiding `time` at the Semgrep source was not possible with 1.182.1.

Use `--no-rewrite-rule-ids` so `check_id` equals the rule `id` for exact-token column inference.

## Smoke (hand fixtures, not evidence)

Commands (scratch `~/tmp/tare_semgrep_p1/smoke/`):

1. Stock Semgrep on `rules_v1.yaml` / `rules_v2.yaml` with `--no-rewrite-rule-ids --json`.
2. TARE fill on v1: `--reference-format yaml-list --output-format json-records --json-rows results --volatile-json-field time --pin --verify full` and `{inputs}`.
3. TARE update on v2 with the fill cache (one rule message changed, one rule added).

| Step | decision.txt |
|---|---|
| Fill | `SHIP` — exact replay under identity normalizer; fill output equals stock_v1 except `time` |
| Update | `SHIP` — `reused_rows: 1`, `n_fresh: 2`, `n_stable: 1`, `f_delta: 0.667`; update output equals stock_v2 except `time` |

Full decision texts: `~/tmp/tare_semgrep_p1/smoke/fill_decision.txt`, `update_decision.txt`.

## Files touched

| File | Why |
|---|---|
| `acts/reference_yaml.py` | **new** — yaml-list parse/write (byte-preserving) |
| `acts/table_json.py` | **new** — json-records parse/render/volatile compare |
| `acts/reference_formats.py` | `Entry.document_header`; opt-in dispatch in `parse_reference` / `write_entries` |
| `acts/reference_run.py` | `{inputs}` expansion; json-records coerce on invoke/pinned/slack; emit JSON on ship |
| `acts/reference_fit.py` | Tab-aware `parse_table_text` (spaces in cells) |
| `acts/replay_batch.py` | Tab-aware `merge_bodies` cell split |
| `acts/__main__.py` | CLI flags (defaults `auto` / `table`) |
| `tests/test_semgrep_domain.py` | Controls + G1 round-trips + G-d |
| `tests/fixtures/semgrep/*` | Tiny rules/targets/records |
| `results/nonbio/p1_baseline.json` | Pre-change snapshot |
| `results/nonbio/p1_gates.json` | Gate numbers |

Shared modules changed only at opt-in dispatch or for tab-cell correctness needed by the synthetic json-records table.

## Open risks for the pilot (prompt 2)

1. **Duplicate bare rule ids** across semgrep-rules packages — TARE refuses duplicates in one document; directory configs rely on `--rewrite-rule-ids` path prefixes. Pilot should use one concatenated file with unique ids, or qualify ids.
2. **`errors` can depend on the rule set** (G1: 2 errors at f=0.10 vs 3 at f=1.00). Envelope non-results fields must still match stock; a subset scan that misses a rule-triggered parse error will `REFUSE_MATCH`.
3. **Cross-rule couplings** (dedup, `nosemgrep`, taint) — not exercised in P1 smoke; pilot must plant controls.
4. **Result order** — merge sorts with Semgrep's key; confirm on larger corpora.
5. **PyYAML** is imported only on yaml-list opt-in (already on the laptop; not a new download).
6. **Laptop walls are not speed evidence** — no timing claims from smoke.
