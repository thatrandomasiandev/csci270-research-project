"""LLM comparison arm L — task files, budget, isolate. Add, don't rewrite EGAS."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from egas.rungs import Rung, propose_from_symbol

PIPE = Path(__file__).resolve().parents[1]
PROTOCOL = PIPE / "docs" / "LLM_ARM_PROTOCOL.md"

ALLOWED = (
    "edit source files inside the isolated copy",
    "build the isolated copy",
    "run the MATCH oracle on the DEV set",
    "run the timing oracle on the DEV set",
)
FORBIDDEN = (
    "changing CLI flags, output format, thresholds, or E-value / Z statistics",
    "touching test data (collections A/B, HG00099, Suite B)",
    "network access beyond the model API named in the config",
    "reading files outside the work directory except declared oracles",
    "T4 PGO/LTO/jemalloc (that is comparison arm T)",
    "T5 new algorithms",
    "rerunning STAR Suite B",
)


@dataclass(frozen=True)
class Budget:
    """PARAMETERS. hours/tokens TBD until Josh fills them; defaults are recommendations."""

    hours: float = 8.0
    tokens: int = 2_000_000
    n_runs: int = 3
    model_id: str = "TBD"
    dollar_cap: float | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["protocol"] = "docs/LLM_ARM_PROTOCOL.md"
        return d


def t1_t3_plan(symbol: str = "score", fraction: float = 0.80) -> list[Rung]:
    """Reuse EGAS propose; T4/T5 stay out of this arm."""
    return propose_from_symbol(symbol, fraction)


def write_task_file(
    dest: Path,
    *,
    budget: Budget,
    workdir: Path,
    rungs: list[Rung] | None = None,
    dev_input: str = "dev.tsv",
    match: str = "order",
) -> Path:
    rungs = rungs or t1_t3_plan()
    rung_lines = "\n".join(
        f"- **{r.cls.value}** `{r.id}`: {r.title}. {r.hint}" for r in rungs
    )
    text = f"""# Arm L task (EGAS-hosted)

Protocol: `docs/LLM_ARM_PROTOCOL.md`. Work directory: `{workdir}`.

## Goal
Propose T1–T3 source edits so the isolated binary is faster on the **dev**
set without changing outputs. MATCH must pass before any speedup counts.

## Allowed
{chr(10).join('- ' + a for a in ALLOWED)}

## Forbidden
{chr(10).join('- ' + a for a in FORBIDDEN)}

## Dev-set oracles
- MATCH: `{match}` + whitespace (`split()`), same family as hmmscan `--cut_ga`.
- Input: `{dev_input}` (BW25113 stand-in in the fixture; real runs use BW25113).
- Timing: wall of this tool on dev only. Not collections A/B.

## Budget (PARAMETERS)
- wall hours: {budget.hours}
- tokens (prompt+completion): {budget.tokens:,}
- independent runs (this is one of {budget.n_runs}): recorded by the harness
- model_id: `{budget.model_id}`  (must be an exact API id before a live run)

Stop when either cap hits, even if MATCH is still green.

## T1–T3 plan (from `egas.rungs.propose_from_symbol`; not a patch)
{rung_lines}

## Ship / refuse
- MATCH fail on **test** (scoring, after this run) → this run scores **1.0×**.
- Budget exhausted with no MATCH-clean patch predicting ≥1.10× on **dev** →
  **incomplete**, not a silent 1×.
"""
    dest.write_text(text)
    return dest


def isolate_source(src: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, dirs_exist_ok=False)
    return dest


def unified_diff(stock: Path, work: Path) -> str:
    r = subprocess.run(
        ["diff", "-ru", str(stock), str(work)],
        check=False,
        capture_output=True,
        text=True,
    )
    # diff exits 1 when files differ, 0 when same, 2 error
    if r.returncode not in (0, 1):
        raise RuntimeError(r.stderr or f"diff failed: {r.returncode}")
    return r.stdout


def parse_tokens(payload: dict) -> int:
    return int(payload.get("prompt_tokens", 0)) + int(payload.get("completion_tokens", 0))


def budget_ok(budget: Budget, *, elapsed_s: float, tokens: int) -> tuple[bool, str]:
    if elapsed_s > budget.hours * 3600:
        return False, f"wall cap {budget.hours}h exceeded ({elapsed_s:.1f}s)"
    if tokens > budget.tokens:
        return False, f"token cap {budget.tokens} exceeded ({tokens})"
    return True, "ok"


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n")


class WallClock:
    def __init__(self) -> None:
        self.t0 = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.t0
