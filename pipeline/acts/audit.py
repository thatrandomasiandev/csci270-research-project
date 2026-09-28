"""Dune-style hit audit. Occupied at command granularity (Dune cache-check-probability).

We apply the same idea at record granularity. Not a novelty claim.
Canonical picker for `acts run --verify audit`. The HMMER savings job
keeps its own copy (do not edit that script while it is queued).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Sequence, TypeVar

AUDIT_P = 0.02
AUDIT_SEED = 20260927
AUDIT_FLOOR = 20

T = TypeVar("T")


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


def pick_audit(
    hits: Sequence[T],
    *,
    p: float = AUDIT_P,
    floor: int = AUDIT_FLOOR,
    rng: random.Random,
    key: Callable[[T], str] | None = None,
) -> list[T]:
    """Bernoulli-*p* sample of hits, then pad to *floor* (or all hits)."""
    if not hits or p <= 0:
        return []
    ident = key or (lambda x: str(x))
    if p >= 1:
        return list(hits)
    chosen = [h for h in hits if rng.random() < p]
    have = {ident(h) for h in chosen}
    need = min(floor, len(hits)) - len(chosen)
    if need > 0:
        extra = [h for h in hits if ident(h) not in have]
        rng.shuffle(extra)
        chosen.extend(extra[:need])
    return chosen
