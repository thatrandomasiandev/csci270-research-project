"""Editor checks for the real-hmmscan confirmation. No grid numbers."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import confirm_hmmscan as confirm
import coupling_shim as shim


def _order() -> list[str]:
    return [f"P{i:02d}" for i in range(22)] + ["A", "B"]


def _env(**overrides) -> None:
    base = {
        "TARE_COUPLING": "none",
        "TARE_K": "1",
        "TARE_SEED": "20261113",
        "TARE_N": "4",
        "TARE_M": "24",
        "TARE_D": "2",
        "TARE_AFFECT": "all",
        "TARE_ANCHOR": "A",
    }
    base.update(overrides)
    os.environ.update(base)


class EditTests(unittest.TestCase):
    def test_presence_drops_the_anchor_until_the_far_model_is_present(self) -> None:
        _env(TARE_COUPLING="presence")
        order = _order()
        only = "NAME  A\nLENG  10\n//\n"
        plus = "NAME  P05\nLENG  10\n//\nNAME  A\nLENG  10\n//\n"
        table = "# h\nA - q0000 - 1e-3 30.0 0.1 note\n"
        dropped, _dom = confirm.post_edit(table, table, only, order)
        kept, _dom = confirm.post_edit(table, table, plus, order)
        self.assertEqual(confirm._body(dropped), [])
        self.assertEqual(len(confirm._body(kept)), 1)

    def test_order_marks_a_missing_predecessor_and_residues_track_length(self) -> None:
        order = _order()
        _env(TARE_COUPLING="order", TARE_D="2")
        only = "NAME  A\nLENG  10\n//\n"
        # Distance 2 from A (index 22) is P20, not the file-order neighbor P21.
        plus = "NAME  P20\nLENG  10\n//\nNAME  A\nLENG  10\n//\n"
        table = "A - q0000 - 1e-3 30.0 0.1 note\n"
        missing, _dom = confirm.post_edit(table, table, only, order)
        present, _dom = confirm.post_edit(table, table, plus, order)
        self.assertTrue(confirm._body(missing)[0].endswith("FAR"))
        self.assertFalse(confirm._body(present)[0].endswith("FAR"))
        _env(TARE_COUPLING="residues")
        edited, _dom = confirm.post_edit(table, table, only, order)
        self.assertTrue(confirm._body(edited)[0].endswith("L10"))

    def test_clean_lines_are_unchanged(self) -> None:
        _env(TARE_COUPLING="none", TARE_AFFECT="", TARE_N="0", TARE_K="0")
        order = _order()
        text = "NAME  A\nLENG  10\n//\n"
        table = "A - q0000 - 1e-3 30.0 0.1 note\n"
        tbl, dom = confirm.post_edit(table, table, text, order)
        self.assertEqual(shim.diff_class(confirm._body(table), confirm._body(tbl)), "identical")
        self.assertEqual(dom, tbl)


if __name__ == "__main__":
    unittest.main()
