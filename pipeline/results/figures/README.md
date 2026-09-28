# Pipeline figures (2026-09-24)

Source numbers only: `../snpeff_timing_fit.json`, `../snpeff_cached_identity.json`, `../vep_chr22_overlap.json`, `../snpeff_identity/report.json`, `../suiteB_dups.csv`, `../suiteB_overlap.csv`, `../snpeff_alternating_carc.json`, `../recurrence_curves.json`, `../probe_eval.json`, `../probe_eval_audit.json`.

```bash
cd pipeline && python3 scripts/plot_pipeline_figures.py
```

STAR ≥2× Suite B plots are a different object: `star/bench/results/figures/`.

| File | What |
|------|------|
| `00_dashboard.png` | Overlap, fit, predicted vs measured wall, Amdahl vs N/miss_n |
| `01_ceu_overlap_recall.png` | CEU pairwise + 96∪97→99 recall_in_new |
| `02_cache_hits_misses.png` | Populate 96→97 then HG00099 hits/misses |
| `03_snpeff_timing_fit.png` | Stock t = a + b·n, 3 runs/size |
| `04_amdahl_decomposition.png` | Locked a / b·n / w stack |
| `05_cached_vs_stock_runs.png` | Part B, 3 runs after MATCH |
| `06_predicted_vs_measured.png` | Locked prediction beside measured (not rewritten) |
| `07_suiteB_unique_frac.png` | STAR instance uniqueness |
| `08_instance_recall_compare.png` | Suite B reads vs CEU variants |
| `09_match_board.png` | Body MATCH; header cmp expected DIFF |
| `10_suiteB_max_speedup_if_pure.png` | Uniqueness bound only; STAR REFUSE_IDENTITY |
| `11_snpeff_alternating_carc.png` | CARC exclusive 10-pair wall + median r with bootstrap CI |
| `17_probe_eval_catch.png` | Probe catch rate vs fault frequency (F1–F8, four `probe_n`) — `--verify full` upper bound (was `12_`, collided with recurrence A) |
| `16_probe_eval_full_vs_audit.png` | Unsafe-ship / false-refuse: full MATCH vs audit |
| `18_probe_eval_audit_catch.png` | Same catch-rate plot in `--verify audit` (deployed; was `15_`, collided with HMMER predicted speedup) |
| `12_recurrence_A_ecoli.png` | Diverse *E. coli* median m(k) + 10–90% band; 1/3 gate |
| `13_recurrence_B_o157.png` | O157:H7 (Eppinger lineage / B1) median m(k) |
| `14_recurrence_C_saureus.png` | *S. aureus* median m(k) |
