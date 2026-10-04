"""Guard: one savings run's STOP must not halt another (2026-09-28 incident).

On CARC, A/hmmsearch hit STOP_MATCH at genome 5 and wrote a single shared
STOP.json; A/hmmscan (passing MATCH) and both B jobs then stopped too.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_hmmer_savings", PIPE / "scripts" / "run_hmmer_savings.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SavingsStopScopeTests(unittest.TestCase):
    def test_stop_files_are_scoped_per_collection_and_mode(self) -> None:
        runner = _load_runner()
        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get("ACTS_SAVINGS_OUT")
            os.environ["ACTS_SAVINGS_OUT"] = td
            try:
                stops = {
                    (c, m): runner.paths_for(c, m)["stop"]
                    for c in ("A", "B")
                    for m in ("hmmscan", "hmmsearch")
                }
            finally:
                if old is None:
                    os.environ.pop("ACTS_SAVINGS_OUT", None)
                else:
                    os.environ["ACTS_SAVINGS_OUT"] = old
            self.assertEqual(len(set(stops.values())), 4)
            runner.write_stop(
                stops[("A", "hmmsearch")],
                {"stopped": True, "where": "cached MATCH", "collection": "A", "mode": "hmmsearch"},
            )
            self.assertIsNotNone(runner.stop_if_flagged(stops[("A", "hmmsearch")]))
            for key, path in stops.items():
                if key != ("A", "hmmsearch"):
                    self.assertIsNone(runner.stop_if_flagged(path), key)

    def test_probe_is_pinned_to_the_preregistered_singleton_8(self) -> None:
        runner = _load_runner()
        self.assertEqual(runner.PROBE_N, 8)
        self.assertEqual(runner.SUBSET_MODE, "singleton")


if __name__ == "__main__":
    unittest.main()
