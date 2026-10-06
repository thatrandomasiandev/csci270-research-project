from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.fasta import FastaRec, read_fasta, write_fasta
from acts.infer_fasta import (
    InferError,
    TableContract,
    infer_table_contract,
    preflight_stock_outputs,
)
from acts.strategies.record_memo import RecordMemo
from acts.table import body_lines
from acts.__main__ import main as acts_main

PIPE = Path(__file__).resolve().parents[1]
FIX = PIPE / "fixtures" / "fasta_memo"
TINY = FIX / "tiny.fa"
PY = sys.executable


def _argv(script: str) -> list[str]:
    return [PY, str(FIX / script)]


class InferFastaFixtureTests(unittest.TestCase):
    def test_per_query_ships_order_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="fasta",
                argv=_argv("per_query_table.py"),
                input_path=TINY,
                out_dir=Path(td),
                verify="full",
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            contract = json.loads((Path(td) / "cache.jsonl.contract.json").read_text())
            self.assertEqual(contract["match"], "order")
            self.assertEqual(contract["query_col"], 0)
            self.assertIn(1, contract["produced_cols"])
            rebuilt = (Path(td) / "reassembled.out").read_text()
            full = (Path(td) / "full.out").read_text()
            self.assertEqual(body_lines(rebuilt), body_lines(full))

    def test_global_score_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="fasta",
                argv=_argv("global_evalue.py"),
                input_path=TINY,
                out_dir=Path(td),
            ).run()
            self.assertEqual(rec.decision, "REFUSE_GLOBAL", rec.reason)

    def test_sorted_output_multiset_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="fasta",
                argv=_argv("sorted_output.py"),
                input_path=TINY,
                out_dir=Path(td),
                verify="full",
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            contract = json.loads((Path(td) / "cache.jsonl.contract.json").read_text())
            self.assertEqual(contract["match"], "multiset")
            self.assertIn("multiset", rec.reason)

    def test_zero_hit_empty_is_cached_hit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "cache.jsonl"
            first = RecordMemo(
                kind="fasta",
                argv=_argv("zero_hit.py"),
                input_path=TINY,
                out_dir=Path(td) / "a",
                cache_path=cache,
            ).run()
            self.assertEqual(first.decision, "SHIP", first.reason)
            payload = [json.loads(ln) for ln in cache.read_text().splitlines() if ln]
            empty_rows = [
                json.loads(row["output"])["rows"]
                for row in payload
                if json.loads(row["output"])["rows"] == []
            ]
            self.assertTrue(empty_rows, "EMPTY result was not cached")

            other = Path(td) / "renamed.fa"
            recs = read_fasta(TINY)
            recs = [
                FastaRec(f"skipX" if r.name.startswith("skip") else f"N{i}", r.description, r.seq)
                for i, r in enumerate(recs)
            ]
            write_fasta(other, recs)
            second = RecordMemo(
                kind="fasta",
                argv=_argv("zero_hit.py"),
                input_path=other,
                out_dir=Path(td) / "b",
                cache_path=cache,
            ).run()
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertEqual(int(second.extra["n_misses"]), 0)
            self.assertEqual(int(second.extra["n_hits"]), 5)
            rebuilt = (Path(td) / "b" / "reassembled.out").read_text()
            self.assertFalse(any(ln.startswith("skip") for ln in body_lines(rebuilt)))
            self.assertTrue(any(ln.startswith("N0") for ln in body_lines(rebuilt)))

    def test_padded_names_and_empty_desc_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "cache.jsonl"
            bare = Path(td) / "bare.fa"
            write_fasta(bare, [FastaRec(r.name, "", r.seq) for r in read_fasta(TINY)])
            first = RecordMemo(
                kind="fasta",
                argv=_argv("padded_table.py"),
                input_path=bare,
                out_dir=Path(td) / "a",
                cache_path=cache,
            ).run()
            self.assertEqual(first.decision, "SHIP", first.reason)
            contract = json.loads((cache.parent / (cache.name + ".contract.json")).read_text())
            self.assertTrue(contract["pad_widths"] or contract["match_ws"] or contract.get("layout", {}).get("pinned"), contract)
            self.assertEqual(contract["empty_desc"], "-")
            self.assertFalse(contract["match_ws"], contract.get("layout"))
            self.assertEqual(contract.get("layout", {}).get("scope"), "per_file")

            other = Path(td) / "long.fa"
            recs = read_fasta(TINY)
            recs = [FastaRec(f"LONGNAME{i:04d}", "", r.seq) for i, r in enumerate(recs)]
            write_fasta(other, recs)
            second = RecordMemo(
                kind="fasta",
                argv=_argv("padded_table.py"),
                input_path=other,
                out_dir=Path(td) / "b",
                cache_path=cache,
                verify="full",
            ).run()
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertEqual(int(second.extra["n_misses"]), 0)
            rebuilt = (Path(td) / "b" / "reassembled.out").read_text()
            full = (Path(td) / "b" / "full.out").read_text()
            self.assertEqual(body_lines(rebuilt), body_lines(full))

    def test_trailing_multiword_desc_is_passthrough(self) -> None:
        """Guard for the 2026-09-28 savings STOP_MATCH (A hmmsearch genome 5).

        The same sequence recurred with a different multi-word description; the cache
        replayed the old one. Descriptions must be copied from the new input.
        """
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "cache.jsonl"
            recs = read_fasta(TINY)
            first_fa = Path(td) / "g1.fa"
            write_fasta(
                first_fa,
                [FastaRec(r.name, f"alpha beta protein {i}", r.seq) for i, r in enumerate(recs)],
            )
            first = RecordMemo(
                kind="fasta",
                argv=_argv("ws_trailing_desc.py"),
                input_path=first_fa,
                out_dir=Path(td) / "a",
                cache_path=cache,
            ).run()
            self.assertEqual(first.decision, "SHIP", first.reason)

            second_fa = Path(td) / "g2.fa"
            descs = ["MULTISPECIES: renamed family [Enterobacteriaceae]", "", "x", "two words"]
            write_fasta(
                second_fa,
                [FastaRec(f"G2_{i:07d}", descs[i % len(descs)], r.seq) for i, r in enumerate(recs)],
            )
            second = RecordMemo(
                kind="fasta",
                argv=_argv("ws_trailing_desc.py"),
                input_path=second_fa,
                out_dir=Path(td) / "b",
                cache_path=cache,
                verify="full",
            ).run()
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertEqual(int(second.extra["n_misses"]), 0)
            rebuilt = (Path(td) / "b" / "reassembled.out").read_text()
            full = (Path(td) / "b" / "full.out").read_text()
            norm = lambda t: sorted(" ".join(ln.split()) for ln in body_lines(t))
            self.assertEqual(norm(rebuilt), norm(full))
            self.assertNotIn("alpha beta protein", rebuilt)

    def test_tab_desc_cell_replaced_on_reuse(self) -> None:
        """Tab tables: a description is one cell, replaced by position on reuse,
        including when the cached record had an empty description."""
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "cache.jsonl"
            recs = read_fasta(TINY)
            g1 = Path(td) / "g1.fa"
            write_fasta(g1, [FastaRec(r.name, "", r.seq) for r in recs])
            first = RecordMemo(
                kind="fasta", argv=_argv("per_query_table.py"), input_path=g1,
                out_dir=Path(td) / "a", cache_path=cache,
            ).run()
            self.assertEqual(first.decision, "SHIP", first.reason)
            g2 = Path(td) / "g2.fa"
            write_fasta(g2, [FastaRec(f"N{i}", f"new desc {i}", r.seq) for i, r in enumerate(recs)])
            second = RecordMemo(
                kind="fasta", argv=_argv("per_query_table.py"), input_path=g2,
                out_dir=Path(td) / "b", cache_path=cache, verify="full",
            ).run()
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertEqual(int(second.extra["n_misses"]), 0)
            rebuilt = (Path(td) / "b" / "reassembled.out").read_text()
            full = (Path(td) / "b" / "full.out").read_text()
            self.assertEqual(body_lines(rebuilt), body_lines(full))

    def test_right_numeric_byte_match_on_rename(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "cache.jsonl"
            bare = Path(td) / "bare.fa"
            write_fasta(bare, [FastaRec(r.name, "", r.seq) for r in read_fasta(TINY)])
            first = RecordMemo(
                kind="fasta",
                argv=_argv("right_numeric.py"),
                input_path=bare,
                out_dir=Path(td) / "a",
                cache_path=cache,
            ).run()
            self.assertEqual(first.decision, "SHIP", first.reason)
            contract = json.loads((cache.parent / (cache.name + ".contract.json")).read_text())
            self.assertFalse(contract["match_ws"], contract.get("layout"))
            self.assertEqual(contract["layout"]["scope"], "fixed")
            self.assertTrue(
                all(c["width_rule"] == "fixed_min" for c in contract["layout"]["columns"]),
                contract.get("layout"),
            )
            aligns = [c["align"] for c in contract["layout"]["columns"]]
            self.assertIn("right", aligns, contract.get("layout"))

            other = Path(td) / "long.fa"
            recs = [FastaRec(f"LONGNAME{i:04d}", "", r.seq) for i, r in enumerate(read_fasta(TINY))]
            write_fasta(other, recs)
            second = RecordMemo(
                kind="fasta",
                argv=_argv("right_numeric.py"),
                input_path=other,
                out_dir=Path(td) / "b",
                cache_path=cache,
                verify="full",
            ).run()
            self.assertEqual(second.decision, "SHIP", second.reason)
            rebuilt = (Path(td) / "b" / "reassembled.out").read_text()
            full = (Path(td) / "b" / "full.out").read_text()
            self.assertEqual(body_lines(rebuilt), body_lines(full))

    def test_per_group_width_scope(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="fasta",
                argv=_argv("per_group_width.py"),
                input_path=TINY,
                out_dir=Path(td),
                verify="full",
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            contract = json.loads((Path(td) / "cache.jsonl.contract.json").read_text())
            self.assertFalse(contract["match_ws"], contract.get("layout"))
            self.assertEqual(contract["layout"]["scope"], "per_query")
            rebuilt = (Path(td) / "reassembled.out").read_text()
            full = (Path(td) / "full.out").read_text()
            self.assertEqual(body_lines(rebuilt), body_lines(full))

    def test_irregular_layout_falls_back_to_ws_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="fasta",
                argv=_argv("irregular_layout.py"),
                input_path=TINY,
                out_dir=Path(td),
                verify="full",
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            contract = json.loads((Path(td) / "cache.jsonl.contract.json").read_text())
            self.assertTrue(contract["match_ws"], contract.get("layout"))
            self.assertFalse(contract.get("layout", {}).get("pinned", True), contract.get("layout"))
            self.assertTrue(contract.get("layout", {}).get("reason"), contract.get("layout"))

    def test_cli_fasta_kind(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            code = acts_main(
                [
                    "run",
                    "--kind",
                    "fasta",
                    "--input",
                    str(TINY),
                    "--out",
                    td,
                    "--cache",
                    str(Path(td) / "c.jsonl"),
                    "--",
                    *_argv("per_query_table.py"),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("SHIP", (Path(td) / "decision.txt").read_text())


def _synth_fa(n: int) -> list[FastaRec]:
    return [FastaRec(f"q{i}", "", "ACGT" * ((i % 5) + 2)) for i in range(n)]


class RareQueryWidenTests(unittest.TestCase):
    """A per-query pad that shows up only on a rare record.

    Without that record the probe cannot refute fixed_min, per-query max,
    or per-file max, so the layout stays unpinned and MATCH is whitespace.
    With one such record the target column is per-query and the rebuild is
    byte MATCH. Both contracts rebuild the full file, including the rare
    record, under the contract's own MATCH.
    """

    def _recs(self, rare: bool) -> list[FastaRec]:
        recs = [
            FastaRec("alpha", "", "ACGTACGTACGT"),
            FastaRec("beta", "", "GGGGTTTTAAAA"),
            FastaRec("gamma", "", "CCCCAAAAGGGG"),
        ]
        if rare:
            recs.append(FastaRec("rare", "", "ACGTRareRAREWIDEN"))
        return recs

    def test_probe_without_rare_record_unpins_and_whitespace_matches(self) -> None:
        argv = _argv("rare_query_widen.py")
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cache = td / "cache.jsonl"
            contract = infer_table_contract(
                argv, self._recs(False), td / "probe", probe_n=8, subset_mode="singleton"
            )
            self.assertFalse(contract.layout.get("pinned"), contract.layout.get("reason"))
            self.assertTrue(contract.match_ws)
            self.assertIn("unique", contract.layout.get("reason", ""))
            contract.save(cache.with_name(cache.name + ".contract.json"))
            normal = td / "normal.fa"
            write_fasta(normal, self._recs(False))
            first = RecordMemo(
                kind="fasta", argv=argv, input_path=normal,
                out_dir=td / "a", cache_path=cache, verify="full", probe_n=8,
            ).run()
            self.assertEqual(first.decision, "SHIP", first.reason)
            renamed = [
                FastaRec(f"N{i}", "", rec.seq) for i, rec in enumerate(self._recs(False))
            ]
            renamed.append(FastaRec("rare2", "", "ACGTRareRAREWIDEN"))
            full = td / "full.fa"
            write_fasta(full, renamed)
            second = RecordMemo(
                kind="fasta", argv=argv, input_path=full,
                out_dir=td / "b", cache_path=cache, verify="full", probe_n=8,
            ).run()
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertGreater(int(second.extra["n_hits"]), 0)
            self.assertGreater(int(second.extra["n_misses"]), 0)
            norm = lambda t: [" ".join(ln.split()) for ln in body_lines(t)]
            self.assertEqual(
                norm((td / "b" / "reassembled.out").read_text()),
                norm((td / "b" / "full.out").read_text()),
            )

    def test_probe_with_rare_record_pins_per_query_and_byte_matches(self) -> None:
        argv = _argv("rare_query_widen.py")
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cache = td / "cache.jsonl"
            src = td / "src.fa"
            write_fasta(src, self._recs(True))
            first = RecordMemo(
                kind="fasta", argv=argv, input_path=src,
                out_dir=td / "a", cache_path=cache, verify="full", probe_n=8,
            ).run()
            self.assertEqual(first.decision, "SHIP", first.reason)
            contract = json.loads((cache.with_name(cache.name + ".contract.json")).read_text())
            self.assertTrue(contract["layout"]["pinned"], contract["layout"].get("reason"))
            self.assertEqual(contract["layout"]["scope"], "per_query")
            self.assertEqual(contract["layout"]["columns"][0]["width_rule"], "max_value")
            self.assertFalse(contract["match_ws"])
            renamed = [FastaRec(f"N{i}", "", rec.seq) for i, rec in enumerate(self._recs(True))]
            other = td / "renamed.fa"
            write_fasta(other, renamed)
            second = RecordMemo(
                kind="fasta", argv=argv, input_path=other,
                out_dir=td / "b", cache_path=cache, verify="full", probe_n=8,
            ).run()
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertEqual(int(second.extra["n_misses"]), 0)
            self.assertEqual(
                body_lines((td / "b" / "reassembled.out").read_text()),
                body_lines((td / "b" / "full.out").read_text()),
            )


class PreflightStockTests(unittest.TestCase):
    def test_unpinned_whitespace_passes_and_wrong_pin_stops(self) -> None:
        pinned = TableContract(
            kind="fasta", argv=["tool"], query_col=0, desc_cols=[], produced_cols=[1],
            delim="ws", match="order", n_cols=2, match_ws=False,
            layout={
                "delim": "ws", "scope": "fixed", "pinned": True,
                "columns": [{"align": "left", "width_rule": "fixed_min", "min_width": 8}],
            },
        )
        stock = "name         1\n"
        bad = preflight_stock_outputs(pinned, [("toy.tbl", stock)])
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["files"][0]["n_mismatch"], 1)
        open_layout = TableContract(
            kind="fasta", argv=["tool"], query_col=0, desc_cols=[], produced_cols=[1],
            delim="ws", match="order", n_cols=2, match_ws=True,
            layout={"delim": "ws", "scope": "fixed", "pinned": False, "columns": [], "reason": "not unique"},
        )
        good = preflight_stock_outputs(open_layout, [("toy.tbl", stock)])
        self.assertTrue(good["ok"], good["reason"])
        self.assertEqual(good["files"][0]["n_mismatch"], 0)
        empty = preflight_stock_outputs(open_layout, [])
        self.assertTrue(empty["ok"])
        self.assertIn("no stock", empty["reason"])


class BatchedSubsetFastaTests(unittest.TestCase):
    def test_batched_is_default_and_independent_of_probe_n(self) -> None:
        argv = _argv("per_query_table.py")
        recs = _synth_fa(80)
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            a = infer_table_contract(argv, recs, work / "a", probe_n=20)
            b = infer_table_contract(argv, recs, work / "b", probe_n=40)
            self.assertEqual(a.subset_mode, "batched")
            self.assertEqual(a.tool_calls, b.tool_calls)
            self.assertEqual(a.tool_calls, 4 + 2 + 4 + 8)
            self.assertEqual(a.tool_call_sizes[:4], [20, 20, 20, 20])
            self.assertEqual(sorted(a.tool_call_sizes[4:6]), [10, 10])
            self.assertEqual(sorted(a.tool_call_sizes[6:10]), [5, 5, 5, 5])
            self.assertEqual(a.tool_call_sizes[10:], [1] * 8)

    def test_singleton_tool_calls_grow_with_probe_n(self) -> None:
        argv = _argv("per_query_table.py")
        recs = _synth_fa(80)
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            small = infer_table_contract(
                argv, recs, work / "s", probe_n=12, subset_mode="singleton"
            )
            big = infer_table_contract(
                argv, recs, work / "b", probe_n=24, subset_mode="singleton"
            )
            self.assertEqual(small.subset_mode, "singleton")
            self.assertEqual(big.tool_calls - small.tool_calls, 12)

    def test_batched_and_singleton_both_refuse_global(self) -> None:
        argv = _argv("global_evalue.py")
        recs = read_fasta(TINY)
        for mode in ("batched", "singleton"):
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(InferError) as ctx:
                    infer_table_contract(argv, recs, Path(td), subset_mode=mode)
                self.assertEqual(ctx.exception.decision, "REFUSE_GLOBAL")
                self.assertGreater(ctx.exception.tool_calls, 0)


if __name__ == "__main__":
    unittest.main()


class ReassembleCellsWidthTests(unittest.TestCase):
    def test_row_keeps_own_width_when_contract_grows(self) -> None:
        """Guard (2026-10-03 hmmscan repro): late-key probes raised n_cols, and every
        rebuilt row was padded to it, adding trailing spaces under byte MATCH."""
        from acts.infer_fasta import TableContract, reassemble_cells

        contract = TableContract(
            kind="fasta", argv=[], query_col=2, desc_cols=[], produced_cols=[0, 1, 3, 4],
            delim="ws", match="order", n_cols=8,
        )
        payload = {"rows": [{"raw": "", "name": "old", "produced": {"0": "M", "1": "PF1", "3": "1e-5", "4": "word"}, "n": 5}]}
        rec = FastaRec("new", "", "ACGT")
        cells = reassemble_cells(rec, payload, contract)
        self.assertEqual(cells, [["M", "PF1", "new", "1e-5", "word"]])
