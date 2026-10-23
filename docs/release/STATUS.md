# TARE 1.0 release status

**Updated:** 2026-10-22  
**Branch:** `release/1.0` · **Worktree:** `/Users/joshuaterranova/Desktop/CSCI270/ACTS-release`  
**Start HEAD:** `de1527c155cbf53c9042c140d2ebeb295e1858d8`  
**Tip:** `80b90de` (pushed `origin/release/1.0`)

## Phase board

| Phase | Status | Notes |
|-------|--------|-------|
| 0 Decisions | **IN PROGRESS** | `DECISIONS_NEEDED.md` written; Josh summary owed |
| 1 Foundation | **STARTED** | `acts.row_diff` + `tare` CLI landed; console **BLOCKED (S1)** |
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
- `a6c5df9` / `80b90de` on `origin/release/1.0`: Phase 0 docs; `acts.row_diff`; `tare` CLI (`version` / `run` / `selftest` / `console` stub); headline script imports shared classifier.
- Full suite: **421 passed, 1 skipped** (`cd pipeline && python3 -m pytest -q`).
- Console prototype present on shared Mac checkout only (`engine.py` 1792 lines); **absent from this branch**.
- Known console defect in shared copy: `compare_bodies` keys on first 4 tokens — must switch to `acts.row_diff` after S1.

## Next engineering (while waiting)

1. Full `pytest -q` green after docstring fix; lockfile / editable install notes.
2. Progress-event channel design (no console yet).
3. Stop console hardening until S1 clears.
