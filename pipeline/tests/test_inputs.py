"""Guards for input resolution. The check itself does no tool work."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.fasta import copy_fasta_head  # noqa: E402
from acts.inputs import (  # noqa: E402
    InputManifestError,
    InputSpec,
    check_manifest,
    check_requirement_pins,
    parse_pins,
    scan_job_directory,
)

# Tool-named flags stay in the test. acts/ does not name programs.
_JOB_FLAGS = ("--old", "--new", "--queries", "--iseq", "--root", "--diamond")

_BUG = textwrap.dedent(
    """\
    ROOT=/project2/example/tree
    OLD_FILE="$(cat "${ROOT}/data/swissprot/OLD_PATH")"
    python3 driver.py \\
      --old "${OLD_FILE}" \\
      --new "${ROOT}/data/swissprot/new.fasta.gz"
    """
)


class InputManifestGuards(unittest.TestCase):
    def test_relative_path_resolves_against_root_not_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            other = Path(tmp) / "other"
            data = root / "data" / "file.bin"
            data.parent.mkdir(parents=True)
            other.mkdir()
            payload = b"root-bytes"
            data.write_bytes(payload)
            cwd_copy = other / "data" / "file.bin"
            cwd_copy.parent.mkdir()
            cwd_copy.write_bytes(b"cwd-bytes")
            digest = hashlib.md5(payload).hexdigest()
            script = textwrap.dedent(
                f"""\
                import os, sys
                os.chdir({str(other)!r})
                sys.path.insert(0, {str(PIPE)!r})
                from acts.inputs import InputSpec, check_manifest
                from pathlib import Path
                found = check_manifest(
                    [InputSpec("old", "data/file.bin", size={len(payload)}, md5={digest!r})],
                    Path({str(root)!r}),
                )
                print(found["old"].path.read_bytes().decode())
                """
            )
            proc = subprocess.run(
                [sys.executable, "-c", script],
                cwd=other,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.strip(), "root-bytes")
            self.assertFalse((other / "work").exists())

    def test_missing_file_and_md5_mismatch_stop_before_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            present = root / "present.bin"
            present.write_bytes(b"abc")
            work = Path(tmp) / "work"
            missing = check_call = None
            with self.assertRaises(InputManifestError) as missing:
                check_manifest(
                    [InputSpec("old", "absent.bin", size=1, md5="0" * 32)],
                    root,
                )
            self.assertIn("STOP_INPUTS", str(missing.exception))
            self.assertIn("missing", str(missing.exception))
            with self.assertRaises(InputManifestError) as mismatch:
                check_manifest(
                    [InputSpec("old", "present.bin", size=3, md5="f" * 32)],
                    root,
                )
            self.assertIn("STOP_INPUTS", str(mismatch.exception))
            self.assertIn("md5", str(mismatch.exception))
            self.assertFalse(work.exists())
            self.assertIsNone(check_call)

    def test_job_scripts_have_no_relative_input_paths(self) -> None:
        findings = scan_job_directory(PIPE / "jobs", _JOB_FLAGS)
        self.assertEqual(findings, [])
        from acts.inputs import relative_input_paths

        bug = relative_input_paths(_BUG)
        self.assertTrue(any(item.startswith("--old ") for item in bug), bug)

    def test_pins_reject_a_mismatch_and_an_unpinned_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / "requirements.txt"
            req.write_text("biopython==1.85\nnumpy==2.4.6\n")
            with self.assertRaises(InputManifestError) as mismatch:
                check_requirement_pins(req, lookup=lambda name: "9.9.9")
            self.assertIn("STOP_INPUTS", str(mismatch.exception))
            self.assertIn("numpy", str(mismatch.exception))
            req.write_text("numpy\n")
            with self.assertRaises(InputManifestError) as unpinned:
                parse_pins(req.read_text())
            self.assertIn("unpinned", str(unpinned.exception))

    def test_fasta_head_stops_before_the_next_record(self) -> None:
        def lines():
            yield ">a d\n"
            yield "AA\n"
            yield ">b d\n"
            yield "BB\n"
            yield ">c d\n"
            raise AssertionError("the body of record 3 must not be read")

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "head.fasta"
            self.assertEqual(copy_fasta_head(lines(), dest, 2), 2)
            self.assertEqual(dest.read_text(), ">a d\nAA\n>b d\nBB\n")
            self.assertNotIn(">c", dest.read_text())


if __name__ == "__main__":
    unittest.main()
