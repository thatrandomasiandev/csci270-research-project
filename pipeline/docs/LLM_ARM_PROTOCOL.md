# LLM code-optimization arm (pre-registered) — 2026-09-27

Written **before** any real optimization-agent run, any MATCH
score on collections A/B, and any CARC timing of this arm.
Do not edit the locked sections after seeing `results/llm_arm_*`
from a live model. Dated addenda below the lock are allowed.

This is comparison **arm L** from `docs/COMPARISON_PROTOCOL.md`,
now with a harness. It is **not** a new method, not a PIE model,
and not permission to rerun STAR Suite B.

Closest trusted priors we are **not** claiming:

- FunSearch (Romera-Paredes et al., Nature 2023) — propose →
  evaluator → keep. Loop *shape* only.
- PIE (Shypula et al., ICLR 2024) — LLM edits + tests on contest
  C++; mean ~6.86× @8 gens on that set, not on these CLIs.
  https://openreview.net/forum?id=ix7rLVHXyY
- FormulaCode (Sehgal et al., arXiv:2603.16011, ICML 2026) —
  957 repo-scale scientific-Python bottlenecks; frontier agents
  **underperform** human experts (negative Adv; global speedups
  ~1.05–1.10× vs expert ~1.10×). Not HMMER/SnpEff.
  https://arxiv.org/abs/2603.16011
- EGAS (`python3 -m egas`) — STAR course driver. Reuse; do not
  rewrite. STAR ≥2× is the sealed extras-inclusive bake-off.

No CARC from this file. No live model call until Josh sets the
PARAMETERS below. No download >1 GB. Do not fetch Pfam.

---

## What this is not (locked)

- Not a novelty claim for LLM code optimization.
- Not permission to start a real agent run.
- Not permission to change CLI flags, `--cut_ga`, `-Z`, E-value
  statistics, tblout columns, VCF ANN schema, or test FASTAs.
- Not permission to train PGO on collections A/B (dev is BW25113).
- Not a timing claim. Mac MATCH in the harness is a **smoke**
  check on tiny fixtures. CARC x86 epyc-7542 timing is later.
- Not a rewrite of `docs/SAVINGS_PROTOCOL.md` or STAR.

---

## Targets (locked)

| Target | What the agent may edit | What it must not touch |
|--------|-------------------------|------------------------|
| HMMER 3.4 `hmmscan --cut_ga` | Copied **source tree** under `pipeline/builds/llm_arm/` (never the system `/opt/homebrew` or CARC module install) | Pfam, collections A/B FASTAs, argv, MATCH type |
| HMMER 3.4 `hmmsearch -Z 1e6 --domZ 1e6` | Same tree, same constraints | Same |
| SnpEff 5.4c | Copied **Java source** under `pipeline/builds/llm_arm/` (jar at `tools/snpEff/` is read-only) | Genome DB, VCF test bodies, JVM flags as a substitute for source edits |
| STAR | **Out of scope.** Sealed EGAS 2× is already arm L. Do not rerun. | Suite B FASTQs, `STAR_opt_mac_s8_pgo` |

`hmmsearch` remains `paper_uses` / primary for savings. hmmscan is
post-hoc wherever it appears.

---

## Host: EGAS, add don't rewrite (locked)

Loop, identical in shape to `egas.driver.Driver`:

```
contract check → Amdahl gate → agent proposes T1–T3 source edits
  → MATCH bake-off → ship or refuse
```

Reuse `egas/` (`contract`, `amdahl`, `rungs.propose_from_symbol`,
`decide`). New code lives in `egas/llm_arm.py` and
`scripts/llm_arm_*.py`. Do not replace the STAR Method.

The agent's **allowed** rungs are T1 (copy/API waste), T2
(dead-path skip), T3 (closed form) from `egas/rungs.py`. T4
(PGO/LTO/jemalloc) is **arm T**, not arm L. T5 (new algorithm)
is out of scope.

---

## Allowed and forbidden agent actions (locked)

**Allowed:** edit files inside the isolated source copy; build
that copy; run the MATCH oracle and a **dev-set** timing oracle.

**Forbidden:**

- Changing CLI flags, output format, gathering thresholds, or
  E-value / Z statistics.
- Touching test data (collections A/B, HG00099, Suite B).
- Network access **beyond** the model API named in the config.
- Reading files outside the work directory except the declared
  oracles and the copied source.
- Editing `egas/`, `acts/`, or this protocol from inside a run.

---

## Data split (locked)

| Split | What | Visible to the agent? |
|-------|------|------------------------|
| **dev** | BW25113 proteome (`GCF_000750555.1`, already the PGO train set in `COMPARISON_PROTOCOL.md`) | **Yes.** MATCH + timing oracles for the loop. |
| **test** | Savings collections A and B (HMMER); HG00099 for SnpEff | **Never.** Scoring only, after the run, via `llm_arm_score.py`. |

A Mac smoke MATCH on `fixtures/llm_arm/` is **not** test data.
Label every such number `smoke`.

---

## PARAMETERS (Josh sets; TBD until then)

Do not fill these in after seeing a live run. Record the **exact
model ID** (vendor string, not a family nickname) at start of
each run.

| Parameter | TBD | Recommended default | Notes |
|-----------|-----|---------------------|--------|
| `hours_per_workload` | TBD | **8** wall-clock hours | Locked in `COMPARISON_PROTOCOL.md`. Stop even if MATCH is still green. |
| `tokens_per_workload` | TBD | **2,000,000** prompt+completion | Combined cap; no rollover across workloads. |
| `n_runs` | TBD | **3** independent runs | Variance. Same budget split across runs unless Josh expands it. |
| `model_id` | TBD | none — Josh names it | Record the API id (e.g. `claude-sonnet-4-…`, `gpt-5-…`). Do not hard-code a vendor in the harness. |
| `dollar_cap_per_workload` | TBD | see estimate below | Optional hard stop in addition to tokens. |

### Recommended default — cost estimate (not a bid)

Three remaining workloads (SnpEff, hmmscan, hmmsearch). STAR is
already spent.

**If the COMPARISON cap is shared across 3 runs** (recommended
until Josh says otherwise):

| | Per workload | ×3 workloads |
|--|--------------|--------------|
| Wall | 8 h | **24 h** serial (less if workloads parallelize) |
| Tokens | 2 M | **6 M** |
| Dollars (illustrative) | ~$10–25 | **~$30–75** |

Dollar range uses public list prices as of 2026-09, ~70/30
input/output mix, Sonnet-class ~$3/M in + $15/M out **or**
GPT-class similar. It is an estimate, not a quote. A more
expensive model or a completion-heavy agent sits at the high
end.

**If Josh instead funds 8 h / 2 M *per run*:** 3 runs × 3
workloads → **72 h**, **18 M** tokens, **~$90–225**. That is
an expansion of the COMPARISON lock; declare it.

CARC timing (epyc-7542 exclusive, interleaved stock anchors) is
**extra** node-hours, not in this table. See `docs/CARC_PLAN.md`.

### Refuse vs 1.0× (locked)

- If the budget produces **no MATCH-clean patch** with a **dev**
  profile predicting ≥ **1.10×** (not hope): that run is
  **incomplete**, not a silent 1× (`COMPARISON_PROTOCOL.md`).
- If MATCH **fails on test data**: that run **scores 1.0×** (no
  credit) and is reported. Do not time it on CARC.

---

## Scoring (locked)

MATCH types are a copy of `docs/SAVINGS_PROTOCOL.md`:

| Output | MATCH |
|--------|--------|
| hmmscan `--cut_ga` tblout | **order** + whitespace (`split()`) |
| hmmsearch `-Z 1e6 --domZ 1e6` tblout | **multiset** + whitespace |
| SnpEff VCF | record **body** (`acts.vcf.bodies_equal`) |

Then, only on MATCH-clean runs: time on CARC x86 epyc-7542,
interleaved with stock anchors, same `--cpu` / heap / `-Z` as
stock. Metrics: per-run speedup at measured *m*, and the
**cumulative** metric of `COMPARISON_PROTOCOL.md`.

Smoke MATCH on the Mac is labeled `smoke` and does not enter
the comparison table.

---

## Reproducibility (locked)

Per run, under `results/llm_arm_<workload>_<run>/`:

- `task.md` — the prompt the agent saw
- `transcript` — full agent stdout/stderr (and any JSONL the
  backend writes)
- `tokens.json` — prompt / completion counts the backend reports
- `diffs/*.diff` — every source diff, in apply order
- `final.diff` — union vs the isolated stock copy
- `build.log` — every compile
- `oracle_dev.json` — MATCH + timing on **dev** only
- `config.used.toml` — resolved PARAMETERS + exact `model_id`

The agent backend is a **CLI command in a config file**. Do not
hard-code a vendor.

---

## Expected outcomes (written BEFORE any run)

### Literature prior

PIE-scale 6× is the **wrong** prior for HMMER3 (already a SIMD
search kernel) and for SnpEff (JVM + genome-DB *a*). FormulaCode
is the right *qualitative* prior: agents stall on repo-scale
scientific bottlenecks (negative Adv vs experts; ~1.05–1.10×
global). We expect most MATCH-clean patches, if any, to land
near 1.0–1.1× on these binaries, and many runs to be incomplete
or 1.0× from a test MATCH fail.

### Cost model: what arm L must achieve to beat cache (arm C)

A uniform source speedup ρ applies to every genome.
`t_L = (a + b·N) / ρ`. Cache is
`t_C = a + b·m·N + w`. L beats C on that genome iff
**ρ > t_S / t_C**, i.e. ρ greater than the predicted cache
speedup at that *m*.

Numbers from `headline_screen.json` and
`hmmer_predicted_speedup.json` (predictions, *N* = 4,192).
SnpEff from `snpeff_alternating_carc.json` / comparison table.

| Workload | Point | Cache predicted / measured | **ρ arm L must beat** |
|----------|-------|----------------------------|------------------------|
| hmmscan A | per-run k=10 | 2.956× | **> 2.956×** |
| hmmscan A | per-run k=30 | 4.097× | **> 4.097×** |
| hmmscan A | cumulative 30 | 2.936× | **> 2.936×** cum. |
| hmmscan B | per-run k=10 | 36.66× | **> 36.66×** |
| hmmscan B | per-run k=39 | 50.72× | **> 50.72×** |
| hmmsearch A | per-run k=10 | 2.120× | **> 2.120×** |
| hmmsearch A | per-run k=30 | 2.521× | **> 2.521×** |
| hmmsearch A | cumulative 30 | 2.111× | **> 2.111×** cum. |
| hmmsearch B | per-run k=10 | 4.473× | **> 4.473×** |
| hmmsearch B | per-run k=39 | 4.597× | **> 4.597×** |
| SnpEff HG00099 | per-run measured *m* | 1.167× meas. / 1.203× pred. | **> 1.203×** to beat C; **> 1.677×** to beat predicted TC |

Arm T (PGO ~1.10×) is a much lower bar than C on HMMER
collections. Beating **C**, not T, is the interesting comparison.
The cost model does **not** predict L beats C on A or B.

SnpEff: L is not predicted to beat TC (*a* is JVM + DB load, not
a PIE kernel). Beating C (~1.2×) is conceivable for a startup
edit; that would be arm T's job (AppCDS), not T1–T3 source.

---

## Harness (after this file is committed)

1. `scripts/llm_arm_run.py` — isolated source copy, task file,
   pluggable agent CLI, wall + token caps, collect artifacts.
2. `scripts/llm_arm_score.py` — final diff, smoke MATCH on Mac
   fixtures, emit CARC timing inputs. Do not time A/B here.
3. Validate **without** an LLM: scripted fake agent, known-safe
   patch (MATCH, scored) and known-bad patch (MATCH fail, 1.0×).

`bash run_tests.sh` must pass. Do not call a model API from
tests.
