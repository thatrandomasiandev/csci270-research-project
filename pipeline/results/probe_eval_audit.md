# Probe miss-rate — `--verify audit` (deployed)

Addendum `4679264`. Seed 20260927. `N_rec`=2500. JSON: `probe_eval_audit.json`.
Figures: `18_probe_eval_audit_catch.png` (renumbered from `15_` to avoid colliding with `15_hmmer_predicted_speedup.png`), `16_probe_eval_full_vs_audit.png`.

`96f786b` / `probe_eval.json` is the **full-MATCH upper bound**. This file is
the **deployed** number: probes + hit audit, no stock tool on the input.

macOS host: no `strace`. F6-file is uncovered here. Docker daemon was down;
Discovery SSH timed out. Linux F6-file + `snpEff.config` check is
**INCOMPLETE** (`scripts/run_f6_trace_linux.py`).

## Headline

| Metric | `--verify full` (`96f786b`) | `--verify audit` (this run) |
|--------|-----------------------------|-----------------------------|
| Unsafe-ship overall | 33 / 256 (0.129) | **68 / 288 (0.236)** |
| Excl. F6 / F6-env+F6-file | **1 / 224 (0.0045)** | **4 / 224 (0.018)** |
| F6-env | 32 / 32 (then F6) | **32 / 32** (limitation) |
| F6-file | — | **32 / 32** on macOS (no tracing) |
| False-refuse | 0 / 20 | **0 / 20** |
| Probe-only catch | (MATCH mixed in) | 151 |
| Audit-only catch | — | **12** |

In-scope on this Mac (excl. F6-env only) is 36 / 256 because F6-file still
counts until Linux tracing is measured.

## Per class (32 cells each)

| Class | Input-1 refuse | Extra catch | Unsafe-ship | Notes |
|-------|----------------|-------------|-------------|-------|
| F1 | 26/32 | audit 2 | 0 | MATCH is gone; leftover live hits can still fail audit |
| F2 | 27/32 | — | 0 | |
| F3 | 25/32 | — | **1** | vcf *p*=0.01 `n`=50: no live in sample; audit on input 2 missed the live hit |
| F4 | 13/32 | audit 1 | **3** | fasta *p*=0.001 `n`∈{50,200}; **vcf *p*=0.01 `n`=50** (same cell as `96f786b`) |
| F5 | 9/32 | audit 8 | 0 | late-key / perturbation |
| F6-env | 0/32 | — | **32** | Env is outside the guarantee |
| F6-file | 0/32 | — | **32** | macOS: no `strace`. Linux not run |
| F7 | 26/32 | audit 1 | 0 | |
| F8 | 25/32 | — | 0 | |

## Old vs new (excl. F6*)

The old in-scope miss (vcf F4, *p*=0.01, `probe_n`=50) **remains**. Random
sampling did not put a live record in that 50-draw. Two new fasta F4 misses
and one F3 miss appear because MATCH no longer runs on the full file.

Audit recovered 12 cells that probes missed (mostly F1/F5/F7). It does not
replace MATCH as an upper bound.

## F6

- **F6-env:** undetectable. Stated limitation.
- **F6-file:** tool reads `hidden.cfg` next to the input. On Linux + `strace`
  the file should enter the namespace (`run_f6_trace_linux.py`). Not measured
  on this Mac. `snpEff.config` check is the same script, same host gap.
