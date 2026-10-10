"""Guards for the uniform Docker behavioral smoke.

Wall time cannot promote an empty exit into a replay. Replay of
genome 2 keeps genome 2's argv, including --tblout. INCR's
annotation column is the tool's flag, not a hmmscan annotation
written here.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE / "scripts"))

import baseline_docker_uniform as uniform  # noqa: E402


class UniformBehavioralGuardTests(unittest.TestCase):
    def test_selfcheck(self) -> None:
        uniform._selfcheck()

    def test_unshare_failure_is_invalid_not_replayed(self) -> None:
        self.assertFalse(uniform.log_says_replay(
            "unshare has no --root; incr.sh cannot start. Load util-linux/2.40."
        ))
        self.assertEqual(
            uniform.judge_behavioral(
                exit_code=0,
                tblout_nonempty=False,
                tblout_header=False,
                newly_written=False,
                replay_marker=False,
                riker_must_run=None,
                match=False,
            ),
            "invalid",
        )

    def test_replay_keeps_genome2_tblout(self) -> None:
        for column in uniform.FACTORS:
            genome2 = uniform.step_plan(column, "hmmscan", "genome2")
            replay = uniform.step_plan(column, "hmmscan", "replay")
            self.assertEqual(genome2["argv"], replay["argv"])
            self.assertTrue(replay["tblout"].endswith("/genome2.tbl"))
            self.assertFalse(replay["rewrite_command"])
            self.assertIn("--cpu", replay["argv"])
            self.assertIn("32", replay["argv"])
            self.assertIn("--cut_ga", replay["argv"])

    def test_dockerfile_only_flips_debug_logs(self) -> None:
        text = (PIPE / "docker" / "Dockerfile.baselines_uniform").read_text()
        self.assertIn(
            "pub(crate) const DEBUG_LOGS: bool = DEBUG && true;",
            text,
        )
        self.assertIn("pub(crate) const DEBUG_LOGS: bool = true;", text)
        self.assertNotIn("STATELESS_COMMANDS", text)
        self.assertNotIn("hmmscan as stateless", text)
        self.assertIn("hmmscan -h", text)
        self.assertIn("a89d13214d8a0a9527ad4400a0a7284158d952a1", text)
        self.assertIn("4b8e5ddf8e275d947518c7cc0f5d2713fe992307", text)
        self.assertIn("bae684b455a4d8fa010fc04b471f5ca9b408f6a8", text)
        self.assertIn("unshare --help", text)

    def test_projections_match_the_paper_factors(self) -> None:
        self.assertEqual(uniform.project_hours("processcache", "hmmsearch")["hours_per_genome"], "0.29575")
        self.assertEqual(uniform.project_hours("incr_default", "hmmsearch")["hours_per_genome"], "0.3518375")
        self.assertEqual(uniform.project_hours("incr_annotations", "hmmscan")["hours_per_genome"], "1.220175")
        four = (
            30 * uniform.FACTORS["processcache"] * (uniform.SAMPLE_HOURS["hmmscan"] / 6)
            + 30 * uniform.FACTORS["processcache"] * (uniform.SAMPLE_HOURS["hmmsearch"] / 6)
            + 40 * uniform.FACTORS["processcache"] * (uniform.SAMPLE_HOURS["hmmscan"] / 6)
            + 40 * uniform.FACTORS["processcache"] * (uniform.SAMPLE_HOURS["hmmsearch"] / 6)
        )
        self.assertEqual(uniform.dec_str(four), "121.2575")


if __name__ == "__main__":
    unittest.main()
