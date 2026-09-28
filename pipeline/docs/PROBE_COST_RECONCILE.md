# Probe-cost reconcile (pre-merge stash vs `agent/probe`)

Written 2026-09-27 after merging `agent/probe` at `e24370f` (main then
`68c423a`). The stash is `stash@{0}` = `f723379`
(`backup/pre-merge-stash`). Do not apply the stash implementation over
main.

This is not a protocol. It records which duplicate to keep.

## Verdict

**Main keeps the `agent/probe` implementation** (helpers live in
`infer_vcf.py` / `infer_fasta.py`; default `subset_mode="batched"` as a
function parameter; no `acts/subset.py`; no `--subset-probe` on
`python -m acts`, which Agent D owns).

The stash is a second, complete implementation of the same
`427fcbb` addendum, done on dirty main before the worktrees. It is
archived, not deleted.

## What each version does

| | Main (`e24370f` / `agent/probe`) | Stash (`f723379`) |
|--|--|--|
| Batching helpers | `batched_index_groups` in `infer_vcf.py`; fasta imports them | `acts/subset.py` (shared) |
| CLI switch | function parameter only; RecordMemo does **not** pass it → batched default | `--subset-probe` on `__main__.py` + `RecordMemo.subset_mode` |
| Eval runner | new `scripts/run_probe_eval_subset.py` | edits to `scripts/run_probe_eval.py` |
| *P* script | `scripts/predict_hmmer_probe_cost.py` | same name, different schedule |
| Tests | `tests/test_infer_*.py` batched classes | `tests/test_subset.py` |

Both implement: 2 random halves + 4 random quarters + 8 singletons, seed
family 20260927, singleton kept for comparison, tool-call counts on the
contract.

Stash FASTA *P* schedule also bills two alignment probes
(`min(16,k)` twice). Main’s HMMER *P* treats tblout as tab-delimited, so
`infer_alignment` is a no-op (INFERENCE_PROTOCOL / Agent A report).

## Protocols

Same pre-registration: `docs/INFERENCE_PROTOCOL.md` addendum 2026-09-27
(`427fcbb`). Stash also drafted addenda for `SAVINGS_PROTOCOL.md` and
`PROBE_EVAL_PROTOCOL.md` (locked text untouched). Those are **ported**
below, pointed at main’s file names.

INCR: both conclude chunk memo needs a crowdsourced “stateless”
annotation, not an inferred test. Stash wrote the §7 phrase into
`RELATED_WORK.md`; that wording is ported. Novelty verdict unchanged.

## Results: miss rates

F3 catch is **identical** in both evals (of 8 cells per `probe_n`):

| `probe_n` | F3 caught | F3 unsafe-ship |
|-----------|-----------|----------------|
| 50 | 4/8 | 1 |
| 200 | 7/8 | 0 |
| 500 | 7/8 | 0 |
| 2000 | 7/8 | 0 |

False-refuse **0** both. Overall unsafe-ship ~68/288 (stash batched
67/288: one F6-env cell differs).

**In-scope labels (resolved 2026-09-27).** Canonical in-scope is
excl. F6-env **and** F6-file (**4/224**). Main’s JSON `in_scope_*`
still stores the macOS carve-out (**36/256**, excl. F6-env only).
Stash already reported 4/224. Same F3 catch; not two evals. See
`docs/PROBE_EVAL_PROTOCOL.md` canonical addendum. Stash’s
side-by-side table remains
`results/probe_eval_subset_compare_stash.json`.

| | Canonical in-scope | JSON `in_scope_*` (macOS) | Unsafe-ship |
|--|--|--|--|
| Main | **4/224** | 36/256 | 68/288 both modes |
| Stash | **4/224** | (wrote 4/224) | 67/288 batched, 68/288 singleton |

## Results: tool-call counts

Complete-path first infer (controls; early REFUSE is fewer):

| `probe_n` | Main batched mean/max | Stash batched mean/max | Main singleton max | Stash singleton max |
|-----------|----------------------|------------------------|--------------------|---------------------|
| 50 | 13.9 / 24 | 14.2 / 24 | 60 | 60 |
| 200 | 12.2 / 24 | 12.6 / 24 | 210 | 210 |
| 500 | 11.8 / 24 | 12.3 / 24 | 510 | 510 |
| 2000 | 11.2 / 24 | 11.6 / 24 | 2010 | 2010 |

Main’s Agent A report: **18** calls at every `probe_n` on the full
batched path (4 full-probe + 14 subset), vs **4 + n** singleton.
Stash’s markdown used complete-path means ~18.6–19.5 (batched) vs
≈ 4 + probe_n (singleton). The 24 max is 4 full + 14 subset + extras
(trace/widen). **Agree on the cost cut.** Disagree on whether FASTA
alignment extras enter *P* (next section).

## Results: predicted *P*

Same `a`,`b` from `headline_screen.json`. Formula both:
`P = Σ (a + b·n_i)`; `cum_cached = P + Σ cached_i`.

| Mode | Account | Main calls / *P* | Stash calls / *P* |
|------|---------|------------------|-------------------|
| hmmscan | singleton `n=8` | **12** / 412 s (0.11 h) | **14** / 488 s (0.14 h) |
| hmmscan | batched `n=500` | **18** / 2750 s (**0.76 h**) | **20** / 2837 s (0.79 h) |
| hmmsearch | singleton `n=8` | **12** / 1595 s (0.44 h) | **14** / 1862 s (0.52 h) |
| hmmsearch | batched `n=500` | **18** / 2744 s (**0.76 h**) | **20** / 3013 s (0.84 h) |

Collection A last-genome cum, batched_500, with *P*: main hmmscan
**4.415×** vs stash **4.410×**; hmmsearch **2.387×** vs **2.363×**.
Close; the gap is the two alignment calls.

**Keep main’s JSON** (`results/hmmer_predicted_speedup_with_probe.json`).
Stash copy archived as
`results/hmmer_predicted_speedup_with_probe_stash.json`.

## Ported (unique names; stash `f723379`)

| Ported as | From stash | Why |
|-----------|------------|-----|
| `docs/SAVINGS_PROTOCOL.md` addendum | +41 lines, **below** locked text | Valid dated addendum; `probe_n=8` gap. Account names retargeted to main keys (`singleton_8`, `batched_500`). |
| `docs/PROBE_EVAL_PROTOCOL.md` addendum | comparison file list | Valid; points at main files + stash archive. |
| `docs/RELATED_WORK.md` INCR §7 phrase | table + Claim 1 | Same verdict; the INCR check the prompt asked to write down. |
| `results/probe_eval_subset_compare_stash.json` | `probe_eval_subset_compare.json` | Unique; side-by-side 4/224 table. |
| `results/probe_eval_subset_stash.md` | `probe_eval_subset.md` | Unique write-up of the stash eval. |
| `results/hmmer_predicted_speedup_with_probe_stash.json` | colliding JSON | Unique name. |
| `figures/22_…_batched_stash.png` | `19_…` | Figure 19 taken on main. |
| `figures/23_…_singleton_stash.png` | `20_…` | Figure 20 taken. |
| `figures/24_…_with_probe_stash.png` | `21_…` | Figure 21 taken. |

## Not ported (and why)

| Stash path | Why |
|------------|-----|
| `acts/subset.py`, `tests/test_subset.py` | Duplicate implementation. Main keeps infer_* helpers. |
| `acts/infer_vcf.py`, `infer_fasta.py`, `vcf_memo.py`, `fasta_memo.py` | Would overlay `e24370f`. |
| `acts/strategies/record_memo.py`, `acts/__main__.py` | Ownership: D owns `__main__.py`; A’s prompt forbade editing both. Stash `--subset-probe` remains an OPEN_REQUEST. |
| `scripts/run_probe_eval.py` edits | Main’s comparison runner is `run_probe_eval_subset.py`. |
| `scripts/predict_hmmer_probe_cost.py` | Main already has it (18-call schedule). |
| `scripts/predict_hmmer_speedup.py` (+4 comment lines) | Cosmetic; main already points at the *P* script. |
| `results/probe_eval_subset_batched.json` / `_singleton.json` | **Name collision.** Main’s committed eval stays. |
| `results/figures/19_` / `20_` / `21_` | **Number collision.** Ported as 22–24 `_stash`. |
| `results/savings/GIT_HASH` | Do not touch `results/savings_*`. Untracked leftover; not a result table. |

Nothing from the stash probe-cost tree was deleted. Unported blobs remain
in `stash@{0}` and `backup/pre-merge-stash`.
