# CSCI 270 Research Project — STAR speedup (A-contract)

**Course contract (Zhang):** improve a widely used solution with a clear measurable win.  
**Target artifact:** scoped optimization of [STAR](https://github.com/alexdobin/STAR) (RNA-seq aligner) with a reproducible **≥2×** runtime improvement on a fixed benchmark at **equal mapping quality**.

**Public reproduce repo:** [thatrandomasiandev/csci270-star-2x](https://github.com/thatrandomasiandev/csci270-star-2x)

**Out of scope for this repo root:** RM-decay / SAC / CARC RL work (archived under [`archive/rm-decay-vs-overopt/`](archive/rm-decay-vs-overopt/); PhD/lab track).

## Layout

```
star/
  upstream/     # STAR source (clone / release tarball)
  src/          # our patches / reimplemented hot path
  bench/        # datasets notes, scripts, results, figures/
  docs/         # design notes, profiling logs, REPRODUCE.md
  writeup/      # course submission LaTeX/Markdown + paper/figures/
AGENTS.md       # agent workflow instructions
STATUS.md       # living target vs current
```

## Figures (Suite B bake-off)

Regenerate locally: `python3 star/bench/scripts/plot_all_figures.py`

| Preview | Description |
|---------|-------------|
| [Dashboard](star/bench/results/figures/00_dashboard.png) | 4-panel overview |
| [Wall-clock](star/bench/results/figures/01_suiteB_stock_vs_opt_wall.png) | Stock vs opt, all 10 datasets |
| [Speedup](star/bench/results/figures/02_suiteB_speedup.png) | Mean × vs 2× claim |
| [Per-pair](star/bench/results/figures/03_suiteB_per_pair_scatter.png) | Every timed pair |
| [Pass board](star/bench/results/figures/04_suiteB_pass_board.png) | min_pair ≥ 2.0 |
| [Rung ladder](star/bench/results/figures/05_rung_ladder_i01.png) | S1→S8 on i01 |
| [Seconds saved](star/bench/results/figures/06_suiteB_seconds_saved.png) | Absolute time saved |
| [Stability](star/bench/results/figures/07_suiteB_cv_stability.png) | Run-to-run CV% |
| [By organism](star/bench/results/figures/08_suiteB_by_organism.png) | Human / fly / nf-core |
| [Cost model](star/bench/results/figures/09_cost_model_schematic.png) | Copy vs productive (schematic) |
| [Negative control](star/bench/results/figures/10_withdrawn_vs_honest.png) | Withdrawn vs honest |

Full index: [`star/bench/results/figures/README.md`](star/bench/results/figures/README.md)  
Browse on GitHub: [figures/](https://github.com/thatrandomasiandev/csci270-star-2x/tree/main/star/bench/results/figures)

## Success criteria (A package)

1. Professor scope lock on email (recorded in `docs/SCOPE.md`)
2. Stock STAR baseline numbers on fixed hardware + data
3. One named hot-path optimization with rationale
4. Bake-off: ≥2× wall-clock on the agreed workload; mapping metrics within tolerance
5. Short write-up + how to reproduce

## Reproduce on another computer (professor)

See **[`star/docs/REPRODUCE.md`](star/docs/REPRODUCE.md)** (includes figure links).

Josh packs bit-identical Suite B inputs (~300 MB):

```bash
./star/bench/scripts/package_for_professor.sh ~/Desktop/STAR_suiteB_repro.tar.gz
```

Professor unpacks and runs `bash RUN_ME.sh` (builds stock + opt, runs all 10 MATCH-gated bake-offs, prints the same scoreboard layout as `STATUS.md`).

Absolute seconds will differ by CPU; **MATCH output** and **≥2× on the same machine** are the graded claims.

## Quick start (agents)

Read `AGENTS.md` → `STATUS.md` → continue the next unchecked milestone.
