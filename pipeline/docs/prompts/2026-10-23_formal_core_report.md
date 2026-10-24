# Formal core hub integration report (2026-10-24)

Hub: `/Users/joshuaterranova/Desktop/CSCI270/ACTS-hub` · branch `hub/submission-ready`

## Final SHA

`7df6e7f` — Integrate the formal core: C0-C4 taxonomy, exact-merge proposition, R1-R6 gate.

## What changed

- Added `\newtheorem{proposition}{Proposition}`.
- Replaced §Problem Model with `pipeline/paper/tare/drafts/formal_core.tex` (from `origin/exp/formal-core`, edited for anonymity + page budget).
- Shortened Design gate (R1–R6 as one surface + break-even), R4 tripwire pointer, Stage 6 (pads keep `eq:miss`; audit points to `eq:audit-s`), Cost Model (narrative + `\cref{eq:cost}` only).
- Unified Design/figure notation to records $R$, reference $E$ (was $Q$,$R'$).
- Q3 guarantee now names C0/C1 + (D)--(O) and `\cref{prop:exact}`.

## Imprecision fixes (one line each)

1. **Coupling → C0–C4:** Problem Model now states C0–C4 with refuse/replay map (was four informal “forms”).
2. **Exact-merge derivation:** `\ref{prop:exact}` + short proof under (D)--(O); was “entry locality” without assumptions.
3. **Q/R vs R/E:** Design and pipeline figure now use $R$,$E$ to match the formal core.
4. **Gate covers R1–R6:** Design gate prose cites the full refusal surface; dropped R1–R3-only equation.
5. **“Exact when entry-local”:** Q3 names C0/C1 and (D)--(O) / `\cref{prop:exact}`.
6. **Side files / groups:** Classified as declarations preserving C1, not a coupling class.
7. **F6 named:** Stated under “Not covered” as closed-family limitation.
8. **Audit vs pad-miss:** `eq:audit-s` (R6) in Problem Model; `eq:miss` kept only for random pads (R5) in Stage 6.

## Gates

| Gate | Result |
|---|---|
| Checker | 0 mismatches (69 source comments) |
| `main.pdf` | Builds |
| Pages | Body ≤12 (Related p11; Tab5+Conclusion+Availability p12; refs p13) |
| Anonymity | OK (no literal discovery/TARE in body) |
| Pytest | `python3 -m pytest -q tests` → 412 passed, 1 skipped |

## Left out

- NONBIO cross-field citations deferred to Step 4 Discussion paragraph.
- Standalone length harnesses from `exp/formal-core` not copied (notes + fragment only).
