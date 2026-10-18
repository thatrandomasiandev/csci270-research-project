"""The reference cache namespace keys the program binary's content."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.reference_cache import UNRESOLVED_BINARY, argv_namespace, program_binary  # noqa: E402
from acts.reference_run import _binary_line, namespace_for  # noqa: E402


def _write_exe(path: Path, body: bytes) -> Path:
    path.write_bytes(body)
    os.chmod(path, 0o755)
    return path


class BinaryNamespaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ref = self.root / "ref.fa"
        self.ref.write_text(">a\nACGT\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _argv(self, exe: Path) -> list[str]:
        return [str(exe), "--cpu", "1", str(self.ref), "{input}"]

    def test_same_argv_different_binary_bytes_differ(self) -> None:
        a = _write_exe(self.root / "hmmscan_a", b"#!/bin/sh\n# 3.4\n")
        b = _write_exe(self.root / "hmmscan_b", b"#!/bin/sh\n# 3.5\n")
        # Same argv shape; only the binary bytes differ. Put both at one path
        # by swapping contents, the HMMER 3.4 -> 3.5 upgrade case.
        same = self.root / "hmmscan"
        _write_exe(same, a.read_bytes())
        before = argv_namespace(self._argv(same), self.ref, None)
        _write_exe(same, b.read_bytes())
        os.utime(same, ns=(1, 1))  # a fresh stat key even on coarse clocks
        after = argv_namespace(self._argv(same), self.ref, None)
        self.assertNotEqual(before, after)

    def test_same_binary_same_namespace(self) -> None:
        exe = _write_exe(self.root / "hmmscan", b"#!/bin/sh\n# 3.4\n")
        first = argv_namespace(self._argv(exe), self.ref, None)
        second = argv_namespace(self._argv(exe), self.ref, None)
        self.assertEqual(first, second)
        # A byte-identical copy at another path keys the same content.
        copy = _write_exe(self.root / "hmmscan_copy", exe.read_bytes())
        self.assertEqual(program_binary([str(copy)])["digest"], program_binary([str(exe)])["digest"])

    def test_namespace_for_carries_binary(self) -> None:
        same = self.root / "hmmscan"
        _write_exe(same, b"one")
        before = namespace_for(self._argv(same), self.ref, None, "pin", None)
        _write_exe(same, b"two")
        os.utime(same, ns=(2, 2))
        after = namespace_for(self._argv(same), self.ref, None, "pin", None)
        self.assertNotEqual(before, after)

    def test_unresolved_binary_is_deterministic_and_reported(self) -> None:
        argv = ["no-such-tool-acts-test", str(self.ref), "{input}"]
        info = program_binary(argv)
        self.assertEqual(info["digest"], UNRESOLVED_BINARY)
        self.assertEqual(argv_namespace(argv, self.ref, None), argv_namespace(argv, self.ref, None))
        self.assertIn("not found on PATH", _binary_line(argv))

    def test_decision_line_names_digest(self) -> None:
        exe = _write_exe(self.root / "hmmscan", b"x")
        line = _binary_line(self._argv(exe))
        self.assertIn("sha256:" + program_binary([str(exe)])["digest"], line)


if __name__ == "__main__":
    unittest.main()
