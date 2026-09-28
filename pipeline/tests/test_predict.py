from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.cache import fingerprint_inputs, namespace
from acts.predict import (
    CEILING_MIN,
    M_GATE,
    SAVED_MIN_S,
    ceiling,
    fit_ab,
    inference_call_sizes,
    miss_fraction,
    probe_cost_s,
    recommend,
    record_keys,
    run_predict,
    subset_sizes,
)
from acts.__main__ import main as acts_main

PIPE = Path(__file__).resolve().parents[1]
LINE_IN = PIPE / "fixtures" / "line_memo" / "input.txt"
LINE_B = PIPE / "fixtures" / "line_memo" / "run_b.txt"
VCF_IN = PIPE / "fixtures" / "vcf_memo" / "tiny.vcf"
FASTA_IN = PIPE / "fixtures" / "fasta_memo" / "tiny.fa"
VCF_TOOL = PIPE / "fixtures" / "vcf_memo" / "annotate_1to1.py"
FASTA_TOOL = PIPE / "fixtures" / "fasta_memo" / "per_query_table.py"
PY = sys.executable


def _cli(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = acts_main(argv)
    text = buf.getvalue()
    json_start = text.find("{")
    json_end = text.rfind("}")
    payload = json.loads(text[json_start : json_end + 1])
    return code, payload


class SubsetAndFitTests(unittest.TestCase):
    def test_sizes_adapt_to_tiny_n(self) -> None:
        self.assertEqual(subset_sizes(1), [1])
        self.assertEqual(subset_sizes(8), [1, 4, 8])
        self.assertEqual(subset_sizes(4), [1, 2, 4])

    def test_sizes_omit_ladder_above_n(self) -> None:
        sizes = subset_sizes(500)
        self.assertIn(1, sizes)
        self.assertIn(50, sizes)
        self.assertIn(200, sizes)
        self.assertIn(500, sizes)
        self.assertNotIn(800, sizes)
        self.assertEqual(sizes[-1], 500)

    def test_fit_ab_recovers_line(self) -> None:
        ns = [1, 4, 8]
        ts = [2.0 + 0.5 * n for n in ns]
        a, b = fit_ab(ns, ts)
        self.assertAlmostEqual(a, 2.0, places=9)
        self.assertAlmostEqual(b, 0.5, places=9)


class ScreenRuleTests(unittest.TestCase):
    def test_m_gate_when_a_vanishes(self) -> None:
        self.assertGreaterEqual(M_GATE, 1.0 / 3.0 - 1e-12)
        decision, why = recommend(a=1e-12, b=1.0, n=100, m=0.4, w=0.0)
        self.assertEqual(decision, "REFUSE")
        self.assertIn("1/3", why)

    def test_a_near_zero_can_ship_if_m_below_gate(self) -> None:
        decision, _ = recommend(a=1e-12, b=1.0, n=100, m=0.2, w=0.0)
        ratio = ceiling(1e-12, 1.0, 100, 0.2, 0.0)
        self.assertIsNotNone(ratio)
        self.assertGreaterEqual(ratio, CEILING_MIN)
        self.assertGreaterEqual(saved_s_check(1e-12, 1.0, 100, 0.2, 0.0), SAVED_MIN_S)
        self.assertEqual(decision, "SHIP")

    def test_ratio_and_saved_gates(self) -> None:
        decision, why = recommend(a=10.0, b=1.0, n=1000, m=0.1, w=1.0)
        self.assertEqual(decision, "SHIP")
        self.assertIn("ceiling", why)
        tiny = recommend(a=1.0, b=0.1, n=100, m=0.1, w=1.0)
        self.assertEqual(tiny[0], "REFUSE")
        self.assertIn("saved", tiny[1])

    def test_bad_linear_model(self) -> None:
        decision, why = recommend(a=-0.1, b=1.0, n=100, m=0.1, w=0.0)
        self.assertEqual(decision, "REFUSE")
        self.assertIn("linear model", why)


def saved_s_check(a: float, b: float, n: int, m: float, w: float) -> float:
    from acts.predict import saved_s

    return saved_s(a, b, n, m, w)


class MissFractionTests(unittest.TestCase):
    def test_first_run_is_unique_frac(self) -> None:
        keys = record_keys("lines", LINE_IN)
        m, detail = miss_fraction(keys, None)
        self.assertEqual(detail["mode"], "first_run")
        self.assertEqual(len(keys), 8)
        self.assertAlmostEqual(m, 0.5)

    def test_incremental_against_cache_keys(self) -> None:
        keys = record_keys("lines", LINE_B)
        cached = {"apple", "banana"}
        m, detail = miss_fraction(keys, cached)
        self.assertEqual(detail["mode"], "incremental")
        self.assertEqual(detail["n_miss_unique"], 2)
        self.assertAlmostEqual(m, 0.5)


class ProbeCostTests(unittest.TestCase):
    def test_lines_have_no_inference_calls(self) -> None:
        self.assertEqual(inference_call_sizes("lines", 1000), [])
        self.assertEqual(probe_cost_s(32.0, 0.7, []), 0.0)

    def test_batched_schedule_independent_of_probe_n(self) -> None:
        for k in (50, 200, 500, 2000):
            sizes = inference_call_sizes("vcf", 10_000, probe_n=k)
            self.assertEqual(len(sizes), 18, msg=k)
        s500 = inference_call_sizes("vcf", 5000, probe_n=500)
        self.assertEqual(s500[:4], [500, 500, 500, 500])
        self.assertEqual(s500[4:6], [250, 250])
        self.assertEqual(s500[6:10], [125, 125, 125, 125])
        self.assertEqual(s500[10:], [1] * 8)

    def test_singleton_grows_with_k(self) -> None:
        sizes = inference_call_sizes(
            "vcf", 1000, probe_n=50, subset_mode="singleton"
        )
        self.assertEqual(len(sizes), 54)

    def test_P_matches_sum_a_plus_bn(self) -> None:
        sizes = inference_call_sizes("fasta", 4192, probe_n=500)
        a, b = 31.96, 0.723
        p = probe_cost_s(a, b, sizes)
        self.assertAlmostEqual(p, sum(a + b * n for n in sizes))


class PredictCliTests(unittest.TestCase):
    def test_probe_still_works(self) -> None:
        code, payload = _cli(["probe", "--kind", "lines", "--input", str(LINE_IN)])
        self.assertEqual(code, 0)
        self.assertEqual(payload["n"], 8)
        self.assertEqual(payload["n_unique"], 4)

    def test_predict_lines_cat_fixture(self) -> None:
        code, payload = _cli(
            ["predict", "--kind", "lines", "--input", str(LINE_IN), "--runs", "1", "--", "cat"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "lines")
        self.assertEqual(payload["n"], 8)
        self.assertEqual(payload["sizes"], [1, 4, 8])
        self.assertTrue(payload["predicted_speedup_includes_P"])
        self.assertEqual(payload["probe_cost_P"], 0.0)
        self.assertEqual(payload["probe_call_sizes"], [])
        self.assertNotIn("stub", payload["probe_cost_note"].lower())
        self.assertIn(payload["decision"], {"SHIP", "REFUSE"})
        self.assertEqual(payload["decision"], "REFUSE")

    def test_predict_vcf_fixture_no_snpeff(self) -> None:
        code, payload = _cli(
            [
                "predict",
                "--kind",
                "vcf",
                "--input",
                str(VCF_IN),
                "--runs",
                "1",
                "--",
                PY,
                str(VCF_TOOL),
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "vcf")
        self.assertGreaterEqual(payload["n"], 1)
        self.assertEqual(payload["decision"], "REFUSE")

    def test_predict_fasta_fixture_no_hmmer(self) -> None:
        code, payload = _cli(
            [
                "predict",
                "--kind",
                "fasta",
                "--input",
                str(FASTA_IN),
                "--runs",
                "1",
                "--",
                PY,
                str(FASTA_TOOL),
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "fasta")
        self.assertEqual(payload["n"], 5)
        self.assertEqual(payload["decision"], "REFUSE")

    def test_predict_cache_miss_fraction(self) -> None:
        argv = ["cat"]
        ns = namespace(argv, "lines", fingerprint_inputs(argv))
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "c.jsonl"
            rows = [
                {"ns": ns, "record": "apple", "output": "apple"},
                {"ns": ns, "record": "banana", "output": "banana"},
            ]
            cache.write_text("".join(json.dumps(r) + "\n" for r in rows))
            report = run_predict(
                kind="lines",
                input_path=LINE_B,
                argv=argv,
                cache_path=cache,
                runs=1,
            )
            self.assertEqual(report.m_detail["mode"], "incremental")
            self.assertEqual(report.m_detail["n_miss_unique"], 2)
            self.assertAlmostEqual(report.m, 0.5)

    def test_missing_tool_is_usage_error(self) -> None:
        buf = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = acts_main(
                ["predict", "--kind", "lines", "--input", str(LINE_IN)]
            )
        self.assertEqual(code, 2)
        self.assertIn("tool after --", err.getvalue())
