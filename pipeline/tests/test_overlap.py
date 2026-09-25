from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.overlap import overlap, unique_keys_lines

PIPE = Path(__file__).resolve().parents[1]


class OverlapTests(unittest.TestCase):
    def test_incremental_fixture(self) -> None:
        a = unique_keys_lines(PIPE / "fixtures" / "line_memo" / "run_a.txt")
        b = unique_keys_lines(PIPE / "fixtures" / "line_memo" / "run_b.txt")
        rep = overlap(a, b)
        self.assertEqual(rep.n_prev, 3)
        self.assertEqual(rep.n_new, 4)
        self.assertEqual(rep.n_shared, 2)
        self.assertAlmostEqual(rep.recall_in_new, 0.5)

    def test_disjoint_is_rare(self) -> None:
        rep = overlap(["a", "b"], ["c", "d"])
        self.assertTrue(rep.overlap_rare)
        self.assertEqual(rep.recall_in_new, 0.0)


if __name__ == "__main__":
    unittest.main()
