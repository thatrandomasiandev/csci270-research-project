from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egas.amdahl import evaluate_amdahl
from egas.profile_io import Profile, Region


def _p(*pairs: tuple[str, float, bool]) -> Profile:
    return Profile(
        tool="t",
        regions=tuple(Region(s, f, legal) for s, f, legal in pairs),
    )


class AmdahlTests(unittest.TestCase):
    def test_half_legal_is_exactly_2x(self) -> None:
        r = evaluate_amdahl(_p(("hot", 0.50, True)), 2.0)
        self.assertTrue(r.proceed)
        self.assertAlmostEqual(r.max_speedup, 2.0, places=5)

    def test_refuse_when_hot_path_is_illegal(self) -> None:
        r = evaluate_amdahl(_p(("gzcat", 0.70, False), ("map", 0.10, True)), 2.0)
        self.assertEqual(r.status, "REFUSE")
        self.assertLess(r.max_speedup, 2.0)

    def test_t4_slack_near_miss(self) -> None:
        r = evaluate_amdahl(_p(("hot", 0.46, True)), 2.0, allow_t4_assist=True)
        self.assertEqual(r.status, "PROCEED_WITH_T4")

    def test_fly_full_genome_class(self) -> None:
        # Documented STAR fly-full ~1.4×: SA-bound and SA was not a legal 2× lever.
        r = evaluate_amdahl(_p(("stitch", 0.28, True), ("SA", 0.55, False)), 2.0)
        self.assertEqual(r.status, "REFUSE")


if __name__ == "__main__":
    unittest.main()
