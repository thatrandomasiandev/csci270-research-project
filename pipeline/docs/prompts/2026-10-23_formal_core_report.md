# Formal core draft — report (2026-10-23)

## Branch and SHA

- Worktree: `../ACTS-formal` (from repo `ACTS`)
- Branch: `exp/formal-core` (from `origin/hub/submission-ready`)
- Final SHA: `5e3879937ef2737163757903e307df41810191c3` (formal draft content in `753b249`)

## File list

| Path | Role |
|---|---|
| `pipeline/paper/tare/drafts/formal_core.tex` | Drop-in formal core fragment |
| `pipeline/paper/tare/drafts/formal_core_notes.md` | Hub integration notes |
| `pipeline/paper/tare/drafts/formal_core_standalone.tex` | Standalone compile harness |
| `pipeline/paper/tare/drafts/before_length_check.tex` | Length “before” harness |
| `pipeline/paper/tare/drafts/after_length_check.tex` | Length “after” harness |
| `pipeline/docs/prompts/2026-10-23_formal_core_report.md` | This report |

Not edited: `pipeline/paper/tare/main.tex`. Not committed: `tools/carc-gpu-dashboard/`, `lab-notebook/`, research-plan PDF.

## Propositions

### Proposition (Exact merge) — **proved**

**Statement.** Under C0 or C1 and Assumptions (determinism; pin fixes $g$; unique attribution; row-determined body), replaying each record against its candidates with $g$ pinned and merging in record order yields $\mathrm{body}(P(R,E',o))$.

**Assumptions (named in draft).**
1. Determinism for fixed $(r,e,o,g)$ — sampled by stock-vs-stock / probe consistency; failure → refuse (C4).
2. Pin fixes $g$ — verified by `_pin_check` (R3) and `uncovered_members` (R2).
3. Unique attribution after key widening — `row_key` / probe decomposition (R1).
4. Body determined by rows in fixed order — stitching contract of `_batched_replay`.

**Proof.** Short derivation in `formal_core.tex` from C0/C1 + pin + candidate completeness.

**Probe/check coverage (not part of the proof).** `probe_fit` / `fit_observations` (factorization + closed normalizers); `_pin_check`; `_ic2` pads; non-candidate tripwire; audit.

### Audit sample size — **proved** (classical)

**Statement.** $s=\lceil\ln\varepsilon/\ln(1-\kappa)\rceil$; for $\varepsilon=0.05$, $\kappa=0.01$, $s=299$.

**Assumptions.** At least fraction $\kappa$ of records affected; with-replacement miss bound $(1-\kappa)^s$ (code uses without-replacement draw of that size; miss probability $\le$ the binomial bound).

**What it bounds.** Probability of shipping a wrong update given $\ge\kappa$ affected (R6).

**What it does not.** Couplings affecting $<\kappa$ of records; proof of entry locality.

**Code.** `acts/audit.bounded_audit_size`; defaults in `acts/__main__.py` (`--audit-bound` on, $\varepsilon=0.05$, $\kappa=0.01$).

### Adversarial shipping rate — **empirical**

**Claim.** With the bounded audit, 3 of 400 trials at $\ge 1\%$ affected still shipped.

**Source.** `% source: MEASURED pipeline/results/adversarial/v2_summary.json arms.bounded.covered_unsafe=3 arms.bounded.covered_trials=400`

### Cost break-even — **definition / engineering** (same as paper)

$T_{\sys}\approx a f_\Delta T_{\mathrm{stock}}+c\,T_{\mathrm{stock}}$; fallback when $f_\Delta>(1-c)/a$; default threshold $0.80$.

**Source.** `% source: MEASURED pipeline/results/breakeven/measured.json threshold_default=0.8`

**Code.** `changed_fraction`, `break_even_f`, `fallback_reason`.

## Mapping table

| Class | TARE action | Refusal rule(s) | Code function(s) | Evidence file |
|---|---|---|---|---|
| C0 entry-local | Replay under identity | — (ship); R1 if probe fails | `probe_fit`, `_run_exact`, `_batched_replay` | Infernal exactness / `exact_replay/exactness_totals.json` |
| C1 reference-size | Pin $g$ then replay | R2 no pin; R3 pin check fail | `pin_tokens`, `uncovered_members`, `_pin_check`, `pin_values` | HMMER pin runs; `reference_kill_r1.json` (churn) |
| C2 neighbor/order | Refuse | R5 (neighbor pad); R1/R3 if seen in probe | `_ic2` + `exact_certificate.neighbor_ids` | `reference_diamond/dx3.json`, `dx3_rootcause.json` |
| C3 cross-record global | Refuse when observed | R1 / R5 / R6 | `probe_fit` (lost whole-only rows), pads, audit | None shipped in suite; taxonomy example (FDR) |
| C4 nondeterministic | Refuse when observed | R1 / stock disagree | probe / audit body compare | Stock-vs-stock controls in protocols |
| (any) incomplete $C_r$ | Refuse | R4 | non-candidate check in `_run_exact` | Protocol tripwire |
| (any) residual hidden | Sampled bound | R6 | `bounded_audit_size`, `_audit_draw` | `adversarial/v2_summary.json` (3/400) |
| (cost) $f_\Delta$ too large | Full-run fallback | (not R1–R6; `fallback_reason`) | `break_even_f` | `breakeven/measured.json` |

AGENTS.md alignment: pass-through / widen for copied vs produced fields lives in fit/key widening; refuse for nondeterminism (C4≈F1/F7), neighbor/order (C2≈F2/F8), global state (C3≈F3); F6 = stated limitation in “Not covered.”

## Length before / after

Harnesses: `drafts/before_length_check.tex`, `drafts/after_length_check.tex` (twocolumn USENIX, no title).

| | TeX lines (non-comment) | Alpha words | Pages | `pdftotext` lines |
|---|---:|---:|---:|---:|
| Before | 88 | 951 | 1 | 78 |
| After | 113 | 739 | 1 | 62 |

**Paragraphs replaced:** Problem Model (280–319); Design gate R1–R3 + break-even (436–451); R4 sentence (484–486); Stage 6 check/audit formal text (488–518). See `drafts/formal_core_notes.md`.

Standalone `drafts/formal_core_standalone.tex` compiles with **no undefined references** (second `pdflatex` pass). Hub must add `\newtheorem{proposition}{Proposition}`.

## Contradictions / imprecisions in current `main.tex` (list only; not fixed)

1. **Coupling definition is not the C0–C4 taxonomy.** It mixes normalizer (C1), side files, entry groups, and neighbor coupling (C2) as four “forms,” without C3/C4 or the refuse/replay map.
2. **“Entry locality under a pin” is stated but never derived as an exact-merge proposition** with explicit assumptions; the draft supplies that derivation.
3. **Notation clash:** paper Design uses records $Q$, reference $R$; formal core uses $R$, $E$ as specified for this draft.
4. **Gate equation lists only R1–R3**; R4–R6 appear later as prose. The formal core treats R1–R6 as one refusal surface.
5. **Guarantee sentence in Q3** (“exact when entry-local”) does not name the assumptions (determinism, unique keys, row order) that the proof needs.
6. **Side files / clans** are described as coupling forms in Problem Model but implemented as *declarations* that preserve C1; the draft reclassifies them.
7. **F6** (closed-family limitation) is in AGENTS.md but unnamed in the paper; the draft states it under “Not covered.”
8. **Audit bound** in Design is correct but interleaved with pad miss equation `(eq:miss)`; the formal core separates the classical $s$ bound (what R6 guarantees) from pad sampling (R5).

## Compile

```bash
cd pipeline/paper/tare
pdflatex drafts/formal_core_standalone.tex   # twice
pdflatex drafts/after_length_check.tex       # length after
pdflatex drafts/before_length_check.tex      # length before
```
