# CSCI 270 Research Project — STAR speedup (A-contract)

**Course contract (Zhang):** improve a widely used solution with a clear measurable win.  
**Target artifact:** scoped optimization of [STAR](https://github.com/alexdobin/STAR) (RNA-seq aligner) with a reproducible **≥2×** runtime improvement on a fixed benchmark at **equal mapping quality**.

**Out of scope for this repo root:** RM-decay / SAC / CARC RL work (archived under [`archive/rm-decay-vs-overopt/`](archive/rm-decay-vs-overopt/); PhD/lab track).

## Layout

```
star/
  upstream/     # STAR source (clone / release tarball)
  src/          # our patches / reimplemented hot path
  bench/        # datasets notes, scripts, results
  docs/         # design notes, profiling logs
  writeup/      # course submission LaTeX/Markdown
AGENTS.md       # agent workflow instructions
STATUS.md       # living target vs current
```

## Success criteria (A package)

1. Professor scope lock on email (recorded in `docs/SCOPE.md`)
2. Stock STAR baseline numbers on fixed hardware + data
3. One named hot-path optimization with rationale
4. Bake-off: ≥2× wall-clock on the agreed workload; mapping metrics within tolerance
5. Short write-up + how to reproduce

## Quick start (agents)

Read `AGENTS.md` → `STATUS.md` → continue the next unchecked milestone.
