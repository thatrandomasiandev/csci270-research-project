"""Guards for the 38.1→38.2 measurement: churn identity and phase clocks."""

from __future__ import annotations

import gzip
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.reference_formats import (  # noqa: E402
    length_weighted_churn,
    parse_reference,
    parse_reference_text,
    write_entries,
)
from acts.reference_run import ReferenceIncremental  # noqa: E402
from acts.reference_formats import iter_profile_raw, parse_profile_text  # noqa: E402
from scripts.run_reference_reannot import (  # noqa: E402
    check_reannot_output,
    decompress,
    scan_argv,
    select_profile_subset,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "reference_fitter"


def _table(records, entries) -> dict[str, str]:
    lines = ["# record entry evalue"]
    for rec in records:
        for entry in entries:
            if entry.primary not in {"e1", "e3"}:
                continue
            lines.append(f"{rec.key} {entry.primary} {len(entries) * float(rec.description):.6f}")
    return {"out": "\n".join(lines) + "\n"}


class LengthChurnTests(unittest.TestCase):
    def test_changed_and_new_length_over_new_total(self) -> None:
        old = parse_reference_text("e0 1\ne1 2\n")
        new = parse_reference_text("e0 1\ne1 4\ne2 3\n")
        report = length_weighted_churn(old, new)
        self.assertEqual(report["n_unchanged_hash"], 1)
        self.assertEqual(report["n_changed_and_new"], 2)
        self.assertEqual(report["length_new"], 8)
        self.assertEqual(report["length_changed_and_new"], 7)
        self.assertEqual(report["c_length"], 7 / 8)

    def test_identical_release_has_zero_churn(self) -> None:
        entries = parse_reference_text("e0 1\ne1 2\n")
        report = length_weighted_churn(entries, entries)
        self.assertEqual(report["c_length"], 0.0)
        self.assertEqual(report["n_unchanged_hash"], 2)


class DecompressTests(unittest.TestCase):
    def test_gzip_magic_is_two_bytes_not_a_full_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "in.gz"
            payload = b"e0 1\n" * 50
            with gzip.open(src, "wb") as handle:
                handle.write(payload)
            original = Path.read_bytes

            def fail_slurp(self):
                raise AssertionError("decompress slurped the whole file")

            Path.read_bytes = fail_slurp
            try:
                dest = root / "out"
                decompress(src, dest)
            finally:
                Path.read_bytes = original
            self.assertEqual(dest.read_bytes(), payload)


class PhaseClockTests(unittest.TestCase):
    def test_second_release_counts_fresh_entries_and_clocks_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref1 = FIX / "ab.entryline"
            records = FIX / "ab.faa"
            kept = [entry for entry in parse_reference(ref1) if entry.primary in {"e1", "e3"}]
            added = parse_reference_text("e9 5\n")
            ref2 = root / "v2.entryline"
            write_entries(kept + added, ref2)
            cache = root / "cache.sqlite"
            argv = ["law", "{reference}", "{input}", "{output}"]

            def run(ref: Path):
                return ReferenceIncremental(
                    argv=argv,
                    input_path=records,
                    out_dir=root / ref.stem,
                    reference=ref,
                    cache_path=cache,
                    verify="audit",
                    audit_p=0.0,
                    runner=lambda recs, ents: _table(recs, ents),
                ).run()

            first = run(ref1)
            self.assertEqual(first.decision, "SHIP", first.reason)
            self.assertGreater(first.extra["phases"]["probe_wall_s"], 0.0)
            self.assertIn("merge_rescale_s", first.extra["phases"])
            second = run(ref2)
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertEqual(second.extra["n_stable"], 2)
            self.assertEqual(second.extra["n_fresh"], 1)
            self.assertEqual(second.extra["n_partial"], 0)
            self.assertEqual(second.extra["phases"]["probe_wall_s"], 0.0)
            self.assertIn("merge_rescale_s", second.extra["phases"])
            self.assertIn("diff_s", second.extra["phases"])

    def test_prep_and_tool_are_separate_clocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool = root / "tool.py"
            tool.write_text(
                "import sys\n"
                "from pathlib import Path\n"
                "ref, rec, dest = map(Path, sys.argv[1:4])\n"
                "if not Path(str(ref) + '.idx').is_file():\n"
                "    raise SystemExit(2)\n"
                "rows = []\n"
                "for record in rec.read_text().splitlines():\n"
                "    if not record.startswith('>'):\n"
                "        continue\n"
                "    name = record[1:].split()[0]\n"
                "    for line in ref.read_text().splitlines():\n"
                "        if line.strip():\n"
                "            rows.append(f'{name} {line.split()[0]} 1.000000')\n"
                "dest.write_text('# record entry value\\n' + '\\n'.join(rows) + '\\n')\n"
            )
            prep = root / "prep.py"
            prep.write_text(
                "import sys\nfrom pathlib import Path\n"
                "Path(sys.argv[1] + '.idx').write_text('1\\n')\n"
            )
            rec = ReferenceIncremental(
                argv=[sys.executable, str(tool), "{reference}", "{input}", "{output}"],
                input_path=FIX / "c.faa",
                out_dir=root / "out",
                reference=FIX / "c.entryline",
                prep=f"{sys.executable} {prep} {{reference}}",
                cache_path=root / "cache.sqlite",
                verify="audit",
                audit_p=0.0,
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            phases = rec.extra["phases"]
            self.assertGreater(phases["prep_s"], 0.0)
            self.assertGreater(phases["tool_s"], 0.0)
            self.assertGreater(phases["probe_wall_s"], 0.0)
            probe = rec.extra["probe_phases"]
            self.assertGreater(probe["prep_s"], 0.0)
            self.assertGreater(probe["tool_s"], 0.0)
            self.assertNotIn("parse_s", probe)
            self.assertIn("parse_s", phases)


class SmokeSubsetTests(unittest.TestCase):
    def test_measurement_argv_stays_32_cpus(self) -> None:
        argv = scan_argv(32)
        self.assertEqual(argv[argv.index("--cpu") + 1], "32")
        self.assertIn("--cut_ga", argv)
        self.assertIn("{reference}", argv)

    def test_smoke_output_directory_is_separate(self) -> None:
        check_reannot_output(Path("/tmp/reference_reannot_smoke/out.json"), True)
        with self.assertRaises(SystemExit):
            check_reannot_output(Path("/tmp/reference_reannot/out.json"), True)
        with self.assertRaises(SystemExit):
            check_reannot_output(Path("/tmp/reference_reannot_smoke/out.json"), False)

    def test_profile_subset_keeps_changed_and_unchanged(self) -> None:
        def hmm(name: str, acc: str) -> str:
            return f"HMMER3/f\nNAME {name}\nACC {acc}\nLENG 1\n//\n"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "old.hmm"
            new = root / "new.hmm"
            old.write_text(hmm("alpha", "PF00001.1") + hmm("beta", "PF00002.1") + hmm("gone", "PF00003.1"))
            new.write_text(
                hmm("beta", "PF00002.1")
                + hmm("alpha", "PF00001.1")
                + hmm("fresh", "PF00009.1")
            )
            self.assertEqual(len(list(iter_profile_raw(old))), len(parse_profile_text(old.read_text())))
            report = select_profile_subset(
                old,
                new,
                root / "old_sub.hmm",
                root / "new_sub.hmm",
                n_unchanged=1,
                n_changed=1,
                preferred={"alpha"},
            )
            self.assertEqual(report["n_unchanged"], 1)
            self.assertEqual(report["n_changed"], 1)
            self.assertEqual(report["n_preferred"], 1)
            self.assertIn("NAME alpha", (root / "old_sub.hmm").read_text())
            new_text = (root / "new_sub.hmm").read_text()
            self.assertIn("NAME alpha", new_text)
            self.assertIn("NAME fresh", new_text)
            self.assertNotIn("NAME gone", new_text)


if __name__ == "__main__":
    unittest.main()
