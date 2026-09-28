# CARC plan — comparison, fourth-tool, F6 (2026-09-27)

Written **before** any of the jobs below are submitted. This is the
pre-registration for Josh: every new job, `--time`, estimated actual
node-hours, account, dependencies, and the total. **Do not sbatch from
the Mac session that adds this file.** No SSH, no `sbatch`, no `scp`.

Account **`biyik_1165`**, partition `main`. Comparison and Mordred jobs
use `--constraint=epyc-7542` (same model as savings / headline job
12377262 on `b22-16`). F6 is a short **non-exclusive** Linux `strace`
job and does not need the constraint.

Predecessor: `docs/SAVINGS_PROTOCOL.md` addendum 2026-09-27 (four
interleaved savings jobs, 47 requested exclusive hours). This plan
**waits for those jobs to finish** so comparison does not compete for
the same exclusive nodes and can reuse Pfam-A already on
`/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/hmmer/`.

Locked protocols (text not edited here):

- `docs/COMPARISON_PROTOCOL.md` — arms S / T / C / TC, MATCH types, PGO
  prior ρ = 1.10, AppCDS α = 0.70 on SnpEff *a*.
- `docs/FOURTH_SCREEN.md` — corrected ceiling; Mordred CPU; Whisper
  **BLOCKED** until Josh approves model size and the PyTorch wheel.
- `docs/PROBE_EVAL_PROTOCOL.md` — Linux F6-file tracing.

`--time` formula (same as the savings addendum): **1.5 × predicted
exclusive-node wall + 1 h setup**, snapped up, except F6 (fixed 30 min)
and SnpEff (fixed 2 h, wall is minutes).

Nothing in this file is a timing claim.

---

## What this is not

- Not a submit. Not permission to open SSH or Duo.
- Not a rewrite of `docs/SAVINGS_PROTOCOL.md` or of any existing
  `jobs/*.job` / `scripts/*savings*`.
- Not arm L (LLM). Design-only in the comparison protocol.
- Not Whisper until Josh says so. Default `turbo` is >1 GB. PyTorch
  wheels can be >1 GB. `tiny` is a strawman — do not use.
- Not a >1 GB download. Pfam-A (399 MB) is reused from savings if
  present; HMMER 3.4 tarball is tens of MB; ChEMBL chemreps are
  tens–low hundreds of MB; LibriSpeech is not fetched in this plan
  because Whisper is BLOCKED.

---

## Jobs

### 0. Savings (already queued — do not resubmit)

| Job name | `--time` | Est. actual | Notes |
|----------|----------|-------------|-------|
| `sav_A_scan` | 22:00:00 | 13.8 h | exclusive epyc-7542 |
| `sav_A_search` | 07:00:00 | 3.5 h | exclusive epyc-7542 |
| `sav_B_scan` | 12:00:00 | 7.0 h | exclusive epyc-7542 |
| `sav_B_search` | 06:00:00 | 2.8 h | exclusive epyc-7542 |

Requested **47** exclusive node-hours (under the approved 56). Comparison
jobs depend on these **finishing** (`afterany` is enough: Pfam and the
collections stay on project2 even if a savings job STOPs).

### 1. Comparison — build + MATCH (`jobs/compare_build.job`)

Build **on the node** (gcc/13.3.0, x86 epyc-7542), not on the Mac.

| Knob | Lock |
|------|------|
| HMMER stock | 3.4, `CFLAGS=-O2`, default configure |
| HMMER tuned | `-O3 -march=native`, LTO, **GCC** PGO (`-fprofile-generate` / `-fprofile-use`). Mac `compare_build.py` is Clang/llvm-profdata and is **not** used as the CARC compiler driver. |
| PGO train proteome | **BW25113** `GCF_000750555.1` (`data/kprot/BW25113.faa.gz`). Not in savings collections A or B (`recurrence_accessions.json` has neither this accession nor MG1655 / W3110). Train **hmmscan `--cut_ga` and hmmsearch `-Z 1e6 --domZ 1e6`** against Pfam-A so the profile matches the timing workload. Not collections A/B FASTAs. Not the MATCH toy FASTA. |
| SnpEff T | AppCDS / CDS archive + `-XX:TieredStopAtLevel=1` + `-Xshare:on`. Jar stays at the read-only `tools/snpEff/` copy. Archive under `builds/snpeff/snpeff.jsa`. |
| MATCH | `scripts/compare_match.py` after prefixes exist (toy HMM / small VCF). Fail → **do not submit** the timing jobs. |
| JSON | `results/compare_build.json` after compile; `results/compare_match.json` after MATCH. Resumable: skip a prefix that already has `hmmscan`. |

| Job name | exclusive | `--time` | Est. actual | Account | Depends on |
|----------|-----------|----------|-------------|---------|------------|
| `cmp_build` | yes, epyc-7542, 32 CPU, 64G | **04:00:00** | **1.7 h** (3× compile ~45 min + Pfam×BW25113 PGO train ~62 min + AppCDS/MATCH) | `biyik_1165` | savings finished (Pfam on disk) |

### 2. Comparison — HMMER timing (`jobs/compare_hmmer.job`)

One exclusive node per (collection, mode). Arms **interleaved** on that
node: for each genome *k* in the locked savings order, if *k* is a
stock-sample position (`A`: 1,2,5,10,20,30; `B`: 1,2,5,10,20,40) run
**S, T, C, TC in that order**; other genomes run **C then TC** only
(S/T predicted from *a*+*b·N* and the ρ = 1.10 rider). JSON after every
arm. Restart skips complete genomes. MATCH fail → STOP that arm (S vs T
fail disables T and TC; C vs S fail STOPs the job like savings).

`--cpu 32`. Probe_n = **8** (same as the queued savings runner). Arm L
is not run.

Predicted wall uses `hmmer_predicted_speedup.json` → `savings_budget`
and ρ_PGO = 1.10 (comparison protocol, prediction, not a measurement):

| Job name | Coll | Mode | S sample | T sample | C full | TC full | Pred. wall | `--time` | Est. actual |
|----------|------|------|----------|----------|--------|---------|------------|----------|-------------|
| `cmp_A_scan` | A | hmmscan | 5.104 h | 4.640 h | 8.691 h | 7.901 h | 26.34 h | **41:00:00** | 26.3 h |
| `cmp_A_search` | A | hmmsearch | 1.052 h | 0.956 h | 2.490 h | 2.264 h | 6.76 h | **12:00:00** | 6.8 h |
| `cmp_B_scan` | B | hmmscan | 5.104 h | 4.640 h | 1.854 h | 1.686 h | 13.28 h | **21:00:00** | 13.3 h |
| `cmp_B_search` | B | hmmsearch | 1.052 h | 0.956 h | 1.720 h | 1.563 h | 5.29 h | **09:00:00** | 5.3 h |

All four: exclusive epyc-7542, 32 CPU, 64G, account `biyik_1165`.
Depend on **`cmp_build` afterok** and savings **afterany**.

JSON: `results/compare/{A,B}_{hmmscan,hmmsearch}.json`.

### 3. Comparison — SnpEff timing (`jobs/compare_snpeff.job`)

HG00099 *N* = 52,638. Warm C/TC caches from HG00096∪HG00097 (logged,
not the metric), then **n = 3** interleaved S / T / C / TC on HG00099.
MATCH record-body before the first timed T/TC. AppCDS from `cmp_build`.

| Job name | exclusive | `--time` | Est. actual | Account | Depends on |
|----------|-----------|----------|-------------|---------|------------|
| `cmp_snpeff` | yes, epyc-7542, 8 CPU, 16G | **02:00:00** | **0.3 h** | `biyik_1165` | `cmp_build` afterok |

JSON: `results/compare_snpeff.json`. STAR is **not** rerun (sealed CSV).

### 4. Fourth-tool screen — Mordred (`jobs/fourth_mordred.job`)

CPU, exclusive, small fetches (ChEMBL 32+33 chemreps, well under 1 GB).
Corrected rule in `FOURTH_SCREEN.md`: `ceiling(m) ≥ 3` **and**
`saved(m) ≥ 60 s`, measured *m*, built-in cache on (Mordred has none to
flip). No ACTS cache. No speedup claim. Seed **20260927**. *N* = 20,000.
Sizes `{1, 200, 1000, 5000, N}`. 3 runs. `w` = no-op that writes an
empty-but-valid CSV header. New files under `data_carcjobs/`
(gitignored), never under shared `data/`.

Moriwaki 2018 puts 2D-all on drug-like molecules at ~0.05–0.5 s/mol.
At 0.10 s/mol the size grid is ~2.2 h of timed wall; at 0.5 s/mol it
approaches 11 h. `--time` uses the slow end plus setup.

| Job name | exclusive | `--time` | Est. actual | Account | Depends on |
|----------|-----------|----------|-------------|---------|------------|
| `fourth_mordred` | yes, epyc-7542, 32 CPU, 32G | **12:00:00** | **3 h** (0.1 s/mol class; pad covers slower *b*) | `biyik_1165` | none |

JSON: `results/fourth_screen.json` (Whisper key = `BLOCKED`).

### 5. Fourth-tool screen — Whisper (`jobs/fourth_whisper.job`) — **BLOCKED**

Written so the script exists. **Do not submit.**

Josh must approve:

1. Model size stays `--model small` (~466 MB). Not `turbo` / `medium` /
   `large`.
2. `pip install openai-whisper` PyTorch wheel. **If the wheel is >1 GB,
   do not install.**

`scripts/submit_fourth.sh` **refuses** to submit this job unless
`ACTS_WHISPER_SUBMIT=1`. Even then this plan still says **BLOCKED**.
The job script itself exits 2 unless `ACTS_WHISPER_APPROVED=1`.

Requested node-hours: **0**. Estimated actual: **0**.

### 6. F6 tracing (`jobs/f6_trace.job`)

Short **non-exclusive** Linux job. Runs
`scripts/run_f6_trace_linux.py` (`strace`). **Do not modify that
script.** It writes `results/probe_eval_f6file_linux.json`. The job
copies the same bytes to `results/f6_trace_linux.json`.

| Script path (do not edit) | Job landing path |
|---------------------------|------------------|
| `results/probe_eval_f6file_linux.json` | `results/f6_trace_linux.json` |

| Job name | exclusive | `--time` | Est. actual | Account | Depends on |
|----------|-----------|----------|-------------|---------|------------|
| `f6_trace` | **no** (2 CPU, 8G) | **00:30:00** | **0.1 h** | `biyik_1165` | none |

If `snpEff.config` / `snpEff.jar` are on disk, the script also traces
that config into the namespace; otherwise it records `skipped`.

---

## Totals (Josh: approve before any sbatch)

Exclusive comparison + Mordred only (Whisper = 0, F6 not exclusive):

| Bucket | Requested (`--time` sum) | Estimated actual |
|--------|--------------------------|------------------|
| `cmp_build` | 4 h | 1.7 h |
| HMMER compare (4 jobs) | 41+12+21+9 = **83 h** | 26.3+6.8+13.3+5.3 = **51.7 h** |
| `cmp_snpeff` | 2 h | 0.3 h |
| `fourth_mordred` | 12 h | 3 h |
| Whisper | **0 (BLOCKED)** | 0 |
| **New exclusive total** | **101 h** | **56.7 h** |
| F6 (shared, not exclusive) | 0.5 h wall | 0.1 h |
| Savings already requested | 47 h | ~27 h |

Do not overlap the new exclusive jobs with the four savings jobs.
After savings drain, **101 exclusive node-hours** is the ask for this
plan. The 1.5× pad is slack for real *N_i* and for PGO compile.

**Do not submit if `biyik_1165` cannot absorb 101 h on top of whatever
savings still has running.**

---

## Submit helpers (dry-run only in the writing session)

From the repo root, after VPN (later session):

```
pipeline/scripts/submit_compare.sh --dry-run
pipeline/scripts/submit_fourth.sh --dry-run
pipeline/scripts/submit_f6.sh --dry-run
```

`--dry-run` prints rsync and `sbatch` lines and **does not SSH**.
`--submit` is for Josh after approval; this writing session must not
pass it.

### `sbatch --test-only` (documentation — do not run from here)

Fill `$REMOTE=/project2/biyik_1165/jjt_373/csci270-star/pipeline` and
savings job IDs after `squeue -u $USER`. Then, **once the VPN is up**,
Josh can run from Discovery:

```
sbatch --test-only --job-name=cmp_build --time=04:00:00 \
  --export=ALL,ACTS_GIT_HASH=$HASH \
  $REMOTE/jobs/compare_build.job

sbatch --test-only --job-name=cmp_A_scan --time=41:00:00 \
  --dependency=afterok:$CMP_BUILD,afterany:$SAV_A_SCAN:$SAV_A_SEARCH:$SAV_B_SCAN:$SAV_B_SEARCH \
  --export=ALL,ACTS_COMPARE_COLLECTION=A,ACTS_COMPARE_MODE=hmmscan,ACTS_GIT_HASH=$HASH \
  $REMOTE/jobs/compare_hmmer.job

sbatch --test-only --job-name=cmp_A_search --time=12:00:00 \
  --dependency=afterok:$CMP_BUILD,afterany:$SAV_A_SCAN:$SAV_A_SEARCH:$SAV_B_SCAN:$SAV_B_SEARCH \
  --export=ALL,ACTS_COMPARE_COLLECTION=A,ACTS_COMPARE_MODE=hmmsearch,ACTS_GIT_HASH=$HASH \
  $REMOTE/jobs/compare_hmmer.job

sbatch --test-only --job-name=cmp_B_scan --time=21:00:00 \
  --dependency=afterok:$CMP_BUILD,afterany:$SAV_A_SCAN:$SAV_A_SEARCH:$SAV_B_SCAN:$SAV_B_SEARCH \
  --export=ALL,ACTS_COMPARE_COLLECTION=B,ACTS_COMPARE_MODE=hmmscan,ACTS_GIT_HASH=$HASH \
  $REMOTE/jobs/compare_hmmer.job

sbatch --test-only --job-name=cmp_B_search --time=09:00:00 \
  --dependency=afterok:$CMP_BUILD,afterany:$SAV_A_SCAN:$SAV_A_SEARCH:$SAV_B_SCAN:$SAV_B_SEARCH \
  --export=ALL,ACTS_COMPARE_COLLECTION=B,ACTS_COMPARE_MODE=hmmsearch,ACTS_GIT_HASH=$HASH \
  $REMOTE/jobs/compare_hmmer.job

sbatch --test-only --job-name=cmp_snpeff --time=02:00:00 \
  --dependency=afterok:$CMP_BUILD \
  --export=ALL,ACTS_GIT_HASH=$HASH \
  $REMOTE/jobs/compare_snpeff.job

sbatch --test-only --job-name=fourth_mordred --time=12:00:00 \
  --export=ALL,ACTS_GIT_HASH=$HASH \
  $REMOTE/jobs/fourth_mordred.job

# Whisper: do not run. submit_fourth.sh refuses without ACTS_WHISPER_SUBMIT=1.
# This plan still says BLOCKED if that flag is set.

sbatch --test-only --job-name=f6_trace --time=00:30:00 \
  --export=ALL,ACTS_GIT_HASH=$HASH \
  $REMOTE/jobs/f6_trace.job
```

---

## Requests for other agents

- **Compare agent:** `scripts/compare_build.py` PGO is Clang
  (`-fprofile-instr-generate`, `llvm-profdata`). CARC jobs use GCC PGO
  in `jobs/compare_build.job`. A gcc branch in `compare_build.py` would
  avoid the split; do not treat the Mac prefixes as the CARC binaries.
- **Savings agent:** collect `results/savings_*` when the four jobs
  finish. Comparison timings are a later exclusive-node run, not a
  reuse of those walls (different node would confound T vs S).
- **Fourth-tool agent:** `scripts/run_fourth_screen.py` is still absent.
  Mordred logic lives in `jobs/fourth_mordred.job` so this plan does not
  wait on that script. Whisper stays BLOCKED.
- **Probe / cache agent:** F6 job wraps `run_f6_trace_linux.py`; do not
  change that script’s output path. Mapping is in the table above.
