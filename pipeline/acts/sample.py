"""Uniform-without-replacement probe sampling. Seed locked in INFERENCE_PROTOCOL addendum."""

from __future__ import annotations

import random
from typing import Sequence, TypeVar

PROBE_SEED = 20260927

T = TypeVar("T")


def sample_records(items: Sequence[T], n: int, *, seed: int = PROBE_SEED) -> list[T]:
    """Return *n* items sampled uniformly, in original order. All items if n >= len."""
    if n <= 0:
        return []
    if n >= len(items):
        return list(items)
    rng = random.Random(seed)
    picked = set(rng.sample(range(len(items)), n))
    return [item for i, item in enumerate(items) if i in picked]


def sample_indices(n_items: int, n: int, *, seed: int = PROBE_SEED) -> list[int]:
    return list(sample_records(range(n_items), n, seed=seed))
