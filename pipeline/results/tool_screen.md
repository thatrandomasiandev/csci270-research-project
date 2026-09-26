# Tool screen results (2026-09-25)

Source: `tool_screen.json`. Protocol: `docs/TOOL_SCREEN.md` (commit `c51ed61`). Stock `t = a + b·n` only. No cache.

Advance if `ceiling(0.2) = (a+bN)/(a+b·0.2·N) ≥ 3.0`.

| Tool | N | a (s) | b (s/rec) | ceil m=0.2 | ceil 100% hits | Advances |
|------|--:|------:|----------:|-----------:|---------------:|:--------:|
| VEP offline chr22 | — | — | — | — | — | skip (no binary/cache) |
| SnpSift dbNSFP | — | — | — | — | — | skip (no TSV) |
| SnpEff 5.4c heavier (stats, −ud 20000) | 52638 | 10.016 | 7.633e−5 | 1.30 | 1.40 | no |
| ruff check −−no-cache 0.8.4 | 16259 | 0.0187 | 4.215e−5 | 4.52 | 37.6 | **yes** |

Machine: Mac, load 4.47 / 10.45 / 10.14 → 5.49 / 8.61 / 9.45. `osascript` quit of Google Drive returned 0; DriveFS auto-restarted. SnpEff n=1 run 1 was 12.61 s vs later 9.29 / 9.43 s.

ruff absolute wall at N is 0.705 s. At m=0.2 the model pays ~0.16 s — a 4.5× ratio on a sub-second job.
