# Shared contract P2d report — verification false-rejection fix + re-pilot

**Final SHA:** `d6cb014bd6ac993d0f93cff1a5d61722ed512a7a`  
**Branch:** `exp/shared-contract`  
**Scratch:** `~/tmp/tare_sharedcontract_p2d/`  
**No CARC. No paper edits.** Laptop walls are shape only.

## Reproduction (Priority 1)

Genome **GCF_004377995.2**, full Pfam-A, `CONFIRM_N=25` sample (pre-recalibration), seed `PROBE_SEED`.

| Contract | All-tables `verify_stored_fit` | Layer-C per-table `[domtbl]` only |
|----------|--------------------------------|-------------------------------------|
| Stored (genome 1) | **ok=True** | **ok=False** — `domtbl: column 11 stored member 'per_key_row_count' does not rescale…` |
| Own (genome 2 b_cache) | **ok=True** | **ok=False** — same reason |

Stored and own domtbl signatures are identical: `index_col=9`; col 11 `per_key_row_count` / `count_table=tbl`; col 12 `entry_count`.

Differing rows under broken Layer-C φ: **46/46** aligned c-Evalue rows. Sibling keys under Layer-C: `['domtbl']` only (tbl missing → φ=NaN). With correct tbl counts, **46/46** accept (example: `WP_000019512.1` part=1, part=`8.9e-74`, whole=`1.8e-73`, φ_correct=2.0, tbl counts part/whole=1/2). Evidence: `~/tmp/tare_sharedcontract_p2d/repro/p2d_repro.json`.

## Root cause

Layer-C called `verify_stored_fit([one_table])`, which built `per_key_row_count` sibling row-counts only from that table. For domtbl col 11, `count_table='tbl'` was invisible, φ was NaN, and a contract identical to the genome’s own (and stock-safe) was falsely rejected. Not genome dependence. Recorded in `SHARED_CONTRACT_DESIGN.md` §6.

## Fix

1. `verify_stored_fit` builds sibling counts once from `count_key_tables` (default: full stored list), and accepts members via the probe’s `_candidate_fits` predicate.
2. Layer-C **accepts** with the full stored table list; per-table diagnosis passes `count_key_tables=full`.
3. Regression: `test_verify_per_key_row_count_needs_sibling_count_table` (positive full + siblings; negatives: poison identity, wrong member, wrong count_table; documents the old one-table failure shape).

Default path (no `--contract-store`) unchanged. Commit: `40e3a8d`.

## n calibration (full Pfam-A)

Script: `scripts/shared_contract_calibrate_confirm_n_p2d.py`.  
Evidence: `results/shared_contract/p2d_confirm_n.json`.  
Genomes with own fits: GCF_003018855.1, GCF_004377995.2, GCF_045689345.1. Seed `PROBE_SEED`.

| n | self-all observed | poison caught | wrong-member caught | eligible |
|---|-------------------|---------------|---------------------|----------|
| **10** | **yes** (3/3) | **yes** | **yes** | **yes → chosen** |

Stopped at first eligible (same rule as P2b). **`CONFIRM_N = 10`**. (P2b’s n=25 was on the 3k-model subset where n=10 had vacuous `no_rows` on one genome.)

## Tests and GATE R

- Full pytest: **429 passed**, 1 skipped (after regression).
- Default import: `acts.contract_store` **not** loaded without `--contract-store`.
- GATE R (main `b3cd9ad` vs branch, no store, real HMMER fill+update): **PASS** — stripped `decision.txt` and table-body sha256 match (`p2d_gate_r.json`).

## Realistic re-pilot (Priority 4)

Same design as P2c: full Pfam-A (shared pressed file from P2c scratch), 500 proteins, seed **20261336**, arms A/B/C, layers A–C on. **N = 5** (disk allowed). `CONFIRM_N=10`.

| Genome | A stock s | B (no store) s | C (store) s | C store | Layer A | Layer C | vs stock |
|--------|-----------|----------------|-------------|---------|---------|---------|----------|
| GCF_003018855.1 | 73.8 | 344.8 | 363.1 | **stored** | stored/stored | — | tbl+domtbl OK |
| GCF_004377995.2 | 72.2 | 345.5 | 216.5 | **reused** | hit/hit | all_tables_verified | OK |
| GCF_045689345.1 | 68.5 | 335.8 | 222.6 | **reused** | hit/hit | all_tables_verified | OK |
| GCF_046107165.1 | 72.4 | 345.9 | 220.3 | **reused** | hit/hit | all_tables_verified | OK |
| GCF_048404355.1 | 70.4 | 344.2 | 219.6 | **reused** | hit/hit | all_tables_verified | OK |

- **q = 1.0** (4/4 after first). Source: laptop arm-C `contract_store`.
- **V (laptop):** mean `contract_confirm_wall_s` ≈ 15.5 s on reused genomes.
- **L (laptop):** parse_s saving first vs later Layer-A hit ≈ 32.1 s.
- Every arm body-identical to stock.

### Projection (W5x; measured q)

```
batch(N) = F1 + (N-1)*[q*(G+V)+(1-q)*(F+V)] - (N-1)*L
rho(N) = batch(N)/(N*T)
```

| Symbol | Value | Source |
|--------|-------|--------|
| T | 241.36 s | W5x stock = 1013.7/4.20 |
| F = F1 | 1013.7 s | W5x first-run total_s |
| G | 475.2 s | F − P; P = 538.5 probe |
| V | ~54.9 s | laptop confirm × (538.5 / mean B probe) |
| L | ~113.8 s | laptop parse saving × same scale |
| q | 1.0 | laptop reuse fraction |

| N | ρ(N) |
|---|------|
| 1 | 4.20 |
| 5 | 2.22 |
| **20** | **1.85** |
| 100 | 1.75 |

## GATE (CARC go / no-go)

**GO.**

Reasons: GATE R PASS; all controls green; every output stock-identical; **q = 1.0 ≥ 0.8**; **projected ρ(20) = 1.85 ≤ 2.5**.

## Free disk

| When | Free |
|------|------|
| Session start (before P2d work) | ~72 GB |
| Pilot start (recorded) | **40.9 GB** (after calib call trees; scrubbed before batch) |
| Pilot end | **47.8 GB** |
| Report write | ~48 GB |

## Priorities finished

| Priority | Status |
|----------|--------|
| P1 reproduce + root cause | **Done** |
| P2 fix + n calibration | **Done** (`CONFIRM_N=10`) |
| P3 tests + GATE R | **Done** |
| P4 realistic re-pilot N=5 | **Done** → **GO** |

## Open issues

- Layer-A refside cache keeps a prepared full Pfam copy under the contract store (~6.6 GB on this laptop); scrub policy is per-genome call trees only.
- `hmmpress` next to a symlinked HMM wrote duplicate `.h3*` sidecars under p2d/pfam/; prefer invoking prep on the real path only.
- Calibration evidence table covers the first eligible n only (n=10); larger candidates not re-run after eligibility (same stop rule as P2b).
- Laptop walls are never speed evidence; CARC still required for headline ρ.

## Commits (P2d)

1. `40e3a8d` — fix Layer-C sibling counts + regression test + design §6  
2. `1afdb4c` — `CONFIRM_N=10`, calibration script/JSON, pilot harness  
3. *(this tip)* — P2d realistic results + this report  

## Paste-back Final SHA

After the tip commit that adds this report and `p2d_realistic.json`:

**Final SHA:** `d6cb014bd6ac993d0f93cff1a5d61722ed512a7a`
