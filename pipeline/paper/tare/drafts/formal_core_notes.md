# Formal core draft — integration notes (hub)

Branch: `exp/formal-core`. Fragment: `drafts/formal_core.tex`.
Standalone: `drafts/formal_core_standalone.tex` (build from `pipeline/paper/tare/`).

## What this replaces in `main.tex`

| Region (hub/submission-ready `bf856b4`) | Content |
|---|---|
| **§Problem Model** lines 280–319 | Entire section body (Release / Exact re-annotation / Coupling / Entry locality + assumptions paragraph) |
| **Design §3** lines 436–451 | Gate equation `(eq:gate)` and R1–R3 prose + break-even sentence |
| **Design §5** lines 484–486 | R4 tripwire sentence (keep batching cost equation `(eq:batch)` and narrative above it) |
| **Design §6** lines 488–518 | Formal pad/audit/miss/bound text (keep a short operational pointer: “pads and audit as in §Problem Model”) |
| **Design Cost Model** | Keep subsection for evaluation narrative; formal core restates `(eq:cost)` so notation matches. Hub may drop the duplicate equation and `\cref{eq:cost}` from Design. |

**Do not replace:** pipeline figure, Stages 1–2 narrative, selection/candidates equation `(eq:cand)`, batching equation `(eq:batch)`, Implementation, Evaluation.

## Hub edit checklist

1. Add `\newtheorem{proposition}{Proposition}` next to the existing assumption theorem.
2. Replace Problem Model body with `\input{drafts/formal_core.tex}` **or** paste the fragment (fragment already contains `\section{Problem Model}`).
3. Delete or shorten the Design rule regions above; keep stage *how* prose.
4. Unify notation: draft uses records $R$, reference $E$; Design still uses $Q$, $R'$. Pick one.
5. Figure refusal caption (R1–R6 one-liners) can stay; it is not counted in the length budget.
6. Cite `pipeline/docs/NONBIO_LITERATURE.md` from `hub/collect-w8-w5x` only if the hub wants those papers in Related Work / Discussion.

## Length (page-neutral)

Measured on `bf856b4` with a twocolumn USENIX harness (no title):

| | Non-comment TeX lines | Alpha words | Rendered PDF pages | `pdftotext` lines |
|---|---:|---:|---:|---:|
| **Before** (PM 280–319 + Design 436–451, 484–486, 488–518) | 88 | 951 | 1 | 78 |
| **After** (`formal_core.tex`) | 113 | 739 | 1 | 62 |

After is denser (more TeX lines from itemize/assumptions) but **shorter in words and rendered lines**, same page count. Standalone with `\maketitle` is 2 pages; ignore that for the budget.

## Code → claim map (summary)

See the report for the full class → action → rule → function → evidence table.

## Contradictions / imprecisions left for the hub (do not fix `main.tex` here)

Listed in `pipeline/docs/prompts/2026-10-23_formal_core_report.md`.
