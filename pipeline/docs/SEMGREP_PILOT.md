# Semgrep domain pilot (TARE)

Pilot only. Numbers here are not measured CARC results and must not enter the paper.

## What ran

- Branch `exp/semgrep-domain`, scratch `~/tmp/tare_semgrep_p2/` (P2) and `~/tmp/w2/` (W2 overnight), Semgrep 1.182.1, `-j 2`.
- Seeds: **20261322** (pilot), **20261324** (min-delta), **20261325** (errors subsets, pre-timeout lock), **20261326** (errors with `--timeout 0`), **20261327** (second release pair).
- Release pairs: `241477b` → `46a0ecf` (OWASP 2025 mapping, P2); `2a5cbda` → `c1da51f` (flask-cors confidence, seed 20261327). Concatenated Python rules with duplicate bare ids path-qualified.
- Corpus: 1000 Python files (`~/tmp/tare_semgrep_p2/corpus/records.txt`), disjoint from G1. Power: **3269** findings (floor 500).

## What it found (P2 + W2)

1. **GATE R PASS** on committed HMMER/DIAMOND tables and live hmmscan; shared tab-aware parse unchanged for default table path.
2. **Stock vs stock PASS** (only `time` differs).
3. **Positive control SHIP (W2).** After locking `--timeout 0` and fixing the json-records empty-batch column lock + tab-aware IC2 split: min-delta, full OWASP pair, and seed-20261327 pair all **SHIP** with `ic2: pass` and output equal to stock except `time`.
4. **Negative control PASS** (P2: drop-one-finding hook → refuse).
5. **Inference PASS:** identity normalizer; declare `--volatile-json-field time`.
6. **Errors dependence (W2, seed 20261326, `--timeout 0`):** rate **0.0** (was 0.7). Remaining top-level `errors`: one **Syntax error** on `0979.py` (`rule_id` null) — present in the full run and every half-rule subset → **rule-independent**.
7. **Laptop shape (not evidence):** with `--timeout 0`, stock ~170 s; fills still multi-scan.

### P2 refuses diagnosed (W2)

| Symptom | Class | Evidence |
|---|---|---|
| Min-delta `REFUSE_MATCH` `(is, {json...})` on `0012.py` / `pass-body-fn` / span 32:1–35:9 | **TARE bug** | Empty first replay batch locked columns to `[__json__]`; whitespace split of `` `pass` is ... `` → fake record key `is` |
| Full-pair IC2 `missing_candidate` | **C4** (timeouts) primary | Same pair SHIPs under `--timeout 0` + column-lock fix |

Checked and not the refuse cause: Semgrep cross-rule dedup plant; qualified-id collisions; `check_id`≠rule id; message wrapping; merge order key.

## Addendum 2026-10-24 (W2 overnight): lock timeouts off

Semgrep’s default `--timeout 5` emits rule×file `Timeout` rows into top-level `errors` (P2: `hardcoded-token` on `0683.py`). Those rows appear or vanish when the rule set or wall clock changes (C4).

**Locked Semgrep argv:**

```
--json --no-rewrite-rule-ids --metrics=off --disable-version-check
--timeout 0 --timeout-threshold 0 --max-memory 0
-j 2
```

Code fixes: `reference_run._coerce_json_tables` / `_seed_json_columns_from_tables`; `exact_certificate.split_body_fields`.

## CARC pre-registration draft (do not submit)

Lock after W2 laptop SHIPs (satisfied 2026-10-24).

| Item | Locked proposal |
|---|---|
| Goal | Decide whether TARE can **SHIP** Semgrep rule-set updates with equal non-volatile JSON and report a wall-time ratio vs stock on an exclusive node |
| Releases | **Three consecutive** semgrep-rules commits that change ≥1 Python rule, drawn with a **fresh** seed (not 20261322–20261329); concatenate with the same unique-id qualification |
| Corpus | **Fresh** ≥1000 Python files, disjoint from pilot/G1/W2 by path+hash; enlarge until stock on the newest release has ≥**500** findings |
| Machine | Exclusive **EPYC 7542**, one job; no other user load |
| Design | `r = 3` alternating **stock / TARE** pairs (stock, TARE, stock, TARE, stock, TARE) |
| Semgrep argv | `--json --no-rewrite-rule-ids --metrics=off --disable-version-check --timeout 0 --timeout-threshold 0 --max-memory 0` plus `-j` matching the exclusive node policy |
| TARE argv | `--strategy reference --reference-format yaml-list --output-format json-records --json-rows results --volatile-json-field time --pin --verify full` |
| Pass | Every TARE update **SHIP**s; output equals stock except `time`; stock-vs-stock (except `time`) holds on the node |
| Fail | Any SHIP with a non-volatile mismatch; or IC2/candidate refuse on a release pair intended to demonstrate reuse |
| Power | ≥500 findings on the newest release stock output; else **INCONCLUSIVE** |
| Errors | Top-level `errors` **must match** stock (not volatile). Require errors-dependence rate **0** on a 10-subset replay on the CARC corpus with the locked timeout argv before timing. Expect only rule-independent entries (e.g. syntax) |
| Primary metric | Median wall ratio stock/TARE over the three TARE updates (laptop timings are not this metric) |

**Do not submit** this job until Josh reviews. Laptop SHIP under IC2 is satisfied (W2).
