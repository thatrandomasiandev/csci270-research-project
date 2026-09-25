"""Record grammars. Add kinds here; do not invent per-tool parsers in the driver."""

from __future__ import annotations

import gzip
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


@dataclass(frozen=True)
class DupReport:
    kind: str
    n: int
    n_unique: int
    unique_frac: float
    max_speedup_if_pure: float
    extra: dict[str, float]

    @property
    def duplicates_rare(self) -> bool:
        return self.unique_frac >= 0.95


def _open(path: Path):
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt")
    return path.open()


def iter_fastq_seqs(path: Path) -> Iterator[str]:
    with _open(path) as fh:
        while True:
            header = fh.readline()
            if not header:
                return
            seq = fh.readline()
            plus = fh.readline()
            qual = fh.readline()
            if not qual:
                raise ValueError(f"truncated FASTQ: {path}")
            del plus
            yield seq.rstrip("\n")


def iter_fastq_pe_keys(r1: Path, r2: Path) -> Iterator[str]:
    a = iter_fastq_seqs(r1)
    b = iter_fastq_seqs(r2)
    for s1, s2 in zip(a, b, strict=True):
        yield f"{s1}\t{s2}"


def iter_lines(path: Path) -> Iterator[str]:
    with _open(path) as fh:
        for line in fh:
            yield line.rstrip("\n")


def count_keys(keys: Iterable[str], *, kind: str) -> DupReport:
    c: Counter[str] = Counter()
    n = 0
    for k in keys:
        c[k] += 1
        n += 1
    n_unique = len(c)
    unique_frac = (n_unique / n) if n else 1.0
    max_x = (n / n_unique) if n_unique else 1.0
    return DupReport(
        kind=kind,
        n=n,
        n_unique=n_unique,
        unique_frac=unique_frac,
        max_speedup_if_pure=max_x,
        extra={"max_mult": float(max(c.values()) if c else 0)},
    )


def probe_fastq_pe(r1: Path, r2: Path) -> DupReport:
    return count_keys(iter_fastq_pe_keys(r1, r2), kind="fastq_pe")


def probe_lines(path: Path) -> DupReport:
    return count_keys(iter_lines(path), kind="lines")
