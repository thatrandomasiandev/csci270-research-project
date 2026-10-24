# Shared contract P2c report — verification fix + layered sharing + realistic re-pilot

**Final SHA:** `2f8a96f0498c70a3f874ea15421842a859cd3a37`  
**Branch:** `exp/shared-contract`  
**Scratch:** `~/tmp/tare_sharedcontract_p2c/`  
**No CARC. No paper edits.** Laptop walls are shape only.

## What changed in the inherited code (and why)

Inherited P2b work compared a *re-inferred* confirm fit to the store (weaker vs stronger sample → false `confirm_fail`). Replaced with a contradiction test:

- `verify_stored_fit` / `confirm_stored_fit`: apply **stored** keys/roles/members to a seeded part-vs-whole sample; fail only on observed disagreement; `no_rows` is not a fail.
- `CONFIRM_N = 25` from `p2b_confirm_n.json` (all-5 self-consistency + poison catch; n=10 had a vacuous `no_rows`).
- Evidence committed: `p2b_diagnosis.json`, `p2b_confirm_n.json`, diagnose/calibrate scripts.

Then layered sharing (opt-in only; default path unchanged):

| Layer | What | decision.txt |
|-------|------|----------------|
| **A** | `RefSideCache` under `--contract-store/refside`: parsed entries + prepared reference keyed by `release_hash\|\|prep` | `contract_refside_parse/prep: stored\|hit` |
| **B** | Fill undetermined fields from this genome’s sample fit; merge only if all stored verification **observations** still verify; never overwrite a determined conflict | `contract_layer_b: noop\|refined\|conflict\|…` |
| **C** | Per-table verify on one invoke; any table fail → whole-probe fallback (per-table re-probe unclean with sibling `per_key_row_count`) | `contract_layer_c: all_tables_verified\|partial_fail_whole_probe_fallback` |

## Priorities finished / partial / not started

| Priority | Status |
|----------|--------|
| P1 verification fix + tests + commit | **Done** (`9191f91`) |
| P2 Layer A / B / C | **Done** (`5ef4fd5` + follow-ups) |
| P3 controls + GATE R | **Done** (unit tests + GATE R PASS + default-import False) |
| P4 realistic re-pilot | **Done at N=3** (disk cap; see below) |
| Optional pooled seeding | **Not started** (time / disk) |

## Controls (P3)

| Control | Evidence |
|---------|----------|
| Self-consistency positive | `test_verify_self_consistency_positive` |
| Poisoned store (identity plant) | `test_verify_poisoned_store_negative` |
| Hand-planted wrong member | `test_verify_hand_planted_wrong_member_negative` |
| Argv / release isolation | existing `test_key_isolation_binary_argv_release` |
| Prep-command isolation (Layer A) | `test_layer_a_prep_command_isolation` |
| Layer A cached prep ≡ fresh prep bodies | `test_layer_a_refside_parse_and_prep_cache` |
| Refinement conflict not merged | `test_layer_b_refinement_conflict_not_merged` |
| Layer C recorded on reuse | `test_layer_c_recorded_on_reuse` |
| Default path no `acts.contract_store` import | `test_default_path_does_not_import_contract_store` + P2c `default_import.ok` |
| Full pytest | **428 passed**, 1 skipped |

## GATE R

Without `--contract-store`, `main` (`b3cd9ad` via P2 `main_code`) vs branch on real HMMER (P2 subset fill + update):

- Stripped `decision.txt` sha256: **match** (fill and update)
- Table body sha256: **match**
- **GATE R = PASS** (`pipeline/results/shared_contract/p2c_gate_r.json` / embedded in `p2c_realistic.json`)

## Realistic-size arms (seed 20261336)

- **Reference:** full Pfam-A decompressed + hmmpress in scratch (`~/tmp/tare_sharedcontract_p2c/pfam/Pfam-A.hmm`).
- **Proteomes:** 500 proteins each from `pipeline/data/recurrence/A`, seed `20261336`.
- **Stock timing:** 67.5 s at 2 threads (under 20 min).
- **N = 3** (not 5): full-Pfam probe subset writes exhausted disk (~Errno 28) mid genome 2 of 5; after cleanup, finished N=3 with call-tree scrubbing. Stock was *not* over 20 min; reduction is a **disk** limit, recorded in `n_reduced_reason`.
- Seeds: `20261336` proteomes; `20261338` stock-probe marker; `20261339` reserved unused.

| Genome | A stock s | B (no store) s | C (store) s | C store | Layer A | Layer C | vs stock |
|--------|-----------|----------------|-------------|---------|---------|---------|----------|
| GCF_003018855.1 | ~66.8 | 324.5 | 361.7 | **stored** | stored/stored | — | tbl+domtbl OK |
| GCF_004377995.2 | 71.8 | 338.0 | 352.0 | **confirm_fail** | hit/hit | partial_fail_whole_probe_fallback | OK |
| GCF_045689345.1 | 71.5 | 342.1 | 347.0 | **confirm_fail** | hit/hit | partial_fail_whole_probe_fallback | OK |

Confirm-fail reason (both later genomes):  
`domtbl: column 11 stored member 'per_key_row_count' does not rescale parts to whole on this sample`  
(tbl verified; Layer C fell back to whole probe). Safety held: every arm body-identical to stock.

Accessions + sha256: see `p2c_realistic.json` → `genomes`.

## q, layer costs, projection

- **q = 0.0** (0/2 genomes after the first reused). Source: laptop arm C `contract_store` outcomes.
- **V (laptop):** mean `contract_confirm_wall_s` ≈ 21.6 s on confirm_fail genomes.
- **L (laptop):** Layer A parse saving on hit vs first stored; scaled to W5x by `P_w5x / mean_laptop_probe`.
- **Projection** (W5x walls; formula as specified; **does not assume q=1**):

```
batch(N) = F1 + (N-1)*[q*(G+V)+(1-q)*(F+V)] - (N-1)*L
rho(N) = batch(N)/(N*T)
```

| Symbol | Value | Source |
|--------|-------|--------|
| T | 241.36 s | W5x stock = 1013.7/4.20 |
| F = F1 | 1013.7 s | W5x first-run total_s |
| G | 475.2 s | F − P; P = 538.5 probe |
| V | ~77.2 s | laptop confirm × (538.5 / mean B probe) |
| L | ~121.1 s | laptop parse saving × same scale |
| q | 0.0 | laptop reuse fraction |

| N | ρ(N) |
|---|------|
| 1 | 4.20 |
| 5 | 4.05 |
| **20** | **4.03** |
| 100 | 4.02 |

## GATE (CARC go / no-go)

**NO-GO.**

Reasons (bar fixed; no redesign):

1. **q = 0.0 < 0.8** at realistic size (full Pfam, N=3).
2. **Projected ρ(20) = 4.03 > 2.5.**

GATE R held; outputs stock-identical; controls green. The blocking failure is **reuse**: genome-1’s stored `domtbl` col-11 `per_key_row_count` does not verify on later genomes’ samples (observed disagreement, not a weak-vs-strong inference artifact). Layer A hits on later genomes but does not move ρ enough with q=0. Layer B never refined (confirm failed first). Layer C correctly isolated the failing table and fell back.

**Stated limitation:** with verification-as-contradiction and layers A–C as implemented, shared-contract reuse did not clear q≥0.8 / ρ(20)≤2.5 on this full-Pfam laptop pilot. Per prompt: no further redesign in this time box.

## Commits (P2c)

1. `9191f91` — verify stored contracts; diagnosis/calibration  
2. `5ef4fd5` — layered sharing A/B/C + tests  
3. (this tip) — P2c pilot script, results, report  

## Paste-back Final SHA

After the tip commit that adds this report and `p2c_realistic.json`, set:

**Final SHA:** `2f8a96f0498c70a3f874ea15421842a859cd3a37`
