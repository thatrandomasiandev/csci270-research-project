# Open requests from the 2026-09-27 agent rounds

Not a protocol. Done items stay here so we do not re-open them.

Round 3 merged `agent/llmarm`, `agent/confirm`, and `agent/bytes`
into `main` (after round 2: analysis, formats, carcjobs; round 1:
cache, probe, usability, compare, fourth, baselines, paper).

## Done in the 2026-09-27c integrator pass

- **LLM-arm harness** (`6968c6b` protocol, `44602d8` EGAS host +
  fake-agent dry-run). Safe no-op MATCH-passes; bad patch scores
  1.0×. No live model. No CARC timing.
- **Confirmatory hmmscan pre-registered and predicted** (`8afe41f`
  protocol, `9d78279` predictions). PRIMARY = hmmscan `--cut_ga` on
  confirm_E (new *E. coli*, seed 20260927) and confirm_C (S. aureus
  prefix). Locked with-*P* cumulative: **2.96×** / **3.12×**. Jobs
  written, not submitted. `docs/CONFIRM_PLAN.md`.
- **Generic table layout** (`e6dbf80` / `b85859e`). hmmscan
  `--cut_ga` byte MATCH true; hmmsearch still whitespace fallback
  (`results/inference_fasta_reuse_bytes.json`). SAVINGS addendum
  records scan bytes only. Do not claim hmmsearch byte identity.
- **SAVINGS_PROTOCOL.md addendum** (this integrator commit): hmmscan
  `--tblout` may be byte MATCH on future runs; queued A/B jobs stay
  token identity.

## Done in the 2026-09-27b integrator pass

- **Pre-commit savings analysis** (`00f9403`, locked in
  `SAVINGS_PROTOCOL.md` addendum `17bb5bc`). Do not rewrite
  `scripts/analyze_savings.py` after job JSON lands unless that
  rewrite is a **declared deviation**.
- **`--kind files` and `--kind linetable`** (`lines->table`) on
  `acts run`. Fixtures as pre-registered. Mordred correctness run
  **skipped** (`pip install mordred rdkit` = 227 MB > ~200 MB cap).
- **CARC jobs written, not submitted.** Comparison / Mordred / F6
  in `docs/CARC_PLAN.md`. Whisper job exists but is **BLOCKED**.

## Done in the integrator pass (round 1)

- **Wire Agent A’s *P* into `acts predict`.** `acts/predict.py` now
  uses `P = Σ (a + b·n_i)` over the batched inference schedule.
  `ceiling_m` stays the P-free screen ratio; `predicted_speedup`
  includes *P*. `lines` have `P = 0`.

## Still open

### Josh: CARC_PLAN totals (do not sbatch until approved)

Source: `docs/CARC_PLAN.md` plus `docs/CONFIRM_PLAN.md` (account
`biyik_1165`). After the four savings jobs finish; do not overlap
with their 47 h request.

| Bucket | `--time` sum | Est. actual |
|--------|----------------|-------------|
| Comparison + Mordred exclusive | **101 h** | **56.7 h** |
| Confirmatory hmmscan exclusive | **52 h** | **23.7 h** |
| Whisper | **0 (BLOCKED)** | 0 |
| F6 (shared, not exclusive) | 0.5 h wall | 0.1 h |
| LLM-arm live optimizer | **0 until Josh names `model_id` and funds it** | 0 |

Dry-run only: `pipeline/scripts/submit_{compare,fourth,f6,confirm}.sh --dry-run`.
`sbatch --test-only` lines are in the plan as text. Local F6 still
needs Docker Desktop; the CARC F6 job is the backup.

`submit_confirm.sh --submit` currently **refuses** (exit 2). Wire the
rsync/sbatch path the way `submit_hmmer_savings.sh` does before any
real submit. Do not compete with the four savings jobs for exclusive
`epyc-7542` nodes.

### Savings / CARC (do not sbatch from here)

- Dated addendum to `docs/SAVINGS_PROTOCOL.md` — **ported 2026-09-27**
  (locked text untouched). Queued jobs use `probe_n = 8`
  (`scripts/run_hmmer_savings.py:37`). After the probe merge, the
  **default** inference path is batched (**18** calls). At `n = 8`
  singleton is cheaper (12 vs 18). The queued jobs were submitted
  from `427fcbb` (singleton-only implementation), so they are not
  silently paying batched-18. Paper reports `probe_n = 8` miss rates
  alongside cumulative savings with and without *P*. Duplicate
  stash *P* JSON archived as
  `results/hmmer_predicted_speedup_with_probe_stash.json`
  (`docs/PROBE_COST_RECONCILE.md`).
- Collect the four interleaved savings jobs when they finish.
  Analyzer (`scripts/analyze_savings.py`, committed `00f9403`)
  expects `results/savings/{A,B}_{hmmsearch,hmmscan}.json` (directory
  + mode names, **not** `savings_A*` / `savings_B*` dumps). Then:

  ```
  python3 scripts/analyze_savings.py \
    --jobs results/savings \
    --out-json results/savings_summary.json \
    --out-md results/savings_summary.md \
    --fig-dir results/figures
  ```

  Do not hand-edit totals. Do not change `run_hmmer_savings.py`
  schema without a protocol addendum. Keep hmmsearch as primary;
  hmmscan is post-hoc. If A / hmmscan kill trips (cached ≥ 50% of
  stock), stop talking about 3× on A.
- Paper: `paper_uses = hmmsearch`. Report `probe_n = 8` and
  singleton_8 (12 calls), not `batched_500`. Include *P* in any
  cumulative headline that includes first-infer time. No 3×
  sentence until this analyzer says so on a **complete** collection.
- Comparison jobs are written (`jobs/compare_*.job`) but **not**
  submitted. CARC PGO is GCC; Mac `compare_build.py` is Clang —
  do not treat Mac prefixes as the CARC binaries. Comparison
  re-times on a later exclusive node (different node would confound
  T vs S).
- Do not `sbatch` baseline wrappers. Confirm Discovery `ptrace`,
  OverlayFS, and privileged Docker. Share savings hostname / `lscpu`.

### Josh gates (no download / no job until OK)

- **eggNOG ~45 GB** core DBs before any eggNOG `-m cache` baseline.
- **Baselines Phase 0:** 2 exclusive node-hours for a ptrace /
  OverlayFS capability probe. Phase 1 smoke: 16 node-hours. Full A/B
  wrappers: 192–220 node-hours **per** wrapper — not until Phase 1
  matches the locked rerun/skip prediction.
- **Whisper / PyTorch:** `pip install openai-whisper` may pull a
  wheel **> 1 GB**. Stop and ask. Default `turbo` (~1.6 GB) is
  gated; lock `small` (~466 MB) if a screen runs. Do not use `tiny`.

### Cache / ACTS runtime

- Keep calling `RecordCache` as today. Do not pass `portable=True`
  unless standing up a **shared lab cache** (digest-only collisions).
  Default keys will **not** share rows across machines or install
  prefixes.
- Mac indicative wrapper `w` is **~4–8 µs/record** lookup+save
  (`results/cache_scale.json`). `open()` is **0.21 s** at 10M rows.
  Re-measure on CARC if `w` enters a locked claim. Prefer `.sqlite`
  paths at large N so jsonl is not dumped.
- The 1e3–1e7 scale harness lived only in gitignored
  `pipeline/data_cache/measure_cache_scale.py` on `agent/cache`.
  Move it into git if that curve must be reproducible.
- JSONL parsers of `cache.jsonl` still work (compatibility dump).
  SQLite is the source of truth. Concurrent jsonl dumps remain
  last-writer-wins.
- `acts predict --cache` still reads jsonl text (and the dump C
  writes). VCF miss keys use default `CHROM/POS/REF/ALT`. If infer
  widens the key (ID, etc.), *m* can disagree with a real `run`.
  Optional: read `*.contract.json` next to the cache.

### Inference / MATCH

- **hmmscan `--cut_ga`:** byte MATCH is now the success path when
  layout is pinned (`inference_fasta_reuse_bytes.json` →
  `scan_cut_ga`). SAVINGS addendum 2026-09-27c records this.
  `COMPARISON_PROTOCOL.md` and `LLM_ARM_PROTOCOL.md` still copy the
  old whitespace table in locked text — dated addenda there if those
  arms score new patches; do not rewrite their locked sections.
- **hmmsearch `--tblout`:** still whitespace-normalized. Do not claim
  bytes.
- Queued A/B savings jobs stay token identity (pre-`b85859e`).
- `run_probe_eval.py` now implicitly measures **batched** via the
  infer default. Keep `probe_eval.json` / `probe_eval_audit.json` as
  the locked singleton-era tables. The comparison is
  `results/probe_eval_subset_*.json`.
- Optional CLI `--subset-mode` on `acts run` if anyone needs
  singleton without `scripts/run_probe_eval_subset.py`. Default
  batched already applies (`infer_contract` default; RecordMemo does
  not pass the flag).

### Paper

- Do not cite `probe_eval_subset_*` or
  `hmmer_predicted_speedup_with_probe.json` until those files are
  on the paper branch / this merge (they **are** on `main` after
  this integrator pass — the skeleton still has `\TODO{}` for
  savings, baselines, Linux F6-file, VEP, and the comparison).
  Update citations in a later paper commit, not by silently
  rewriting unmeasured sections.
- Linux F6-file + `snpEff.config` namespace (Mac audit left this
  INCOMPLETE). 2026-09-27: `docker info` failed (daemon not at
  `~/.docker/run/docker.sock`); `scripts/run_f6_trace_linux.py`
  skipped. Needs Docker Desktop locally, or the written
  `jobs/f6_trace.job` on CARC. Do not change
  `run_f6_trace_linux.py`’s output path; the job copies it to
  `results/f6_trace_linux.json`.
- INCR Zenodo https://zenodo.org/records/19488802 returned **403**
  from this network. Cite as “GitHub live, Zenodo unverified” until
  that is resolved. Runnable artifact:
  https://github.com/atlas-brown/incr

### Formats (`files` / `linetable`)

- `docs/USAGE.md` and `acts/predict.py` still list only `vcf` /
  `fasta` / `lines`. Add `files` and `linetable` if those surfaces
  should match `acts run`.
- `acts probe`: `records.py` has no `probe_files`; probe CLI kinds
  are still `fastq_pe` / `lines` only.
- Probe-eval F-suite is VCF/FASTA only. Extend only if that
  comparison is wanted.
- Do not put Mordred or Whisper column names in `acts/`.

### Fourth-tool screen (not this session)

- Mordred job is written (`jobs/fourth_mordred.job`);
  `scripts/run_fourth_screen.py` is still absent — screen logic
  lives in the job. Not submitted.
- Do not time `FOURTH_SCREEN.md` in the same session that wrote it.
- Whisper FORMAT is new (directory of per-file TSVs keyed by audio
  SHA-256). Do not pretend it is VCF/FASTA. Job
  `jobs/fourth_whisper.job` is **BLOCKED** until Josh approves
  model size and PyTorch. `submit_fourth.sh` refuses Whisper
  unless `ACTS_WHISPER_SUBMIT=1`.
- LibriSpeech test-clean vs test-other is `REFUSE_M`. Use the locked
  80/20 union split, or Common Voice metadata overlap.
- ClamAV `--disable-cache` is a strawman. Best mode already memos
  clean hashes for the daemon lifetime.
- OPERA is the heavier chemistry follow-up only if Mordred’s
  measured `b` is too small.

### Packaging

- Do **not** publish to PyPI. Dist name is `acts-memo` (`acts` and
  `pyacts` are taken). Console script stays `acts`.

### STAR / EGAS

- Do not rerun Suite B. `star/bench/results/illumina10_s8j_mac.csv`
  is the code-opt arm of the comparison. PGO and AppCDS are not a
  method.

### Confirm / analysis

- `scripts/analyze_savings.py` still discovers only collections
  `A`/`B`. After confirm jobs dump
  `results/confirm/confirm_{E,C}_hmmscan.json`, extend discovery to
  `confirm_E` / `confirm_C` **without** changing the locked A/B
  analysis. That extension is a **declared deviation** from
  `00f9403` and must be labeled as such. Do not edit
  `run_hmmer_savings.py`; `scripts/confirm_run.py` already wraps it.

### LLM-arm (harness done; live run gated)

- No live optimizer until Josh: (1) funds it, (2) accepts or changes
  8 h / 2 M tokens / `n_runs=3`, (3) shared cap (~$30–75, 24 h / 6 M)
  vs per-run expansion (~$90–225, 72 h / 18 M), (4) exact `model_id`
  and the CLI in `agent.toml`, (5) workload order among SnpEff,
  hmmscan, hmmsearch. STAR stays sealed.
- MATCH-fail runs must never be timed on CARC. Collections A/B and
  HG00099 stay **invisible** to the agent.

### Do not implement in this file

- Baseline wrappers (Riker / ProcessCache / INCR / eggNOG).
- A live LLM-agent run (harness exists; PARAMETERS are TBD).
- CARC timing of tuned HMMER / SnpEff AppCDS, confirmatory hmmscan,
  or LLM-arm patches (jobs/harness written; submit only after Josh
  approves the matching plan).
