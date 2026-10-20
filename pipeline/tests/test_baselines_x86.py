"""Locked Table 4 ratio math and the tblout controls. No HMMER."""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE / "scripts"))

import baselines_x86 as harness  # noqa: E402


class BaselineX86Tests(unittest.TestCase):
    def test_table4_riker_interval_rounds_like_the_paper(self) -> None:
        ratios = [
            Decimal("1.5464069019112173"),
            Decimal("1.6056444407150765"),
            Decimal("1.659961327464189"),
            Decimal("1.6651450473191905"),
        ]
        summary = harness.paired_summary(ratios)
        self.assertEqual(summary["status"], "MEASURED")
        self.assertEqual(summary["mean_paired_ratio_2dp"], "1.62")
        self.assertEqual(summary["ci95_low_2dp"], "1.53")
        self.assertEqual(summary["ci95_high_2dp"], "1.71")

    def test_fewer_than_four_is_inconclusive(self) -> None:
        summary = harness.paired_summary([Decimal("1.5"), Decimal("1.6"), Decimal("1.7")])
        self.assertEqual(summary["status"], "INCONCLUSIVE")
        self.assertIsNone(summary["ci95_low"])

    def test_rotation_and_alternation(self) -> None:
        systems = list(harness.SYSTEMS)
        firsts = [harness.pairs_for_repeat(i, systems)[0]["system"] for i in range(4)]
        self.assertEqual(firsts, systems)
        flags = [row["system_first"] for row in harness.pairs_for_repeat(0, systems)]
        self.assertEqual(flags, [False, True, False, True])

    def test_known_good_and_known_bad_tblout(self) -> None:
        stock = "# header\ntarget PF00001 query Q1 1.2e-5 10.0 rest\n"
        self.assertEqual(harness.classify_tblout(stock, stock)["relation"], "identical")
        mutated = harness.mutate_evalue(stock)
        bad = harness.classify_tblout(stock, mutated)
        self.assertEqual(bad["relation"], "different")
        self.assertIn("value-only", bad["classes"])
        self.assertNotIn("missing", bad["classes"])

    def test_missing_row_is_not_value_only(self) -> None:
        stock = "t1 PF1 q1 1 2\nt2 PF2 q2 3 4\n"
        dropped = "t1 PF1 q1 1 2\n"
        classes = harness.classify_tblout(stock, dropped)["classes"]
        self.assertIn("missing", classes)
        self.assertNotIn("value-only", classes)

    def test_lock_sentence_matches_the_protocol(self) -> None:
        text = (PIPE / "docs" / "BASELINES_X86_PROTOCOL.md").read_text()
        self.assertIn(harness.lock_sentence(), text)
        self.assertIn(str(harness.PILOT_SEED), text)
        self.assertIn(str(harness.MEASURED_SEED_RESERVED), text)

    def test_tare_argv_includes_hmmpress_prep(self) -> None:
        """Pilot 13241865 REFUSEd without --prep (use hmmpress first)."""
        source = (PIPE / "scripts" / "baselines_x86.py").read_text()
        self.assertIn('"--prep", "hmmpress -f {reference}"', source)
        self.assertIn("def run_tare", source)
