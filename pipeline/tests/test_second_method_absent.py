from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egas.contract import load_contract
from egas.decide import Decision
from egas.driver import Driver

PIPE = Path(__file__).resolve().parents[1]


class SecondMethodAbsentTests(unittest.TestCase):
    def test_contract_loads_and_is_not_a_bakeoff(self) -> None:
        c = load_contract(PIPE / "contracts" / "second_method.toml")
        self.assertEqual(c.name, "second_method")
        self.assertIsNone(c.profile_path)
        self.assertFalse(Path(c.resolve(c.stock_bin)).is_file())
        self.assertFalse(Path(c.resolve(c.opt_bin)).is_file())

    def test_run_is_incomplete_not_ship(self) -> None:
        c = load_contract(PIPE / "contracts" / "second_method.toml")
        out = PIPE / "egas_out" / "second_method_test"
        report = Driver(c, out_dir=out).run()
        self.assertEqual(report.decision, Decision.INCOMPLETE.value)
        self.assertIn("artifacts absent", report.reason)
        self.assertEqual(report.bakeoffs, [])
        self.assertEqual(report.proposed, [])
        self.assertTrue((out / "decision.txt").is_file())


if __name__ == "__main__":
    unittest.main()
