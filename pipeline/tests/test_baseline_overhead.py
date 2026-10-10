"""Overhead repeats stay behind the locked subset sentence."""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE / "scripts"))

import baseline_overhead as overhead  # noqa: E402


class OverheadGuardTests(unittest.TestCase):
    def test_rotation_puts_each_tool_first(self) -> None:
        firsts = [overhead.repeat_order(i)[0] for i in range(overhead.N_REPEATS)]
        self.assertEqual(firsts, list(overhead.TOOLS))
        self.assertEqual(overhead.repeat_order(1)[-1], "stock")

    def test_press_is_outside_the_timed_window(self) -> None:
        script = overhead.timed_script("incr_default", "hmmscan")
        self.assertLess(script.index("hmmpress"), script.index("ACTS_T0"))
        self.assertLess(script.index("run.sh"), script.index("ACTS_T0"))
        self.assertLess(script.index("ACTS_T0"), script.index("ACTS_T1"))
        incr_argv = overhead.docker_argv("incr_default", Path("/tmp/w"), script)
        self.assertIn("--privileged", incr_argv)
        self.assertNotIn("SYS_PTRACE", incr_argv)
        riker_argv = overhead.docker_argv("riker", Path("/tmp/w"), script)
        self.assertIn("SYS_PTRACE", riker_argv)
        self.assertNotIn("--privileged", riker_argv)
        stock_argv = overhead.docker_argv("stock", Path("/tmp/w"), script)
        self.assertNotIn("--privileged", stock_argv)
        self.assertNotIn("SYS_PTRACE", stock_argv)
        riker = overhead.timed_script("riker", "hmmsearch")
        self.assertLess(riker.index("Rikerfile"), riker.index("ACTS_T0"))
        self.assertIn("/opt/riker/release/bin/rkr --show", riker)
        self.assertNotIn("--enable_annotations", overhead.timed_script("incr_default", "hmmscan"))
        self.assertIn("--enable_annotations", overhead.timed_script("incr_annotations", "hmmscan"))

    def test_measure_requires_the_lock_sentence(self) -> None:
        self.assertFalse(overhead.subset_is_locked("no subset yet", 100, 50))
        text = "prefix\n" + overhead.lock_sentence(1200, 400) + "\n"
        self.assertTrue(overhead.subset_is_locked(text, 1200, 400))
        self.assertFalse(overhead.subset_is_locked(text, 1200, 401))

    def test_parse_timing_uses_decimal_seconds(self) -> None:
        parsed = overhead.parse_timing("ACTS_T0 10.25\nACTS_EXIT 0\nACTS_T1 70.50\n")
        self.assertEqual(parsed["wall_s"], "60.25")
        self.assertEqual(parsed["exit_code"], 0)
        mean, std = overhead.mean_std([Decimal("1"), Decimal("3")])
        self.assertEqual(mean, "2")
        self.assertTrue(abs(float(std) - math_sqrt2()) < 1e-9)


def math_sqrt2() -> float:
    return 2 ** 0.5


if __name__ == "__main__":
    unittest.main()
