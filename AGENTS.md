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

## Test design standard (2026-10-12; applies to every experiment)

Goal: the smoothest path forward and the most reliable data. A KILL must
mean the method failed, never that the test was blind. Four of the first
five knob/DIAMOND runs died on test design (empty sample, comparison rule
blind to count columns, a gate across independent questions). Do not repeat that.

1. **Semantics review first (no runs).** Read the tool's docs/source for
   every behavior that could make a check fail for a reason unrelated to
   the claim (nondeterminism, size-dependent auto settings, heuristics that
   read the database, tie order, print rounding, count/index columns).
   Write each one down with how it would show up and how the pilot detects it.
2. **Pilot before lock.** Run the whole design once on disjoint data (own
   seed, never reused). The pilot must show: the test can observe the
   effect (rows exist, power floor met), the parser/criteria pass a
   known-good case and fail a known-bad case, and the run completes end to
   end. The pilot may change the design; it is reported as a pilot, not a result.
3. **Lock, then measure.** Pre-register after the pilot, with the pilot's
   findings cited. The measured run uses a fresh sample.
4. **Independent questions run independently.** Gate a step only on a true
   logical dependency. Exactness is never gated on inference, or vice versa.
5. **Every acceptance rule has controls.** A positive control that must
   pass and a negative control that must fail, both checked in the pilot.
6. **Power and determinism are checked, not assumed.** Stock-vs-stock
   identity first; a locked minimum count of observable rows; INCONCLUSIVE
   (not KILL) when power is missing.
7. **Diagnose every failure.** A failing check reports difference classes
   (value-only / different row / missing / extra / order) so the next step
   is obvious from the result file.
8. **No third redesign of the same question.** After two locked failures,
   record the limitation and move on.

## Paper ownership (2026-10-19)

The only paper is `pipeline/paper/tare/main.tex` on `main`. Only the hub session edits it.
Experiment agents never edit `main.tex` and never keep an uncommitted copy of the paper in their worktree.
They commit results, figure scripts under `pipeline/paper/tare/figures/`, and protocol docs on their own
branch, and end their report with proposed paper sentences, each with its `% source:` keys. The hub verifies
those against the result files and integrates them. Archived papers live under `archive/`; do not edit them.

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
