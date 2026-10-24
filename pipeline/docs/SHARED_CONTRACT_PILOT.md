# Shared contract — laptop pilot (P2)

**Status:** PILOT (shape / gate / safety). Not a paper result. No CARC.  
**Branch:** `exp/shared-contract`. Scratch: `~/tmp/tare_sharedcontract_p2/`.  
**Artifact:** `pipeline/results/shared_contract/pilot.json`.

## Known projection issue (hub)

| Case | ρ(20) | Assumptions |
|------|-------|-------------|
| Design headline | **1.29** | Share parse + probe + pin once; ignore confirm tax |
| Design conservative | **2.08** | Share probe only; re-pay pin (+ parse) every genome; no confirm tax |
| **Code as built** | **≈2.74** (PROJECTED on W5x + laptop confirm/probe ratio) | Skip full probe on reuse; pay reduced-n confirm; **always re-run pin check**; parse always runs |

The code implements the conservative pin policy (never publishes `pin_checks`; pin check every genome). Headline 1.29 assumes shared pin check and is **not** what shipped.

## Data (seeded; disclosed)

| Item | Value |
|------|-------|
| Primary seed | `20261332` (also `SEED_B` in `tests/test_shared_contract.py`) |
| Proteome draw | `20261334` → 5 accessions from `data/recurrence/A`, 300 proteins each |
| Pfam subset | `20261335` → 3000 models from `data/hmmer/Pfam-A.hmm.gz` (full = 30134) |
| Update ref (GATE R) | `20261336` → drop 40 / add 40 models |
| Why not full Pfam | Full proteome × full Pfam-A at 2 threads would exceed 10 min (protocol → ≥3000-model subset) |
| Threads / nice | `--cpu 2`, `nice -n 10` |

Accessions (seeded order for arm C):  
`GCF_025782825.1`, `GCF_049949335.1`, `GCF_052882435.1`, `GCF_055382035.1`, `GCF_057098645.1`.

## GATE R (blocking)

Fill + update **without** `--contract-store`: `origin/main` (`b3cd9ad`) vs branch.

- Stripped `decision.txt`: **match** (fill and update).
- Output tables: **body sha256 match** (comment-stripped). Raw file sha256 differs only in hmmscan footer comments (Query/Target paths, cwd, Date).
- **GATE R = PASS.** No TARE code change required.
- Re-checked P1 G-a (`tests/test_shared_contract.py` 7 passed) and G-d (no default import of `acts.contract_store`).

## Pilot batch (arms A / B / C)

All five genomes: arm B and arm C outputs **body-identical to stock** (arm A).

| Genome | A stock s | B (no store) | C (store) | C status | Confirm tax s |
|--------|-----------|--------------|-----------|----------|---------------|
| GCF_025782825.1 | ~4.6 | ~28.2 SHIP | ~31.0 SHIP | **stored** | — |
| GCF_049949335.1 | ~4.8 | ~30.8 SHIP | ~18.8 SHIP | **reused** | ~5.75 |
| GCF_052882435.1 | ~4.6 | ~30.6 SHIP | ~38.9 SHIP | **confirm_fail** → full probe | ~5.66 |
| GCF_055382035.1 | ~5.1 | ~31.6 SHIP | ~36.2 SHIP | **confirm_fail** | ~5.17 |
| GCF_057098645.1 | ~4.7 | ~31.7 SHIP | ~34.8 SHIP | **confirm_fail** | ~5.17 |

Mean full probe (arm B `probe_wall_s`) ≈ 17.5 s. Mean confirm ≈ 5.4 s → ratio ≈ **0.31**.  
Confirm-fail reasons: `table 'tbl'|'domtbl' column roles/members disagree` — safety path held (stock-identical). First-writer-wins then overwrite on confirm_fail (`contract_store_write: stored`).

Laptop walls are **shape only**.

## Safety checks

1. **Contradiction:** poison stored roles → follow-up `confirm_fail`, SHIP, stock-identical. **PASS.**
2. **Key isolation:** `-E 10` vs `--cut_ga` → not `reused` (stored/REFUSE path). Different Pfam subset release → not `reused`. **PASS.**
3. **Pin-check sharing (evidence only; policy unchanged):** all five genomes ran `pin_check_s` ≈ 4.7–5.1 s and SHIP. Conclusion (ok) identical here; could still differ on empty/sparse samples or hit-set layout.  
   - **For sharing:** W5x pin is 151.8 s; if ok is stable given confirmed size members + same pin template, sharing approaches headline ρ.  
   - **Against:** pin check samples **this** genome; design already marks `pin_checks` cross-genome-unsafe. Hub decides.

## PROJECTED ρ(N) (W5x walls; laptop ratio)

Stock \(T = 1013.7/4.20 = 241.36\) s. Probe \(P=538.5\). Confirm tax \(C = P \times 0.3115 \approx 167.7\) s.

**As built** (share full probe only on reuse; pay \(C\); re-pay pin inside per-genome remainder):

\[
\mathrm{batch}(N)=1013.7+(N-1)\big((1013.7-538.5)+C\big),\quad
\rho(N)=\frac{\mathrm{batch}(N)/N}{T}
\]

| N | Headline (shared pin, no C) | Conservative (no C) | **Code + confirm tax** |
|---|----------------------------|---------------------|-------------------------|
| 1 | 4.20 | 4.20 | 4.20 |
| 5 | 1.75 | 2.42 | **2.97** |
| 20 | **1.29** | **2.08** | **2.74** |
| 100 | 1.17 | 1.99 | 2.68 |

GATE 1 bar ρ(20)≤3.15: code+tax **2.74 still PASS**, but **confirm_fail on 3/5** genomes means real batch savings can be far weaker than reuse-every-genome. Prompt 3 must measure reuse rate, not only ρ under forced reuse.

## Proposed pre-registration (prompt 3)

- **Where:** CARC exclusive EPYC 7542 (same class as W5x).
- **N:** 1, 5, 20 genomes; **r = 3** replicates.
- **Arms:** (A) stock hmmscan; (B) TARE first-run no store; (C) TARE first-run `--contract-store`, fixed seeded order.
- **Pass:** every output body byte-identical to stock; report measured ρ(20) with CI; record per-genome `stored|reused|confirm_fail` and confirm wall.
- **Controls:** argv isolation (`--cut_ga` vs `-E`); release isolation; one poisoned-store contradiction must `confirm_fail` + stock-identical.
- **Pin policy:** unchanged (per-genome pin check); optional *evidence* log of pin ok across genomes for hub.
- **Primary metric:** ρ(20) under arm C vs A; secondary: reuse fraction.
- **Kill:** any stock mismatch; or ρ(20) CI entirely above 3.15 with reuse fraction disclosed.
