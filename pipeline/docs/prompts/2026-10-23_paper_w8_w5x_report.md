# Paper W8 + W5x fold-in report (2026-10-23 / 2026-10-24)

Hub worktree: `/Users/joshuaterranova/Desktop/CSCI270/ACTS-hub`
Branch: `hub/submission-ready`

## Final SHA (this step)

`9aa316f` — Fold measured W8 release chain and matched W5x baselines into the paper.

## Gates

| Gate | Result |
|---|---|
| Checker | `tare_source_comments=69 mismatches=0 unsourced=0` (PENDING macros for W13/W12a/W12b/WA2 timing remain; expected) |
| `main.pdf` | Builds (`latexmk -pdf` OK) |
| Page limit | Body ≤12 pages; Availability + early refs on p12; refs continue p13 (13 pages total) |
| Anonymity | `ANONYMITY OK (paper surfaces)` (prose uses “selection”, not “discovery”) |
| Pytest | `cd pipeline && python3 -m pytest -q tests` → **412 passed, 1 skipped** (bare `pytest -q` also walks `artifact/` and hits ImportPathMismatch; ignore that tree) |
| finalize.sh | **W8 COLLECTED**, **W5x COLLECTED**; W13/W12a/W12b STILL RUNNING; WA2 correctness COLLECTED (INCONCLUSIVE), timing not eligible |

## Merge

- Fast-forward merged `origin/hub/collect-w8-w5x` (tip includes `4c5f77b` collector fix + measured JSON + later planning docs left untouched).
- Pre-existing `s{=}299` / `missed=741` source labels already on base with `NOMINAL` keys; checker accepts them — kept, no separate revert.

## Sentences changed (with `% source:` keys)

### Release chain (`sec:eval-exact`, “Other releases”)

Replaced pilot-only / “timed version is running” with measured chain:

- Three genomes, seed `20261222`, EPYC 7542, $r{=}3$; 2/3 PASS exact at every step.
- Per-step $S_g$: 7.08/8.92 (37.4), 0.91/0.68 (38.0), 4.29/4.54 (38.1), 4.01/5.35 (38.2).
- Cumulative $C_{\mathrm{stock}}/C_{\sys}$: 1.66 and 1.71 after 38.2; 1.31 and 1.46 after 37.4.
- 38.0 is the break-even-fallback case; measured run is pre-fallback frozen code.
- Third genome scored FAIL at fill (37.3) duplicate row key; same needless-refusal class later fixed; pre-fix code.

Keys: `MEASURED pipeline/results/release_chain/measured.json` (seed, n_pass, $S_g$, payback cumulatives, fail); prior pairs/cost-model keys retained; `HAS 7542`.

### Table 4 + Q4 prose

Matched x86 first-run $\rho$ on one EPYC 7542 node (500 proteins, 30{,}134 models, $n{=}4$):

| System | New release | First-run $\rho$ |
|---|---|---|
| INCR | reruns everything | $1.50\times$ [0.87, 2.13] |
| ProcessCache | reruns everything | $14.49\times$ [14.06, 14.92] |
| Riker | reruns everything | blocked (ptrace) |
| \sys | replays changed part | $4.20\times$ [4.17, 4.24] |

Caption footnote: laptop Riker $1.62\times$ [1.53, 1.71] on the same protein count.

First-run explanation: \sys $4.20\times$ vs INCR $1.50\times$ on the small input because fixed phases dominate (parse 48.9\,s, press 9.7\,s, fill tool 405.5\,s, selection 246.5\,s, pin check 151.8\,s vs ~240\,s stock); whole-genome first-run median $1.32\times$, break-even median 0.26 updates; caches give no release speedup.

Keys: `MEASURED pipeline/results/baselines_x86/measured.json` (systems.* ratios/CIs, phases, stock wall); `MEASURED pipeline/results/baseline_overhead.json` (laptop Riker); `MEASURED pipeline/results/exact_replay/headline_carc.json` (`first_run_overhead_median`, `break_even_n_median`).

### Threats + conclusion

- Threats: headline times 38.1→38.2; measured chain covers 37.3→38.2 without fallback.
- Conclusion: drop “next steps: the other releases”; note measured chain stays exact when it ships.

Abstract / intro: no number changes required.

## Left out (could not source / not claimed)

- PROJECTED “with fallback” cumulative for the 38.0 step (brief forbids presenting as measured).
- Genome accessions in prose (checker treats `GCF_…` tails as decimals); IDs remain only in JSON / source comments.
- Shared-contract feature (results not landed).
- Semgrep / non-bio planning docs (untouched).

## Open issues

- W13 / W12a / W12b still PENDING macros.
- Bare `pytest -q` under `pipeline/` collects `artifact/` and errors; use `tests/` or `--ignore=artifact`.
- `_staging_measured.json` from collector rsync left untracked — do not commit.
