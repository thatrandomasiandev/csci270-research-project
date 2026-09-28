from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.infer_files import InferError, infer_files_contract, list_records
from acts.strategies.record_memo import RecordMemo
from acts.__main__ import main as acts_main

PIPE = Path(__file__).resolve().parents[1]
FIX = PIPE / "fixtures" / "files_memo"
TINY = FIX / "tiny"
PY = sys.executable


def _argv(script: str) -> list[str]:
    return [PY, str(FIX / script)]


class InferFilesFixtureTests(unittest.TestCase):
    def test_per_file_ships_and_renames_hit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "cache.jsonl"
            rec = RecordMemo(
                kind="files",
                argv=_argv("per_file.py"),
                input_path=TINY,
                out_dir=Path(td) / "a",
                cache_path=cache,
                verify="full",
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            contract = json.loads((cache.parent / (cache.name + ".contract.json")).read_text())
            self.assertEqual(contract["cache_key_fields"], ["sha256"])
            self.assertEqual(contract["stem_rule"], "stem")
            self.assertIn(".tsv", contract["suffixes"])

            renamed = Path(td) / "renamed"
            renamed.mkdir()
            for i, src in enumerate(sorted(TINY.iterdir())):
                if src.is_file() and not src.name.startswith("."):
                    shutil.copy2(src, renamed / f"R{i}{src.suffix}")
            second = RecordMemo(
                kind="files",
                argv=_argv("per_file.py"),
                input_path=renamed,
                out_dir=Path(td) / "b",
                cache_path=cache,
                verify="full",
            ).run()
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertEqual(int(second.extra["n_misses"]), 0)
            self.assertEqual(int(second.extra["n_hits"]), 8)
            out_names = {p.name for p in (Path(td) / "b" / "reassembled").iterdir() if p.is_file()}
            self.assertTrue(any(n.startswith("R0") for n in out_names))

    def test_uses_name_widens_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "cache.jsonl"
            rec = RecordMemo(
                kind="files",
                argv=_argv("uses_name.py"),
                input_path=TINY,
                out_dir=Path(td) / "a",
                cache_path=cache,
                verify="full",
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            contract = json.loads((cache.parent / (cache.name + ".contract.json")).read_text())
            self.assertIn("name", contract["cache_key_fields"])
            self.assertIn("name", contract["widen_history"])

            renamed = Path(td) / "renamed"
            renamed.mkdir()
            for i, src in enumerate(sorted(TINY.iterdir())):
                if src.is_file() and not src.name.startswith("."):
                    shutil.copy2(src, renamed / f"R{i}{src.suffix}")
            second = RecordMemo(
                kind="files",
                argv=_argv("uses_name.py"),
                input_path=renamed,
                out_dir=Path(td) / "b",
                cache_path=cache,
            ).run()
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertEqual(int(second.extra["n_hits"]), 0)
            self.assertEqual(int(second.extra["n_misses"]), 8)

    def test_reads_all_refuses_global(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="files",
                argv=_argv("reads_all.py"),
                input_path=TINY,
                out_dir=Path(td),
            ).run()
            self.assertEqual(rec.decision, "REFUSE_GLOBAL", rec.reason)

    def test_cli_files_kind(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            code = acts_main(
                [
                    "run",
                    "--kind",
                    "files",
                    "--input",
                    str(TINY),
                    "--out",
                    td,
                    "--cache",
                    str(Path(td) / "c.jsonl"),
                    "--",
                    *_argv("per_file.py"),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("SHIP", (Path(td) / "decision.txt").read_text())


def _synth_dir(n: int, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (dest / f"f{i}.txt").write_text(f"payload-{i}\n")
    return dest


class BatchedSubsetFilesTests(unittest.TestCase):
    def test_batched_is_default_and_independent_of_probe_n(self) -> None:
        argv = _argv("per_file.py")
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            recs = list_records(_synth_dir(80, base / "in"))
            a = infer_files_contract(argv, recs, base / "a", probe_n=20)
            b = infer_files_contract(argv, recs, base / "b", probe_n=40)
            self.assertEqual(a.subset_mode, "batched")
            self.assertEqual(a.tool_calls, b.tool_calls)
            self.assertEqual(a.tool_calls, 4 + 2 + 4 + 8)
            self.assertEqual(a.tool_call_sizes[:4], [20, 20, 20, 20])
            self.assertEqual(sorted(a.tool_call_sizes[4:6]), [10, 10])
            self.assertEqual(sorted(a.tool_call_sizes[6:10]), [5, 5, 5, 5])
            self.assertEqual(a.tool_call_sizes[10:], [1] * 8)

    def test_singleton_tool_calls_grow_with_probe_n(self) -> None:
        argv = _argv("per_file.py")
        with tempfile.TemporaryDirectory() as td:
            recs = list_records(_synth_dir(80, Path(td) / "in"))
            small = infer_files_contract(
                argv, recs, Path(td) / "s", probe_n=12, subset_mode="singleton"
            )
            big = infer_files_contract(
                argv, recs, Path(td) / "b", probe_n=24, subset_mode="singleton"
            )
            self.assertEqual(small.subset_mode, "singleton")
            self.assertEqual(big.tool_calls - small.tool_calls, 12)

    def test_batched_and_singleton_both_refuse_global(self) -> None:
        argv = _argv("reads_all.py")
        recs = list_records(TINY)
        for mode in ("batched", "singleton"):
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(InferError) as ctx:
                    infer_files_contract(argv, recs, Path(td), subset_mode=mode)
                self.assertEqual(ctx.exception.decision, "REFUSE_GLOBAL")
                self.assertGreater(ctx.exception.tool_calls, 0)


if __name__ == "__main__":
    unittest.main()
