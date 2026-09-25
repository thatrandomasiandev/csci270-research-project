"""Dune-style hit audit. Occupied at command granularity (Dune cache-check-probability).

We apply the same idea at record granularity. Not a novelty claim.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditReport:
    n_hits: int
    n_checked: int
    n_mismatch: int
    p: float

    @property
    def ok(self) -> bool:
        return self.n_mismatch == 0


def sample_hits(hits: list[str], *, p: float, rng: random.Random) -> list[str]:
    if p <= 0:
        return []
    if p >= 1:
        return list(hits)
    return [h for h in hits if rng.random() < p]
