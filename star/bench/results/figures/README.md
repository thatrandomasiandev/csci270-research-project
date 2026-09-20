# Figures

Locked Mac Suite B plots (stock STAR 2.7.11b vs S1–S8 + jemalloc + PGO).

**Browse on GitHub (public):**  
https://github.com/thatrandomasiandev/csci270-star-2x/tree/main/star/bench/results/figures

**Also mirrored for the paper:** `star/writeup/paper/figures/`

Regenerate:

```bash
python3 star/bench/scripts/plot_all_figures.py
```

| File | Content | Direct link |
|------|---------|-------------|
| `00_dashboard.png` | 4-panel overview | [open](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/00_dashboard.png) |
| `01_suiteB_stock_vs_opt_wall.png` | Wall-clock bars, all 10 | [open](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/01_suiteB_stock_vs_opt_wall.png) |
| `02_suiteB_speedup.png` | Mean speedup vs 2× | [open](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/02_suiteB_speedup.png) |
| `03_suiteB_per_pair_scatter.png` | Every timed pair | [open](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/03_suiteB_per_pair_scatter.png) |
| `04_suiteB_pass_board.png` | min_pair pass board | [open](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/04_suiteB_pass_board.png) |
| `05_rung_ladder_i01.png` | S1→S8 ladder on i01 | [open](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/05_rung_ladder_i01.png) |
| `06_suiteB_seconds_saved.png` | Absolute seconds saved | [open](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/06_suiteB_seconds_saved.png) |
| `07_suiteB_cv_stability.png` | Run-to-run CV% | [open](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/07_suiteB_cv_stability.png) |
| `08_suiteB_by_organism.png` | Human / fly / nf-core | [open](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/08_suiteB_by_organism.png) |
| `09_cost_model_schematic.png` | Copy vs productive (conceptual) | [open](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/09_cost_model_schematic.png) |
| `10_withdrawn_vs_honest.png` | Negative control | [open](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/10_withdrawn_vs_honest.png) |
| `honest_*.png` | Legacy lock / early s8j plots | (same folder) |

Reference CSV: [`../illumina10_s8j_mac.csv`](../illumina10_s8j_mac.csv)
