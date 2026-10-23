# Decisions log — TARE 1.0

Format: date · decision · options · choice · who.

---

## 2026-10-22 — Release branch and worktree

- **Options:** work on shared `main` checkout · isolated worktree.
- **Choice:** worktree `/Users/joshuaterranova/Desktop/CSCI270/ACTS-release`, branch `release/1.0` from `origin/main` @ `de1527c155cbf53c9042c140d2ebeb295e1858d8`. Never edit the shared checkout; never `git worktree remove` without checking ignored data.
- **Who:** Lead engineer (session), standing rules.

## 2026-10-22 — Product shape for 1.0 (provisional)

- **Options:** (a) local console + CLI only · (b) shared lab server with institutional login in 1.0.
- **Choice:** **(a)** until Josh confirms D8. No hosted multi-user service in the default plan.
- **Who:** Lead engineer recommendation; Josh confirmation pending (`DECISIONS_NEEDED.md` D8).

## 2026-10-22 — Console source not on branch

- **Options:** copy untracked prototype into `release/1.0` without commit · wait for Josh to commit to `main` · stop console work.
- **Choice:** **Stop console work on the release branch** until Josh commits source (or authorizes the copy). Standing rule S1.
- **Who:** Lead engineer; **Josh owes S1**.

## 2026-10-22 — Research engine remains source of truth

- **Options:** reimplement reuse/safety in product code · call `pipeline/acts`.
- **Choice:** product calls `acts`; no reimplementation. Packaging may add a `tare` entry point that aliases the same code.
- **Who:** Standing rules / Josh brief.
