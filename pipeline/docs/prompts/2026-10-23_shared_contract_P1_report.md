# Shared contract P1 report (2026-10-23)

## Branch / SHAs

| | |
|--|--|
| Branch | `exp/shared-contract` |
| Worktree | `../ACTS-sharedcontract` |
| Base (origin/main) | `b3cd9ad32269c01880f4e2819b26f7fdd8d14cf8` |
| Final | `039e8d959ad6fbe0639fb6bdc0602291cba2b022` |
| Commits | STEP 0 baseline `2e6b235` → design `aa01035` → feature+tests+gates `039e8d9` |

No paper edits. No CARC. Seeds reserved `20261331`–`20261339` (no prior collisions); smoke marker `20261333`.

## STEP 1 — phase table (nesting + SHAREABLE vs PER-GENOME)

Nesting (from `_phase_from` / probe clock clear): `X_build_s` and `X_scan_s` sit **inside** `X_s`. Global `prep_s`/`tool_s` accumulate every invoke, including nested ones — **do not add** them on top of discovery/pin_check/replay. Probe work is reported under `probe_phases` after the post-probe clock clear.

| Phase | Nested? | Reads | Class |
|-------|---------|-------|-------|
| `parse_s` | no (pre-probe) | reference + genome | MIXED (ref SHAREABLE; genome PER-GENOME) |
| probe wall | separate clock | binary, argv, release, **genome sample** | Facts SHAREABLE w/ confirm; runtime uses genome |
| `pin_check_s` | wall; tool nested in accumulators | sample + pin + tables | Confirm / re-check per genome; do not trust stored `pin_checks` |
| `discovery_s` | build/scan nested | fresh entries × genome | PER-GENOME |
| `cache_*`, `diff`, `merge_rescale` | no | this genome's cache | PER-GENOME |
| `replay_*` | build/scan nested | candidates + genome | PER-GENOME |
| `ic2_*`, audit/`verify` | build/scan nested | safety | PER-GENOME (never share) |

Full write-up: `pipeline/docs/SHARED_CONTRACT_DESIGN.md`.

## Facts + soundness risks

| Fact | Cross-genome risk? | Example | Policy |
|------|--------------------|---------|--------|
| column `role`/`member`, key cols | yes | constant col on A → identity; varies on B → entry_count | confirm reduced-n probe |
| `decision` / exact_eligible / ties | yes | band rows only on B | confirm |
| `layout` / `meta` | yes | wider names on B | roles compared; layout not required equal |
| `inferred_pin` template | medium | wrong member if mis-fit | store; size members re-checked via confirm |
| `pin_checks[*]` | **yes** | empty sample on B | **never publish**; always re-run pin check |
| `slack_factor` | no (argv) | — | SHAREABLE |
| row cache / coverage | yes | — | never share |

## PROJECTED ρ(N) and GATE 1

W5x r0: total 1013.7 s, ratio 4.20× → \(T=241.36\) s.  
Shareable once: parse 48.9 + probe 538.5 + pin_check 151.8 → \(S=739.2\).  
Per-genome: \(G=274.5\).

\[
\rho(N)=\frac{274.5+739.2/N}{241.36}
\]

| N | ρ(N) |
|---|------|
| 1 | 4.20 |
| 5 | 1.75 |
| 20 | **1.29** |
| 100 | 1.17 |

**GATE 1 PASS** (need ρ(20)≤3.15). Conservative (share probe only): ρ(20)=2.08 still PASS. Confirmation tax not in this projection (prompt 2).

## Built (opt-in)

- Flag `--contract-store DIR` (default unset).
- Module `acts/contract_store.py` (lazy-imported only when flag set).
- Key: sha256(binary digest ∥ argv digest ∥ release content hash).
- Stores shareable FitResult (+ inferred_pin, slack_factor); strips `pin_checks`.
- On hit: reduced-n confirm (`CONFIRM_N=50`); mismatch → `confirm_fail`, full probe.
- Atomic write: temp + `os.replace`.
- `decision.txt`: `contract_store`, `contract_key`, `contract_confirmations`, optional reason.

## Gates

| Gate | Result |
|------|--------|
| G-a pytest | **419 passed, 1 skipped**, 0 failed (was 412+1; +7 new) |
| G-b corpus no flag | **PASS** — stripped decision + table sha256 match baseline for exact_replay first/update and identity |
| G-c phase shape no flag | **PASS** — identical phase key sets vs baseline (shape only) |
| G-d default isolation | **PASS** — subprocess: `acts.contract_store` not in `sys.modules` |

New tests (`tests/test_shared_contract.py`): reuse, key isolation (argv/release/binary), contradiction, corruption, concurrency, default import, signature helper.

## Smoke (shape only, not evidence)

4 synthetic genomes, one store: genome0 `stored`; genomes1–3 `reused` with `probe_roles_n=4` + `roles_match`; all outputs byte-equal to stock; pin_check/discovery/IC2 still present per genome. File: `pipeline/results/shared_contract/p1_smoke.json`.

## Files touched

| Path | Why |
|------|-----|
| `pipeline/docs/SHARED_CONTRACT_DESIGN.md` | STEP 1 table + ρ(N) |
| `pipeline/acts/contract_store.py` | store, key, confirm signatures, atomic save |
| `pipeline/acts/reference_run.py` | opt-in load/confirm/publish |
| `pipeline/acts/__main__.py` | `--contract-store` |
| `pipeline/tests/test_shared_contract.py` | positive/negative controls |
| `pipeline/scripts/capture_shared_contract_baseline.py` | STEP 0 harness |
| `pipeline/results/shared_contract/*` | baseline, gates, smoke |

## Open risks for prompt 2 / 3

**Prompt 2 (laptop pilot with controls)**  
- Measure confirmation tax vs full probe on real hmmscan toys / small Pfam slice.  
- Does reduced-n confirm miss a role change that full probe would catch (power)?  
- First-writer-wins store vs last-writer on confirm_fail overwrite policy.  
- Positive/negative controls for reuse on real binaries (not only in-process runners).

**Prompt 3 (CARC, N=1,5,20)**  
- Measure ρ(N) on exclusive EPYC; compare to PROJECTED 1.29 at N=20.  
- Honest matched first-run table for the paper (W5x 4.20× vs baselines) regardless of feature.  
- Pin-check still per-genome (~152 s on W5x): if confirm cannot shrink it, ρ floor is higher than optimistic projection.  
- Concurrent batch writers on shared NFS/Lustre: verify `os.replace` behavior on CARC scratch.
