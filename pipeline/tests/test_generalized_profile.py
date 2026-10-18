"""Generalized-profile reference entries. No tool binary is involved."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.reference_formats import (  # noqa: E402
    FormatError,
    GENERALIZED_PROFILE,
    alias_map,
    length_weighted_churn,
    parse_reference_text,
    write_entries,
)

MATRIX = """\
ID   SH2; MATRIX.
AC   PS50001;
DT   NOV-1995 (CREATED).
DE   Src homology 2 (SH2) domain profile.
DR   P12345;
MA   /GENERAL_SPEC: ALPHABET='AC'; LENGTH=2;
MA   /M: SY='W'; M=-16,-34;
MA   /M:/M: SY='Y'; M=-17,-24;
CC   calibration note
//
"""

PATTERN = """\
ID   DH_1; PATTERN.
AC   PS00741;
PA   [LM]-x(2)-[LI].
//
"""

BANNER = """\
** release banner
** not an entry
//
"""


class GeneralizedProfileTests(unittest.TestCase):
    def test_matrix_keys_length_and_volatile_hash(self) -> None:
        entries = parse_reference_text(MATRIX)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.format_name, GENERALIZED_PROFILE)
        self.assertEqual(entry.keys, ("PS50001|SH2", "PS50001", "SH2"))
        self.assertEqual(entry.primary, "PS50001|SH2")
        # LENGTH=2 is informative. Three /M: marks are the match positions.
        self.assertEqual(entry.length, 3)
        self.assertIn("//\n", entry.raw)

        dated = MATRIX.replace("DR   P12345;", "DR   P99999;")
        dated = dated.replace("DT   NOV-1995 (CREATED).", "DT   JAN-2026 (DATA UPDATE).")
        other = parse_reference_text(dated)[0]
        self.assertEqual(other.content_hash, entry.content_hash)

        scored = MATRIX.replace("M=-16,-34;", "M=-1,-34;")
        changed = parse_reference_text(scored)[0]
        self.assertNotEqual(changed.content_hash, entry.content_hash)

    def test_banner_pattern_and_roundtrip(self) -> None:
        text = BANNER + PATTERN + MATRIX
        entries = parse_reference_text(text)
        self.assertEqual([entry.primary for entry in entries], ["PS00741|DH_1", "PS50001|SH2"])
        # Non-space characters of the PA body: [LM]-x(2)-[LI].
        self.assertEqual(entries[0].length, len("[LM]-x(2)-[LI]."))
        with tempfile.TemporaryDirectory() as tmp:
            written = write_entries(entries, Path(tmp) / "library.prf")
            again = parse_reference_text(written.read_text())
        self.assertEqual([entry.content_hash for entry in again], [entry.content_hash for entry in entries])
        self.assertEqual(alias_map(entries)["PS50001"], 1)
        self.assertEqual(alias_map(entries)["SH2"], 1)

    def test_cross_reference_churn_is_not_a_scoring_change(self) -> None:
        old = parse_reference_text(MATRIX)
        new = parse_reference_text(MATRIX.replace("DR   P12345;", "DR   Q9ZZZ9;"))
        report = length_weighted_churn(old, new)
        self.assertEqual(report["n_unchanged_hash"], 1)
        self.assertEqual(report["n_changed_and_new"], 0)
        self.assertEqual(report["c_length"], 0.0)

    def test_truncated_and_missing_accession(self) -> None:
        with self.assertRaises(FormatError):
            parse_reference_text("ID   SH2; MATRIX.\nAC   PS50001;\n")
        with self.assertRaises(FormatError):
            parse_reference_text("ID   SH2; MATRIX.\n//\n")


if __name__ == "__main__":
    unittest.main()
