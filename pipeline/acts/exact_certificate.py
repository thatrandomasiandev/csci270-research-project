"""IC2, the exact-mode independence certificate.

A pass is a test, not a proof that the replay body equals a full run.
The predicate is the one locked in the DX3 addendum: the multiset of
body lines whose subject is a candidate must be unchanged, and a pad
subject must not appear. Random pads use the locked seeds. The neighbor
pad is the release-file predecessor and successor of each candidate.
The near-miss pad is tool-specific and is not built here.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Sequence

SEEDS = (20261031, 20261032, 20261033)


def body_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def judge(
    r_text: str,
    plus_text: str,
    u_ids: set[str],
    pad_ids: set[str],
    subject_col: int,
) -> dict:
    def take(text: str, keep) -> list[str]:
        chosen = []
        for line in body_lines(text):
            cells = line.split()
            if subject_col < len(cells) and keep(cells[subject_col]):
                chosen.append(line)
        return chosen

    r_u = Counter(take(r_text, lambda subject: subject in u_ids))
    plus_u = Counter(take(plus_text, lambda subject: subject in u_ids))
    missing = sum(count - plus_u[line] for line, count in r_u.items() if count > plus_u[line])
    extra = sum(count - r_u[line] for line, count in plus_u.items() if count > r_u[line])
    pad_hits = len(take(plus_text, lambda subject: subject in pad_ids))
    other = len(take(plus_text, lambda subject: subject not in u_ids and subject not in pad_ids))
    passed = missing == 0 and extra == 0 and pad_hits == 0 and other == 0
    if passed:
        mode = "pass"
    elif pad_hits:
        mode = "pad_hit"
    elif missing and extra:
        mode = "missing_and_extra_candidate"
    elif missing:
        mode = "missing_candidate"
    elif extra:
        mode = "extra_candidate"
    else:
        mode = "other_subject"
    return {
        "pass": passed,
        "fail_mode": mode,
        "missing_candidate_rows": missing,
        "extra_candidate_rows": extra,
        "pad_hit_rows": pad_hits,
        "other_subject_rows": other,
    }


def pad_miss_probability(*, n: int, k: int, s: int, q: float, repetitions: int = len(SEEDS)) -> float:
    """Probability the random pads miss one coupling that is not a neighbor.

    ``h = C(n-k, s) / C(n, s)`` when ``s <= n-k``, and ``h = 0`` otherwise.
    With ``repetitions`` pads that each contain the coupling entry with
    probability ``q``,

        P = h + (1-h) * (1-q) ** repetitions

    A skipped layer has ``repetitions = 0``, so ``P = 1``. This is a
    counting identity. It does not say that a pad which contains the
    entry changes a row. Three pads stay when the layer runs: the
    injected-drop control refuses on the second and third, and one pad
    replaces ``(1-q)^3`` with ``(1-q)``.
    """
    if repetitions < 0:
        raise ValueError("repetitions must be non-negative")
    if repetitions == 0:
        return 1.0
    if n <= 0 or k <= 0 or not 0.0 <= q <= 1.0:
        return 1.0
    if s < 0 or s > n:
        raise ValueError("sample size out of range")
    if s > n - k:
        h = 0.0
    else:
        h = math.comb(n - k, s) / math.comb(n, s)
    return h + (1.0 - h) * ((1.0 - q) ** repetitions)


def sample_keys(keys: Sequence[str], k: int, seed: int) -> list[str]:
    """A fixed-seed sample, in the original key order. ``k`` above the length keeps every key."""
    if k < 0:
        raise ValueError("sample size must be non-negative")
    if k >= len(keys):
        return list(keys)
    chosen = set(random.Random(seed).sample(range(len(keys)), k))
    return [key for index, key in enumerate(keys) if index in chosen]


def neighbor_ids(entries: Sequence, candidate_ids: set[str]) -> set[str]:
    """File-order predecessor and successor of each candidate, excluding candidates."""
    index = {entry.primary: i for i, entry in enumerate(entries)}
    chosen = {index[key] for key in candidate_ids if key in index}
    n = len(entries)
    out: set[str] = set()
    for i in chosen:
        if i > 0 and (i - 1) not in chosen:
            out.add(entries[i - 1].primary)
        if i + 1 < n and (i + 1) not in chosen:
            out.add(entries[i + 1].primary)
    return out


def pad_indices(entries: Sequence, candidate_ids: set[str], seeds: tuple[int, ...] = SEEDS) -> list[tuple[str, list[int]]]:
    """Index lists into ``entries``. A short reference uses every non-candidate."""
    n = len(entries)
    index = {entry.primary: i for i, entry in enumerate(entries)}
    u_idx = {index[key] for key in candidate_ids if key in index}
    non = [i for i in range(n) if i not in u_idx]
    width = min(max(200, len(u_idx)), len(non))
    pads: list[tuple[str, list[int]]] = []
    for seed in seeds:
        chosen = sorted(random.Random(seed).sample(non, width)) if width else []
        pads.append((f"random_{seed}", chosen))
    neighbors: set[int] = set()
    for i in u_idx:
        if i > 0 and (i - 1) not in u_idx:
            neighbors.add(i - 1)
        if i + 1 < n and (i + 1) not in u_idx:
            neighbors.add(i + 1)
    pads.append(("neighbor", sorted(neighbors)))
    return pads
