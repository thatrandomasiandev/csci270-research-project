"""ref-merge uses the locked predicate against the source printed value.

The fitter's T1–T4 outcomes live in test_reference_fitter.py and are rerun
with the rest of the suite. This file is the checker guard.
"""

from __future__ import annotations

import json
import random
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.reference_fit import (  # noqa: E402
    BYTE,
    IDENTITY,
    ColumnReport,
    consistent,
    dump_rescale_provenance,
    half_ulp,
    load_rescale_provenance,
    ref_merge_printed_rows,
    ref_merge_rows,
    reprint_like,
)
from acts.reference_formats import parse_reference, read_records, write_entries  # noqa: E402
from acts.reference_run import (  # noqa: E402
    ReferenceIncremental,
    _provenance_held,
    _rescale_held,
    _row_for_cache,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "reference_fitter"
T1 = PIPE / "results" / "reference_fitter_t1.json"
PHIS = (1.097, 7.44, 30.0)
SMOKE_PHI = 30134 / 4052


def _columns() -> list[ColumnReport]:
    return [
        ColumnReport(index=0, role="byte", member=BYTE),
        ColumnReport(index=1, role="byte", member=BYTE),
        ColumnReport(index=2, role="numeric", member="entry_count"),
    ]


def _pair(source: str, stock: str, phi: float, *, identity: str = "m"):
    key = ("q", "m", "")
    emitted = reprint_like(source, float(source) * phi)
    rows_stock = {key: ["q", "m", stock]}
    rows_ours = {key: ["q", identity, emitted]}
    provenance = {key: {2: (source, phi)}}
    return rows_stock, rows_ours, provenance


def _printed(sig: int, rng: random.Random) -> str:
    digits = rng.randrange(10 ** (sig - 1), 10**sig)
    exp = rng.randint(-30, 6)
    sign = -1.0 if rng.random() < 0.05 else 1.0
    value = sign * digits * 10 ** (exp - (sig - 1))
    return f"{value:.{sig - 1}e}"


def _walk_worst(node, found: list[dict]) -> None:
    if isinstance(node, dict):
        if {"part_printed", "whole_printed", "phi"} <= set(node):
            found.append(node)
        for value in node.values():
            _walk_worst(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk_worst(value, found)


class RefMergeTests(unittest.TestCase):
    def test_property_accepted_values_pass_ref_merge(self) -> None:
        rng = random.Random(20261009)
        columns = _columns()
        mismatches = 0
        for sig in (2, 3):
            for phi in PHIS:
                accepted = 0
                trials = 0
                while accepted < 400 and trials < 8000:
                    trials += 1
                    source = _printed(sig, rng)
                    nominal = reprint_like(source, float(source) * phi)
                    if not nominal or nominal in {"nan", "inf", "-inf"}:
                        continue
                    ulp = 2 * half_ulp(nominal)
                    stock = reprint_like(source, float(source) * phi + rng.randint(-6, 6) * ulp)
                    if stock in {"nan", "inf", "-inf"} or not consistent(source, stock, phi):
                        continue
                    accepted += 1
                    emitted = reprint_like(source, float(source) * phi)
                    if emitted != stock:
                        mismatches += 1
                    bound = (
                        half_ulp(stock)
                        + half_ulp(emitted)
                        + abs(phi) * half_ulp(source)
                    )
                    gap = abs(float(emitted) - float(stock))
                    self.assertLessEqual(gap, bound * (1 + 1e-9) + 1e-15)
                    left, right, provenance = _pair(source, stock, phi)
                    ok, why = ref_merge_rows(left, right, columns, provenance)
                    self.assertTrue(ok, f"{source} * {phi} vs {stock}: {why}")
                self.assertEqual(accepted, 400, f"sig={sig} phi={phi} trials={trials}")
        self.assertGreater(mismatches, 0)

    def test_smoke_example_and_r2p_r3c_still_pass(self) -> None:
        source = "1.2e-21"
        stock = "8.7e-21"
        emitted = reprint_like(source, float(source) * SMOKE_PHI)
        self.assertEqual(emitted, "8.9e-21")
        self.assertTrue(consistent(source, stock, SMOKE_PHI))
        self.assertFalse(consistent(emitted, stock, 1.0))
        columns = _columns()
        left, right, provenance = _pair(source, stock, SMOKE_PHI)
        ok, why = ref_merge_rows(left, right, columns, provenance)
        self.assertTrue(ok, why)
        self.assertTrue(consistent(source, stock, 7.44))
        left, right, provenance = _pair(source, stock, 7.44)
        ok, why = ref_merge_rows(left, right, columns, provenance)
        self.assertTrue(ok, why)

        found: list[dict] = []
        _walk_worst(json.loads(T1.read_text()), found)
        passed = 0
        for row in found:
            part = str(row["part_printed"])
            whole = str(row["whole_printed"])
            phi = float(row["phi"])
            if not consistent(part, whole, phi):
                continue
            left, right, provenance = _pair(part, whole, phi)
            ok, why = ref_merge_rows(left, right, columns, provenance)
            self.assertTrue(ok, f"{part} * {phi} vs {whole}: {why}")
            passed += 1
        self.assertGreaterEqual(passed, 4)

    def test_off_by_factor_missing_row_and_identity_still_fail(self) -> None:
        source = "1.2e-21"
        phi = SMOKE_PHI
        bad = reprint_like(source, float(source) * phi * 1.2)
        self.assertFalse(consistent(source, bad, phi))
        columns = _columns()
        left, right, provenance = _pair(source, bad, phi)
        ok, why = ref_merge_rows(left, right, columns, provenance)
        self.assertFalse(ok)
        self.assertIn("mismatch", why)

        key = ("q", "m", "")
        other = ("q", "other", "")
        emitted = reprint_like(source, float(source) * phi)
        stock = {key: ["q", "m", "8.7e-21"], other: ["q", "other", "8.7e-21"]}
        ours = {key: ["q", "m", emitted]}
        ok, why = ref_merge_rows(stock, ours, columns, {key: {2: (source, phi)}})
        self.assertFalse(ok)
        self.assertIn("row-key", why)

        left, right, provenance = _pair(source, "8.7e-21", phi, identity="changed")
        ok, why = ref_merge_rows(left, right, columns, provenance)
        self.assertFalse(ok)
        self.assertIn("column 1", why)

    def test_per_key_phi_is_the_post_merge_count(self) -> None:
        table_columns = [
            ColumnReport(index=0, role="byte", member=BYTE),
            ColumnReport(index=1, role="byte", member=BYTE),
            ColumnReport(
                index=2,
                role="numeric",
                member="per_key_row_count",
                count_table="out",
            ),
        ]
        from acts.reference_fit import TableReport

        table = TableReport(
            name="out",
            record_col=0,
            entry_col=1,
            index_col=None,
            meta=[],
            columns=table_columns,
        )

        def row(entry: str) -> dict:
            return {
                "table": "out",
                "record_key": "q",
                "entry_hash": entry,
                "entry_token": entry,
                "row_index": "",
                "cells": ["q", entry, "1.000000"],
                "basis": {
                    "entry_count": 2,
                    "total_entry_length": 4,
                    "row_count": {"out": 1},
                },
            }

        scaled = _rescale_held([row("a"), row("b")], [table], 2, 4)
        self.assertEqual(scaled[0]["rescale"][2][1], 2.0)
        self.assertEqual(scaled[0]["cells"][2], reprint_like("1.000000", 2.0))
        stored = _row_for_cache(scaled[0])
        self.assertNotIn("rescale", stored)

    def test_sidecar_roundtrip_and_cache_omits_provenance(self) -> None:
        key = ("q", "m", "")
        payload = dump_rescale_provenance({key: {2: ("1.2e-21", SMOKE_PHI)}})
        self.assertEqual(load_rescale_provenance(payload), {key: {2: ("1.2e-21", SMOKE_PHI)}})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref1 = FIX / "ab.entryline"
            records = FIX / "ab.faa"
            keep = [entry for entry in parse_reference(ref1) if entry.primary in {"e1", "e3"}]
            ref2 = root / "v2.entryline"
            write_entries(keep + _added(), ref2)
            cache = root / "cache.sqlite"

            def run(ref: Path):
                return ReferenceIncremental(
                    argv=["law", "{reference}", "{input}", "{output}"],
                    input_path=records,
                    out_dir=root / ref.stem,
                    reference=ref,
                    cache_path=cache,
                    verify="full",
                    runner=lambda recs, ents: _table(recs, ents),
                ).run()

            first = run(ref1)
            self.assertEqual(first.decision, "SHIP", first.reason)
            second = run(ref2)
            self.assertEqual(second.decision, "SHIP", second.reason)
            sidecar = json.loads((root / "v2" / "tables" / "out.provenance.json").read_text())
            self.assertEqual(sidecar["version"], 1)
            loaded = load_rescale_provenance(sidecar)
            self.assertTrue(loaded)
            conn = sqlite3.connect(cache)
            try:
                payloads = conn.execute("SELECT payload FROM rows").fetchall()
            finally:
                conn.close()
            self.assertTrue(payloads)
            for (blob,) in payloads:
                row = json.loads(blob)
                self.assertNotIn("rescale", row)
                self.assertIn("cells", row)
                self.assertIn("basis", row)
            third = run(ref2)
            self.assertEqual(third.decision, "SHIP", third.reason)
            again = json.loads((root / "v2" / "tables" / "out.provenance.json").read_text())
            self.assertTrue(load_rescale_provenance(again))

    def test_second_render_keeps_the_source_printed_value(self) -> None:
        """A reprint that is not byte-identical to stock must still pass after reload.

        Job 12865788 preflight matched, then the timed arm stored the reprint.
        The next render saw phi 1, dropped provenance, and failed column 4.
        """
        from acts.reference_fit import TableReport

        columns = [
            ColumnReport(index=0, role="byte", member=BYTE),
            ColumnReport(index=1, role="numeric", member=IDENTITY),
            ColumnReport(index=2, role="numeric", member="total_entry_length"),
        ]
        table = TableReport(
            name="out",
            record_col=0,
            entry_col=1,
            index_col=None,
            meta=[],
            columns=columns,
        )
        source = "1.2e-21"
        stock = "8.7e-21"
        row = {
            "table": "out",
            "record_key": "q",
            "entry_hash": "h",
            "entry_token": "m",
            "row_index": "",
            "cells": ["q", "m", source],
            "basis": {
                "entry_count": 10,
                "total_entry_length": 100,
                "row_count": {"out": 1},
            },
        }
        scaled = _rescale_held([row], [table], 10, 744)
        self.assertEqual(scaled[0]["rescale"][2][0], source)
        self.assertAlmostEqual(scaled[0]["rescale"][2][1], 7.44)
        self.assertNotEqual(scaled[0]["cells"][2], stock)
        key = ("q", "m", "")
        ok, why = ref_merge_rows(
            {key: ["q", "m", stock]},
            {key: scaled[0]["cells"]},
            columns,
            _provenance_held(scaled, table),
        )
        self.assertTrue(ok, why)
        # The cache keeps the source. A later render rescales it again.
        stored = _row_for_cache(row)
        self.assertEqual(stored["cells"][2], source)
        again = _rescale_held([stored], [table], 10, 744)
        ok, why = ref_merge_rows(
            {key: ["q", "m", stock]},
            {key: again[0]["cells"]},
            columns,
            _provenance_held(again, table),
        )
        self.assertTrue(ok, why)
        self.assertIn(2, _provenance_held(again, table)[key])


def _added():
    from acts.reference_formats import parse_entryline

    return parse_entryline("e4 5\n")


def _table(records, entries) -> dict[str, str]:
    lines = ["# record entry evalue"]
    for rec in records:
        for entry in entries:
            if entry.primary not in {"e1", "e3"}:
                continue
            lines.append(f"{rec.key} {entry.primary} {len(entries) * float(rec.description):.6f}")
    return {"out": "\n".join(lines) + "\n"}


class PrintedThirdPartyTests(unittest.TestCase):
    def test_printed_half_ulp_is_not_the_acts_checker(self) -> None:
        columns = [
            ColumnReport(index=0, role="byte", member=BYTE),
            ColumnReport(index=1, role="numeric", member=IDENTITY),
            ColumnReport(index=2, role="numeric", member="total_entry_length"),
        ]
        key = ("q", "s", "")
        stock = {key: ["q", "same", "1.00e-05"]}
        near = {key: ["q", "same", "1.01e-05"]}
        ok, why = ref_merge_printed_rows(stock, near, columns)
        self.assertTrue(ok, why)
        ok, why = ref_merge_rows(stock, near, columns, {})
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
