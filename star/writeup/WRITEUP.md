# Course write-up

## Paper (conference length, PhD-level draft)

Primary deliverable:

- **LaTeX:** [`paper/main.tex`](paper/main.tex)
- **Bib:** [`paper/refs.bib`](paper/refs.bib)
- **PDF:** [`paper/main.pdf`](paper/main.pdf)

**Title:** ACTS: Observationally Equivalent Acceleration of Spliced Alignment in STAR

(*ACTS* = Amortized Candidate Transcript Stitching)

Build:

```bash
cd star/writeup/paper
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

## Framing (for graders)

Paper draft complete (2026-09-20): ACTS title, full sections, Suite B 10/10 figures.
`paper/main.tex` / `paper/main.pdf`. Rebuild with `pdflatex` + `bibtex` as below.

## Professor criteria (Zhang, 2026-09-08)
1. Output identical to STAR (same flags) — MATCH every timed pair
2. Fair: same machine, same threads (1) — locked
3. Ten Illumina short-read datasets — **10/10** in paper Table (Suite B)
4. ≥2× wall-clock — worst min_pair **2.039×** (i03); means **2.066–2.360×**

## Supporting docs
- `star/docs/SCOPE.md`, `OPTIMIZATION.md`, `PROFILING_LOG.md`
- `star/bench/results/bakeoff_lock_i0{1,2,3,4}/`
