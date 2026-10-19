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
# Bounded audit: binomial (with-replacement) sample size for zero expected
# misses. If at least ``fraction`` of the records are affected,
# ``(1 - fraction) ** s <= epsilon``. This is the classical audit-sample
# size for a zero-error sample; the hypergeometric miss probability of a
# without-replacement draw is at most this value. Not a new bound.
# epsilon = 0.05 and fraction = 0.01 give s = 299.
AUDIT_EPSILON = 0.05
AUDIT_K_MIN_FRACTION = 0.01
# First-use window. Off unless the caller sets it. When on, the default
# length of the full-comparison window is 2 updates.
FIRST_USE_K = 2

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


def bounded_audit_size(
    n: int,
    *,
    epsilon: float = AUDIT_EPSILON,
    fraction: float = AUDIT_K_MIN_FRACTION,
) -> int:
    """Smallest ``s`` with ``(1 - fraction) ** s <= epsilon``, capped at ``n``.

    ``fraction`` is ``k_min / n``. The formula is the with-replacement
    (binomial) upper bound used in classical audit sampling when no
    misstatement is expected in the sample:

        s = ceil(ln(epsilon) / ln(1 - fraction))

    A without-replacement draw of that size has hypergeometric miss
    probability at most ``epsilon`` whenever at least ``fraction`` of the
    ``n`` records are affected. ``s`` is capped at ``n``.
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0:
        return 0
    if not 0.0 < epsilon < 1.0:
        raise ValueError("epsilon must lie in (0, 1)")
    if not 0.0 < fraction < 1.0:
        raise ValueError("fraction must lie in (0, 1)")
    raw = math.log(epsilon) / math.log(1.0 - fraction)
    # Subtract a tiny tolerance so a value that is an integer in exact
    # arithmetic is not ceiled up by floating-point noise.
    size = int(math.ceil(raw - 1e-12))
    if size < 1:
        size = 1
    return min(size, n)


def sample_fixed(
    hits: Sequence[T],
    size: int,
    rng: random.Random,
) -> list[T]:
    """Simple random sample of ``size`` hits, without replacement."""
    if size < 0:
        raise ValueError("sample size must be non-negative")
    if not hits or size == 0:
        return []
    if size >= len(hits):
        return list(hits)
    return rng.sample(list(hits), size)


def with_replacement_miss(*, fraction: float, size: int) -> float:
    """``(1 - fraction) ** size``. One when the sample is empty."""
    if size <= 0 or fraction <= 0:
        return 1.0
    if fraction >= 1:
        return 0.0
    return (1.0 - fraction) ** size


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
