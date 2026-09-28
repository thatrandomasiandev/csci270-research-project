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
from acts.infer_vcf import InferError, batched_index_groups, infer_contract
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
                verify="full",
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
            self.assertEqual(contract["subset_mode"], "batched")
            self.assertGreater(contract["tool_calls"], 0)

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

    def test_global_rank_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = RecordMemo(
                kind="vcf",
                argv=_argv("annotate_global.py"),
                input_path=TINY,
                out_dir=Path(td),
            ).run()
            self.assertEqual(rec.decision, "REFUSE_GLOBAL", rec.reason)

    def test_rare_key_is_late_probed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            first = RecordMemo(
                kind="vcf",
                argv=_argv("annotate_rare_key.py"),
                input_path=TINY,
                out_dir=Path(td) / "a",
                cache_path=Path(td) / "cache.jsonl",
            ).run()
            self.assertEqual(first.decision, "SHIP", first.reason)
            c1 = json.loads((Path(td) / "cache.jsonl.contract.json").read_text())
            self.assertNotIn("RARE", c1.get("info_roles", {}))
            rare = Path(td) / "with_rare.vcf"
            rare.write_text(TINY.read_text() + "22\t99999999\t.\tA\tG\t.\tPASS\t.\n")
            second = RecordMemo(
                kind="vcf",
                argv=_argv("annotate_rare_key.py"),
                input_path=rare,
                out_dir=Path(td) / "b",
                cache_path=Path(td) / "cache.jsonl",
            ).run()
            self.assertEqual(second.decision, "SHIP", second.reason)
            c2 = json.loads((Path(td) / "cache.jsonl.contract.json").read_text())
            self.assertEqual(c2["info_roles"].get("RARE"), "produced")
            self.assertIn("RARE", c2.get("late_key_probes", []))
            rebuilt = (Path(td) / "b" / "reassembled.out").read_text()
            rare_lines = [ln for ln in body_lines(rebuilt) if "\t99999999\t" in ln]
            self.assertEqual(len(rare_lines), 1)
            self.assertIn("RARE=1", rare_lines[0])


def _synth_vcf(n: int) -> tuple[list[str], list[str]]:
    header = [
        "##fileformat=VCFv4.2",
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
    ]
    body = [f"22\t{1000 + i}\t.\tA\tG\t.\tPASS\t." for i in range(n)]
    return header, body


class BatchedSubsetVcfTests(unittest.TestCase):
    def test_index_groups_cover_and_are_fixed(self) -> None:
        groups = batched_index_groups(40)
        self.assertEqual(len(groups), 2 + 4 + 8)
        halves, quarters = groups[:2], groups[2:6]
        self.assertEqual(sorted(i for part in halves for i in part), list(range(40)))
        self.assertEqual(sorted(i for part in quarters for i in part), list(range(40)))
        self.assertEqual(batched_index_groups(40), groups)

    def test_batched_is_default_and_independent_of_probe_n(self) -> None:
        argv = _argv("annotate_1to1.py")
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            header, body = _synth_vcf(80)
            a = infer_contract(argv, header, body, work / "a", probe_n=20)
            b = infer_contract(argv, header, body, work / "b", probe_n=40)
            self.assertEqual(a.subset_mode, "batched")
            self.assertEqual(b.subset_mode, "batched")
            self.assertEqual(a.tool_calls, b.tool_calls)
            self.assertEqual(a.tool_calls, 4 + 2 + 4 + 8)

    def test_singleton_tool_calls_grow_with_probe_n(self) -> None:
        argv = _argv("annotate_1to1.py")
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            header, body = _synth_vcf(80)
            small = infer_contract(
                argv, header, body, work / "s", probe_n=12, subset_mode="singleton"
            )
            big = infer_contract(
                argv, header, body, work / "b", probe_n=24, subset_mode="singleton"
            )
            self.assertEqual(small.subset_mode, "singleton")
            self.assertGreater(big.tool_calls, small.tool_calls)
            self.assertEqual(big.tool_calls - small.tool_calls, 12)

    def test_batched_and_singleton_both_refuse_global(self) -> None:
        argv = _argv("annotate_global.py")
        header, body = read_vcf_parts(TINY)
        for mode in ("batched", "singleton"):
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(InferError) as ctx:
                    infer_contract(
                        argv, header, body, Path(td), subset_mode=mode, singleton_workers=1
                    )
                self.assertEqual(ctx.exception.decision, "REFUSE_GLOBAL")
                self.assertGreater(ctx.exception.tool_calls, 0)


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
