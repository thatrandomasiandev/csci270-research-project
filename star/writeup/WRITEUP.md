# Course write-up

## Paper (conference length, PhD-level draft)

Primary deliverable:

- **LaTeX:** [`paper/main.tex`](paper/main.tex)
- **Bib:** [`paper/refs.bib`](paper/refs.bib)
- **PDF:** [`paper/main.pdf`](paper/main.pdf)

**Title:** Observationally Equivalent Acceleration of Spliced Alignment: Amortizing Candidate Transcript State in STAR

Build:

```bash
cd star/writeup/paper
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

## Framing (for graders)

The paper is written as a research article (observational equivalence, cost model, threats to validity), not as a course checklist. Empirical claims remain honest: 4/10 Illumina sets, Mac ratios, mean ≥2× with MATCH.

## Professor criteria (Zhang, 2026-09-08)
1. Output identical to STAR (same flags) — MATCH every timed pair
2. Fair: same machine, same threads (1) — locked
3. Ten Illumina short-read datasets — **4/10** in paper
4. ≥2× wall-clock — mean **2.02–2.14×** on i01–i04

## Supporting docs
- `star/docs/SCOPE.md`, `OPTIMIZATION.md`, `PROFILING_LOG.md`
- `star/bench/results/bakeoff_lock_i0{1,2,3,4}/`
