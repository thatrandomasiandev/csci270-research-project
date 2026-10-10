#!/usr/bin/env python3
"""T3 synthetic oracle: ship A/B/C, refuse D/E, and the identity-only baseline.

The laws and fixtures are the ones in pipeline/tests/test_reference_fitter.py
and pipeline/tests/fixtures/reference_fitter/. Expected decisions are the
pre-registered table in pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md
(section T3) and the outcome addendum that records them passed.
No HMMER binary. No results JSON is written: the protocol says there is none.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PIPE = REPO / "pipeline"
sys.path.insert(0, str(PIPE))

from acts.reference_run import probe_fit  # noqa: E402


def _load_tests():
    path = PIPE / "tests" / "test_reference_fitter.py"
    spec = importlib.util.spec_from_file_location("artifact_t3_oracles", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"FAIL cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check(name: str, ok: bool, detail: str) -> bool:
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
    return ok


def main() -> int:
    started = time.perf_counter()
    tests = _load_tests()
    failures = 0

    cases = (
        (
            "A",
            "ab.entryline",
            "ab.faa",
            tests._law_count,
            "SHIP",
            "entry_count",
            True,
        ),
        (
            "B",
            "ab.entryline",
            "ab.faa",
            tests._law_length,
            "SHIP",
            "total_entry_length",
            True,
        ),
        (
            "C",
            "c.entryline",
            "c.faa",
            tests._law_rows,
            "SHIP",
            "per_key_row_count",
            False,
        ),
        (
            "D",
            "d.entryline",
            "d.faa",
            tests._law_rank,
            "REFUSE",
            None,
            None,
        ),
    )
    for label, reference, records, law, decision, member, tie in cases:
        result = probe_fit(
            *tests._load(reference, records),
            lambda recs, ents, law=law: tests._table(recs, ents, law),
        )
        cols = tests._numeric(result)
        got_member = cols[0].member if cols else None
        ok = result.decision == decision
        if member is not None:
            ok = ok and got_member == member
        if tie is not None:
            ok = ok and result.used_tie_break is tie
        detail = (
            f"decision={result.decision} member={got_member} "
            f"tie_break={result.used_tie_break} reason={result.reason}"
        )
        if not _check(f"T3-{label}", ok, detail):
            failures += 1

    pairs = probe_fit(*tests._load("e.entryline", "e.faa"), tests._law_pairs)
    ok = pairs.decision == "REFUSE" and "row-key" in pairs.reason
    if not _check("T3-E", ok, f"decision={pairs.decision} reason={pairs.reason}"):
        failures += 1

    gestore = probe_fit(
        *tests._load("ab.entryline", "ab.faa"),
        lambda recs, ents: tests._table(recs, ents, tests._law_count),
        baseline="gestore",
    )
    ok = gestore.decision == "REFUSE" and "normalizer" in gestore.reason
    if not _check(
        "T3-gestore-A",
        ok,
        f"decision={gestore.decision} reason={gestore.reason}",
    ):
        failures += 1

    elapsed = time.perf_counter() - started
    print(f"wall_s={elapsed:.3f} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
