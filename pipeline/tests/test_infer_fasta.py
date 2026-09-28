from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.fasta import FastaRec, read_fasta, write_fasta
from acts.infer_fasta import InferError, infer_table_contract
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
            self.assertTrue(contract["pad_widths"] or contract["match_ws"], contract)
            self.assertEqual(contract["empty_desc"], "-")

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
