"""Opt-in Semgrep domain features: yaml-list, json-records, {inputs}."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.reference_formats import (  # noqa: E402
    FormatError,
    parse_reference,
    parse_reference_text,
    write_entries,
)
from acts.reference_run import materialize_argv  # noqa: E402
from acts.reference_yaml import (  # noqa: E402
    concat_yaml_list_files,
    parse_yaml_list_text,
    write_yaml_list,
)
from acts.table_json import (  # noqa: E402
    equal_except_volatile,
    parse_json_records,
    prove_round_trip,
    render_json_records,
    round_trip_bytes,
    to_line_table,
)

PIPE = Path(__file__).resolve().parents[1]
FIX = PIPE / "tests" / "fixtures" / "semgrep"
FIT = PIPE / "tests" / "fixtures" / "reference_fitter"
G1_OUT = Path.home() / "tmp" / "tare_g1" / "semgrep"
G1_RULES = Path.home() / "tmp" / "tare_g1" / "rules" / "python"


class YamlListTests(unittest.TestCase):
    def test_hand_fixtures_round_trip(self) -> None:
        for name in ("rules_v1.yaml", "rules_v2.yaml", "rules_indent2.yaml"):
            text = (FIX / name).read_text()
            entries = parse_yaml_list_text(text)
            with tempfile.TemporaryDirectory() as raw:
                out = Path(raw) / "out.yaml"
                write_yaml_list(entries, out)
                self.assertEqual(out.read_text(), text)

    def test_duplicate_id_raises(self) -> None:
        with self.assertRaises(FormatError) as ctx:
            parse_yaml_list_text((FIX / "rules_dup.yaml").read_text())
        self.assertIn("duplicate", str(ctx.exception))

    def test_missing_id_raises(self) -> None:
        with self.assertRaises(FormatError) as ctx:
            parse_yaml_list_text((FIX / "rules_noid.yaml").read_text())
        self.assertIn("missing", str(ctx.exception))

    def test_pfam_forced_yaml_list_raises(self) -> None:
        hmm = "HMMER3/f\nNAME beta\nACC PF00001.1\nLENG 4\n//\n"
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "x.hmm"
            path.write_text(hmm)
            with self.assertRaises(FormatError):
                parse_reference(path, reference_format="yaml-list")

    def test_auto_never_selects_yaml_list(self) -> None:
        text = (FIX / "rules_v1.yaml").read_text()
        with self.assertRaises(FormatError):
            parse_reference_text(text)
        # Existing fixtures keep their previous format names.
        self.assertEqual(parse_reference_text((FIT / "ab.entryline").read_text())[0].format_name, "entryline")
        self.assertEqual(parse_reference_text((FIT / "ab.faa").read_text())[0].format_name, "fasta")
        hmm = "HMMER3/f\nNAME beta\nACC PF00001.1\nLENG 4\n//\n"
        self.assertEqual(parse_reference_text(hmm)[0].format_name, "profile_text")

    @unittest.skipUnless(G1_RULES.is_dir(), "G1 rules clone not on disk")
    def test_all_python_rules_concat_round_trip(self) -> None:
        paths = sorted(p for p in G1_RULES.rglob("*.yaml") if "/test" not in str(p))
        self.assertEqual(len(paths), 336)
        n_items = 0
        # Every file round-trips alone (covers both indent-0 and indent-2 styles).
        for path in paths:
            text = path.read_text()
            entries = parse_yaml_list_text(text)
            n_items += len(entries)
            with tempfile.TemporaryDirectory() as raw:
                out = Path(raw) / "one.yaml"
                write_yaml_list(entries, out)
                self.assertEqual(out.read_text(), text, path.name)
        # One concatenated list: the public ruleset reuses bare ids across
        # packages, so duplicates are skipped (first wins). TARE still refuses
        # duplicates inside a single document (see test_duplicate_id_raises).
        text, skipped = concat_yaml_list_files(paths, on_duplicate="skip")
        self.assertGreater(skipped, 0)
        entries = parse_yaml_list_text(text)
        self.assertEqual(len(entries) + skipped, n_items)
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw) / "all.yaml"
            write_entries(entries, out)
            self.assertEqual(out.read_text(), text)


class JsonRecordsTests(unittest.TestCase):
    @unittest.skipUnless(G1_OUT.is_dir(), "G1 Semgrep outputs not on disk")
    def test_g1_round_trip_with_time_volatile(self) -> None:
        files = sorted(G1_OUT.glob("out_*.json"))
        self.assertEqual(len(files), 15)
        for path in files:
            prove_round_trip(path.read_text(), volatile=("time",))

    def test_mutated_result_compare_fails(self) -> None:
        # Positive control: identity. Negative: drop one finding / change a field.
        doc = {
            "version": "1.0",
            "results": [
                {"check_id": "a", "path": "/t.py", "start": {"line": 1, "col": 1}, "end": {"line": 1, "col": 2}, "extra": {"message": "m"}},
                {"check_id": "b", "path": "/t.py", "start": {"line": 2, "col": 1}, "end": {"line": 2, "col": 2}, "extra": {"message": "n"}},
            ],
            "errors": [],
            "paths": {"scanned": ["/t.py"]},
        }
        raw = json.dumps(doc, separators=(",", ":"))
        prove_round_trip(raw)
        parsed = parse_json_records(raw)
        dropped = render_json_records(
            envelope=parsed.envelope,
            key_order=parsed.key_order,
            rows_key="results",
            row_objects=parsed.rows[:1],
        )
        self.assertFalse(equal_except_volatile(dropped, raw, ()))
        changed_rows = [dict(parsed.rows[0]), parsed.rows[1]]
        changed_rows[0] = {**changed_rows[0], "check_id": "Z"}
        changed = render_json_records(
            envelope=parsed.envelope,
            key_order=parsed.key_order,
            rows_key="results",
            row_objects=changed_rows,
        )
        self.assertFalse(equal_except_volatile(changed, raw, ()))
        # Non-array field change.
        env = dict(parsed.envelope)
        env["version"] = "9.9"
        other = render_json_records(
            envelope=env,
            key_order=parsed.key_order,
            rows_key="results",
            row_objects=parsed.rows,
        )
        self.assertFalse(equal_except_volatile(other, raw, ()))

    def test_line_table_exposes_path_and_check_id(self) -> None:
        raw = json.dumps(
            {
                "results": [
                    {
                        "check_id": "demo.print",
                        "path": "/tmp/a.py",
                        "start": {"line": 1, "col": 1},
                        "end": {"line": 1, "col": 5},
                        "extra": {"message": "m", "severity": "WARNING"},
                    }
                ],
                "version": "1",
            },
            separators=(",", ":"),
        )
        doc = parse_json_records(raw)
        table = to_line_table(doc)
        self.assertIn("path", table.splitlines()[0])
        self.assertIn("check_id", table.splitlines()[0])
        self.assertIn("/tmp/a.py", table)
        self.assertIn("demo.print", table)


class InputsPlaceholderTests(unittest.TestCase):
    def test_inputs_expands_in_order_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            work = Path(raw)
            cmd, outputs = materialize_argv(
                ["tool", "--config", "{reference}", "{inputs}", "-o", "{output}"],
                input_slot=work / "records",
                input_file=work / "records",
                reference_slot=work / "ref",
                reference_file=work / "ref.yaml",
                work=work / "call",
                input_paths=["/tmp/a file.py", "/tmp/b.py"],
            )
            self.assertEqual(
                cmd,
                ["tool", "--config", str(work / "ref.yaml"), "/tmp/a file.py", "/tmp/b.py", "-o", str(work / "call" / "out")],
            )
            self.assertEqual(set(outputs), {"out"})

    def test_input_singular_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            work = Path(raw)
            cmd, _ = materialize_argv(
                ["tool", "{input}", "{reference}"],
                input_slot=work / "in",
                input_file=work / "records",
                reference_slot=work / "ref",
                reference_file=work / "ref.yaml",
                work=work / "call",
            )
            self.assertEqual(cmd, ["tool", str(work / "records"), str(work / "ref.yaml")])


class CliOptInTests(unittest.TestCase):
    def test_help_shows_defaults(self) -> None:
        env = {**os.environ, "PYTHONPATH": str(PIPE)}
        proc = subprocess.run(
            [sys.executable, "-m", "acts", "run", "--help"],
            cwd=PIPE,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--reference-format", proc.stdout)
        self.assertIn("--output-format", proc.stdout)
        self.assertRegex(proc.stdout, r"reference-format.*auto|default:\s*auto")
        self.assertRegex(proc.stdout, r"output-format.*table|default:\s*table")

    def test_default_run_does_not_import_new_modules(self) -> None:
        """G-d: a run without the new flags never imports the new modules."""
        script = r"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(%r)))
# Import the package the way the CLI does for a default reference run path.
import acts.__main__ as main
# Simulate parse of a default run (no yaml-list / json-records flags).
# The modules must not be loaded merely by importing acts or parsing help.
assert "acts.reference_yaml" not in sys.modules
assert "acts.table_json" not in sys.modules
from acts.reference_formats import parse_reference_text
parse_reference_text("e0 1\ne1 2\n")
assert "acts.reference_yaml" not in sys.modules
assert "acts.table_json" not in sys.modules
print("OK")
""" % str(PIPE)
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(PIPE)},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("OK", proc.stdout)



class LineTableSanityTests(unittest.TestCase):
    def test_line_table_sanitizes_newlines_in_scalars(self) -> None:
        doc = parse_json_records(
            json.dumps(
                {
                    "results": [
                        {
                            "check_id": "r1",
                            "path": "/a.py",
                            "start": {"line": 1},
                            "extra": {"message": "line1\nline2\txx"},
                        }
                    ]
                }
            )
        )
        text = to_line_table(doc)
        widths = {ln.count("\t") + 1 for ln in text.splitlines() if not ln.startswith("#") and ln.strip()}
        self.assertEqual(widths, {len(doc.columns)})
        self.assertEqual(len(text.splitlines()) - 1, 1)

    def test_empty_first_result_does_not_lock_json_only_header(self) -> None:
        """Empty first batch must not lock [__json__] (P2 min-delta false REFUSE_MATCH)."""
        from acts.reference_fit import TableReport
        from acts.reference_run import ReferenceIncremental
        from acts.table_json import to_line_table

        empty = '{"version":"1","results":[],"errors":[]}'
        hit = json.dumps(
            {
                "version": "1",
                "results": [
                    {
                        "check_id": "pass-body-fn",
                        "path": "/tmp/0012.py",
                        "start": {"line": 32, "col": 1, "offset": 703},
                        "end": {"line": 35, "col": 9, "offset": 838},
                        "extra": {"message": "`pass` is the body of function foo"},
                    }
                ],
                "errors": [],
            },
            separators=(",", ":"),
        )
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            # Path A: seed from fill meta, then empty then hit.
            strat = ReferenceIncremental(
                argv=["true"],
                input_path=out / "in",
                out_dir=out,
                output_format="json-records",
                json_rows="results",
            )
            meta = [
                "#check_id\tpath\tstart.line\tstart.col\tstart.offset\tend.line\tend.col\tend.offset\textra.message\t__json__"
            ]
            strat._seed_json_columns_from_tables(
                [TableReport(name="out", record_col=1, entry_col=0, index_col=4, meta=meta, columns=[])]
            )
            strat._coerce_json_tables({"out": empty})
            full_table = strat._coerce_json_tables({"out": hit})["out"]
            body = [ln for ln in full_table.splitlines() if ln.strip() and not ln.startswith("#")]
            self.assertTrue(body)
            self.assertIn("\t", body[0])
            fields = body[0].split("\t")
            self.assertEqual(fields[0], "pass-body-fn")
            self.assertEqual(fields[1], "/tmp/0012.py")
            # Path B: no seed; empty must not lock, so the later hit still tabs.
            strat2 = ReferenceIncremental(
                argv=["true"],
                input_path=out / "in",
                out_dir=out / "b",
                output_format="json-records",
                json_rows="results",
            )
            strat2._coerce_json_tables({"out": empty})
            self.assertNotIn("out", strat2._json_columns)
            ok = strat2._coerce_json_tables({"out": hit})["out"]
            ok_body = [ln for ln in ok.splitlines() if ln.strip() and not ln.startswith("#")]
            self.assertIn("\t", ok_body[0])
            # Old failure shape (manual lock to __json__ only): whitespace-split → record "is".
            doc = parse_json_records(hit)
            legacy = to_line_table(doc, columns=["__json__"])
            legacy_body = [ln for ln in legacy.splitlines() if ln.strip() and not ln.startswith("#")]
            self.assertNotIn("\t", legacy_body[0])
            self.assertEqual(legacy_body[0].split()[1], "is")


if __name__ == "__main__":
    unittest.main()
