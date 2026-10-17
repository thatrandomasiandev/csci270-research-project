"""The measured-run analysis, checked on the pilot JSON before any result exists."""
from __future__ import annotations

import hashlib
import json
import random
import statistics
import sys
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE / "scripts"))

import headline_analysis as analysis  # noqa: E402
import headline_carc_measured as runner  # noqa: E402

PILOT = PIPE / "results" / "exact_replay" / "headline_pilot_carc.json"
ACCESSIONS = PIPE / "results" / "recurrence_accessions.json"


class HeadlineAnalysisTest(unittest.TestCase):
    def test_quantiles_are_the_locked_order_statistics(self) -> None:
        ordered = [float(i) for i in range(analysis.BOOT_N)]
        self.assertEqual(analysis.empirical_quantile(ordered, 0.025), 249.0)
        self.assertEqual(analysis.empirical_quantile(ordered, 0.975), 9749.0)

    def test_bootstrap_is_deterministic(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        first = analysis.bootstrap_median_ci(values)
        second = analysis.bootstrap_median_ci(values)
        self.assertEqual(first, second)
        self.assertLessEqual(first["low"], statistics.median(values))
        self.assertGreaterEqual(first["high"], statistics.median(values))
        self.assertEqual(first["seed"], 20261047)
        self.assertEqual(first["resamples"], 10000)

    def test_coefficients_come_from_the_pilot_pairs(self) -> None:
        pairs = (
            (2206.1550126140937, 489.1797169428319, 275.8698603990488),
            (2053.695990220178, 501.117714765016, 280.5428986046463),
            (2027.7076938920654, 545.3729357882403, 299.4008898450993),
        )
        a_values = [discovery / (analysis.F_DELTA * stock) for stock, _tare, discovery in pairs]
        c_values = [(tare - discovery) / stock for stock, tare, discovery in pairs]
        self.assertAlmostEqual(statistics.fmean(a_values), analysis.A_COEF)
        self.assertAlmostEqual(statistics.fmean(c_values), analysis.C_COEF)
        self.assertAlmostEqual(analysis.S_PRED, 4.0832874372486945)

    def test_pilot_is_exact_and_cv_is_only_a_flag(self) -> None:
        payload = json.loads(PILOT.read_text())
        row = analysis.score_genome(payload)
        walls_a = [2206.1550126140937, 2053.695990220178, 2027.7076938920654]
        walls_b = [489.1797169428319, 501.117714765016, 545.3729357882403]
        self.assertEqual(row["outcome"], "EXACT")
        self.assertEqual(row["fail_reasons"], [])
        self.assertAlmostEqual(row["S_g"], statistics.median(walls_a) / statistics.median(walls_b))
        self.assertAlmostEqual(row["cv_A"], statistics.stdev(walls_a) / statistics.fmean(walls_a))
        self.assertAlmostEqual(row["cv_B"], statistics.stdev(walls_b) / statistics.fmean(walls_b))
        self.assertFalse(row["cv_flag_A"])
        self.assertTrue(row["cv_flag_B"])
        self.assertAlmostEqual(row["first_run_overhead"], 2489.3551150541753 / 2476.1234619501047)
        stock = statistics.median(walls_a)
        tare = statistics.median(walls_b)
        self.assertAlmostEqual(row["break_even_n"], (2489.3551150541753 - stock) / (stock - tare))
        summary = analysis.summarize([row])
        self.assertEqual(summary["n_speedups"], 1)
        self.assertEqual(summary["dropped"], 0)
        self.assertAlmostEqual(summary["headline_median"], row["S_g"])
        self.assertEqual(summary["bootstrap_ci95"]["low"], row["S_g"])
        self.assertEqual(summary["bootstrap_ci95"]["high"], row["S_g"])

    def test_a_fail_is_kept(self) -> None:
        payload = json.loads(PILOT.read_text())
        payload["unpinned"]["differs"] = False
        failed = analysis.score_genome(payload)
        self.assertEqual(failed["outcome"], "FAIL")
        self.assertIsNotNone(failed["S_g"])
        kept = analysis.score_genome(json.loads(PILOT.read_text()))
        summary = analysis.summarize([failed, kept])
        self.assertEqual(summary["n_speedups"], 2)
        self.assertEqual(summary["dropped"], 0)
        self.assertTrue(summary["any_fail"])

    def test_draw_is_the_locked_sample(self) -> None:
        data = json.loads(ACCESSIONS.read_text())
        stems = sorted(row["accession"] for row in data["collections"]["A"]["genomes"])
        pool = [stem for stem in stems if stem not in runner.EXCLUDE_REASONS]
        digest = hashlib.sha256("\n".join(pool).encode()).hexdigest()
        self.assertEqual(len(pool), runner.POOL_N)
        self.assertEqual(digest, runner.POOL_SHA256)
        drawn = sorted(random.Random(runner.SEED).sample(pool, runner.N_DRAW))
        self.assertEqual(tuple(drawn), runner.DRAWS)
        self.assertEqual(len(runner.EXCLUDE_REASONS), 50)
        self.assertTrue(set(runner.DRAWS).isdisjoint(runner.EXCLUDE_REASONS))


if __name__ == "__main__":
    unittest.main()
