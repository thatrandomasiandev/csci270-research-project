"""Row-occurrence index and pass-through text.

The four duplicate keys and the two mixed description columns are the
recorded HMMER refusals. The cells are the recorded tokens; the surrounding
columns are the smallest table that makes the same decision.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.reference_fit import (
    fit_observations,
    index_candidates,
    index_rows,
    with_occurrence,
)

# Recorded duplicate keys: (protein, family, shared E-value), accession.
DUPLICATE_KEYS = (
    ("WP_000726974.1", "Gly-zipper_OmpA", "1.2e-06", "GCF_015290725.1", "2.4e-06", "2.5e-06"),
    ("WP_196795573.1", "TPR_17", "2.4e-08", "GCF_002078355.1", "4.8e-08", "4.9e-08"),
    ("WP_014453168.1", "DNA_gyraseA_C", "1.6e-12", "GCF_000284335.1", "3.2e-12", "3.3e-12"),
    ("WP_052881759.1", "Hexapep_2", "1.4e-05", "GCF_001017655.1", "2.8e-05", "2.9e-05"),
)


def _line(cells: list[str]) -> str:
    return " ".join(cells)


def _table(rows: list[list[str]]) -> str:
    return "\n".join(_line(row) for row in rows) + "\n"


def _fit_duplicate(protein: str, family: str, part_e: str, whole_a: str, whole_b: str):
    """Two domains share an E-value on the part and not on the whole.

    Domain number uniques both sides. The E-value column is a candidate on
    the whole, so the old gate raised while scoring it.
    """
    other = "other_query"
    other_fam = "OtherFam"
    part_rows = [
        [protein, family, "1", part_e, "10"],
        [protein, family, "2", part_e, "80"],
    ]
    whole_rows = [
        [protein, family, "1", whole_a, "10"],
        [protein, family, "2", whole_b, "80"],
        [other, other_fam, "1", "2.0", "5"],
    ]
    part_other = [[other, other_fam, "1", "1.0", "5"]]
    return fit_observations(
        entries_n=2,
        lengths=[100, 300],
        part_index_lists=[[0], [1]],
        record_ids={protein, other},
        alias_to_index={family: 0, other_fam: 1},
        whole_tables={"domtblout": _table(whole_rows)},
        part_tables=[
            {"domtblout": _table(part_rows)},
            {"domtblout": _table(part_other)},
        ],
    )


def _tbl_row(query: str, description: list[str]) -> list[str]:
    """19 fixed tokens, then any extra description words. Column 18 is first."""
    cells = ["PF00001", "PF00001.1", query, "1", "1.5", "10.0", "0.0", "1.5", "10.0", "0.0",
             "1.2", "1", "0", "0", "1", "1", "1", "1"]
    return cells + description


def _fit_tbl(descriptions: list[list[str]]):
    queries = [f"q{i}" for i in range(len(descriptions))]
    rows = [_tbl_row(query, desc) for query, desc in zip(queries, descriptions)]
    return fit_observations(
        entries_n=2,
        lengths=[10, 10],
        part_index_lists=[[0], [1]],
        record_ids=set(queries),
        alias_to_index={"PF00001": 0, "PF99999": 1},
        whole_tables={"tblout": _table(rows)},
        part_tables=[{"tblout": _table(rows)}, {"tblout": ""}],
    )


class OccurrenceIndexTests(unittest.TestCase):
    def test_unique_key_is_unchanged(self) -> None:
        rows = [["q", "s", "1.2e-06"]]
        indexed = index_rows(rows, 0, 1, 2)
        self.assertEqual(list(indexed), [("q", "s", "1.2e-06")])
        self.assertEqual(indexed[("q", "s", "1.2e-06")], rows[0])

    def test_no_unique_column_uses_occurrence_instead_of_refusing(self) -> None:
        rows = [
            ["q", "s", "1", "9"],
            ["q", "s", "1", "8"],
            ["q", "s", "2", "9"],
        ]
        self.assertEqual(index_candidates(rows, 0, 1), [None])
        indexed = index_rows(rows, 0, 1, None)
        keys = list(indexed)
        self.assertEqual(keys[0], ("q", "s", ""))
        self.assertEqual(keys[1], with_occurrence(("q", "s", ""), 1))
        self.assertEqual(keys[2], with_occurrence(("q", "s", ""), 2))
        self.assertEqual(list(indexed.values()), rows)

    def test_four_recorded_duplicate_keys_keep_file_order(self) -> None:
        for protein, family, evalue, accession, _whole_a, _whole_b in DUPLICATE_KEYS:
            with self.subTest(accession=accession):
                rows = [
                    [protein, family, "1", evalue, "10"],
                    [protein, family, "2", evalue, "80"],
                ]
                indexed = index_rows(rows, 0, 1, 3)
                keys = list(indexed)
                base = (protein, family, evalue)
                self.assertEqual(keys, [base, with_occurrence(base, 1)])
                self.assertEqual(list(indexed.values()), rows)
                self.assertNotIn("\x1f", " ".join(rows[0] + rows[1]))
                self.assertIn("\x1f", keys[1][2])

    def test_recorded_duplicate_keys_ship_by_domain_number(self) -> None:
        for protein, family, evalue, accession, whole_a, whole_b in DUPLICATE_KEYS:
            with self.subTest(accession=accession):
                result = _fit_duplicate(protein, family, evalue, whole_a, whole_b)
                self.assertEqual(result.decision, "SHIP", result.reason)
                self.assertNotIn("duplicate row key", result.reason)
                table = result.tables[0]
                self.assertEqual(table.index_col, 2)
                evalue_col = next(col for col in table.columns if col.index == 3)
                self.assertEqual(evalue_col.role, "numeric")
                self.assertEqual(evalue_col.member, "entry_count")


class PassThroughTextTests(unittest.TestCase):
    def test_drosophila_column_18_trailing_text_ships(self) -> None:
        """GCF_000001215.4. Column 18 is the tail. Most first tokens are numbers."""
        result = _fit_tbl(
            [
                ["10"],
                ["20"],
                ["30"],
                ["Notch", "ligand"],
            ]
        )
        self.assertEqual(result.decision, "SHIP", result.reason)
        self.assertNotIn("mixed numeric and text", result.reason)
        column = next(col for col in result.tables[0].columns if col.index == 18)
        self.assertEqual(column.role, "byte")
        self.assertEqual(column.member, "byte")

    def test_gca_001817145_column_18_mostly_text_ships(self) -> None:
        """GCA_001817145.1. Equal width, so the majority rule is what ships it."""
        result = _fit_tbl(
            [
                ["kinase"],
                ["42"],
                ["channel"],
                ["subunit"],
            ]
        )
        self.assertEqual(result.decision, "SHIP", result.reason)
        self.assertNotIn("mixed numeric and text", result.reason)
        column = next(col for col in result.tables[0].columns if col.index == 18)
        self.assertEqual(column.role, "byte")

    def test_mostly_numeric_text_token_still_refuses(self) -> None:
        descriptions = [["1"], ["2"], ["3"], ["note"]]
        # Fixed width, and column 18 is mostly numeric: the majority rule refuses.
        result = _fit_tbl(descriptions)
        self.assertEqual(result.decision, "REFUSE")
        self.assertIn("tblout: column 18 is mixed numeric and text", result.reason)

    def test_even_split_still_refuses(self) -> None:
        result = _fit_tbl([["1"], ["note"]])
        self.assertEqual(result.decision, "REFUSE")
        self.assertIn("mixed numeric and text", result.reason)


if __name__ == "__main__":
    unittest.main()
