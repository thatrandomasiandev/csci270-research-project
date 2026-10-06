"""The ±25% rule is fixed before the timed JSON exists."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_reference_reannot import (  # noqa: E402
    GENOMES,
    primary,
    judge,
)


def _payload(factor: float, stop: dict | None = None) -> dict:
    runs = []
    for genome in GENOMES:
        stock = 1000.0
        acts = stock / (primary(genome["n_proteins"]) * factor)
        for repeat in (1, 2, 3):
            runs.append(
                {
                    "timed": True,
                    "accession": genome["accession"],
                    "arm": "stock",
                    "repeat": repeat,
                    "wall_s": stock,
                }
            )
            runs.append(
                {
                    "timed": True,
                    "accession": genome["accession"],
                    "arm": "acts",
                    "repeat": repeat,
                    "wall_s": acts,
                    "phases": {
                        "prep_s": 1.0,
                        "tool_s": acts - 5.0,
                        "merge_rescale_s": 2.0,
                        "render_s": 1.0,
                    },
                }
            )
    return {"runs": runs, "stop": stop, "setup": {"probe_wall_s": 100.0}}


class VerdictTests(unittest.TestCase):
    def test_exact_primary_is_confirmed(self) -> None:
        report = judge(_payload(1.0))
        self.assertEqual(report["verdict"], "CONFIRMED")
        self.assertFalse(report["no_speedup"])
        self.assertLess(report["relative_error"], 1e-9)

    def test_outside_twenty_five_percent_is_refuted(self) -> None:
        report = judge(_payload(1.26))
        self.assertEqual(report["verdict"], "REFUTED")
        self.assertGreater(report["relative_error"], 0.25)

    def test_match_failure_reports_no_speedup(self) -> None:
        report = judge(_payload(1.0, stop={"kind": "STOP_MATCH", "why": "column 4"}))
        self.assertEqual(report["verdict"], "STOP_MATCH")
        self.assertTrue(report["no_speedup"])
        self.assertIsNone(report["speedup"])

    def test_rewritten_count_fraction_is_a_protocol_mismatch(self) -> None:
        payload = _payload(1.0)
        payload["predictions"] = {"c_count": 0.5, "c_length": 600557 / 4754065}
        report = judge(payload)
        self.assertEqual(report["verdict"], "PROTOCOL_MISMATCH")
        self.assertTrue(report["no_speedup"])

    def test_preflight_runs_are_not_in_the_mean(self) -> None:
        payload = _payload(1.0)
        extra = copy.deepcopy(payload["runs"][0])
        extra["timed"] = False
        extra["wall_s"] = 1.0
        extra["arm"] = "stock"
        payload["runs"].append(extra)
        report = judge(payload)
        self.assertEqual(report["verdict"], "CONFIRMED")


if __name__ == "__main__":
    unittest.main()
