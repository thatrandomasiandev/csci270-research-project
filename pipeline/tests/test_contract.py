from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egas.contract import ContractError, load_contract

PIPE = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_star_contract_loads(self) -> None:
        c = load_contract(PIPE / "contracts" / "star_suiteB.toml")
        self.assertEqual(c.method, "star")
        self.assertEqual(c.threads, 1)
        self.assertGreaterEqual(c.runs, 3)
        self.assertEqual(len(c.held_out()), 9)
        self.assertEqual(c.diagnostic()[0].id, "i01")

    def test_fat_copy_contract_loads(self) -> None:
        c = load_contract(PIPE / "contracts" / "fat_copy.toml")
        self.assertEqual(c.method, "generic")
        self.assertNotEqual(c.resolve(c.stock_bin), c.resolve(c.opt_bin))

    def test_second_method_contract_loads(self) -> None:
        c = load_contract(PIPE / "contracts" / "second_method.toml")
        self.assertEqual(c.name, "second_method")
        self.assertNotEqual(c.resolve(c.stock_bin), c.resolve(c.opt_bin))

    def test_same_binary_rejected(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as td:
            p = Path(td) / "bad.toml"
            p.write_text(
                """
[contract]
name = "bad"
target_speedup = 2.0
threads = 1
runs = 3
[method]
kind = "generic"
stock_bin = "/bin/true"
opt_bin = "/bin/true"
run = "{bin}"
match = "true"
[[workloads]]
id = "w"
"""
            )
            with self.assertRaises(ContractError):
                load_contract(p)


if __name__ == "__main__":
    unittest.main()
