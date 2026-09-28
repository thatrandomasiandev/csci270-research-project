# Open requests from the 2026-09-27 agent round

Collected from each agent report after merging `agent/cache`,
`agent/probe`, `agent/usability`, `agent/compare`, `agent/fourth`,
`agent/baselines`, and `agent/paper` into `main`. Not a protocol.
Done items stay here so we do not re-open them.

## Done in the integrator pass

- **Wire Agent A’s *P* into `acts predict`.** `acts/predict.py` now
  uses `P = Σ (a + b·n_i)` over the batched inference schedule.
  `ceiling_m` stays the P-free screen ratio; `predicted_speedup`
  includes *P*. `lines` have `P = 0`.

## Still open

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
- Collect the four interleaved savings jobs when they finish; land
  `results/savings_*`. Keep hmmsearch as primary; do not promote
  hmmscan after seeing numbers (`SAVINGS_PROTOCOL` / paper §5.3).
- Comparison HMMER rankings are **predictions** against that
  cumulative metric. Timing is a later CARC job, not this round.
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

### Inference / MATCH (do not change)

- Do not change MATCH types. Comparison MATCH copies the
  savings-protocol table (hmmscan: order + whitespace; hmmsearch:
  multiset + whitespace; SnpEff: record body).
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
  INCOMPLETE). Needs VPN / a Linux host with `strace`.
- INCR Zenodo https://zenodo.org/records/19488802 returned **403**
  from this network. Cite as “GitHub live, Zenodo unverified” until
  that is resolved. Runnable artifact:
  https://github.com/atlas-brown/incr

### Fourth-tool screen (not this session)

- Do not time `FOURTH_SCREEN.md` in the same session that wrote it.
- Whisper FORMAT is new (directory of per-file TSVs keyed by audio
  SHA-256). Do not pretend it is VCF/FASTA.
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

### Do not implement in this file

- Baseline wrappers (Riker / ProcessCache / INCR / eggNOG).
- LLM code-optimization arm (budget is in `COMPARISON_PROTOCOL.md`;
  not run).
- CARC timing of tuned HMMER / SnpEff AppCDS.
