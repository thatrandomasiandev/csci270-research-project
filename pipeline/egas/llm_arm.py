"""LLM comparison arm L — isolate, budget, EGAS host loop.

Add, do not rewrite ``egas.driver.Driver`` or the STAR Method.
T4 is arm T; T5 is out of scope. No live model API lives here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from acts.table import tables_match
from egas.amdahl import AmdahlResult, evaluate_amdahl
from egas.contract import Contract
from egas.decide import DecideInput, DecisionRecord, decide
from egas.profile_io import Profile
from egas.report import RunReport, amdahl_dict, format_human
from egas.rungs import Rung, RungClass, propose_from_symbol

PIPE = Path(__file__).resolve().parents[1]
PROTOCOL = PIPE / "docs" / "LLM_ARM_PROTOCOL.md"
SOURCE_RUNGS = frozenset(
    {RungClass.T1_COPY, RungClass.T2_DEAD_PATH, RungClass.T3_CLOSED_FORM}
)
DIFF_IGNORE = frozenset({"tokens.json", "transcript.txt", "__pycache__"})

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
        d["protocol"] = PROTOCOL.name
        return d


@dataclass(frozen=True)
class HostPrep:
    contract: Contract
    amdahl: AmdahlResult | None
    rungs: list[Rung]
    proceed: bool
    reason: str


def t1_t3_plan(symbol: str = "score", fraction: float = 0.80) -> list[Rung]:
    """Reuse EGAS propose; drop T4/T5 if a caller ever injects them."""
    return [r for r in propose_from_symbol(symbol, fraction) if r.cls in SOURCE_RUNGS]


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
- Timing: wall of this tool on **dev** only. Not collections A/B.

## Budget (PARAMETERS)
- wall hours: {budget.hours}
- tokens (prompt+completion): {budget.tokens}
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
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text)
    return dest


def isolate_source(src: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )
    return dest


def snapshot_tree(src: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)
    return dest


def unified_diff(stock: Path, work: Path) -> str:
    r = subprocess.run(
        ["diff", "-ru", str(stock), str(work)],
        check=False,
        capture_output=True,
        text=True,
    )
    if r.returncode not in (0, 1):
        raise RuntimeError(r.stderr or f"diff failed: {r.returncode}")
    kept: list[str] = []
    skip = False
    for line in r.stdout.splitlines(keepends=True):
        if line.startswith("diff ") or line.startswith("Binary files"):
            skip = any(name in line for name in DIFF_IGNORE)
        if not skip:
            kept.append(line)
    return "".join(kept)


def parse_tokens(payload: dict) -> int:
    return int(payload.get("prompt_tokens", 0)) + int(payload.get("completion_tokens", 0))


def budget_ok(budget: Budget, *, elapsed_s: float, tokens: int) -> tuple[bool, str]:
    if elapsed_s > budget.hours * 3600:
        return False, f"wall cap {budget.hours}h exceeded ({elapsed_s:.1f}s)"
    if tokens > budget.tokens:
        return False, f"token cap {budget.tokens} exceeded ({tokens})"
    return True, "ok"


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def write_toml(path: Path, tables: dict[str, dict]) -> None:
    """Minimal TOML writer for config.used.toml. No vendor library."""

    def lit(v: object) -> str:
        if v is None:
            return '""'
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int) and not isinstance(v, bool):
            return str(v)
        if isinstance(v, float):
            return repr(v)
        return json.dumps(str(v))

    chunks: list[str] = ["# resolved PARAMETERS + exact model_id (TBD until Josh names it)", ""]
    for name, rows in tables.items():
        chunks.append(f"[{name}]")
        for key, val in rows.items():
            chunks.append(f"{key} = {lit(val)}")
        chunks.append("")
    path.write_text("\n".join(chunks))


class WallClock:
    def __init__(self) -> None:
        self.t0 = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.t0


def prepare_host(contract: Contract, profile: Profile | None) -> HostPrep:
    """Contract check → Amdahl. T4 slack is not a proceed for arm L."""
    if profile is None:
        rungs = t1_t3_plan()
        return HostPrep(
            contract=contract,
            amdahl=None,
            rungs=rungs,
            proceed=True,
            reason="no profile; Amdahl skipped (fixture/incomplete — not a live claim)",
        )
    amdahl = evaluate_amdahl(
        profile,
        contract.target_speedup,
        allow_t4_assist=False,
    )
    hot = amdahl.hottest_legal
    rungs = t1_t3_plan(hot.symbol if hot else "score", hot.fraction if hot else 0.80)
    proceed = amdahl.proceed
    return HostPrep(
        contract=contract,
        amdahl=amdahl,
        rungs=rungs,
        proceed=proceed,
        reason=amdahl.reason if proceed else (
            amdahl.reason + " Arm L does not take T4; refuse rather than proceed_with_t4."
        ),
    )


def finish_host(
    *,
    contract: Contract,
    prep: HostPrep,
    match: bool | None,
    out_dir: Path,
    applied: list[str] | None = None,
) -> tuple[DecisionRecord, RunReport]:
    """MATCH bake-off → ship/refuse. Mac smoke is not n≥3 timing — never SHIP here."""
    rec = decide(
        DecideInput(
            match=match,
            min_pair=None,
            mean_speedup=None,
            n_pairs=0,
            target=contract.target_speedup,
            amdahl_ok=prep.proceed and (prep.amdahl is None or prep.amdahl.proceed),
            amdahl_t4_only=False,
            automated_rungs_left=False,
            source_rungs_left=bool(prep.rungs),
            runs_required=contract.runs,
        )
    )
    report = RunReport(
        contract=contract.name,
        method="llm_arm",
        decision=rec.decision.value,
        reason=rec.reason,
        amdahl=amdahl_dict(prep.amdahl) if prep.amdahl else None,
        bakeoffs=[],
        proposed=[
            {"id": r.id, "cls": r.cls.value, "title": r.title, "hint": r.hint}
            for r in prep.rungs
        ],
        applied=list(applied or []),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    report.write(out_dir / "report.json")
    (out_dir / "decision.txt").write_text(format_human(report, rec))
    return rec, report


def run_score_rows(script: Path, table: Path, outp: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), str(table), str(outp)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def match_fixture_table(stock_src: Path, work_src: Path, table: Path) -> dict:
    """Order + whitespace MATCH on the fixture TSV. Not collections A/B."""
    stock_py = stock_src / "score_rows.py"
    work_py = work_src / "score_rows.py"
    with tempfile.TemporaryDirectory(prefix="llm_arm_match_") as td:
        tmp = Path(td)
        stock_out, work_out = tmp / "stock.tsv", tmp / "work.tsv"
        rs = run_score_rows(stock_py, table, stock_out)
        rw = run_score_rows(work_py, table, work_out)
        if rs.returncode != 0 or rw.returncode != 0:
            return {
                "match": False,
                "match_type": "order+ws",
                "error": {
                    "stock_rc": rs.returncode,
                    "work_rc": rw.returncode,
                    "stock_err": rs.stderr[-500:],
                    "work_err": rw.stderr[-500:],
                },
            }
        a, b = stock_out.read_text(), work_out.read_text()
        ok = tables_match(a, b, "order", match_ws=True)
        rows = len([ln for ln in a.splitlines() if ln.strip()]) - 1
        return {
            "match": ok,
            "match_type": "order+ws",
            "rows": rows,
            "stock_head": a.splitlines()[:4],
            "work_head": b.splitlines()[:4],
        }


def smoke_dev_oracle(stock_src: Path, work_src: Path, table: Path) -> dict:
    """Dev MATCH + tiny walls. Label every number smoke. Not a comparison timing."""
    match = match_fixture_table(stock_src, work_src, table)
    walls: dict[str, float] = {}
    if match.get("match") is not False or "error" not in match:
        with tempfile.TemporaryDirectory(prefix="llm_arm_oracle_") as td:
            tmp = Path(td)
            for label, src in (("stock", stock_src), ("work", work_src)):
                t0 = time.perf_counter()
                proc = run_score_rows(src / "score_rows.py", table, tmp / f"{label}.tsv")
                walls[f"{label}_s"] = time.perf_counter() - t0
                walls[f"{label}_rc"] = float(proc.returncode)
    return {
        "label": "smoke",
        "split": "dev",
        "note": "Mac fixture oracle; not collections A/B; not a CARC timing",
        "match": match,
        "walls_s": walls,
    }
