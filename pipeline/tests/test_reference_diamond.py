"""Guards for the DIAMOND second-tool driver. No DIAMOND binary, no download."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.reference_formats import length_weighted_churn, parse_fasta_entries  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "run_reference_diamond",
    PIPE / "scripts" / "run_reference_diamond.py",
)
assert _SPEC and _SPEC.loader
_DRIVER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_DRIVER)

confirmed = _DRIVER.confirmed
dbinfo_letters = _DRIVER.dbinfo_letters
fitter_churn_c = _DRIVER.fitter_churn_c
residue_identity = _DRIVER.residue_identity
s1_argv = _DRIVER.s1_argv
speedup = _DRIVER.speedup


class DiamondProtocolGuards(unittest.TestCase):
    def test_s1_is_the_locked_command(self) -> None:
        argv = s1_argv("diamond", k="0")
        self.assertNotIn("--freq-masking", argv)
        self.assertNotIn("--freq-sd", argv)
        self.assertNotIn("--symmetrize-evalue", argv)
        self.assertIn("--min-score", argv)
        self.assertEqual(argv[argv.index("--min-score") + 1], "40")
        self.assertEqual(argv[argv.index("-k") + 1], "0")
        self.assertEqual(argv[argv.index("--motif-masking") + 1], "0")
        self.assertEqual(argv[argv.index("-b") + 1], "2.0")
        self.assertEqual(argv[argv.index("--threads") + 1], "32")
        self.assertIn("evalue", argv)
        self.assertIn("bitscore", argv)
        negative = s1_argv("diamond", k="25")
        self.assertEqual(negative[negative.index("-k") + 1], "25")

    def test_c_is_entry_count_not_length(self) -> None:
        old = parse_reference_text(">a d\nAA\n>b d\nAAA\n")
        new = parse_reference_text(">a d\nAA\n>c d\nA\n")
        # identical first record, one replacement. Lengths differ, so the
        # two fractions are not the same number.
        report = length_weighted_churn(old, new)
        c = fitter_churn_c(report)
        self.assertEqual(report["n_new"], 2)
        self.assertEqual(report["n_unchanged_hash"], 1)
        self.assertEqual(c, 0.5)
        self.assertNotEqual(c, report["c_length"])

    def test_header_edit_changes_the_fitter_hash_only(self) -> None:
        same = parse_reference_text(">a one\nAC\n")
        edited = parse_reference_text(">a two\nAC\n")
        self.assertNotEqual(same[0].content_hash, edited[0].content_hash)
        self.assertEqual(residue_identity(same[0].raw), residue_identity(edited[0].raw))
        report = length_weighted_churn(same, edited)
        self.assertEqual(fitter_churn_c(report), 1.0)

    def test_speedup_and_confirmation_band(self) -> None:
        # a = 0, b = 1, c = 0.25, n = 100 → 100 / 25 = 4
        self.assertEqual(speedup(0.0, 1.0, 0.25, 100), 4.0)
        self.assertIsNone(speedup(1.0, 1.0, 0.0, 100))
        self.assertIsNone(speedup(1.0, 0.0, 0.5, 100))
        self.assertTrue(confirmed(8.0, 2.0, 4.0))
        self.assertFalse(confirmed(8.0, 2.0, 2.0))

    def test_dbinfo_letters_line(self) -> None:
        text = "                   Letters  208482574\n                   Sequences  574627\n"
        self.assertEqual(dbinfo_letters(text), 208482574)

    def test_protocol_holds_the_release_pair(self) -> None:
        text = (PIPE / "docs" / "REFERENCE_SECOND_TOOL_PROTOCOL.md").read_text()
        self.assertIn("6042adf20dad1ab62112c9053bdebd20", text)
        self.assertIn("2026_01 → 2026_03", text)
        self.assertIn("MMseqs2 is not the second tool", text)


def parse_reference_text(text: str):
    return parse_fasta_entries(text)


if __name__ == "__main__":
    unittest.main()
