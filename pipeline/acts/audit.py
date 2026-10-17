"""Dune-style hit audit. Occupied at command granularity (Dune cache-check-probability).

We apply the same idea at record granularity. Not a novelty claim.
Canonical picker for `acts run --verify audit`. The savings job
keeps its own copy (do not edit that script while it is queued).

The residue budget is the same picker plus a cap. The inclusion
probability is the residue fraction the draw is sized to cover in
expectation. The floor is a record count. A single record longer than
half the residues cannot be drawn without exceeding that cap, and the
layer is skipped. The picker itself is unchanged when the cap does not
bind, so a proteome-scale input keeps the locked sample.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Sequence, TypeVar

AUDIT_P = 0.02
AUDIT_SEED = 20260927
AUDIT_FLOOR = 20
# Declared residue budget for the audit draw.
RESIDUE_FRACTION = AUDIT_P
RESIDUE_FLOOR = AUDIT_FLOOR
RESIDUE_CAP_FRACTION = 0.5

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


def residue_cap_binds(lengths: Sequence[int], cap_fraction: float = RESIDUE_CAP_FRACTION) -> bool:
    """True when one record is longer than ``cap_fraction`` of the residues.

    The shipped cap is one half, compared in integers: a length binds when
    ``2 * length > total``. A draw cannot include that record and stay
    under the cap, so the caller skips the layer.
    """
    total = sum(lengths)
    if total <= 0 or cap_fraction >= 1:
        return False
    if cap_fraction == 0.5:
        return any(length * 2 > total for length in lengths)
    if cap_fraction <= 0:
        return any(length > 0 for length in lengths)
    return any(length > cap_fraction * total for length in lengths)


def audit_miss_probability(*, n: int, k: int, s: int, skipped: bool) -> float:
    """Probability an audit misses a body difference on ``k`` of ``n`` records.

    With the floor of 20, ``s = n`` whenever ``n <= 20``, so any difference
    on at least one record is seen. A skipped audit does not look.
    """
    if skipped or k <= 0 or n <= 0 or s <= 0:
        return 1.0
    if s > n:
        raise ValueError("sample size exceeds the record count")
    if s > n - k:
        return 0.0
    return math.comb(n - k, s) / math.comb(n, s)
