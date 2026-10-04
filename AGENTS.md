# Agent workflow — STAR ≥2× (course) + ACTS strategies

Two objects. Do not mix them.

1. **Zhang A-contract:** STAR ≥2×, Suite B, MATCH, one thread. Sealed Mac 10/10. Do not delete `star/` or invent a second timer.
2. **Research method:** `python3 -m acts` — first strategy is record memoization (Survivor 1). More strategies later, only when named. EGAS stays as the source-edit driver; it is not a new method.

You are **not** on the archived RL research.

Orientation: [`WHAT_WE_ARE_BUILDING.md`](WHAT_WE_ARE_BUILDING.md).

## Non-negotiables

- Goal: **reproducible ≥2× runtime** vs stock [STAR](https://github.com/alexdobin/STAR) on a **fixed** benchmark, **equal mapping quality** (define tolerance in SCOPE).
- Do **not** try to “make all of STAR 2× faster.” Pick **one hot path / mode / workload**.
- Do **not** resurrect RM-decay work into the course deliverable (`archive/rm-decay-vs-overopt/` is lab/PhD only).
- Prefer measurable progress every session: profile → hypothesize → patch → benchmark → update `STATUS.md`.

## Review standard (Principal Architect / PC chair)

Every ACTS design, critique or proposal is judged as an OSDI/SOSP/PLDI PC chair would judge it. Worked application: [`pipeline/docs/ARCHITECT_REVIEW.md`](pipeline/docs/ARCHITECT_REVIEW.md).

1. **Amdahl first.** Split runtime into wrapper `w`, startup `a`, per-record `b·n`, probe `P` (`acts/predict.py` model). Name the dominant term before designing anything. No micro-optimization of a term under 5% of runtime.
2. **Generic primitives.** Records, delimiters, key vs pass-through vs produced fields, cross-record state. Per-format parsers are fine; per-tool code is not. Credit borrowed mechanisms (group testing, property testing, Dune audit) and do not claim them as novel.
3. **Formal, not invented.** State assumptions, then derive closed forms (`T = a + b·n`, `(1-p)^n` probe miss, cumulative `S(K)`). No fake theorems.
4. **Inference vs refusal.** Perturbation that changes only copied fields → pass-through; produced-field change → widen the key. Refuse only for nondeterminism (F1/F7), neighbor/order (F2/F8), global state (F3). F6 is a stated limitation.
5. **Empirical integrity.** Every number is MEASURED (committed file) or PROJECTED (formula + assumptions). Strongest baselines (tool's own cache, Riker/ProcessCache, INCR). Every safety proposal has a kill experiment **and** ship controls (SnpEff MATCH 52,638; fill-tags widening) that must still ship.
6. **Red-team.** Name the 3 most dangerous reviewer attacks and the exact proof or experiment that defeats each.

Required output shape when asked for a review: (1) cost decomposition + Amdahl target, (2) core abstraction + ≥3 domains split TESTED / HYPOTHESIZED, (3) formal model + invariants, (4) algorithm with widen-vs-refuse handling, (5) red-team + kill experiments + ship controls.

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
