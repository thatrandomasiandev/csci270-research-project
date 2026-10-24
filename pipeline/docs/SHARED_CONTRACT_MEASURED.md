# Shared contract — CARC measured pre-registration (2026-10-24)

**Status:** PRE-REGISTERED. No measured wall below is a result until
`pipeline/results/shared_contract/measured.json` is committed after the
CARC job finishes. Written after P2d GO and before any measured sbatch.

**Branch:** `exp/shared-contract`. Scratch:
`/scratch1/$USER/tare-sharedcontract/`. Stage:
`/project2/biyik_1165/jjt_373/csci270-star/tare-sharedcontract/`.
Account: `biyik_1173`. Never edit `pipeline/paper/tare/main.tex`.

## Gate that unlocked this run (P2d)

| Check | Value | Source |
|-------|-------|--------|
| GATE R | PASS | `results/shared_contract/p2d_gate_r.json` |
| CONFIRM_N | **10** | `results/shared_contract/p2d_confirm_n.json` |
| Laptop reuse q | 1.0 (4/4 after first) | `results/shared_contract/p2d_realistic.json` |
| PROJECTED ρ(20) | 1.85 ≤ 2.5 | P2d report (W5x walls + measured q) |

Laptop walls are shape only. This pre-registration is the CARC timing
claim.

## What stays per genome (unchanged)

- Per-genome pin check (never share `pin_checks` across genomes)
- Neighbor + random pads (IC2)
- Bounded audit (default path; `audit_bound`, size 299 when applicable)
- Per-genome row cache; discovery / replay / render
- Default path without `--contract-store` (GATE R already PASS)

## Seeds (this workstream: 20261341–20261349)

| Seed | Role |
|------|------|
| **20261341** | Proteome draw |
| **20261342** | Bootstrap CIs for ρ(N) |
| 20261343 | Smoke Pfam-subset model draw |
| 20261344 | Poisoned-store control |
| 20261345–20261349 | Reserved unused |

## Proteome draw (locked)

File: `pipeline/results/shared_contract/measured_draw.json`.

- Pool: `pipeline/data/recurrence/A/*_protein.faa.gz` minus every
  accession in `exclude_reasons` (headline `EXCLUDE_REASONS` + headline
  `DRAWS`, diverse pilot+measured, W8 pilot+measured, W12a
  pilot+measured, shared-contract P2/P2c/P2d pilots).
- `pool_n = 27`, `pool_sha256 =
  adaa36290e628443b08d8e7a47750177968f4104225ac81493d165bce3f62e21`
  (local recurrence/A; CARC must match before sbatch).
- `sorted(random.Random(20261341).sample(pool, 20))` → the twenty
  accessions listed in `measured_draw.json` `draws`.
- Nested N: **N = 1, 5, 20** use the first 1 / 5 / 20 of that sorted
  draw (same prefix). Fresh data: none of these accessions appear in
  prior headline / diverse / W8 / W12a / shared-contract pilots.

## Workload (headline-matched)

- Full bacterial proteomes (not protein subsets).
- Full Pfam-A 38.2 (`Pfam-A.hmm.gz`), pressed once per job.
- HMMER **3.4** from the pinned tarball
  (`sha256 ca70d94fd0cf271bd7063423aabb116d42de533117343a9b27a65c17ff06fbf3`).
  Module HMMER is not used.
- Argv (stock and TARE tool remainder), same as headline measured:
  `hmmscan --cut_ga --noali --cpu 4 --tblout {output:tblout}
  --domtblout {output:domtblout} -o /dev/null {reference} {input}`
- TARE: `--strategy reference --pin '-Z {entry_count}' --verify audit
  --prep 'hmmpress -f {reference}'` and, for arm C only,
  `--contract-store DIR`. `CONFIRM_N = 10` (code default after P2d).

## Arms

| Arm | Meaning |
|-----|---------|
| A | Stock `hmmscan` (pressed Pfam) |
| B | TARE first run, **no** `--contract-store` (fresh per-genome cache) |
| C | TARE first run with `--contract-store` (one store per (N, replicate)) |

Order within each N: for replicate `r = 0..2`, run **A then B then C**
(alternating stock / TARE pairs as A–B and the store arm C after B).
r = 3. Crash → write partial JSON and exit non-zero; do not silently
retry.

## Pass / fail / inconclusive

- **Pass (exactness):** every B and C table body (comment-stripped) is
  identical to the paired stock A body for that genome and replicate.
  Difference classes on failure: value-only / different row / missing /
  extra / order (same vocabulary as headline).
- **Stock-vs-stock:** before timing arms for N=1, two stock runs on
  draw[0] must body-match; else STOP.
- **Primary metric:**  
  \(\rho(N) = T_C(N) / T_A(N)\)  
  where \(T_A(N)\) is the sum of arm-A walls over the N genomes in one
  replicate and \(T_C(N)\) is the arm-C batch wall (store cold at the
  first genome). Report mean over r=3 and a 95% percentile bootstrap CI
  (10 000 resamples of the three replicate ρ values, seed **20261342**).
  Same for N ∈ {1, 5, 20}.
- **Secondary:** reuse fraction \(q\) among genomes 2..N on arm C
  (`contract_store: reused`); mean `contract_confirm_wall_s` on reused
  genomes; Layer-A saving (parse_s first stored genome vs mean parse_s
  on reused genomes, when phases present).
- **INCONCLUSIVE (not KILL):** power failure (empty bodies, or fewer
  than the locked N genomes completed) with exactness still holding on
  completed rows.
- **KILL:** any stock mismatch on a completed genome; or poisoned-store
  / isolation control failure.

## Controls (must run before scoring ρ)

1. **Poisoned store:** write a store entry with corrupted column roles;
   next genome with `--contract-store` must `confirm_fail` (or equivalent
   non-reuse), fall back to full probe, and stay body-identical to stock.
2. **Argv isolation:** store filled under `--cut_ga`; follow-up with
   `-E 10` instead of `--cut_ga` must not `reused`.
3. **Release isolation:** store filled on full Pfam; follow-up on a
   disjoint smoke-sized Pfam subset must not `reused`.

Controls may use a short Pfam subset and the first smoke genome; they
are correctness, not speed evidence.

## Smoke (blocking, non-exclusive)

- N = 2 (first two of the locked draw), r = 1, Pfam subset of 500 models
  (seed 20261343), arms A/B/C, same exactness rule.
- Must PASS before the exclusive measured job is allowed to start
  (`--dependency=afterok:<smoke>`).
- Measured also waits `--dependency=afterany:13260162` (W13 array).

## Node shape and time

- Measured: `#SBATCH --account=biyik_1173 --exclusive --mem=0
  --constraint=epyc-7542`, one prepared Pfam per job.
- Time: never under 8 h for whole-genome HMMER timing. Measured is an
  array of three exclusive tasks (N=1, N=5, N=20), each with r=3,
  sized from W5x shape × 1.5 with an 8 h floor:

  | Task | N | `#SBATCH --time` |
  |------|---|------------------|
  | 0 | 1 | `08:00:00` |
  | 1 | 5 | `24:00:00` |
  | 2 | 20 | `72:00:00` |

  Smoke: `#SBATCH --time=02:00:00`, not exclusive.
- Exclusive node cap ≤ 6; measured array uses `%1` after W13 so it does
  not stack with remaining W13 slots. Do not cancel or modify live jobs
  `13260162_*`, `13347581`, `13347608`, `12864756`.

## Outputs

- Smoke: `results/shared_contract/smoke_<jobid>.json` on CARC, copied to
  `pipeline/results/shared_contract/smoke.json` when collected.
- Measured per task: `results/shared_contract/measured_N{1,5,20}_<jobid>.json`
  on CARC; hub merges into `pipeline/results/shared_contract/measured.json`
  (provenance: git HEAD, dirty flag, node, HMMER sha256, pool sha256,
  draw, seeds, CONFIRM_N, every arm wall, contract_store status,
  exactness, ρ(N)+CI, q, confirm walls, Layer-A saving, controls).

## Proposed paper integration (after results exist)

Hub (W3) only. Experiment agent supplies proposed sentences with
`% source:` keys; does not edit `main.tex`.
