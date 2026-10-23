"""Shared row-diff classifier — positive and negative controls."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from acts.row_diff import classify, compare_pair, row_key


class RowKeyTests(unittest.TestCase):
    def test_tbl_key_uses_target_and_query(self) -> None:
        toks = "PF00001  -  WP_1  -  1  2  3".split()
        self.assertEqual(row_key(toks, "tbl"), ("PF00001", "WP_1"))

    def test_dom_key_uses_alignment_span(self) -> None:
        toks = [f"t{i}" for i in range(19)]
        self.assertEqual(
            row_key(toks, "dom"),
            (toks[0], toks[3], toks[15], toks[16], toks[17], toks[18]),
        )


class ClassifyControls(unittest.TestCase):
    def test_positive_byte_identical(self) -> None:
        body = ["PF1 - Q1 - rest a", "PF2 - Q2 - rest b"]
        out = classify(body, body, "tbl")
        self.assertTrue(out["byte_equal"])
        self.assertEqual(out["classes"], [])

    def test_whitespace_only(self) -> None:
        stock = ["PF1  -  Q1  -  rest"]
        replay = ["PF1 - Q1 - rest"]
        out = classify(replay, stock, "tbl")
        self.assertFalse(out["byte_equal"])
        self.assertTrue(out["token_equal"])
        self.assertEqual(out["classes"], ["whitespace-only"])

    def test_missing_row(self) -> None:
        stock = ["PF1 - Q1 - a", "PF2 - Q2 - b"]
        replay = ["PF1 - Q1 - a"]
        out = classify(replay, stock, "tbl")
        self.assertIn("missing", out["classes"])
        self.assertEqual(out["missing_keys"], 1)

    def test_extra_row(self) -> None:
        stock = ["PF1 - Q1 - a"]
        replay = ["PF1 - Q1 - a", "PF2 - Q2 - b"]
        out = classify(replay, stock, "tbl")
        self.assertIn("extra", out["classes"])
        self.assertEqual(out["extra_keys"], 1)

    def test_value_only(self) -> None:
        stock = ["PF1 - Q1 - score 1.0"]
        replay = ["PF1 - Q1 - score 2.0"]
        out = classify(replay, stock, "tbl")
        self.assertIn("value-only", out["classes"])
        self.assertEqual(out["missing_keys"], 0)
        self.assertEqual(out["extra_keys"], 0)

    def test_order(self) -> None:
        stock = ["PF1 - Q1 - a", "PF2 - Q2 - b"]
        replay = ["PF2 - Q2 - b", "PF1 - Q1 - a"]
        out = classify(replay, stock, "tbl")
        self.assertIn("order", out["classes"])


class ComparePairTests(unittest.TestCase):
    def test_pair_byte_equal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            tbl = "PF1 - Q1 - a\n"
            dom = " ".join(f"x{i}" for i in range(19)) + "\n"
            (base / "rt").write_text(tbl)
            (base / "st").write_text(tbl)
            (base / "rd").write_text(dom)
            (base / "sd").write_text(dom)
            out = compare_pair(base / "rt", base / "rd", base / "st", base / "sd")
            self.assertTrue(out["byte_equal"])


if __name__ == "__main__":
    unittest.main()
