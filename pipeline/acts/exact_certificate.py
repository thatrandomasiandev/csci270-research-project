"""IC2, the exact-mode independence certificate.

A pass is a test, not a proof that the replay body equals a full run.
The predicate is the one locked in the DX3 addendum: the multiset of
body lines whose subject is a candidate must be unchanged, and a pad
subject must not appear. Random pads use the locked seeds. The neighbor
pad is the release-file predecessor and successor of each candidate.
The near-miss pad is tool-specific and is not built here.
"""

from __future__ import annotations

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
