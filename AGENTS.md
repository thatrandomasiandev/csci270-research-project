# Agent workflow — STAR ≥2× for CSCI 270 A

You are working on Josh’s **course A-contract** project, not the archived RL research.

## Non-negotiables

- Goal: **reproducible ≥2× runtime** vs stock [STAR](https://github.com/alexdobin/STAR) on a **fixed** benchmark, **equal mapping quality** (define tolerance in SCOPE).
- Do **not** try to “make all of STAR 2× faster.” Pick **one hot path / mode / workload**.
- Do **not** resurrect RM-decay work into the course deliverable (`archive/rm-decay-vs-overopt/` is lab/PhD only).
- Prefer measurable progress every session: profile → hypothesize → patch → benchmark → update `STATUS.md`.

## Session protocol

1. Read [`STATUS.md`](STATUS.md) and [`star/docs/SCOPE.md`](star/docs/SCOPE.md) (create SCOPE if missing).
2. Pick the **single next milestone** (see STATUS).
3. Make the smallest change that advances that milestone.
4. Record commands, timings, and outcomes in `star/docs/PROFILING_LOG.md` or `star/bench/results/`.
5. Update `STATUS.md` checkboxes and “Current blockers.”
6. Stop when the milestone is done or blocked on Josh (email, Duo, hardware).

## Milestone order (do not skip)

1. **Scope lock** — draft sent; Josh confirms Zhang OK → write `star/docs/SCOPE.md`
2. **Build stock STAR** — compile upstream; record version + flags
3. **Benchmark harness** — one script: time STAR on fixed FASTQs; log CSV
4. **Baseline** — ≥3 runs; mean ± std wall time + mapping rate
5. **Profile** — `perf` / Instruments / gprof; name the hot function(s)
6. **Optimize** — implement only that path in `star/src/` or upstream patch
7. **Bake-off** — same data/flags; claim 2× only if numbers say so
8. **Write-up** — `star/writeup/` for course submission

## If 2× fails

Narrow the workload further (shorter reads, single-end, smaller genome subset) **or** change hot path — do not inflate claims. Update SCOPE with Josh if the graded claim changes.

## Useful commands (fill in as you go)

```bash
# build (example)
cd star/upstream/source && make STAR

# bench (once harness exists)
./star/bench/scripts/run_baseline.sh
./star/bench/scripts/run_optimized.sh
```
