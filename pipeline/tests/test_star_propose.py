from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egas.contract import load_contract
from egas.driver import Driver
from egas.decide import Decision

PIPE = Path(__file__).resolve().parents[1]


class StarProposeTests(unittest.TestCase):
    def test_propose_writes_s1_s8_plan(self) -> None:
        c = load_contract(PIPE / "contracts" / "star_suiteB.toml")
        out = PIPE / "egas_out" / "star_propose_test"
        report = Driver(c, out_dir=out).run(skip_bakeoff=True)
        self.assertEqual(report.decision, Decision.PROPOSE.value)
        self.assertTrue(any("stitch" in p["hint"].lower() or "stitch" in p["title"].lower()
                            or "S1" in p["title"] or "Bounded" in p["title"]
                            for p in report.proposed))
        self.assertTrue((out / "RUNG_PLAN.md").is_file())


if __name__ == "__main__":
    unittest.main()
