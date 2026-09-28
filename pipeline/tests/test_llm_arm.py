from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egas.llm_arm import Budget, t1_t3_plan, write_task_file
from egas.rungs import RungClass

PIPE = Path(__file__).resolve().parents[1]
RUN = PIPE / "scripts" / "llm_arm_run.py"
SCORE = PIPE / "scripts" / "llm_arm_score.py"
CFG = PIPE / "fixtures" / "llm_arm" / "agent.toml"


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *argv],
        cwd=PIPE,
        capture_output=True,
        text=True,
    )


class LlmArmProtocolTests(unittest.TestCase):
    def test_t1_t3_from_egas_rungs(self) -> None:
        rungs = t1_t3_plan("score", 0.8)
        self.assertTrue(any(r.cls == RungClass.T3_CLOSED_FORM for r in rungs))
        self.assertFalse(any("T4" in r.cls.value or "T5" in r.cls.value for r in rungs))

    def test_task_file_names_budget_and_forbid_test_data(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "task.md"
            write_task_file(p, budget=Budget(model_id="TBD"), workdir=Path(td))
            text = p.read_text()
            self.assertIn("2,000,000", text.replace("_", ""))
            self.assertIn("collections A/B", text)
            self.assertIn("T4", text)


class LlmArmHarnessTests(unittest.TestCase):
    def test_refuses_tbd_model_without_allow_fake(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "run"
            r = _run([str(RUN), "--config", str(CFG), "--out", str(out), "--run-id", "no"])
            self.assertEqual(r.returncode, 2)
            self.assertIn("TBD", r.stderr)

    def test_safe_patch_match_and_is_scored(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "safe"
            r = _run([
                str(RUN), "--config", str(CFG), "--out", str(out),
                "--run-id", "dry_safe", "--patch", "safe", "--allow-fake",
                "--hours", "1", "--tokens", "10000",
            ])
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertTrue((out / "task.md").is_file())
            self.assertTrue((out / "final.diff").is_file())
            self.assertTrue((out / "transcript").is_file())
            self.assertIn("n = len(token)", (out / "work" / "score_rows.py").read_text())
            s = _run([str(SCORE), "--run-dir", str(out), "--which", "test"])
            self.assertEqual(s.returncode, 0, s.stderr + s.stdout)
            score = json.loads((out / "score.json").read_text())
            self.assertTrue(score["match"])
            self.assertNotEqual(score["speedup"], 1.0)
            self.assertTrue(score["carc_timing"]["ready"])

    def test_bad_patch_match_fails_scores_1x(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "bad"
            r = _run([
                str(RUN), "--config", str(CFG), "--out", str(out),
                "--run-id", "dry_bad", "--patch", "bad", "--allow-fake",
                "--hours", "1", "--tokens", "10000",
            ])
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertIn("+ 1", (out / "work" / "score_rows.py").read_text())
            s = _run([str(SCORE), "--run-dir", str(out), "--which", "test"])
            self.assertEqual(s.returncode, 0, s.stderr + s.stdout)
            score = json.loads((out / "score.json").read_text())
            self.assertFalse(score["match"])
            self.assertEqual(score["speedup"], 1.0)
            self.assertFalse(score["carc_timing"]["ready"])

    def test_token_cap_trips(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cap"
            r = _run([
                str(RUN), "--config", str(CFG), "--out", str(out),
                "--run-id", "cap", "--patch", "safe", "--allow-fake",
                "--hours", "1", "--tokens", "1",
            ])
            self.assertEqual(r.returncode, 3)
            self.assertIn("token cap", r.stderr)


if __name__ == "__main__":
    unittest.main()
