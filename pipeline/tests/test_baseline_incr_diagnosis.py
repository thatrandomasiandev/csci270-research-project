"""The INCR diagnosis observes the uniform sequence; it does not rewrite it."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE / "scripts"))

import baseline_docker_uniform as uniform  # noqa: E402
import baseline_incr_diagnosis as diag  # noqa: E402


class IncrDiagnosisGuardTests(unittest.TestCase):
    def test_replay_dump_is_after_the_tblout_read_and_before_incr(self) -> None:
        script = diag.diagnosis_script("incr_default")
        replay_at = script.index("echo ACTS_STEP incr_default hmmscan replay")
        incr_at = script.index("hmmscan_replay.log", replay_at)
        window = script[replay_at:incr_at]
        self.assertIn("ACTS_TBLOUT_MTIME_BEFORE", window)
        self.assertIn("ACTS_DUMP incr_default hmmscan", window)
        self.assertLess(window.index("ACTS_TBLOUT_MTIME_BEFORE"), window.index("ACTS_DUMP"))
        genome2_at = script.index("echo ACTS_STEP incr_default hmmscan genome2")
        genome2_incr = script.index("hmmscan_genome2.log", genome2_at)
        self.assertNotIn("ACTS_DUMP", script[genome2_at:genome2_incr])

    def test_replay_argv_is_the_uniform_genome2_command(self) -> None:
        script = diag.diagnosis_script("incr_annotations")
        plan = uniform.step_plan("incr_annotations", "hmmsearch", "replay")
        rendered = " ".join(plan["argv"])
        self.assertIn(rendered, script)
        self.assertFalse(plan["rewrite_command"])
        self.assertNotIn("DEBUG: bool = true", script)
        self.assertNotIn("STATELESS_COMMANDS", script)

    def test_observer_layout_matches_incr_cache_data(self) -> None:
        source = (PIPE / "scripts" / "baseline_incr_cache_dump" / "src" / "main.rs").read_text()
        exit_at = source.index("exit_code: i32,")
        read_at = source.index("read_dependencies: HashMap<PathBuf, DependencyKey>,")
        write_at = source.index("write_outputs: HashSet<PathBuf>,")
        compressed_at = source.index("compressed_output: bool,")
        self.assertLess(exit_at, read_at)
        self.assertLess(read_at, write_at)
        self.assertLess(write_at, compressed_at)
        enum_at = source.index("enum DependencyKey")
        window = source[enum_at:source.index("struct CacheData")]
        self.assertLess(window.index("DoesNotExist"), window.index("Timestamp(u128)"))
        self.assertLess(window.index("Timestamp(u128)"), window.index("Hash(u64)"))
        cargo = (PIPE / "scripts" / "baseline_incr_cache_dump" / "Cargo.toml").read_text()
        self.assertIn('bincode = { version = "=2.0.1"', cargo)
        self.assertIn('xxhash-rust = { version = "=0.8.15"', cargo)


if __name__ == "__main__":
    unittest.main()
