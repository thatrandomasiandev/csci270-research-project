"""Guards for the BLAST+ boundary driver. No BLAST binary and no database."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.reference_fit import (  # noqa: E402
    MEMBERS,
    PROBE_K,
    PROBE_SEED,
    disambiguating_indices,
    partition_indices,
)
from acts.reference_formats import RecordItem, parse_reference_text  # noqa: E402
from acts.reference_run import probe_fit  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "run_reference_boundary",
    PIPE / "scripts" / "run_reference_boundary.py",
)
assert _SPEC and _SPEC.loader
_DRIVER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_DRIVER)

_DIAG_SPEC = importlib.util.spec_from_file_location(
    "diagnose_reference_boundary",
    PIPE / "scripts" / "diagnose_reference_boundary.py",
)
assert _DIAG_SPEC and _DIAG_SPEC.loader
_DIAG = importlib.util.module_from_spec(_DIAG_SPEC)
_DIAG_SPEC.loader.exec_module(_DIAG)

b1_argv = _DRIVER.b1_argv
column_residuals = _DRIVER.column_residuals
select_queries = _DRIVER.select_queries
OUTFMT_FIELDS = _DRIVER.OUTFMT_FIELDS
QUERY_N = _DRIVER.QUERY_N
PROTOCOL = (PIPE / "docs" / "REFERENCE_BOUNDARY_PROTOCOL.md").read_text()


def _combination_tables(records, entries):
    lengths = sum(item.length for item in entries)
    # n' = n - 3 N. Printed finer than BLAST's one-digit E-value so a
    # combination cannot hide inside half-ULP.
    value = (lengths - 3 * len(entries)) * 0.5
    lines = ["# record entry evalue"]
    for rec in records:
        for entry in entries:
            lines.append(f"{rec.key} {entry.primary} {value:.8f}")
    return {"out": "\n".join(lines) + "\n"}


class ReferenceBoundaryTests(unittest.TestCase):
    def test_family_stays_the_closed_four(self) -> None:
        self.assertEqual(
            MEMBERS,
            ("identity", "entry_count", "total_entry_length", "per_key_row_count"),
        )
        source = (PIPE / "scripts" / "run_reference_boundary.py").read_text()
        self.assertNotIn("effective_length", source)
        self.assertNotIn("MEMBERS =", source)

    def test_b1_is_the_locked_command(self) -> None:
        argv = b1_argv("blastp", threads="4")
        self.assertEqual(argv[0], "blastp")
        self.assertEqual(argv[argv.index("-evalue") + 1], "1000")
        self.assertEqual(argv[argv.index("-max_target_seqs") + 1], "100000")
        self.assertEqual(argv[argv.index("-num_threads") + 1], "4")
        outfmt = argv[argv.index("-outfmt") + 1]
        self.assertTrue(outfmt.startswith("6 "))
        fields = outfmt.split()[1:]
        self.assertEqual(fields, list(OUTFMT_FIELDS))
        self.assertEqual(fields.index("evalue"), 10)
        self.assertEqual(fields.index("bitscore"), 11)
        self.assertNotIn("-comp_based_stats", argv)
        self.assertNotIn("-max_hsps", argv)
        self.assertNotIn("-dbsize", argv)
        self.assertNotIn("-searchsp", argv)
        self.assertIn("-evalue 1000", PROTOCOL)
        self.assertIn("-max_target_seqs 100000", PROTOCOL)

    def test_query_draw_uses_the_locked_seed(self) -> None:
        records = [
            RecordItem(key=f"q{i}", name=f"q{i}", description="", sequence="A")
            for i in range(40)
        ]
        drawn = select_queries(records)
        again = select_queries(records, n=QUERY_N, seed=PROBE_SEED)
        self.assertEqual([item.key for item in drawn], [item.key for item in again])
        self.assertEqual(len(drawn), 20)
        self.assertEqual(len({item.key for item in drawn}), 20)
        self.assertIn("sample_record_indices(n, 20, 20261006)", PROTOCOL)

    def test_karlin_combination_is_refused(self) -> None:
        text = "e0 10\ne1 100\ne2 10\ne3 100\n"
        entries = parse_reference_text(text)
        records = [RecordItem(key="q0", name="q0", description="", sequence="")]
        result = probe_fit(entries, records, lambda recs, ents: _combination_tables(recs, ents))
        self.assertEqual(result.decision, "REFUSE", result.reason)
        self.assertTrue(result.used_tie_break)
        self.assertIn("tie-break", result.reason)

        parts = partition_indices(len(entries), PROBE_K, PROBE_SEED)
        whole = _combination_tables(records, entries)["out"]
        part_texts = [
            _combination_tables(records, [entries[i] for i in indices])["out"] for indices in parts
        ]
        primary = column_residuals(entries, {"q0"}, parts, whole, part_texts)
        evalue = next(col for col in primary["columns"] if col["index"] == 2)
        self.assertTrue(evalue["members"]["entry_count"]["fits"])
        self.assertTrue(evalue["members"]["total_entry_length"]["fits"])
        self.assertFalse(evalue["members"]["identity"]["fits"])

        split = disambiguating_indices(
            [entry.length for entry in entries],
            [entry.content_hash for entry in entries],
        )
        self.assertIsNotNone(split)
        assert split is not None
        tie_texts = [
            _combination_tables(records, [entries[i] for i in indices])["out"] for indices in split
        ]
        broken = column_residuals(entries, {"q0"}, list(split), whole, tie_texts)
        evalue = next(col for col in broken["columns"] if col["index"] == 2)
        self.assertFalse(evalue["members"]["entry_count"]["fits"])
        self.assertFalse(evalue["members"]["total_entry_length"]["fits"])
        self.assertFalse(evalue["members"]["per_key_row_count:out"]["fits"])
        self.assertGreater(evalue["members"]["total_entry_length"]["max_abs_residual"], 1.0)

    def test_protocol_locks_the_prediction(self) -> None:
        self.assertIn("blast-plus/2.14.1", PROTOCOL)
        self.assertIn("712c2dbdf0fb13cc1c2d4f4ef5dd1ce4b06c3b57e96dfea8f23e6e99f5b1650e", PROTOCOL)
        self.assertIn("BLAST_SpougeStoE", PROTOCOL)
        self.assertIn("n − N·ℓ", PROTOCOL)
        self.assertIn("OLD_FSC", PROTOCOL)
        self.assertIn("only-union", PROTOCOL)
        self.assertIn("total_entry_length", PROTOCOL)
        self.assertIn("bitscore", PROTOCOL)
        self.assertIn("Overall.** REFUSE", PROTOCOL)
        self.assertIn("Addendum 2026-10-09 — outcome", PROTOCOL)
        self.assertIn("different_hsp", PROTOCOL)
        self.assertIn("out: column 2 matches no normalizer", PROTOCOL)
        self.assertIn("15,124", PROTOCOL)
        locked = PROTOCOL.split("## Addendum 2026-10-09 — outcome", 1)[0]
        self.assertNotIn("different_hsp", locked)

    def test_outcome_files_agree_with_the_addendum(self) -> None:
        measured = json.loads((PIPE / "results" / "reference_boundary_blast.json").read_text())
        diagnosis = json.loads((PIPE / "results" / "reference_boundary_diagnosis.json").read_text())
        self.assertEqual(measured["decision"], "REFUSE")
        self.assertEqual(measured["reason"], "out: column 2 matches no normalizer")
        keys = measured["primary_residuals"]["key_sets"]
        self.assertEqual(keys["only_union"], 13812)
        self.assertEqual(keys["only_whole"], 0)
        self.assertEqual(keys["whole"], 15125)
        self.assertEqual(diagnosis["label"], "POST-HOC")
        self.assertEqual(diagnosis["key_sets"]["only_union"], 13812)
        self.assertEqual(diagnosis["joined_same_hsp"], 15124)
        self.assertEqual(diagnosis["mismatch_counts"], {"different_hsp": 1})
        self.assertEqual(diagnosis["mismatches"][0]["subject"], "sp|A0KJE6|LOLA_AERHH")
        evalue = next(
            col for col in diagnosis["same_hsp_residuals"]["columns"] if col["field"] == "evalue"
        )
        bitscore = next(
            col for col in diagnosis["same_hsp_residuals"]["columns"] if col["field"] == "bitscore"
        )
        self.assertTrue(evalue["members"]["total_entry_length"]["fits"])
        self.assertFalse(evalue["members"]["identity"]["fits"])
        self.assertTrue(bitscore["members"]["identity"]["fits"])
        for name in ("whole", "part0", "part1"):
            path = PIPE / "results" / "reference_boundary_tables" / f"{name}.tsv"
            digest = hashlib.md5(path.read_bytes()).hexdigest()
            self.assertEqual(digest, diagnosis["table_md5"][name])

    def test_classify_a_different_hsp_and_a_misjoined_interval(self) -> None:
        classify = _DIAG.classify_joined
        whole = "q s 33.333 36 23 1 10 37 5 36 205 25.0".split()
        other = "q s 21.875 128 72 5 10 105 5 125 180 24.3".split()
        self.assertEqual(classify(whole, other, [other]), "different_hsp")
        hidden = "q s 33.333 36 23 1 10 37 5 36 205 25.0".split()
        self.assertEqual(classify(whole, other, [other, hidden]), "misaligned_row_key")
        same_interval = "q s 21.875 36 23 1 10 37 5 36 180 24.3".split()
        self.assertEqual(
            classify(whole, same_interval, [same_interval]),
            "same_interval_different_score",
        )
        self.assertEqual(classify(whole, list(whole), [list(whole)]), "same_hsp")
