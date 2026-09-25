"""Cross-run overlap. This is the incremental-headline kill test.

recall_in_new = |prev ∩ new| / |new|  — fraction of the new file already paid for.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class OverlapReport:
    n_prev: int
    n_new: int
    n_shared: int
    recall_in_new: float
    jaccard: float

    @property
    def overlap_rare(self) -> bool:
        return self.recall_in_new < 0.05


def overlap(prev: Iterable[str], new: Iterable[str]) -> OverlapReport:
    a = set(prev)
    b = set(new)
    shared = a & b
    union = a | b
    return OverlapReport(
        n_prev=len(a),
        n_new=len(b),
        n_shared=len(shared),
        recall_in_new=(len(shared) / len(b)) if b else 0.0,
        jaccard=(len(shared) / len(union)) if union else 0.0,
    )


def unique_keys_fastq_pe(r1: Path, r2: Path) -> set[str]:
    from acts.records import iter_fastq_pe_keys

    return set(iter_fastq_pe_keys(r1, r2))


def unique_keys_lines(path: Path) -> set[str]:
    from acts.records import iter_lines

    return set(iter_lines(path))
