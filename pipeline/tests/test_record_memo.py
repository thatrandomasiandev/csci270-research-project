from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.infer import star_identity_risk
from acts.records import probe_lines
from acts.strategies.record_memo import RecordMemo
from acts.__main__ import main as acts_main

PIPE = Path(__file__).resolve().parents[1]
FIXTURE = PIPE / "fixtures" / "line_memo" / "input.txt"


class RecordMemoTests(unittest.TestCase):
    def test_fixture_has_enough_dups(self) -> None:
        rep = probe_lines(FIXTURE)
        self.assertEqual(rep.n, 8)
        self.assertEqual(rep.n_unique, 4)
        self.assertLess(rep.unique_frac, 0.95)
        self.assertAlmostEqual(rep.max_speedup_if_pure, 2.0)

    def test_cat_ships_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            rec = RecordMemo(
                kind="lines",
                argv=["cat"],
                input_path=FIXTURE,
                out_dir=out,
            ).run()
            self.assertEqual(rec.decision, "SHIP")
            self.assertEqual(
                (out / "reassembled.out").read_bytes(),
                (out / "full.out").read_bytes(),
            )
            self.assertEqual(
                (out / "reassembled.out").read_text(),
                FIXTURE.read_text(),
            )

    def test_rare_dups_refuse(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "uniq.txt"
            inp.write_text("a\nb\nc\nd\n")
            rec = RecordMemo(
                kind="lines",
                argv=["cat"],
                input_path=inp,
                out_dir=Path(td) / "out",
            ).run()
            self.assertEqual(rec.decision, "REFUSE_DUPS_RARE")

    def test_star_argv_refuses_identity(self) -> None:
        risk = star_identity_risk()
        self.assertFalse(risk.can_be_byte_identical)
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="fastq_pe",
                argv=["STAR", "--runThreadN", "1"],
                r1=FIXTURE,
                r2=FIXTURE,
                out_dir=Path(td),
            ).run()
            self.assertEqual(rec.decision, "REFUSE_IDENTITY")
            self.assertIn("QNAME", rec.reason)

    def test_cli_cat_ship(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            code = acts_main(
                [
                    "run",
                    "--strategy",
                    "record_memo",
                    "--kind",
                    "lines",
                    "--input",
                    str(FIXTURE),
                    "--out",
                    td,
                    "--",
                    "cat",
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("SHIP", (Path(td) / "decision.txt").read_text())

    def test_incremental_second_file_reuses_cache(self) -> None:
        a = PIPE / "fixtures" / "line_memo" / "run_a.txt"
        b = PIPE / "fixtures" / "line_memo" / "run_b.txt"
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "cache.jsonl"
            first = RecordMemo(
                kind="lines",
                argv=["cat"],
                input_path=a,
                out_dir=Path(td) / "a",
                cache_path=cache,
            ).run()
            self.assertEqual(first.decision, "SHIP")
            second = RecordMemo(
                kind="lines",
                argv=["cat"],
                input_path=b,
                out_dir=Path(td) / "b",
                cache_path=cache,
            ).run()
            self.assertEqual(second.decision, "SHIP")
            self.assertEqual(second.extra["mode"], "incremental")
            self.assertEqual(int(second.extra["n_misses"]), 2)
            self.assertEqual(int(second.extra["n_hits"]), 2)
            self.assertEqual(
                (Path(td) / "b" / "reassembled.out").read_text(),
                b.read_text(),
            )

    def test_all_unique_second_file_still_pays_if_no_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.txt"
            b = Path(td) / "b.txt"
            a.write_text("a\nb\na\n")
            b.write_text("x\ny\nz\nw\n")
            cache = Path(td) / "cache.jsonl"
            self.assertEqual(
                RecordMemo(
                    kind="lines",
                    argv=["cat"],
                    input_path=a,
                    out_dir=Path(td) / "oa",
                    cache_path=cache,
                ).run().decision,
                "SHIP",
            )
            rec = RecordMemo(
                kind="lines",
                argv=["cat"],
                input_path=b,
                out_dir=Path(td) / "ob",
                cache_path=cache,
            ).run()
            self.assertEqual(rec.decision, "REFUSE_DUPS_RARE")
            self.assertEqual(rec.extra["mode"], "incremental")

    def test_cli_star_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            code = acts_main(["run", "--out", td, "--", "STAR", "--genomeDir", "x"])
            self.assertEqual(code, 1)
            self.assertIn("REFUSE_IDENTITY", (Path(td) / "decision.txt").read_text())


if __name__ == "__main__":
    unittest.main()
