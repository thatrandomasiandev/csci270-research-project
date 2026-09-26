from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.cache import RecordCache
from acts.infer_vcf import infer_contract
from acts.strategies.record_memo import RecordMemo
from acts.vcf import bodies_equal, body_lines
from acts.vcf_memo import cached_annotate, read_vcf_parts
from acts.__main__ import main as acts_main

PIPE = Path(__file__).resolve().parents[1]
FIX = PIPE / "fixtures" / "vcf_memo"
TINY = FIX / "tiny.vcf"
PY = sys.executable


def _argv(script: str) -> list[str]:
    return [PY, str(FIX / script)]


class InferVcfFixtureTests(unittest.TestCase):
    def test_1to1_ships(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="vcf",
                argv=_argv("annotate_1to1.py"),
                input_path=TINY,
                out_dir=Path(td),
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            self.assertTrue(
                bodies_equal(
                    (Path(td) / "reassembled.out").read_text(),
                    (Path(td) / "full.out").read_text(),
                )
            )
            contract = json.loads((Path(td) / "cache.jsonl.contract.json").read_text())
            self.assertEqual(contract["cache_key_fields"], ["CHROM", "POS", "REF", "ALT"])
            self.assertEqual(contract["info_roles"].get("ANN"), "produced")
            self.assertNotIn("ID", contract["widen_history"])

    def test_neighbors_refuses_shuffle(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="vcf",
                argv=_argv("annotate_neighbors.py"),
                input_path=TINY,
                out_dir=Path(td),
            ).run()
            self.assertEqual(rec.decision, "REFUSE_NEIGHBORS", rec.reason)

    def test_uses_id_widens_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="vcf",
                argv=_argv("annotate_uses_id.py"),
                input_path=TINY,
                out_dir=Path(td),
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            self.assertIn("ID", rec.extra.get("widen", "").split(",") + rec.extra.get("cache_key_fields", "").split(","))
            contract = json.loads((Path(td) / "cache.jsonl.contract.json").read_text())
            self.assertIn("ID", contract["cache_key_fields"])
            self.assertEqual(contract["info_roles"].get("ANN"), "produced")

    def test_rewrites_filter_is_produced(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="vcf",
                argv=_argv("annotate_rewrites_filter.py"),
                input_path=TINY,
                out_dir=Path(td),
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            contract = json.loads((Path(td) / "cache.jsonl.contract.json").read_text())
            self.assertEqual(contract["column_roles"].get("FILTER"), "produced")
            rebuilt = (Path(td) / "reassembled.out").read_text()
            for ln in body_lines(rebuilt):
                parts = ln.split("\t")
                self.assertEqual(parts[6], "ANNOTATED")
            # A second file with a different FILTER must still emit ANNOTATED.
            other = Path(td) / "other.vcf"
            other.write_text(
                TINY.read_text().replace("\tPASS\t", "\tLOWQUAL\t")
            )
            rec2 = RecordMemo(
                kind="vcf",
                argv=_argv("annotate_rewrites_filter.py"),
                input_path=other,
                out_dir=Path(td) / "second",
                cache_path=Path(td) / "cache.jsonl",
            ).run()
            self.assertEqual(rec2.decision, "SHIP", rec2.reason)
            for ln in body_lines((Path(td) / "second" / "reassembled.out").read_text()):
                self.assertEqual(ln.split("\t")[6], "ANNOTATED")
            self.assertNotIn("LOWQUAL", (Path(td) / "second" / "reassembled.out").read_text())

    def test_cli_vcf_kind(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            code = acts_main(
                [
                    "run",
                    "--kind",
                    "vcf",
                    "--input",
                    str(TINY),
                    "--out",
                    td,
                    "--cache",
                    str(Path(td) / "c.jsonl"),
                    "--",
                    *_argv("annotate_1to1.py"),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("SHIP", (Path(td) / "decision.txt").read_text())


@unittest.skipUnless(shutil.which("bcftools"), "bcftools not on PATH")
class InferVcfBcftoolsTests(unittest.TestCase):
    def test_fill_tags_detects_genotype_dependence(self) -> None:
        gt = FIX / "with_gt.vcf"
        argv = ["bcftools", "+fill-tags", "{input}", "-Ov", "--", "-t", "AF,AC"]
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            header, body = read_vcf_parts(gt)
            contract = infer_contract(argv, header, body, work / "probe")
            self.assertEqual(contract.decision, "OK", contract.reason)
            self.assertIn("SAMPLES", contract.cache_key_fields)
            cache = RecordCache(work / "cache.jsonl", argv=argv, kind="vcf")
            text, stats = cached_annotate(header, body, cache, contract, argv, work / "memo")
            stock = subprocess.run(
                ["bcftools", "+fill-tags", str(gt), "-Ov", "--", "-t", "AF,AC"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertTrue(bodies_equal(text, stock))
            self.assertIn("AF", contract.info_roles)
            self.assertIn(contract.info_roles["AF"], {"produced", "depends"})

    def test_annotate_ships_with_zero_new_code(self) -> None:
        if not (shutil.which("bgzip") and shutil.which("tabix")):
            self.skipTest("bgzip/tabix missing")
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            table = work / "annot.tsv"
            table.write_text(
                "22\t16050075\tA\tG\tfrom_table\n"
                "22\t16050115\tG\tT\tfrom_table\n"
                "22\t16050200\tC\tA\tfrom_table\n"
            )
            gz = work / "annot.tsv.gz"
            with gz.open("wb") as fh:
                subprocess.run(["bgzip", "-c", str(table)], check=True, stdout=fh)
            subprocess.run(["tabix", "-s", "1", "-b", "2", "-e", "2", str(gz)], check=True)
            hdr = work / "annot.hdr"
            hdr.write_text('##INFO=<ID=NOTE,Number=1,Type=String,Description="table">\n')
            argv = [
                "bcftools",
                "annotate",
                "-a",
                str(gz),
                "-h",
                str(hdr),
                "-c",
                "CHROM,POS,REF,ALT,INFO/NOTE",
                "-Ov",
                "{input}",
            ]
            rec = RecordMemo(
                kind="vcf",
                argv=argv,
                input_path=FIX / "with_gt.vcf",
                out_dir=work / "out",
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            contract = json.loads((work / "out" / "cache.jsonl.contract.json").read_text())
            self.assertEqual(contract["info_roles"].get("NOTE"), "produced")
            self.assertEqual(contract["cache_key_fields"], ["CHROM", "POS", "REF", "ALT"])


if __name__ == "__main__":
    unittest.main()
