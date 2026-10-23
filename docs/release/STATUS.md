# TARE 1.0 release status

**Updated:** 2026-10-22  
**Branch:** `release/1.0` · **Worktree:** `/Users/joshuaterranova/Desktop/CSCI270/ACTS-release`  
**Start HEAD:** `de1527c155cbf53c9042c140d2ebeb295e1858d8`

## Phase board

| Phase | Status | Notes |
|-------|--------|-------|
| 0 Decisions | **IN PROGRESS** | `DECISIONS_NEEDED.md` written; Josh summary owed |
| 1 Foundation | **STARTED** | Packaging + shared row classifier; console **BLOCKED (S1)** |
| 2 Clusters | not started | Needs D2 questionnaire answers + sbatch yes |
| 3 Trust | not started | Needs campaign plan + CARC yes |
| 4 Usability / docs | not started | |
| 5 Partner beta | not started | Needs Josh + D16 |
| Release gates | not met | |

## Blockers on Josh

1. **S1** — Commit `tools/tare-console` source to `main` (exclude `state/`), or authorize copy onto `release/1.0`.
2. **S2** — Confirm no conflicting CARC jobs before additive packaging lands (ControlMaster to `discovery` was down at session start; could not poll).
3. **D1–D16** — See `DECISIONS_NEEDED.md` (license, matrix, distribution, telemetry, scale, fetch URLs, beta terms).

## Defaults in force

Local single-user console + CLI; Linux x86_64 + macOS arm64; Python ≥3.10,<3.13; HMMER/Infernal ship-with-reuse; DIAMOND/BLAST+ decline; no telemetry; no publishing; Josh-only partner contact.

## Evidence this session

- Worktree created from `origin/main` (shared checkout was 47 commits behind).
- Research suite: 413 tests collected on worktree.
- Console prototype present on shared Mac checkout only (`engine.py` 1792 lines, `server.py`, `static/`); **absent from this branch**.
- Known console defect confirmed in shared copy: `compare_bodies` keys on first 4 whitespace tokens (`engine.py`), not the HMMER tbl/dom classifier in `pipeline/scripts/headline_carc_measured.py`.

## Next engineering (while waiting)

1. Shared `acts.row_diff` classifier + tests; research scripts import it.
2. Installable package: keep `python3 -m acts`; add `tare` CLI entry point (additive).
3. Stop console hardening until S1 clears.
