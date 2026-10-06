"""Guards for the 38.1→38.2 measurement: churn identity and phase clocks."""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
