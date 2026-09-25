"""Ship / refuse / narrow. n=1 timings never ship."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    SHIP = "SHIP"
    REFUSE_AMDAHL = "REFUSE_AMDAHL"
    REFUSE_MATCH = "REFUSE_MATCH"
    REFUSE_SPEEDUP = "REFUSE_SPEEDUP"
    NARROW = "NARROW"
    PROPOSE = "PROPOSE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class DecideInput:
    match: bool | None
    min_pair: float | None
    mean_speedup: float | None
    n_pairs: int
    target: float
    amdahl_ok: bool
    amdahl_t4_only: bool
    automated_rungs_left: bool
    source_rungs_left: bool
    runs_required: int = 3


@dataclass(frozen=True)
class DecisionRecord:
    decision: Decision
    reason: str


def decide(inp: DecideInput) -> DecisionRecord:
    if not inp.amdahl_ok and not inp.amdahl_t4_only:
        return DecisionRecord(
            Decision.REFUSE_AMDAHL,
            "legal region cannot reach the target; refuse or narrow the contract",
        )
    if inp.match is False:
        return DecisionRecord(
            Decision.REFUSE_MATCH,
            "MATCH failed — discard the timing; never report a speedup from a DIFF",
        )
    if inp.match is True and inp.n_pairs < inp.runs_required:
        return DecisionRecord(
            Decision.INCOMPLETE,
            f"MATCH but n={inp.n_pairs} < {inp.runs_required}; do not ship on a single run",
        )
    if inp.match is True and inp.min_pair is not None and inp.min_pair >= inp.target:
        return DecisionRecord(
            Decision.SHIP,
            f"MATCH and min_pair {inp.min_pair:.3f}× ≥ {inp.target:.2f}× (n={inp.n_pairs})",
        )
    if inp.match is True and inp.min_pair is not None and inp.min_pair < inp.target:
        if inp.automated_rungs_left:
            return DecisionRecord(
                Decision.INCOMPLETE,
                f"MATCH but min_pair {inp.min_pair:.3f}× < {inp.target:.2f}×; more T4 rungs remain",
            )
        if inp.source_rungs_left:
            return DecisionRecord(
                Decision.PROPOSE,
                f"MATCH but min_pair {inp.min_pair:.3f}× < {inp.target:.2f}×; write a T1–T3 plan",
            )
        if inp.amdahl_t4_only:
            return DecisionRecord(
                Decision.NARROW,
                f"T4-assisted path still {inp.min_pair:.3f}×; narrow the workload or drop the target",
            )
        return DecisionRecord(
            Decision.REFUSE_SPEEDUP,
            f"MATCH but min_pair {inp.min_pair:.3f}× < {inp.target:.2f}×; rungs exhausted",
        )
    if inp.automated_rungs_left:
        return DecisionRecord(Decision.INCOMPLETE, "no bake-off yet; automated T4 rungs remain")
    if inp.source_rungs_left:
        return DecisionRecord(Decision.PROPOSE, "no bake-off yet; emit a T1–T3 plan from the profile")
    return DecisionRecord(Decision.INCOMPLETE, "no MATCH result and no remaining rungs")
