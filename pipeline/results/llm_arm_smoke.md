# LLM arm L — EGAS-hosted smoke dry-run (no model)

Not a live optimization run. Scripted `fake_agent.py` only.
Protocol: `docs/LLM_ARM_PROTOCOL.md` (`6968c6b`, locked; no addendum).
Loop: contract → Amdahl → T1–T3 propose → agent source edit → MATCH → decide.
T4/T5 unused. Isolated trees also under `pipeline/builds/llm_arm/` (gitignored).

| Run | Patch | MATCH smoke / fixture-test | EGAS decide | Score |
|-----|-------|------------------------------|-------------|-------|
| `results/llm_arm_smoke_safe/` | no-op rename in `score()` | **pass / pass** | INCOMPLETE (n=0 < 3; Mac is not a ship) | MATCH-clean; Mac timing is smoke; CARC later |
| `results/llm_arm_smoke_bad/` | `len(token)+1` (output column) | **fail / fail** | REFUSE_MATCH | **1.0×** (no credit); CARC not ready |

`model_id=TBD` is refused unless `--allow-fake`. Token cap is enforced
(exit 3). No network. Collections A/B were not used. No live model API.
