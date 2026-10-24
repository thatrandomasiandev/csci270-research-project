# Shared contract across genomes — design (P1)

**Status:** PROJECTED (W5x numbers) + code-justified phase table.  
**Branch:** `exp/shared-contract`. No paper edits. No CARC in this prompt.  
**P2 note:** Headline ρ(20)=1.29 assumes shared pin check; **code re-runs pin every genome** (conservative ρ(20)=2.08 without confirm tax; see `SHARED_CONTRACT_PILOT.md`).

## 0. Claim

For a batch of *N* genomes against one `(tool binary, argv template, reference
release)`, pay genome-independent first-run work once, then reuse those facts
with a cheap per-genome confirmation. Default path (no `--contract-store`) is
byte-identical to today.

## 1. Phase table (from `acts/reference_run.py`)

### Nesting rules (do not add nested times)

From `_phase_from` (lines 223–236): for a named wall `X_s`, the splits
`X_build_s` and `X_scan_s` are **inside** `X_s` (prep/subref_build and tool
deltas), not extra. Global `prep_s` / `tool_s` / `subref_build_s` /
`read_output_s` **accumulate every** `subprocess_invoke` call, including those
nested under discovery, pin_check, replay, verify, and IC2. After the probe,
`self.clock` is cleared and only `parse_s` is restored (`_run_cached`
1335–1355); probe work is reported under `probe_phases` / `probe_wall_s`.

**Non-overlapping first-run wall decomposition:**

| Phase | Nested inside | Reads | Class | Code justification |
|-------|---------------|-------|-------|--------------------|
| `parse_s` | — (pre-probe; restored) | reference file + genome records | **MIXED** → treat reference parse as SHAREABLE; genome read PER-GENOME | `run()` 1128–1134: `parse_reference(reference)` then `read_records(input)`. One timer wraps both. |
| probe wall (`probe_phases`: `subref_build_s`, `prep_s`, `tool_s`, `read_output_s`) | separate clock; not in post-probe `phases` totals as nested | binary, argv, **full release**, **genome sample** (`sample_record_indices`) | Runtime: PER-GENOME sample. **Facts** (FitResult): SHAREABLE candidates with confirmation | `probe_fit` 359–387 samples records; fits columns on whole vs parts of **entries** only. |
| `pin_check_s` | — wall; its invoke costs also add to `prep_s`/`tool_s` | binary, argv, release, **genome sample**, stored tables, pin | Runtime uses genome → confirm before reuse. Result today stored on contract as `pin_checks[template]` | `_pin_check` 1758–1775: sample records, whole vs pinned body bytes. |
| pin inference (`inferred_pin` store) | inside probe / pre-exact path; not a top-level W5x line | help text (binary), argv, half-ref, **genome sample**, tables | Template SHAREABLE with confirmation; evidence tool_calls are historical | `_take_inferred_pin` 1210–1263 |
| `coverage_read_s`, `diff_s` | — | cache + this genome's record keys + entry content hashes | PER-GENOME | `_incremental` 1791–1821 |
| `discovery_s` (`discovery_build_s`/`discovery_scan_s` nested) | — | fresh/partial entries × **this genome's records** | PER-GENOME | `_incremental` 1853–1861: `invoke(records, fresh)` |
| `cache_load_s`, `merge_rescale_s`, `cache_store_s` | — | cache rows for this genome | PER-GENOME | `_incremental` 1846–1880 |
| `replay_plan_s`, `replay_s` | —; build/scan nested | held rows + this genome + pin | PER-GENOME | `_run_exact` 1540–1546 |
| `ic2_*_s` (neighbor + random pads) | — | replayed records, candidates, pin | PER-GENOME (safety; never share) | `_ic2` 1677–1756 |
| `verify_s` / audit sample | — | stock vs ours on this genome | PER-GENOME (safety) | `_run_exact` 1577–1624 |
| `render_s` | — | held rows | PER-GENOME | write tables |
| top-level `prep_s` / `tool_s` | **not** additive with discovery/pin_check/replay | same as nested calls | do not classify separately | accumulator only |

### Update run (warm cache, same genome namespace)

Probe skipped if contract present. Pin check skipped if `pin_checks[key]`
present. Discovery/replay/IC2/audit still PER-GENOME. Shared-contract store
does not replace the per-genome row cache.

### W5x measured lines (job 13260165, r0) — nesting-aware

Quoted from the prompt (MEASURED elsewhere on `hub/collect-w8-w5x`):

| Line | Seconds | Role in non-overlap sum |
|------|---------|-------------------------|
| parse_s | 48.9 | unique |
| probe (prep+tool+subref) | 80.5+453.4+4.6 = 538.5 | unique (probe_phases) |
| pin_check_s | 151.8 | unique |
| discovery_s | 246.5 | unique (scan 245.1 nested) |
| replay_s | 5.3 | unique |
| cache_store_s | 1.1 | unique |
| **sum named** | **992.1** | |
| total_s | 1013.7 | remainder ≈ 21.6 (IC2/audit/render/merge/…) |
| stock | ≈ 1013.7/4.20 = **241.36** | uses measured ratio 4.20× |

Top-level `prep_s` 9.7 and `tool_s` 405.5 are **nested accumulators**, not
extra on top of discovery+pin_check+replay.

## 2. Facts the probe and pin check conclude — soundness risks

| Fact | Where stored | Could differ across genomes (same binary, argv, release)? | Concrete failure mode | Share policy |
|------|--------------|-----------------------------------------------------------|----------------------|--------------|
| `decision` / `reason` | FitResult | Yes | Genome A sample has only identity-looking columns; genome B exposes a size-dependent E-value column → wrong SHIP/REFUSE | Store; **confirm** on B's sample |
| per-table `record_col`, `entry_col`, `index_col` | TableReport | Yes | Sparse genome: one column constant → mistaken index; dense genome varies | Confirm |
| column `role` (`byte`/`numeric`) and `member` (`identity`, `entry_count`, `total_entry_length`, `per_key_row_count`) | ColumnReport | Yes | Constant column on A's sample fits `identity`; on B it scales with Z | Confirm |
| `primary_fits` / `tie` / `tie_break` / `used_tie_break` | FitResult | Yes | Tie broken by A's rows; B's rows prefer another member | Confirm; on mismatch full probe |
| `primary_key_equal`, `column_only_refusal`, `exact_eligible` | FitResult | Yes | Part-vs-whole key mismatch only visible when B's sample hits band rows | Confirm |
| table `meta` (header comments) | TableReport | Usually no for hmmscan | Tool header can embed query count / date | Treat as SHAREABLE only if byte-equal on confirm sample headers; else widen to re-probe |
| `layout` (padding / delim) | TableReport | Yes | Wider accession names on B change fixed-width layout | Confirm layout on B sample |
| `inferred_pin` template | contract | Low for help-derived flag; medium for member choice | Wrong member if tables mis-fitted | Store template; confirm size members still fitted; re-infer on fail |
| `pin_checks[template].ok` | contract | **Yes** | Pin works on A's hits; B's sample empty or pin fails body match | **Do not trust across genomes** without re-check (full or reduced-n pin check) |
| `slack_factor` | contract | No (from argv rewrite) | — | SHAREABLE (argv-derived) |
| coverage / row payloads | row cache | Yes | Genome-specific | Never share (PER-GENOME) |
| IC2 / audit outcomes | decision only | Yes | — | Never share |

## 3. PROJECTED first-run ratio ρ(N)

**Assumptions (PROJECTED, not measured):**

1. W5x r0 walls above; stock \(T = 1013.7 / 4.20 = 241.36\) s.
2. SHAREABLE paid once per batch: parse_ref≈parse_s (48.9; genome read negligible vs Pfam), full probe wall 538.5, pin_check 151.8 → \(S = 739.2\) s.
3. PER-GENOME remainder \(G = 1013.7 - 739.2 = 274.5\) s (discovery+replay+store+IC2/audit/…).
4. Confirmation tax on genomes 2..N is **ignored here** (upper-bound savings). Prompt 2 must measure confirmation.
5. No concurrency; exclusive node shape as W5x.

\[
\rho(N) = \frac{G + S/N}{T} = \frac{274.5 + 739.2/N}{241.36}
\]

| N | ρ(N) | vs 4.20 |
|---|------|--------|
| 1 | 4.20 | — |
| 5 | 1.75 | −58% |
| 20 | **1.29** | −69% |
| 100 | 1.17 | −72% |

**GATE 1:** require ρ(20) ≤ 3.15 (25% below 4.20). **PASS** (1.29 ≤ 3.15).

Conservative sensitivity (share probe only, re-pay pin_check+parse every genome):
\(S=538.5\), \(G=475.2\) → ρ(20)=2.08 ≤ 3.15, still PASS.

## 4. Feature shape (opt-in)

- Flag: `--contract-store DIR` (default unset → today's behavior).
- Key: `sha256(program binary) || normalized argv namespace blob || release content hash`
  (same binary+argv ingredients as `argv_namespace` / `program_binary`; release
  hash = sha256 of reference file bytes).
- Store: FitResult payload + `inferred_pin` + `slack_factor`. **Not** row cache,
  **not** raw `pin_checks` without confirm.
- On hit: run confirmation (reduced-n probe sample: re-derive roles/members;
  must match stored). On match, inject contract into this run's sqlite and skip
  full probe. Always run pin check on this genome (or reduced-n equivalent
  recorded in decision.txt). On mismatch: discard store entry for this genome,
  full probe, record reason.
- Atomic writes: `*.tmp` + `os.replace`.
- decision.txt: `contract_store: reused|miss|confirm_fail|corrupt|…`, key, confirmations.

## 5. What stays unchanged per genome

Neighbor + random pads (IC2), bounded audit (s=299 default path), refusal rules,
break-even fallback, exactness tests, default path without the flag.
EOF
