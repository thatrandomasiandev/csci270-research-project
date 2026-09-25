from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egas.decide import DecideInput, Decision, decide


def _inp(**kw):
    base = dict(
        match=True,
        min_pair=2.1,
        mean_speedup=2.2,
        n_pairs=3,
        target=2.0,
        amdahl_ok=True,
        amdahl_t4_only=False,
        automated_rungs_left=False,
        source_rungs_left=False,
        runs_required=3,
    )
    base.update(kw)
    return DecideInput(**base)


class DecideTests(unittest.TestCase):
    def test_ship(self) -> None:
        self.assertEqual(decide(_inp()).decision, Decision.SHIP)

    def test_no_ship_on_n1(self) -> None:
        self.assertEqual(decide(_inp(n_pairs=1)).decision, Decision.INCOMPLETE)

    def test_diff_never_ships(self) -> None:
        self.assertEqual(decide(_inp(match=False, min_pair=4.0)).decision, Decision.REFUSE_MATCH)

    def test_amdahl_first(self) -> None:
        self.assertEqual(
            decide(_inp(amdahl_ok=False, match=True)).decision,
            Decision.REFUSE_AMDAHL,
        )

    def test_propose_when_short(self) -> None:
        rec = decide(_inp(min_pair=1.4, source_rungs_left=True))
        self.assertEqual(rec.decision, Decision.PROPOSE)


if __name__ == "__main__":
    unittest.main()
