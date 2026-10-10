"""Replay must reuse the command's output path and must not rewrite it."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import baseline_smoke  # noqa: E402
import riker_docker  # noqa: E402


class ReplayOutputGuard(unittest.TestCase):
    def test_processcache_replay_argv_matches_genome1(self) -> None:
        self.assertEqual(
            baseline_smoke.step_output_name("replay"),
            baseline_smoke.step_output_name("genome1"),
        )
        genome1 = baseline_smoke.hmmer_argv(
            "hmmsearch", "hmmsearch", "/work/hmmsearch/genome1.tbl",
            "/data/g1.faa", "/data/Pfam-A.hmm",
        )
        replay = baseline_smoke.hmmer_argv(
            "hmmsearch", "hmmsearch",
            f"/work/hmmsearch/{baseline_smoke.step_output_name('replay')}.tbl",
            "/data/g1.faa", "/data/Pfam-A.hmm",
        )
        self.assertEqual(genome1, replay)
        self.assertIn("/work/hmmsearch/genome1.tbl", replay)

    def test_snapshot_leaves_source_bytes_and_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "genome1.tbl"
            src.write_text("# comment\nseq1 PF00001 1\n")
            before_ns = src.stat().st_mtime_ns
            snap = baseline_smoke.snapshot_output(src, root / "comparisons" / "replay.tbl")
            self.assertEqual(src.read_text(), "# comment\nseq1 PF00001 1\n")
            self.assertEqual(src.stat().st_mtime_ns, before_ns)
            self.assertEqual((root / "comparisons" / "replay.tbl").read_text(), src.read_text())
            self.assertTrue(snap["source_mtime_ns_unchanged"])
            self.assertEqual(snap["sha256"], baseline_smoke.sha256_file(src))

    def test_riker_same_container_script_does_not_rewrite_replay(self) -> None:
        script = riker_docker.same_container_script()
        self.assertEqual(script.count("> /work/hmmscan/Rikerfile"), 2)
        self.assertEqual(script.count("> /work/hmmsearch/Rikerfile"), 2)
        self.assertNotIn("\nrm ", "\n" + script)
        self.assertNotIn("truncate ", script)
        replay = script.split("echo STEP hmmscan replay", 1)[1].split("echo ENDSTEP hmmscan replay", 1)[0]
        self.assertNotIn("> /work/hmmscan/Rikerfile", replay)
        self.assertIn("/work/hmmscan/genome2.tbl", replay)
        self.assertNotIn("rm ", replay)
