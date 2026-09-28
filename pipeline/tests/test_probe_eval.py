from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures" / "probe_eval"))

from acts.strategies.record_memo import RecordMemo
from suite import is_live, run_tool, write_fasta, write_vcf

PIPE = Path(__file__).resolve().parents[1]
TOOL = PIPE / "fixtures" / "probe_eval" / "tool.py"
PY = sys.executable


class ProbeEvalSuiteTests(unittest.TestCase):
    def test_f6_always_live(self) -> None:
        self.assertTrue(is_live("F6", "vcf", 0, 0.001))
        self.assertFalse(is_live("C1", "vcf", 0, 1.0))

    def test_live_is_deterministic(self) -> None:
        a = [is_live("F4", "vcf", i, 0.1) for i in range(200)]
        b = [is_live("F4", "vcf", i, 0.1) for i in range(200)]
        self.assertEqual(a, b)
        self.assertTrue(any(a))
        self.assertTrue(any(not x for x in a))

    def test_c1_ships(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            inp = write_vcf(Path(td) / "in.vcf", list(range(30)))
            rec = RecordMemo(
                kind="vcf",
                argv=[PY, str(TOOL), "vcf", "C1", "0.0", "{input}"],
                input_path=inp,
                out_dir=Path(td) / "out",
                probe_n=20,
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)

    def test_f2_full_frequency_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            inp = write_vcf(Path(td) / "in.vcf", list(range(30)))
            rec = RecordMemo(
                kind="vcf",
                argv=[PY, str(TOOL), "vcf", "F2", "1.0", "{input}"],
                input_path=inp,
                out_dir=Path(td) / "out",
                probe_n=20,
            ).run()
            self.assertIn(rec.decision, {"REFUSE_NEIGHBORS", "REFUSE_GLOBAL"}, rec.reason)

    def test_c4_fasta_ships(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            inp = write_fasta(Path(td) / "in.fa", list(range(20)))
            rec = RecordMemo(
                kind="fasta",
                argv=[PY, str(TOOL), "fasta", "C4", "0.0", "{input}"],
                input_path=inp,
                out_dir=Path(td) / "out",
                probe_n=12,
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)

    def test_tool_emits(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            inp = write_vcf(Path(td) / "in.vcf", [0, 1, 2])
            text = run_tool("vcf", "C1", 0.0, inp)
            self.assertIn("ANN=", text)
            self.assertIn("#CHROM", text)

    def test_input2_same_length_as_input1(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from run_probe_eval import N_REC, write_inputs  # noqa: WPS433

        with tempfile.TemporaryDirectory() as td:
            paths = write_inputs(Path(td), "vcf", "F3")
            n1 = sum(1 for ln in paths["in1"].read_text().splitlines() if ln and not ln.startswith("#"))
            n2 = sum(1 for ln in paths["in2"].read_text().splitlines() if ln and not ln.startswith("#"))
            n3 = sum(1 for ln in paths["in3"].read_text().splitlines() if ln and not ln.startswith("#"))
            self.assertEqual(n1, N_REC)
            self.assertEqual(n2, N_REC)
            self.assertEqual(n3, 100)
