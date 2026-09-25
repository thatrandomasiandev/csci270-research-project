from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egas.contract import load_contract
from egas.driver import Driver
from egas.decide import Decision

PIPE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("cc") or shutil.which("clang") or shutil.which("gcc"), "no C compiler")
class FatCopyDriverTests(unittest.TestCase):
    def test_held_out_ships_or_records_honest_miss(self) -> None:
        """Fixture is the smoke Method. A compiler that elides the copy can fail 2×;
        that is a refuse/propose, not a hidden pass.
        """
        c = load_contract(PIPE / "contracts" / "fat_copy.toml")
        out = PIPE / "egas_out" / "fat_copy_test"
        d = Driver(c, out_dir=out)
        report = d.run(workloads=["held"])
        self.assertIn(
            report.decision,
            {
                Decision.SHIP.value,
                Decision.REFUSE_SPEEDUP.value,
                Decision.PROPOSE.value,
                Decision.NARROW.value,
                Decision.INCOMPLETE.value,
            },
        )
        self.assertTrue((out / "report.json").is_file())
        if report.bakeoffs:
            self.assertTrue(report.bakeoffs[0]["match"])


if __name__ == "__main__":
    unittest.main()
