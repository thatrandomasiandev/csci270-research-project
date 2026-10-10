"""Guards for the baseline smoke harness.

The wall-clock SKIP rule is not allowed to describe a step that never
ran HMMER. hmmscan is not allowed to start on an unpressed database.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE / "scripts"))

from baseline_smoke import (  # noqa: E402
    HMM_AUX_SUFFIXES,
    classify,
    database_pressed,
    documented_incr_argv,
    judge_step,
    refuse_unpressed_hmmscan,
)


class BaselineSmokeGuardTests(unittest.TestCase):
    def test_fast_empty_exit_is_invalid_never_skip(self) -> None:
        self.assertEqual(classify(0.13, 1200.0, cold=False), "SKIP")
        action, status = judge_step(
            wall_s=0.13,
            cold_wall_s=1200.0,
            cold=False,
            exit_code=0,
            output_nonempty=False,
            newly_written=False,
            log="ModuleNotFoundError: No module named 'libbash'",
            match=False,
            cache_unchanged=True,
            argv_matches_prior=True,
        )
        self.assertEqual(action, "INVALID")
        self.assertEqual(status, "invalid")
        self.assertNotEqual(action, "SKIP")

    def test_hmmscan_refuses_unpressed_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hmm = Path(tmp) / "Pfam-A.hmm"
            hmm.write_text("HMMER3/f\nNAME  x\n")
            self.assertFalse(database_pressed(hmm))
            with self.assertRaises(SystemExit) as caught:
                refuse_unpressed_hmmscan("hmmscan", hmm)
            self.assertIn("use hmmpress first", str(caught.exception))
            self.assertIn("refusing to start hmmscan", str(caught.exception))
            refuse_unpressed_hmmscan("hmmsearch", hmm)
            for suffix in HMM_AUX_SUFFIXES:
                Path(str(hmm) + suffix).write_bytes(b"pressed")
            self.assertTrue(database_pressed(hmm))
            refuse_unpressed_hmmscan("hmmscan", hmm)

    def test_incr_argv_is_the_documented_entrypoint(self) -> None:
        argv = documented_incr_argv("/work/run.sh", "/work/cache")
        self.assertEqual(
            argv,
            ["bash", "./src/incr.sh", "/work/run.sh", "/work/cache"],
        )


if __name__ == "__main__":
    unittest.main()
