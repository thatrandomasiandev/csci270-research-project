# Decisions Josh owes — TARE 1.0

**Branch:** `release/1.0` · **Worktree:** `../ACTS-release`  
**Start HEAD:** `de1527c155cbf53c9042c140d2ebeb295e1858d8` (origin/main tip at worktree create)  
**Updated:** 2026-10-22

Reply in place (or email). Until answered, engineering continues on defaults marked **RECOMMEND**. Items marked **STOP** block shipping that path.

---

## STOP — must answer before product code lands on the branch

### S1. Commit `tools/tare-console`
The mockup console (`engine.py`, `server.py`, `static/`) exists **only as untracked files** on the shared Mac checkout. It is **not** on `origin/main` and therefore not on `release/1.0`.

**Ask:** Commit the **source** (not `state/`, not SQLite, not run outputs) to `main`, or explicitly authorize copying those source files onto `release/1.0`.

Without this, Phase 1 console hardening cannot proceed on the release branch.

### S2. Rename / packaging while other CARC jobs run
Phase 1 wants an installable `tare` package while keeping `python3 -m acts` as a thin alias.

**Ask:** Any CARC jobs from other sessions still running that would break if we add packaging / entry points (not renaming `pipeline/acts/` paths yet)?  
**RECOMMEND:** Proceed with additive packaging (`tare` CLI + `acts` alias) without renaming directories until you confirm the queue is clear.

---

## License and partners

### D1. License
What license for TARE 1.0 source and redistributable binaries?

Options: MIT · Apache-2.0 · BSD-3 · GPL-3 · other (name it).

**Also:** Does USC IP / tech-transfer, or any partner agreement, constrain the license or require review before public release?

**STOP for:** PyPI, bioconda, container registries, GitHub Release, public website.

### D2. Partner environments
Fill or return the questionnaire: [`PARTNER_QUESTIONNAIRE.md`](PARTNER_QUESTIONNAIRE.md).

Needed per lab (Columbia, Harvard, USC, UCLA, …): cluster name, scheduler, OS, container runtime, shared FS type, compute-node internet, typical references and input sizes.

**STOP for:** site-specific Slurm profiles and “selftest on partner cluster” gate.

### D3. Who may contact partners
Confirm: engineering never contacts partner labs; Josh relays onboarding kits and collects beta manifests.

**RECOMMEND:** yes (already assumed).

---

## Supported matrix (1.0)

### D4. Operating systems
**RECOMMEND:** Linux x86_64 + macOS arm64.  
Confirm or revise. Windows: out of 1.0?

### D5. Python
**RECOMMEND:** CPython 3.10–3.12 (matches current `requires-python`).  
Confirm upper bound (3.13?).

### D6. Tools
**RECOMMEND for ship-with-reuse:**
- HMMER 3.3.x and 3.4 (`hmmscan` score-thresholded / `--cut_ga` path as today)
- Infernal 1.1.x (`cmscan`, with documented check skips on long-sequence genomes)

**RECOMMEND for decline-and-full-run (supported as ordinary tool fallback):**
- DIAMOND (SAFE-REFUSE)
- BLAST+ (SAFE-REFUSE / no row-index)

Confirm. Any other tool in 1.0?

### D7. Schedulers and formats
**RECOMMEND:** Slurm only for cluster backend; PBS/SGE out of 1.0.  
Output formats: ship whatever the tool writes (tblout/domtblout/…); TARE does not invent formats.

### D8. Console deployment mode
**RECOMMEND:** 1.0 = single-user local console (`tare console` on 127.0.0.1) + headless `tare` CLI on clusters.  
**Not in 1.0:** shared lab-server with institutional login (avoids per-university IT approval of a hosted service).

Confirm.

---

## Distribution, support, data

### D9. Distribution channels (each needs yes before publish)
- [ ] PyPI (`tare` or other name — `acts` is taken; current package is `acts-memo`)
- [ ] bioconda
- [ ] Container images (Apptainer/Singularity + Docker)
- [ ] GitHub Releases (signed artifacts + checksums)
- [ ] Docs website host

### D10. Support commitment
Who answers issues? Response-time target? GitHub Issues only, or also email?

### D11. Release cadence
**RECOMMEND:** semver; patch for correctness; minor for adapters; major for guarantee changes. Confirm.

### D12. Data / telemetry policy
**RECOMMEND:** no telemetry; unpublished sequences never leave the user’s machine or cluster; beta may share **manifests only** (not sequences) if the lab opts in.

Confirm.

### D13. Scale targets
**RECOMMEND:** ≥5,000 inputs per run; full Pfam and full Rfam; caches tens of GB; resumable; bounded memory. Confirm or give numbers.

### D14. Reference download URLs
May 1.0 fetch official Pfam/Rfam releases when the user asks (with checksums), or local-file import only until you approve URLs?

**STOP for:** any network fetch of databases.

### D15. CARC validation jobs
Correctness campaign and performance re-measure need exclusive EPYC nodes. Each `sbatch` needs your yes. Approve a campaign plan when Phase 3 is ready (not now).

### D16. Beta terms
Approve beta terms text before any partner kit is sent.

---

## Defaults in force until you reply

| Topic | Default |
|-------|---------|
| Console mode | Local single-user only |
| OS | Linux x86_64 + macOS arm64 |
| Python | ≥3.10,<3.13 |
| Tools (reuse) | HMMER 3.3–3.4, Infernal 1.1.x |
| Tools (decline) | DIAMOND, BLAST+ |
| Scheduler | Slurm |
| Telemetry | None |
| Partner contact | Josh only |
| Publishing | None until D1 + D9 |
| Console source on branch | **Blocked (S1)** |
