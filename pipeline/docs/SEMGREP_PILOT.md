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

**Locked Semgrep argv (laptop pilot):**

```
--json --no-rewrite-rule-ids --metrics=off --disable-version-check
--timeout 0 --timeout-threshold 0 --max-memory 0
-j 2
```

Code fixes: `reference_run._coerce_json_tables` / `_seed_json_columns_from_tables`; `exact_certificate.split_body_fields`.

## CARC pre-registration draft — SUPERSEDED

The table below was the W2 draft labeled **do not submit**. It is **superseded** by the locked pre-registration in the next section (Josh approved via Saturday orchestrator paste 2026-10-24). Do not use the draft for staging or scoring.

| Item | Draft (superseded) |
|---|---|
| Goal | Decide whether TARE can **SHIP** Semgrep rule-set updates with equal non-volatile JSON and report a wall-time ratio vs stock on an exclusive node |
| Releases | Three consecutive semgrep-rules commits… (fresh seed) |
| Corpus | Fresh ≥1000 Python files… |
| … | … |

---

## CARC measured pre-registration (LOCKED 2026-10-24)

**Status:** LOCKED. Cite W2 pilot findings above. Commit this section **before** staging or `sbatch`. Prior “do not submit” draft is superseded; Josh approved via Saturday orchestrator paste.

**Frozen code:** branch `exp/semgrep-domain` tip recorded in the staging `FROZEN_COMMIT` file (must be the commit that contains this locked pre-reg or a descendant that only adds harness/results).

### W2 findings this pre-reg cites

- Timeout-0 argv → errors-dependence rate **0.0** (seed 20261326); remaining error is rule-independent syntax.
- Empty-batch json-records column lock + tab-aware IC2 split → release-pair updates **SHIP** stock-identical except `time`.
- Negative control (injected drop finding) **REFUSE** (P2, unchanged).
- Laptop walls are **not** evidence.

### Locked design

| Item | Locked value |
|---|---|
| Goal | Decide whether TARE can **SHIP** Semgrep rule-set updates with equal non-volatile JSON (except declared volatile `time`) and report wall-time ratios vs stock on one exclusive EPYC 7542 node |
| Corpus seed | **20261351** |
| Corpus | Fresh ≥**1000** Python files, never used in G1, P2, or W2 (exclude by **path and content sha256** against G1 target + P2/W2 corpus manifests). Enlarge until stock on the **newest** release has ≥**500** findings; else score **INCONCLUSIVE** (not KILL) |
| Release seed | **20261352** |
| Releases | **Three consecutive** commits in the ordered list of semgrep-rules commits that each change ≥1 `python/**/*.yaml` (filtered history; non-Python commits may sit between in full git). Concatenate all Python rules at each commit with the same path-qualification for duplicate bare ids (`tare_source_path` + qualified `id`) |
| Machine | Exclusive **EPYC 7542**, `--account=biyik_1173`, `--exclusive --mem=0 --constraint=epyc-7542`. Smoke is non-exclusive (exactness only) |
| Semgrep | `semgrep==1.182.1` (pinned). Binary checksum recorded in result JSON |
| Semgrep argv | `--json --no-rewrite-rule-ids --metrics=off --disable-version-check --timeout 0 --timeout-threshold 0 --max-memory 0 -j 32` |
| TARE argv | `--strategy reference --reference-format yaml-list --output-format json-records --json-rows results --volatile-json-field time --pin --verify full` |
| Tool template | `semgrep --config {reference} <semgrep argv> -o {output} {inputs}` |
| Volatile field | **`time` only** (JSON envelope). Top-level `errors` are **not** volatile and must match stock |
| Design | Commits oldest→newest `A,B,C`. Fill cache at `A` once. For each update step `B` then `C`: restore cache to post-previous; run **r = 3** alternating **stock / TARE** (stock, TARE, stock, TARE, stock, TARE) on that release |
| Smoke | One release step (`A→B`), **r = 1**, non-exclusive, 1h limit; must **SHIP** and equal stock except `time` before measured may proceed (`--dependency=afterok`) |
| Pass | Every TARE update **SHIP**s; shipped output equals stock except `time`; stock-vs-stock (except `time`) holds on the node for the newest release |
| Fail | Any SHIP with a non-volatile mismatch; or IC2/candidate refuse on a release pair intended to demonstrate reuse |
| Controls | **Positive:** stock-vs-stock identity (newest release, except `time`). **Negative:** injected-drop finding hook must **refuse** (not SHIP) |
| Power | ≥500 stock findings on newest release; else **INCONCLUSIVE** |
| Errors policy | Top-level `errors` must match stock. Pre-timing: 10 half-rule-subset errors-dependence rate must be **0** on the CARC corpus with locked timeout argv (expect only rule-independent entries) |
| Metrics | Per-step speedup \(S\) = median(stock walls) / median(TARE walls); CV of walls; payback over the chain (fill + updates vs repeated stock). Refusals are **counted, never dropped** |
| Seeds reserved | 20261351–20261359 for this workstream. **Do not** reuse 20261322–20261329 |
| Staging | `/project2/biyik_1165/jjt_373/csci270-star/tare-semgrep/` |
| Scratch | `/scratch1/$USER/tare-semgrep/` |
| Results path | `pipeline/results/nonbio/semgrep_measured.json` |

### Time limit

Pilot laptop stock ~170 s (`-j 2`, timeout 0). Measured uses `-j 32` on exclusive node. Bound: scale observed smoke/pilot walls ×1.5 for the full chain (fill + 2 steps × r=3 × (stock+TARE) + controls). Floor for this job: **04:00:00** (Semgrep shorter than whole-genome HMMER; do not under-scale below pilot×1.5).

### Provenance (required in result JSON)

git head, frozen commit, seeds, tool version + checksums, host/CPU, full argv, walls, per-run outcomes, corpus manifest sha256, rules commit SHAs + concat sha256.
