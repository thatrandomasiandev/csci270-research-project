# Arm L task (EGAS-hosted)

Protocol: `docs/LLM_ARM_PROTOCOL.md`. Work directory: `/Users/joshuaterranova/Desktop/CSCI270/ACTS-llmarm/pipeline/builds/llm_arm/smoke_safe/work`.

## Goal
Propose T1–T3 source edits so the isolated binary is faster on the **dev**
set without changing outputs. MATCH must pass before any speedup counts.

## Allowed
- edit source files inside the isolated copy
- build the isolated copy
- run the MATCH oracle on the DEV set
- run the timing oracle on the DEV set

## Forbidden
- changing CLI flags, output format, thresholds, or E-value / Z statistics
- touching test data (collections A/B, HG00099, Suite B)
- network access beyond the model API named in the config
- reading files outside the work directory except declared oracles
- T4 PGO/LTO/jemalloc (that is comparison arm T)
- T5 new algorithms
- rerunning STAR Suite B

## Dev-set oracles
- MATCH: `order` + whitespace (`split()`), same family as hmmscan `--cut_ga`.
- Input: `/Users/joshuaterranova/Desktop/CSCI270/ACTS-llmarm/pipeline/fixtures/llm_arm/data/dev.tsv` (BW25113 stand-in in the fixture; real runs use BW25113).
- Timing: wall of this tool on **dev** only. Not collections A/B.

## Budget (PARAMETERS)
- wall hours: 0.05
- tokens (prompt+completion): 2000000
- independent runs (this is one of 3): recorded by the harness
- model_id: `TBD`  (must be an exact API id before a live run)

Stop when either cap hits, even if MATCH is still green.

## T1–T3 plan (from `egas.rungs.propose_from_symbol`; not a patch)
- **T2_DEAD_PATH** `t2_score`: Dead-path skip in score. Profile early-exit rates. If most calls fail a cheap predicate, hoist it.
- **T3_CLOSED_FORM** `t3_score`: Closed form in score. Replace a constant-iteration score loop with a multiply if the paper/code allows.

## Ship / refuse
- MATCH fail on **test** (scoring, after this run) → this run scores **1.0×**.
- Budget exhausted with no MATCH-clean patch predicting ≥1.10× on **dev** →
  **incomplete**, not a silent 1×.
