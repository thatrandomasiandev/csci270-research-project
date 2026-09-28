# Probe eval — batched vs singleton (main)

JSON: `probe_eval_subset_batched.json`, `probe_eval_subset_singleton.json`
(`e24370f`). `--verify audit`, seed 20260927. Figures:
`19_probe_eval_subset_batched.png`, `20_probe_eval_subset_singleton.png`.

Raw JSON `report.in_scope_*` still stores the macOS carve-out
(**36/256**, excl. F6-env only) and is **not** rewritten. Labels below
follow the 2026-09-27 canonical addendum in
`docs/PROBE_EVAL_PROTOCOL.md`.

F6-file is covered by probe-time tracing on Linux and is not yet
measured (`docker info` failed 2026-09-27). F6-env is the real
limitation.

## Headline (both subset modes)

| Label | batched | singleton |
|-------|---------|-----------|
| Unsafe-ship overall | 68/288 | 68/288 |
| **In-scope (canonical):** excl. F6-env and F6-file | **4/224** | **4/224** |
| Excl. F6-env only (macOS, no tracing) | **36/256** | **36/256** |
| F6-env (limitation) | 32/32 | 32/32 |
| F6-file (Linux tracing; unmeasured here) | 32/32 on this Mac | 32/32 on this Mac |
| False-refuse | 0/20 | 0/20 |

Canonical 4/224 is `unsafe_ship_n` minus F6-env minus F6-file, over
288 − 32 − 32. Same four in-scope misses as `probe_eval_audit.md`
(F4 field-role plus one F3 at `probe_n`=50, *p*=0.01).

A pre-merge stash snapshot of the same comparison is
`probe_eval_subset_stash.md` (`f723379`).
