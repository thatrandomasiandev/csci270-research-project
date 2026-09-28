from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egas.amdahl import evaluate_amdahl
from egas.contract import load_contract
from egas.decide import Decision
from egas.llm_arm import (
    Budget,
    budget_ok,
    parse_tokens,
    prepare_host,
    t1_t3_plan,
)
from egas.profile_io import Profile, Region, load_profile
from egas.rungs import RungClass

PIPE = Path(__file__).resolve().parents[1]
RUN = PIPE / "scripts" / "llm_arm_run.py"
SCORE = PIPE / "scripts" / "llm_arm_score.py"
CFG = PIPE / "fixtures" / "llm_arm" / "agent.toml"


def _run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *argv],
        cwd=cwd or PIPE,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _harness(tmp: Path, *, patch: str, tokens_cap: int = 2_000_000, extra: list[str] | None = None) -> Path:
    out = tmp / f"run_{patch}"
    builds = tmp / "builds"
    cmd = [
        str(RUN),
        "--config",
        str(CFG),
        "--out",
        str(out),
        "--run-id",
        f"fixture_{patch}",
        "--patch",
        patch,
        "--allow-fake",
        "--hours",
        "0.05",
        "--tokens",
        str(tokens_cap),
        "--builds-root",
        str(builds),
    ]
    if extra:
        cmd.extend(extra)
    proc = _run(cmd)
    if proc.returncode != 0:
        raise AssertionError(f"harness rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    return out


class LlmArmUnitTests(unittest.TestCase):
    def test_t1_t3_plan_excludes_t4_t5(self) -> None:
        rungs = t1_t3_plan("score", 0.80)
        self.assertTrue(rungs)
        self.assertTrue(all(r.cls in {RungClass.T1_COPY, RungClass.T2_DEAD_PATH, RungClass.T3_CLOSED_FORM} for r in rungs))
        self.assertFalse(any(r.cls is RungClass.T4_BUILD for r in rungs))
        self.assertFalse(any(r.cls is RungClass.T5_ALGORITHM for r in rungs))

    def test_budget_ok_and_token_parse(self) -> None:
        b = Budget(hours=8, tokens=100)
        self.assertEqual(parse_tokens({"prompt_tokens": 40, "completion_tokens": 60}), 100)
        ok, _ = budget_ok(b, elapsed_s=1.0, tokens=100)
        self.assertTrue(ok)
        bad, why = budget_ok(b, elapsed_s=1.0, tokens=101)
        self.assertFalse(bad)
        self.assertIn("token cap", why)

    def test_fixture_contract_loads(self) -> None:
        c = load_contract(PIPE / "fixtures" / "llm_arm" / "contract.toml")
        self.assertEqual(c.name, "llm_arm_fixture")
        self.assertGreaterEqual(c.runs, 3)
        self.assertAlmostEqual(c.target_speedup, 1.10)
        self.assertFalse(c.allow_t4_assist)

    def test_amdahl_proceeds_on_fixture_profile(self) -> None:
        profile = load_profile(PIPE / "fixtures" / "llm_arm" / "profile.json")
        c = load_contract(PIPE / "fixtures" / "llm_arm" / "contract.toml")
        prep = prepare_host(c, profile)
        self.assertTrue(prep.proceed)
        self.assertIsNotNone(prep.amdahl)
        self.assertEqual(prep.amdahl.status, "PROCEED")

    def test_amdahl_refuse_when_legal_fraction_too_small(self) -> None:
        c = load_contract(PIPE / "fixtures" / "llm_arm" / "contract.toml")
        profile = Profile(
            tool="t",
            regions=(
                Region("score", 0.02, True),
                Region("gzcat", 0.90, False),
            ),
        )
        prep = prepare_host(c, profile)
        self.assertFalse(prep.proceed)
        self.assertEqual(prep.amdahl.status, "REFUSE")
        # confirm evaluate_amdahl itself refuses a 2×-class target too
        r = evaluate_amdahl(profile, 2.0, allow_t4_assist=False)
        self.assertEqual(r.status, "REFUSE")


class LlmArmHarnessTests(unittest.TestCase):
    def test_tbd_model_requires_allow_fake(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            proc = _run(
                [
                    str(RUN),
                    "--out",
                    str(Path(td) / "x"),
                    "--run-id",
                    "blocked",
                ]
            )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("TBD", proc.stderr)

    def test_no_vendor_hardcoded_in_harness(self) -> None:
        blobs = []
        for path in (
            PIPE / "scripts" / "llm_arm_run.py",
            PIPE / "scripts" / "llm_arm_score.py",
            PIPE / "egas" / "llm_arm.py",
            PIPE / "fixtures" / "llm_arm" / "fake_agent.py",
        ):
            blobs.append(path.read_text().lower())
        text = "\n".join(blobs)
        for needle in ("openai", "anthropic", "api.openai.com", "generativelanguage.googleapis"):
            self.assertNotIn(needle, text)

    def test_safe_match_passes_and_is_scored(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            out = _harness(tmp, patch="safe")
            smoke = _run([str(SCORE), "--run-dir", str(out), "--which", "smoke"])
            test = _run([str(SCORE), "--run-dir", str(out), "--which", "test"])
            self.assertEqual(smoke.returncode, 0, smoke.stderr)
            self.assertEqual(test.returncode, 0, test.stderr)
            score = json.loads((out / "score.json").read_text())
            host = json.loads((out / "egas_host.json").read_text())
            oracle = json.loads((out / "oracle_dev.json").read_text())
            run = json.loads((out / "run.json").read_text())
            self.assertTrue(json.loads(smoke.stdout)["match"])
            self.assertTrue(json.loads(test.stdout)["match"])
            self.assertTrue(score["match"])
            self.assertNotEqual(score["speedup"], 1.0)
            self.assertTrue((out / "score_smoke.json").is_file())
            self.assertTrue((out / "score_test.json").is_file())
            self.assertEqual(
                json.loads((out / "score_smoke.json").read_text())["label"], "smoke"
            )
            self.assertEqual(score["label"], "fixture_test_not_collections_AB")
            self.assertTrue(oracle["match"]["match"])
            self.assertEqual(oracle["label"], "smoke")
            self.assertEqual(host["steps"], [
                "contract", "amdahl", "propose_t1_t3", "agent", "match_dev", "decide",
            ])
            self.assertFalse(host["t4_used"])
            self.assertFalse(host["t5_used"])
            self.assertIn(RungClass.T2_DEAD_PATH.value, host["rung_classes"])
            self.assertEqual(run["decision"], Decision.INCOMPLETE.value)
            self.assertTrue((out / "task.md").is_file())
            self.assertTrue((out / "config.used.toml").is_file())
            self.assertTrue((out / "final.diff").is_file())
            self.assertIn("return n", (out / "work" / "score_rows.py").read_text())
            self.assertIn("return len(token)", (out / "stock_src" / "score_rows.py").read_text())
            self.assertTrue((tmp / "builds" / "fixture_safe" / "work" / "score_rows.py").is_file())
            task = (out / "task.md").read_text()
            self.assertIn("collections A/B", task)
            self.assertIn("T4", task)
            self.assertNotIn("openai", task.lower())

    def test_bad_match_fails_and_scores_1x(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            out = _harness(tmp, patch="bad")
            smoke = _run([str(SCORE), "--run-dir", str(out), "--which", "smoke"])
            test = _run([str(SCORE), "--run-dir", str(out), "--which", "test"])
            self.assertEqual(smoke.returncode, 0)
            self.assertEqual(test.returncode, 0)
            score = json.loads((out / "score.json").read_text())
            host = json.loads((out / "egas_host.json").read_text())
            self.assertFalse(json.loads(smoke.stdout)["match"])
            self.assertFalse(json.loads(test.stdout)["match"])
            self.assertFalse(score["match"])
            self.assertEqual(score["speedup"], 1.0)
            self.assertEqual(host["decision"], Decision.REFUSE_MATCH.value)
            self.assertFalse(host["t4_used"])
            self.assertIn("+ 1", (out / "work" / "score_rows.py").read_text())

    def test_token_cap_stops_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            out = tmp / "run_over"
            proc = _run(
                [
                    str(RUN),
                    "--out",
                    str(out),
                    "--run-id",
                    "over",
                    "--patch",
                    "safe",
                    "--allow-fake",
                    "--hours",
                    "0.05",
                    "--tokens",
                    "10",
                    "--builds-root",
                    str(tmp / "builds"),
                ]
            )
        self.assertEqual(proc.returncode, 3)
        self.assertIn("token cap", proc.stderr)

    def test_agent_command_comes_from_config(self) -> None:
        text = CFG.read_text()
        self.assertIn("fake_agent.py", text)
        self.assertIn("model_id = \"TBD\"", text)
        self.assertNotIn("openai", text.lower())
        self.assertNotIn("anthropic", text.lower())


if __name__ == "__main__":
    unittest.main()
