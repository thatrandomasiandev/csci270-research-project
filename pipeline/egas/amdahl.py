"""Amdahl feasibility. This is the product: most Methods should refuse here."""

from __future__ import annotations

from dataclasses import dataclass

from egas.profile_io import Profile, Region


@dataclass(frozen=True)
class AmdahlResult:
    legal_fraction: float
    max_speedup: float
    target: float
    proceed: bool
    proceed_with_t4: bool
    reason: str
    hottest_legal: Region | None

    @property
    def status(self) -> str:
        if self.proceed:
            return "PROCEED"
        if self.proceed_with_t4:
            return "PROCEED_WITH_T4"
        return "REFUSE"


def evaluate_amdahl(
    profile: Profile,
    target: float,
    *,
    allow_t4_assist: bool = True,
    t4_slack: float = 0.85,
) -> AmdahlResult:
    """Max end-to-end speedup if every legal region went to zero time.

    1 / (1 − f_legal). T4 (PGO/allocator) may recover a bit of the residual,
    so we allow proceed_with_t4 when max_speedup ≥ target * t4_slack.
    """
    if target <= 1.0:
        raise ValueError("target must be > 1")

    legal = [r for r in profile.regions if r.legal and r.fraction > 0]
    f = min(sum(r.fraction for r in legal), 0.999999)
    max_speedup = 1.0 / (1.0 - f) if f < 1.0 else float("inf")
    hottest = max(legal, key=lambda r: r.fraction) if legal else None

    if max_speedup >= target:
        return AmdahlResult(
            legal_fraction=f,
            max_speedup=max_speedup,
            target=target,
            proceed=True,
            proceed_with_t4=False,
            reason=(
                f"legal f={f:.3f} allows ≤{max_speedup:.2f}× ≥ target {target:.2f}×"
                + (f" (hottest {hottest.symbol} {hottest.fraction:.3f})" if hottest else "")
            ),
            hottest_legal=hottest,
        )

    if allow_t4_assist and max_speedup >= target * t4_slack:
        return AmdahlResult(
            legal_fraction=f,
            max_speedup=max_speedup,
            target=target,
            proceed=False,
            proceed_with_t4=True,
            reason=(
                f"legal f={f:.3f} allows ≤{max_speedup:.2f}×, short of {target:.2f}× "
                f"but ≥ {t4_slack:.0%} of target — T4 (PGO/allocator) may close the gap"
            ),
            hottest_legal=hottest,
        )

    return AmdahlResult(
        legal_fraction=f,
        max_speedup=max_speedup,
        target=target,
        proceed=False,
        proceed_with_t4=False,
        reason=(
            f"REFUSE: legal f={f:.3f} caps speedup at {max_speedup:.2f}× < {target:.2f}×. "
            "Narrow the contract or drop the target. Do not search."
        ),
        hottest_legal=hottest,
    )
