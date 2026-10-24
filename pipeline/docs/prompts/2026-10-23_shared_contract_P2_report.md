# Shared contract P2 report — laptop pilot (2026-10-23)

## Final SHA

`57ffee1077541959c74bf70d598b63f02ea848e9` — branch `exp/shared-contract`, worktree `../ACTS-sharedcontract`.

Base `origin/main`: `b3cd9ad32269c01880f4e2819b26f7fdd8d14cf8`.  
P1 tip before this pilot: `86adef392f632a427a034cbe125637bae8482c37`.

No paper edits. No CARC. No downloads/installs. Scratch `~/tmp/tare_sharedcontract_p2/`.

## Known issue: ρ(20) 1.29 vs 2.08

| Projection | ρ(20) | Matches code? |
|------------|-------|---------------|
| Design headline (share parse+probe+**pin**) | **1.29** | **No** — pin check is re-run every genome |
| Design conservative (share probe only) | **2.08** | Closer; still omits confirm tax |
| **Code as built + laptop confirm/probe ratio on W5x** | **≈2.74** | **Yes** |

## GATE R

Fill + update without `--contract-store`, main (`b3cd9ad`) vs branch.

| Check | Result |
|-------|--------|
| Stripped decision.txt | Match (fill & update) |
| Table **body** sha256 | Match |
| Decisions | SHIP / SHIP both sides |
| **GATE R** | **PASS** |

Initial raw-file table sha256 FAIL was only hmmscan comment footers (paths, cwd, Date). Bodies identical. No TARE fix. Re-ran G-a (7 passed) and G-d (contract_store not imported on default path). G-b/G-c left as P1 artifacts (no code change).

## Arms A / B / C (N=5, seed 20261332)

Pfam: seeded **3000** models (`20261335`). Proteins: **300**/genome (`20261334`). Order fixed for arm C.

| Accession | A s | B s / dec | C s / dec | C store | Confirm s |
|-----------|-----|-----------|-----------|---------|-----------|
| GCF_025782825.1 | 4.59 | 28.22 SHIP | 31.02 SHIP | stored | — |
| GCF_049949335.1 | 4.83 | 30.83 SHIP | 18.84 SHIP | **reused** | 5.75 |
| GCF_052882435.1 | 4.64 | 30.61 SHIP | 38.88 SHIP | confirm_fail | 5.66 |
| GCF_055382035.1 | 5.11 | 31.56 SHIP | 36.18 SHIP | confirm_fail | 5.17 |
| GCF_057098645.1 | 4.68 | 31.68 SHIP | 34.78 SHIP | confirm_fail | 5.17 |

All B/C outputs body-identical to stock. Confirm tax / full probe ≈ **0.31** (laptop shape).

## Safety

| Check | Result |
|-------|--------|
| Contradiction (poisoned store) | confirm_fail + SHIP + stock-identical **PASS** |
| Key isolation (argv `-E 10`, other release) | not reused **PASS** |
| Pin-check evidence | pin ran all 5 (~4.7–5.1 s), all SHIP; hub owns share-or-not |

## PROJECTED ρ(N) (formula)

\(T=241.36\), \(P=538.5\), \(C=P\times 0.3115\approx 167.7\):

\[
\mathrm{batch}(N)=1013.7+(N-1)((1013.7-P)+C),\quad \rho(N)=(\mathrm{batch}/N)/T
\]

| N | Headline 1.29-case | Conservative 2.08-case | **Code+tax** |
|---|--------------------|------------------------|--------------|
| 1 | 4.20 | 4.20 | 4.20 |
| 5 | 1.75 | 2.42 | 2.97 |
| 20 | 1.29 | 2.08 | **2.74** |
| 100 | 1.17 | 1.99 | 2.68 |

Caveat: **3/5 confirm_fail** on this toy — prompt 3 must measure reuse fraction.

## Proposed prompt-3 pre-registration

CARC exclusive EPYC 7542; N∈{1,5,20}; r=3; arms A/B/C; pass = body-identical to stock + report ρ(20) with CI; controls = argv + release isolation + poisoned confirm_fail; pin policy unchanged; kill = mismatch or ρ(20) CI above 3.15 (with reuse rate disclosed). Details: `pipeline/docs/SHARED_CONTRACT_PILOT.md`.

## Priorities vs time box (~4.5 h)

| Priority | Status |
|----------|--------|
| P1 GATE R | **Done** (PASS) |
| P2 pilot batch | **Done** |
| P3 safety | **Done** |
| P4 projection + pre-reg | **Done** |
| Deliverables | `pilot.json`, `SHARED_CONTRACT_PILOT.md`, this report |

Not started: none within the assigned priorities.
