#!/usr/bin/env python3
"""Confirmatory collection selection (docs/CONFIRM_PROTOCOL.md).

No downloads. No timing. Selection rules only.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_recurrence_curves import (  # noqa: E402
    K12_RE,
    Assembly,
    eligible,
    is_k12,
    one_per_strain,
    sample_n,
    seq_md5,
    faa_keys,
)

PROTOCOL = "pipeline/docs/CONFIRM_PROTOCOL.md"
CONFIRM_E_SEED = 20260927
RECURRENCE_SEED = 20260926
N_GENOMES = 30
STOCK_POS = (1, 2, 5, 10, 20, 30)
C_ORDERING0_PREFIX30 = [
    4,
    2,
    1,
    37,
    14,
    32,
    11,
    40,
    48,
    7,
    23,
    31,
    15,
    45,
    8,
    26,
    3,
    19,
    12,
    18,
    44,
    24,
    36,
    22,
    5,
    6,
    33,
    16,
    10,
    43,
]
COLLECTION_IDS = ("confirm_E", "confirm_C")
PRIMARY_MODE = "hmmscan"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def excluded_accessions(recurrence_accessions: dict) -> set[str]:
    """Every accession in collections A and B."""
    out: set[str] = set()
    for cid in ("A", "B"):
        for genome in recurrence_accessions["collections"][cid]["genomes"]:
            out.add(genome["accession"])
    return out


def confirm_e_pool(rows: list[Assembly], excluded: set[str]) -> list[Assembly]:
    """Eligible Complete Genome E. coli, drop K-12 regex and A∪B, one per strain."""
    kept = [
        row
        for row in eligible(rows)
        if not is_k12(row) and row.accession not in excluded
    ]
    return one_per_strain(kept)


def draw_confirm_e(
    pool: list[Assembly],
    n: int = N_GENOMES,
    seed: int = CONFIRM_E_SEED,
) -> list[Assembly]:
    """Sample n without replacement, re-sort by accession (collection A style)."""
    if seed == RECURRENCE_SEED:
        raise ValueError("confirm_E seed must not be the recurrence seed 20260926")
    return sample_n(pool, n, seed)


def run_order_indices(n: int = N_GENOMES, seed: int = CONFIRM_E_SEED) -> list[int]:
    if seed == RECURRENCE_SEED:
        raise ValueError("confirm_E run-order seed must not be 20260926")
    return list(random.Random(seed).sample(range(n), n))


def order_rows(rows: list[Assembly], indices: list[int]) -> list[Assembly]:
    return [rows[i] for i in indices]


def c_prefix_indices(curves: dict, k: int = N_GENOMES) -> list[int]:
    prefix = list(curves["collections"]["C"]["orderings"][0][:k])
    if prefix != C_ORDERING0_PREFIX30[:k]:
        raise ValueError(
            "collection C orderings[0] prefix does not match the locked "
            "CONFIRM_PROTOCOL.md indices"
        )
    return prefix


def c_prefix_genomes(recurrence_accessions: dict, indices: list[int]) -> list[dict]:
    listed = recurrence_accessions["collections"]["C"]["genomes"]
    return [listed[i] for i in indices]


def miss_along_order(keysets: list[set[str]], order: list[int]) -> list[float]:
    """m(k) for k = 1 … K-1 along one locked ordering.

    m[k-1] is the miss of genome k+1 given genomes 1…k (RECURRENCE_PROTOCOL.md).
    """
    if len(order) != len(keysets):
        raise ValueError("order and keysets must cover the same genomes")
    miss: list[float] = []
    seen: set[str] = set()
    for i, idx in enumerate(order):
        later = keysets[idx]
        if i == 0:
            seen |= later
            continue
        if not later:
            miss.append(1.0)
        else:
            miss.append(1.0 - (len(later & seen) / len(later)))
        seen |= later
    return miss


def replace_from_pool(
    selected: list[Assembly],
    pool: list[Assembly],
    failed: set[str],
) -> tuple[list[Assembly], list[str]]:
    """Replace HEAD-failed rows from remaining pool, accession order."""
    selected_acc = {row.accession for row in selected}
    remaining = [
        row
        for row in sorted(pool, key=lambda x: x.accession)
        if row.accession not in selected_acc
    ]
    kept = [row for row in selected if row.accession not in failed]
    replacements: list[str] = []
    for row in remaining:
        if len(kept) >= N_GENOMES:
            break
        if row.accession in failed:
            continue
        kept.append(row)
        replacements.append(row.accession)
    kept = sorted(kept, key=lambda x: x.accession)
    return kept, replacements


__all__ = [
    "CONFIRM_E_SEED",
    "C_ORDERING0_PREFIX30",
    "COLLECTION_IDS",
    "K12_RE",
    "N_GENOMES",
    "PRIMARY_MODE",
    "PROTOCOL",
    "RECURRENCE_SEED",
    "STOCK_POS",
    "c_prefix_genomes",
    "c_prefix_indices",
    "confirm_e_pool",
    "draw_confirm_e",
    "excluded_accessions",
    "faa_keys",
    "miss_along_order",
    "order_rows",
    "replace_from_pool",
    "run_order_indices",
    "seq_md5",
]
