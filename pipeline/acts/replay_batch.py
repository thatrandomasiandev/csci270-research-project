"""Group records so each search sees the union of its own candidates.

The cost of a batching, in pair-scan units, is

    T = α·k + π·Σ_b |U_b| + Σ_b |B_b|·|U_b|

where k is the number of batches, U_b is the union of the candidate sets
in batch b, α is the per-batch startup measured in pair scans, and π is
the per-entry build cost measured in pair scans. α and π are caller data.

Records with candidates are sorted by their rarest candidate (lowest
frequency among those records, then the candidate id), then by input
position. The planner scores equal contiguous chunks of that order on a
grid (powers of two, then a step through the neighborhood of the best)
and keeps the chunk size with the lowest T. A tie keeps the smaller
chunk. That is the minimum on the grid, inside this family of partitions.
Each chunk is then written in input order.

Body lines are put back in the caller's record order. A line's record
field is whitespace-split column ``record_col``. Lines that start with
'#' stay in the header or the tail and are not reordered.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence


def plan_batches(
    record_order: Sequence[str],
    candidates: dict[str, set[str]],
    *,
    startup_pairs: float,
    press_pairs: float,
) -> list[list[str]]:
    """Return batches of record keys. Records with no candidates are omitted."""
    if startup_pairs < 0 or press_pairs < 0:
        raise ValueError("batch costs must be non-negative")
    freq: dict[str, int] = defaultdict(int)
    indexed: list[tuple[int, str, set[str]]] = []
    for index, key in enumerate(record_order):
        cand = candidates.get(key)
        if not cand:
            continue
        indexed.append((index, key, set(cand)))
        for entry in cand:
            freq[entry] += 1
    if not indexed:
        return []
    ordered = sorted(
        indexed,
        key=lambda item: (freq[min(item[2], key=lambda e: (freq[e], e))], min(item[2], key=lambda e: (freq[e], e)), item[0]),
    )
    size = _best_chunk_size(ordered, startup_pairs, press_pairs)
    batches: list[list[str]] = []
    for start in range(0, len(ordered), size):
        chunk = sorted(ordered[start : start + size], key=lambda item: item[0])
        batches.append([item[1] for item in chunk])
    return batches


def batch_cost(
    batches: Sequence[Sequence[str]],
    candidates: dict[str, set[str]],
    *,
    startup_pairs: float,
    press_pairs: float,
) -> float:
    """The closed form above, in pair-scan units."""
    total = startup_pairs * len(batches)
    for keys in batches:
        union: set[str] = set()
        for key in keys:
            union |= candidates.get(key, set())
        total += press_pairs * len(union) + len(keys) * len(union)
    return total


def merge_bodies(texts: Sequence[str], record_col: int, record_order: Sequence[str]) -> str:
    """One table. Header from the first text, body in ``record_order``, tail from the last text."""
    if not texts:
        return ""
    header: list[str] = []
    tail: list[str] = []
    grouped: dict[str, list[str]] = {key: [] for key in record_order}
    unknown: list[str] = []
    header_taken = False
    for text in texts:
        head, body, end = _split(text)
        if not header_taken:
            header = head
            header_taken = True
        if end:
            tail = end
        for line in body:
            cells = line.split("\t") if "\t" in line else line.split()
            if record_col < len(cells) and cells[record_col] in grouped:
                grouped[cells[record_col]].append(line)
            else:
                unknown.append(line)
    parts = list(header)
    for key in record_order:
        parts.extend(grouped[key])
    parts.extend(unknown)
    parts.extend(tail)
    return "".join(parts)


def _best_chunk_size(
    ordered: Sequence[tuple[int, str, set[str]]],
    startup_pairs: float,
    press_pairs: float,
) -> int:
    """Chunk size of lowest closed-form cost. Ties keep the smaller size."""
    n = len(ordered)
    sizes = []
    size = 1
    while size < n:
        sizes.append(size)
        size *= 2
    sizes.append(n)

    def score(chunk: int) -> tuple[float, int]:
        return (_chunk_cost(ordered, chunk, startup_pairs, press_pairs), chunk)

    best = min(sizes, key=score)
    lo = max(1, best // 2)
    hi = min(n, best * 2)
    step = max(1, (hi - lo) // 20)
    for chunk in range(lo, hi + 1, step):
        if score(chunk) < score(best):
            best = chunk
    return best


def _chunk_cost(
    ordered: Sequence[tuple[int, str, set[str]]],
    chunk: int,
    startup_pairs: float,
    press_pairs: float,
) -> float:
    total = 0.0
    for start in range(0, len(ordered), chunk):
        union: set[str] = set()
        part = ordered[start : start + chunk]
        for _index, _key, cand in part:
            union |= cand
        total += startup_pairs + press_pairs * len(union) + len(part) * len(union)
    return total


def _split(text: str) -> tuple[list[str], list[str], list[str]]:
    lines = text.splitlines(keepends=True)
    if text and not text.endswith(("\n", "\r")) and lines:
        pass
    body_at = [i for i, line in enumerate(lines) if line.strip() and not line.startswith("#")]
    if not body_at:
        return lines, [], []
    first, last = body_at[0], body_at[-1]
    return lines[:first], lines[first : last + 1], lines[last + 1 :]
