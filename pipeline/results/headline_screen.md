# HMMER headline screen — job 12377262

Stock CLI only. No ACTS cache. No speedup claim. Protocol:
`docs/HEADLINE_SCREEN.md` (erratum 2026-09-26). JSON:
`results/headline_screen.json`. Logs: `headline_hmmer-12377262.out`,
`.err`.

## Run

| Knob | Value |
|------|-------|
| Job | **12377262** |
| Node | **b22-16** (exclusive `main`, account `biyik_1165`) |
| CPU | AMD EPYC 7542, `--cpu 32` (`nproc` on the allocated socket) |
| HMMER | **3.4** (Aug 2023), built on the node |
| Pfam-A | **38.2**, 30,134 models (2026-01 / UniProtKB 2025_03) |
| Input | BW25113 `protein.faa.gz`, **N = 4,192** |
| `m` | K-12 MG1655 ∪ W3110 → BW25113 **0.0019** (`kprot_overlap.json`) |

The gate used that K-12 `m`. It is a **best case**. Diverse *E. coli*
`m(10)` in `recurrence_curves.json` sits near 1/3; do not read the
81× / 4.7× ceilings as a realistic-collection claim.

## Modes (both subset-invariant, k = 8)

| Mode | a (s) | b (s/record) | w (s) | ceiling(m) | saved (s) | decision |
|------|------:|-------------:|------:|-----------:|----------:|----------|
| hmmscan `--cut_ga` | 31.96 | 0.723 | 0.019 | **81.1** | 3024 | ADVANCE |
| hmmsearch `-Z 1e6 --domZ 1e6` | 132.56 | 0.119 | 0.018 | **4.73** | 497 | ADVANCE |

`paper_uses` = hmmsearch (locked rule: first mode that passes (b2) and
the ceiling; if both, hmmsearch).

## Noted anomaly

hmmscan **n = 800**, three runs: **531.1, 708.3, 783.9 s** (mean 674.4,
stdev 129.7). Same tblout count (1,579). Load was not idle. The OLS
`a`/`b` still include this point. Treat the hmmscan slope as noisier
than hmmsearch (n=800 stdev 3.2 s).
