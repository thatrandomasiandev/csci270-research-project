"""Guards for the DIAMOND second-tool driver. No DIAMOND binary, no download."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.reference_formats import length_weighted_churn, parse_fasta_entries  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "run_reference_diamond",
    PIPE / "scripts" / "run_reference_diamond.py",
)
assert _SPEC and _SPEC.loader
_DRIVER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_DRIVER)

confirmed = _DRIVER.confirmed
dbinfo_letters = _DRIVER.dbinfo_letters
fitter_churn_c = _DRIVER.fitter_churn_c
residue_identity = _DRIVER.residue_identity
s1_argv = _DRIVER.s1_argv
speedup = _DRIVER.speedup
timing_plan = _DRIVER.timing_plan
check_output_dir = _DRIVER.check_output_dir
EXPECTED = _DRIVER.EXPECTED


class DiamondProtocolGuards(unittest.TestCase):
    def test_s1_is_the_locked_command(self) -> None:
        argv = s1_argv("diamond", k="0")
        self.assertNotIn("--freq-masking", argv)
        self.assertNotIn("--freq-sd", argv)
        self.assertNotIn("--symmetrize-evalue", argv)
        self.assertIn("--min-score", argv)
        self.assertEqual(argv[argv.index("--min-score") + 1], "40")
        self.assertEqual(argv[argv.index("-k") + 1], "0")
        self.assertEqual(argv[argv.index("--motif-masking") + 1], "0")
        self.assertEqual(argv[argv.index("-b") + 1], "2.0")
        self.assertEqual(argv[argv.index("--threads") + 1], "32")
        self.assertIn("evalue", argv)
        self.assertIn("bitscore", argv)
        negative = s1_argv("diamond", k="25")
        self.assertEqual(negative[negative.index("-k") + 1], "25")

    def test_c_is_entry_count_not_length(self) -> None:
        old = parse_reference_text(">a d\nAA\n>b d\nAAA\n")
        new = parse_reference_text(">a d\nAA\n>c d\nA\n")
        # identical first record, one replacement. Lengths differ, so the
        # two fractions are not the same number.
        report = length_weighted_churn(old, new)
        c = fitter_churn_c(report)
        self.assertEqual(report["n_new"], 2)
        self.assertEqual(report["n_unchanged_hash"], 1)
        self.assertEqual(c, 0.5)
        self.assertNotEqual(c, report["c_length"])

    def test_header_edit_changes_the_fitter_hash_only(self) -> None:
        same = parse_reference_text(">a one\nAC\n")
        edited = parse_reference_text(">a two\nAC\n")
        self.assertNotEqual(same[0].content_hash, edited[0].content_hash)
        self.assertEqual(residue_identity(same[0].raw), residue_identity(edited[0].raw))
        report = length_weighted_churn(same, edited)
        self.assertEqual(fitter_churn_c(report), 1.0)

    def test_speedup_and_confirmation_band(self) -> None:
        # a = 0, b = 1, c = 0.25, n = 100 → 100 / 25 = 4
        self.assertEqual(speedup(0.0, 1.0, 0.25, 100), 4.0)
        self.assertIsNone(speedup(1.0, 1.0, 0.0, 100))
        self.assertIsNone(speedup(1.0, 0.0, 0.5, 100))
        self.assertTrue(confirmed(8.0, 2.0, 4.0))
        self.assertFalse(confirmed(8.0, 2.0, 2.0))

    def test_dbinfo_letters_line(self) -> None:
        text = "                   Letters  208482574\n                   Sequences  574627\n"
        self.assertEqual(dbinfo_letters(text), 208482574)

    def test_protocol_holds_the_release_pair(self) -> None:
        text = (PIPE / "docs" / "REFERENCE_SECOND_TOOL_PROTOCOL.md").read_text()
        self.assertIn("6042adf20dad1ab62112c9053bdebd20", text)
        self.assertIn("2026_01 → 2026_03", text)
        self.assertIn("MMseqs2 is not the second tool", text)
        self.assertIn(
            "Job 12759635 failed on input resolution before any measurement; fix; resubmission.",
            text,
        )
        for _name, (size, digest) in EXPECTED.items():
            self.assertIn(digest, text)
            self.assertIn(str(size), text)

    def test_smoke_plan_is_not_the_measurement(self) -> None:
        smoke = timing_plan(True)
        real = timing_plan(False)
        self.assertFalse(smoke["measurement"])
        self.assertEqual(smoke["entries"], 2000)
        self.assertEqual(smoke["n_queries"], 50)
        self.assertEqual(smoke["repeats"], 1)
        self.assertEqual(smoke["threads"], "4")
        self.assertTrue(real["measurement"])
        self.assertEqual(real["threads"], "32")
        self.assertEqual(real["repeats"], 3)
        self.assertEqual(real["fit"], ((300, 3), (5117, 3)))
        argv = s1_argv("diamond", k="0")
        self.assertEqual(argv[argv.index("--threads") + 1], "32")

    def test_smoke_cannot_write_the_real_result_directory(self) -> None:
        from acts.inputs import InputManifestError

        with self.assertRaises(InputManifestError) as caught:
            check_output_dir(Path("/tmp/reference_diamond"), smoke=True)
        self.assertIn("STOP_INPUTS", str(caught.exception))
        with self.assertRaises(InputManifestError):
            check_output_dir(Path("/tmp/reference_diamond_smoke"), smoke=False)

    def test_missing_input_stops_before_diamond(self) -> None:
        called: list[str] = []

        def _boom(*_args, **_kwargs):
            called.append("diamond")
            raise AssertionError("diamond ran")

        original = _DRIVER._diamond_version
        _DRIVER._diamond_version = _boom
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "root"
                root.mkdir()
                work = Path(tmp) / "work"
                args = argparse.Namespace(
                    root=root,
                    diamond=Path("/no/such/diamond"),
                    old=Path("/no/such/old.fasta.gz"),
                    new=Path("/no/such/new.fasta.gz"),
                    queries=Path("/no/such/queries.faa.gz"),
                    iseq=Path("/no/such/iseq"),
                    out=Path(tmp) / "reference_diamond",
                    work=work,
                    smoke=False,
                )
                with self.assertRaises(SystemExit) as caught:
                    _DRIVER.run(args)
                self.assertIn("STOP_INPUTS", str(caught.exception))
                self.assertEqual(called, [])
                self.assertFalse(work.exists())
        finally:
            _DRIVER._diamond_version = original

    def test_diamond_jobs_pin_a_venv_and_absolute_inputs(self) -> None:
        for name in ("reference_diamond.job", "reference_diamond_smoke.job"):
            text = (PIPE / "jobs" / name).read_text()
            self.assertNotIn("pip install", text)
            self.assertIn('cd "${ROOT}"', text)
            self.assertIn("venv/bin/python", text)
            self.assertNotIn("OLD_PATH", text)
        pins = (PIPE / "requirements-diamond.txt").read_text()
        self.assertIn("biopython==1.85", pins)
        self.assertIn("numpy==2.4.6", pins)
        self.assertIn("tqdm==4.67.1", pins)
        smoke = (PIPE / "jobs" / "reference_diamond_smoke.job").read_text()
        self.assertNotIn("--exclusive", smoke)
        real = (PIPE / "jobs" / "reference_diamond.job").read_text()
        self.assertIn("--exclusive", real)
        self.assertIn("--constraint=epyc-7542", real)
        self.assertIn("--cpus-per-task=32", real)
        self.assertIn("--mem=0", real)
        self.assertNotIn("--mem=64G", real)
        self.assertIn("--time=24:00:00", real)
        self.assertIn("/scratch1/${USER}", real)
        self.assertIn("--resume-d3", real)
        self.assertIn("STOP_SCRATCH", real)
        self.assertNotIn('WORK="${SLURM_TMPDIR', real)
        protocol = (PIPE / "docs" / "REFERENCE_SECOND_TOOL_PROTOCOL.md").read_text()
        self.assertIn("`--mem=64G`", protocol)
        self.assertIn("Addendum 2026-10-10", protocol)
        self.assertIn("12866389", protocol)

    def test_filesystem_type_uses_the_longest_mount(self) -> None:
        mounts = "\n".join(
            [
                "tmpfs / tmpfs rw 0 0",
                "tmpfs /tmp tmpfs rw 0 0",
                "10.1.1.1:/lfs1 /scratch1 lustre rw 0 0",
            ]
        )
        self.assertEqual(_DRIVER.filesystem_type(Path("/tmp/acts/job"), mounts=mounts), "tmpfs")
        self.assertEqual(
            _DRIVER.filesystem_type(Path("/scratch1/jjt_373/acts"), mounts=mounts),
            "lustre",
        )
        self.assertEqual(_DRIVER.filesystem_type(Path("/home/x"), mounts=mounts), "tmpfs")

    def test_d3_refuses_tmpfs_scratch_unless_allowed(self) -> None:
        original = _DRIVER.filesystem_type
        _DRIVER.filesystem_type = lambda _path, mounts=None: "tmpfs"
        try:
            with self.assertRaises(SystemExit) as caught:
                _DRIVER.require_durable_scratch(Path("/tmp/acts"), allow_tmpfs=False)
            self.assertIn("STOP_SCRATCH", str(caught.exception))
            self.assertEqual(
                _DRIVER.require_durable_scratch(Path("/tmp/acts"), allow_tmpfs=True),
                "tmpfs",
            )
        finally:
            _DRIVER.filesystem_type = original

    def test_measurement_refuses_tmpfs_before_diamond(self) -> None:
        called: list[str] = []

        def _boom(*_args, **_kwargs):
            called.append("diamond")
            raise AssertionError("diamond ran")

        def _gate(_args):
            return {}, {}, _DRIVER.timing_plan(False)

        original_gate = _DRIVER._gate
        original_version = _DRIVER._diamond_version
        original_fs = _DRIVER.filesystem_type
        _DRIVER._gate = _gate
        _DRIVER._diamond_version = _boom
        _DRIVER.filesystem_type = lambda _path, mounts=None: "tmpfs"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                args = argparse.Namespace(
                    work=Path(tmp) / "work",
                    allow_tmpfs_scratch=False,
                    resume_d3=False,
                )
                with self.assertRaises(SystemExit) as caught:
                    _DRIVER.run(args)
                self.assertIn("STOP_SCRATCH", str(caught.exception))
                self.assertEqual(called, [])
        finally:
            _DRIVER._gate = original_gate
            _DRIVER._diamond_version = original_version
            _DRIVER.filesystem_type = original_fs

    def test_index_out_file_matches_the_row_index_and_does_not_keep_the_text(self) -> None:
        from acts.reference_fit import index_rows, parse_table_text

        text = "q1\ts1\t1\t2\t0\t0\t1\t2\t3\t4\t1e-5\t40\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.m8"
            path.write_text(text)
            indexed = _DRIVER.index_out_file(path, 0, 1, None)
        parsed = index_rows(parse_table_text("out", text).rows, 0, 1, None)
        self.assertEqual(indexed, parsed)
        self.assertEqual(indexed[("q1", "s1", "")][10], "1e-5")

    def test_committed_d0_through_d2n_are_the_measured_outcomes(self) -> None:
        prior = _DRIVER.load_prior_stages(PIPE / "results" / "reference_diamond")
        self.assertTrue(prior["D0"]["old_equal"])
        self.assertTrue(prior["D0"]["new_equal"])
        self.assertEqual(prior["D0"]["old"]["dbinfo_letters"], 208482574)
        self.assertEqual(prior["D0"]["new"]["dbinfo_letters"], 209017843)
        self.assertEqual(prior["D0"]["new"]["n_entries"], 575748)
        self.assertEqual(prior["D1"]["c"], 0.01778382208883056)
        self.assertEqual(prior["D1"]["library"]["n_new"], 575748)
        self.assertEqual(prior["D1"]["n_added_or_changed"], 10239)
        self.assertEqual(prior["D1"]["n_removed"], 9118)
        self.assertEqual(prior["D2"]["decision"], "SHIP")
        self.assertTrue(prior["D2"]["expectation"]["matches"])
        by_index = {row["index"]: row for row in prior["D2"]["assignment"]}
        self.assertEqual(by_index[10]["member"], "total_entry_length")
        for index in (2, 3, 4, 5, 6, 7, 8, 9, 11):
            self.assertEqual(by_index[index]["member"], "identity")
        self.assertEqual(prior["D2n"]["decision"], "REFUSE")
        self.assertIn("whole 3686", prior["D2n"]["reason"])
        self.assertIn("union 6121", prior["D2n"]["reason"])
        self.assertIn("only-union 2435", prior["D2n"]["reason"])
        self.assertTrue(prior["D0"]["git"].startswith("9cbd81b"))

    def test_resume_stops_when_a_stage_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "reference_diamond_d0.json").write_text(json.dumps({"stage": "D0"}))
            with self.assertRaises(SystemExit) as caught:
                _DRIVER.load_prior_stages(out)
            self.assertIn("STOP_RESUME", str(caught.exception))


def parse_reference_text(text: str):
    return parse_fasta_entries(text)


if __name__ == "__main__":
    unittest.main()
