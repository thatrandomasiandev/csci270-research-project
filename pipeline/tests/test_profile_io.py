from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egas.profile_io import load_profile, parse_perf_report

PIPE = Path(__file__).resolve().parents[1]


class ProfileTests(unittest.TestCase):
    def test_json_star(self) -> None:
        p = load_profile(PIPE / "profiles" / "star_stitch.json")
        self.assertEqual(p.hottest_legal.symbol, "stitchWindowAligns")
        self.assertFalse(any(r.legal and r.symbol == "gzcat" for r in p.regions))

    def test_perf_stdio(self) -> None:
        text = """
# Overhead  Command  Shared Object  Symbol
    47.12%  STAR     STAR           [.] stitchWindowAligns
    12.00%  STAR     STAR           [.] compareSeqToGenome
     8.10%  STAR     libz           [.] gzcat
"""
        p = parse_perf_report(text)
        self.assertAlmostEqual(p.hottest_legal.fraction, 0.4712, places=4)
        gz = next(r for r in p.regions if r.symbol == "gzcat")
        self.assertFalse(gz.legal)


if __name__ == "__main__":
    unittest.main()
