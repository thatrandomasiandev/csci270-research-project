# Tool screen (pre-registered) — 2026-09-25

Written **before** any screen timing run. Do not edit this section after seeing `results/tool_screen.json`.

SnpEff 5.4c on HG00099 (locked prefix fit, `701d24b`) has a ≈ 8.91 s and b·N ≈ 4.43 s. Cache hits cannot take that much past ~1.5×. The headline needs a tool whose **per-record** term dominates.

This screen measures **stock** `t = a + b·n` only. No cache. No speedup claim. A tool that fails does not get a wrapper.

## Advance rule (locked)

For miss fraction `m` (fraction of records still sent to the tool):

```
ceiling(m) = (a + b·N) / (a + b·m·N)
```

- `m = 0.2` is the CEU-like 79% hit rate (96∪97 → 99 miss_frac ≈ 0.213).
- `m = 0` is 100% hits: `ceiling(0) = (a + b·N) / a`.

**A tool advances only if `ceiling(0.2) ≥ 3.0`.** Equivalently `b·N / a ≥ 5`. Wall time is the fit. User+sys CPU is logged, not the rule.

OLS is on the per-size **mean** wall times (same estimator as `snpeff_timing_fit.json`). If `a ≤ 0` or `b ≤ 0`, the linear model failed; the tool does **not** advance.

## Design (all tools that run)

- Random subsets, **not** prefixes (SnpEff prefixes showed position bias). One subset per `n`, reused for the 3 runs at that size.
- Seed **20260925**. Sizes `{1, 1000, 5000, 20000, N}` omitting any `n > N`.
- 3 runs each. Outputs under `/tmp/acts_tool_screen/` (not the repo, not Drive).
- Log `uptime` and load before every timed run. Pause Google Drive before the first timed run.
- `resource.getrusage(RUSAGE_CHILDREN)` user+sys CPU per run, alongside `perf_counter` wall.

## Candidates

| # | Tool | N | Status before timing |
|---|------|---|----------------------|
| 1 | VEP `--offline --cache --vcf --no_stats --fork 1`, chr22 | 52,638 (HG00099 `-c1`) | **Skip.** `vep` is not on PATH. No `~/.vep` cache. A partial chr22 cache is not on disk. Full human cache is not downloaded (VEP_PROTOCOL.md). |
| 2 | SnpEff 5.4c GRCh38.86, heavier than the locked `-noStats -noLog` run | 52,638 (HG00099 `-c1`) | **Run.** `-lof` / HGVS are already defaults in 5.4c; they are not a new switch. Heavier argv: **stats on** (no `-noStats`), **`-ud 20000`** (locked run used the 5 kb default). SnpSift dbNSFP is **skip** — only `make_dbNSFP.sh` is present; the TSV is multi-GB and is not fetched. |
| 3 | `ruff check --no-cache` (unmodified), one invocation per subset | count of `*.py` under `~/Desktop/Coding Projects` and `~/Desktop/CSCI270/ACTS`, excluding `.venv` / `venv` / `node_modules` / `__pycache__` / `site-packages` / `.git` / `dist` / `build` (expected ~16k; exact N recorded at run) | **Run.** No local LLM (`ollama` absent). `ruff` 0.8.4 is the installed per-file linter. Subset = random files, symlinked into `/tmp`; N < 20,000 so the 20k size is omitted. |

## What this is not

- Not a cached-path MATCH.
- Not a rewrite of `results/snpeff_timing_fit.json`.
- Not permission to download VEP or dbNSFP.
- Not STAR.

```
python3 scripts/run_tool_screen.py
```

Report: `results/tool_screen.json`.
