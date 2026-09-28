from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.infer_linetable import header_and_body, infer_linetable_contract
from acts.strategies.record_memo import RecordMemo
from acts.__main__ import main as acts_main

PIPE = Path(__file__).resolve().parents[1]
FIX = PIPE / "fixtures" / "linetable_memo"
TINY = FIX / "tiny.smi"
PY = sys.executable


def _argv(script: str) -> list[str]:
    return [PY, str(FIX / script)]


class InferLinetableFixtureTests(unittest.TestCase):
    def test_per_line_ships_order_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="linetable",
                argv=_argv("per_line_csv.py"),
                input_path=TINY,
                out_dir=Path(td),
                verify="full",
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            contract = json.loads((Path(td) / "cache.jsonl.contract.json").read_text())
            self.assertEqual(contract["match"], "order")
            self.assertEqual(contract["correspondence"], "echo")
            self.assertEqual(contract["query_col"], 0)
            rebuilt = (Path(td) / "reassembled.out").read_text()
            full = (Path(td) / "full.out").read_text()
            self.assertEqual(header_and_body(rebuilt)[1], header_and_body(full)[1])

    def test_sorted_csv_multiset_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="linetable",
                argv=_argv("sorted_csv.py"),
                input_path=TINY,
                out_dir=Path(td),
                verify="full",
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            contract = json.loads((Path(td) / "cache.jsonl.contract.json").read_text())
            self.assertEqual(contract["match"], "multiset")
            self.assertIn("multiset", rec.reason)

    def test_cli_linetable_kind(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            code = acts_main(
                [
                    "run",
                    "--kind",
                    "linetable",
                    "--input",
                    str(TINY),
                    "--out",
                    td,
                    "--cache",
                    str(Path(td) / "c.jsonl"),
                    "--",
                    *_argv("per_line_csv.py"),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("SHIP", (Path(td) / "decision.txt").read_text())


def _synth_lines(n: int) -> list[str]:
    return [f"SMILES{i}" for i in range(n)]


class BatchedSubsetLinetableTests(unittest.TestCase):
    def test_batched_is_default_and_independent_of_probe_n(self) -> None:
        argv = _argv("per_line_csv.py")
        lines = _synth_lines(80)
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            a = infer_linetable_contract(argv, lines, work / "a", probe_n=20)
            b = infer_linetable_contract(argv, lines, work / "b", probe_n=40)
            self.assertEqual(a.subset_mode, "batched")
            self.assertEqual(a.tool_calls, b.tool_calls)
            self.assertEqual(a.tool_calls, 4 + 2 + 4 + 8)
            self.assertEqual(a.tool_call_sizes[:4], [20, 20, 20, 20])
            self.assertEqual(sorted(a.tool_call_sizes[4:6]), [10, 10])
            self.assertEqual(sorted(a.tool_call_sizes[6:10]), [5, 5, 5, 5])
            self.assertEqual(a.tool_call_sizes[10:], [1] * 8)

    def test_singleton_tool_calls_grow_with_probe_n(self) -> None:
        argv = _argv("per_line_csv.py")
        lines = _synth_lines(80)
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            small = infer_linetable_contract(
                argv, lines, work / "s", probe_n=12, subset_mode="singleton"
            )
            big = infer_linetable_contract(
                argv, lines, work / "b", probe_n=24, subset_mode="singleton"
            )
            self.assertEqual(small.subset_mode, "singleton")
            self.assertEqual(big.tool_calls - small.tool_calls, 12)


if __name__ == "__main__":
    unittest.main()
