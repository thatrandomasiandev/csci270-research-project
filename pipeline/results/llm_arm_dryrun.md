# LLM arm L — harness dry-run (no model)

Not a live optimization run. Scripted `fake_agent.py` only.
Protocol: `docs/LLM_ARM_PROTOCOL.md` (`6968c6b`).

| Run | Patch | MATCH (fixture test TSV) | Score |
|-----|-------|--------------------------|-------|
| `results/llm_arm_dryrun_safe/` | no-op rename in `score()` | **pass** | MATCH-clean; Mac timing is smoke; CARC later |
| `results/llm_arm_dryrun_bad/` | `len(token)+1` (output column) | **fail** | **1.0×** (no credit); not timed |

`model_id=TBD` is refused unless `--allow-fake`. Token cap is enforced
(exit 3). No network. Collections A/B were not used.
