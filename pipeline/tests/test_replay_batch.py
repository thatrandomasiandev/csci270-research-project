"""Batch cost and body merge. No tool is named."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.replay_batch import batch_cost, merge_bodies, plan_batches


class PlanTests(unittest.TestCase):
    def test_zero_startup_keeps_disjoint_records_apart(self) -> None:
        cand = {"a": {"m1"}, "b": {"m2"}, "c": {"m3"}}
        batches = plan_batches(["a", "b", "c"], cand, startup_pairs=0, press_pairs=0)
        self.assertEqual(batches, [["a"], ["b"], ["c"]])

    def test_large_startup_uses_one_batch(self) -> None:
        cand = {"a": {"m1"}, "b": {"m2"}, "c": {"m3"}}
        batches = plan_batches(["a", "b", "c"], cand, startup_pairs=1e9, press_pairs=0)
        self.assertEqual(batches, [["a", "b", "c"]])

    def test_shared_candidates_share_a_chunk(self) -> None:
        cand = {"a": {"m1"}, "b": {"m1"}, "c": {"m9"}, "d": {"m9"}}
        batches = plan_batches(["a", "c", "b", "d"], cand, startup_pairs=1, press_pairs=0)
        self.assertEqual(batches, [["a", "b"], ["c", "d"]])
        chosen = batch_cost(batches, cand, startup_pairs=1, press_pairs=0)
        self.assertLess(chosen, batch_cost([list(cand)], cand, startup_pairs=1, press_pairs=0))
        self.assertLess(chosen, batch_cost([[key] for key in cand], cand, startup_pairs=1, press_pairs=0))

    def test_a_chunk_keeps_input_order(self) -> None:
        cand = {"a": {"m1"}, "b": {"m1"}}
        batches = plan_batches(["b", "a"], cand, startup_pairs=1e9, press_pairs=0)
        self.assertEqual(batches, [["b", "a"]])

    def test_records_without_candidates_are_omitted(self) -> None:
        batches = plan_batches(["a", "b"], {"a": {"m1"}, "b": set()}, startup_pairs=0, press_pairs=0)
        self.assertEqual(batches, [["a"]])

    def test_negative_cost_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plan_batches(["a"], {"a": {"m"}}, startup_pairs=-1, press_pairs=0)


class MergeTests(unittest.TestCase):
    def test_bodies_return_to_input_order(self) -> None:
        first = "# head\na m1 1\nc m3 3\n# tail-a\n"
        second = "# other\nb m2 2\n# tail-b\n"
        merged = merge_bodies([second, first], 0, ["a", "b", "c"])
        self.assertTrue(merged.startswith("# other\n"))
        self.assertTrue(merged.endswith("# tail-a\n"))
        body = [line for line in merged.splitlines() if not line.startswith("#")]
        self.assertEqual(body, ["a m1 1", "b m2 2", "c m3 3"])

    def test_header_only_batch_does_not_erase_a_body(self) -> None:
        merged = merge_bodies(["# only\n", "q e 1\n"], 0, ["q"])
        self.assertIn("q e 1", merged)
        self.assertTrue(any(line.startswith("#") for line in merged.splitlines()))


if __name__ == "__main__":
    unittest.main()
