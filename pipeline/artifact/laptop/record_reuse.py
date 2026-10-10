#!/usr/bin/env python3
"""Record-side reuse on the committed line fixtures.

Expected values are the decisions of `acts run --kind lines` on
pipeline/fixtures/line_memo/, verify=full (byte MATCH):

- input.txt is one file with repeated lines: SHIP, n=8, n_unique=4.
- run_b.txt reuses a cache filled by run_a.txt: SHIP, n_hits=2
  (the lines "apple" and "banana").

These counts are properties of the committed fixtures, not paper speedups.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PIPE = REPO / "pipeline"
sys.path.insert(0, str(PIPE))

from acts.strategies.record_memo import RecordMemo  # noqa: E402

FIX = PIPE / "fixtures" / "line_memo"


def _check(name: str, ok: bool, detail: str) -> bool:
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
    return ok


def main() -> int:
    started = time.perf_counter()
    failures = 0
    work = Path(tempfile.mkdtemp(prefix="acts_artifact_lines_"))
    within = RecordMemo(
        kind="lines",
        argv=["cat"],
        input_path=FIX / "input.txt",
        out_dir=work / "within",
        verify="full",
    ).run()
    ok = (
        within.decision == "SHIP"
        and within.extra.get("n") == 8
        and within.extra.get("n_unique") == 4
        and "byte-identical" in within.reason
    )
    if not _check(
        "lines-within",
        ok,
        f"decision={within.decision} n={within.extra.get('n')} "
        f"n_unique={within.extra.get('n_unique')} reason={within.reason}",
    ):
        failures += 1

    cache = work / "cache.jsonl"
    first = RecordMemo(
        kind="lines",
        argv=["cat"],
        input_path=FIX / "run_a.txt",
        out_dir=work / "run_a",
        cache_path=cache,
        verify="full",
    ).run()
    second = RecordMemo(
        kind="lines",
        argv=["cat"],
        input_path=FIX / "run_b.txt",
        out_dir=work / "run_b",
        cache_path=cache,
        verify="full",
    ).run()
    ok = first.decision == "SHIP" and int(first.extra.get("n_hits", -1)) == 0
    if not _check(
        "lines-run-a",
        ok,
        f"decision={first.decision} n_hits={first.extra.get('n_hits')} reason={first.reason}",
    ):
        failures += 1
    ok = (
        second.decision == "SHIP"
        and int(second.extra.get("n_hits", -1)) == 2
        and int(second.extra.get("n_misses", -1)) == 2
        and second.extra.get("mode") == "incremental"
        and "byte-identical" in second.reason
    )
    if not _check(
        "lines-run-b",
        ok,
        f"decision={second.decision} n_hits={second.extra.get('n_hits')} "
        f"n_misses={second.extra.get('n_misses')} mode={second.extra.get('mode')} "
        f"reason={second.reason}",
    ):
        failures += 1

    elapsed = time.perf_counter() - started
    print(f"wall_s={elapsed:.3f} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
