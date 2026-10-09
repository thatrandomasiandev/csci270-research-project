"""Synthetic-only tests for scripts/analyze_savings.py.

Invokes the analyzer with explicit tmp / fixture paths so results/ is
never written. Does not create results/savings_* job dumps.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "scripts"))

from analyze_savings import (  # noqa: E402
    DEFAULT_JOB_NAMES,
    ERROR_FLAG,
    EXPECTED_N,
    KILL_FRAC,
    PRIMARY,
    PROBE_ACCOUNT,
    PROBE_N,
    PROBE_N_CALLS,
    PROBE_SIZES,
    STOCK_POS,
    analyze,
    analyze_job,
    discover_jobs,
    load_json,
    main,
    probe_cost_s,
    write_figures,
    write_markdown,
)

FIX = PIPE / "tests" / "fixtures" / "analyze_savings"
PRED = PIPE / "results" / "hmmer_predicted_speedup.json"
PRED_P = PIPE / "results" / "hmmer_predicted_speedup_with_probe.json"

FIT = {
    "hmmscan": {
        "a": 31.959641573764316,
        "b": 0.7228553909794854,
        "w": 0.019063675698513787,
        "N_screen": 4192,
    },
    "hmmsearch": {
        "a": 132.55764028895294,
        "b": 0.11889530446294444,
        "w": 0.018338670022785664,
        "N_screen": 4192,
    },
}
N_I = 200.0


def _stock_pred(mode: str, n_i: float = N_I) -> float:
    fit = FIT[mode]
    return fit["a"] + fit["b"] * n_i


def make_job(
    collection: str,
    mode: str,
    *,
    n: int | None = None,
    cached_frac: float = 0.25,
    fit_err: float = 0.02,
    stop_at: int | None = None,
    stop: str | None = None,
    audit_fail_at: int | None = None,
    match_fail_at: int | None = None,
    resumed: bool = False,
    n_i: float = N_I,
) -> dict:
    """Build a runner-schema payload. Times are synthetic, not from CARC."""
    n = n if n is not None else EXPECTED_N[collection]
    fit = dict(FIT[mode])
    pred = _stock_pred(mode, n_i)
    genomes = []
    for pos in range(1, n + 1):
        sampled = pos in STOCK_POS[collection]
        cached = pred * cached_frac * (0.55 + 0.45 * (pos / n))
        # First genome is all misses: cached ≈ stock.
        if pos == 1:
            cached = pred * (1.0 + fit_err) if sampled else pred
        row: dict = {
            "position": pos,
            "index": pos - 1,
            "accession": f"GCF_SYNTH_{collection}_{pos:03d}.1",
            "strain": f"synth-{collection}-{pos}",
            "N_i": n_i,
            "n_unique": int(n_i),
            "cached_wall_s": cached,
            "cached_cpu_s": cached * 32.0,
            "n_hits": int(n_i * (1.0 - 1.0 / pos)),
            "n_misses": max(1, int(n_i / pos)),
            "n_empty_hits": int(n_i * 0.4),
            "n_nonempty_hits": max(0, int(n_i * 0.1)),
            "match": None,
            "audit": None,
        }
        if sampled:
            row["stock_wall_s"] = pred * (1.0 + fit_err)
            row["stock_cpu_s"] = row["stock_wall_s"] * 32.0
            row["match"] = pos != match_fail_at
        else:
            row["stock_source"] = "predicted a+b*N_i"
            row["audit"] = {
                "n_hits": row["n_hits"],
                "n_checked": 20,
                "n_nonempty_checked": 20,
                "ok": pos != audit_fail_at,
            }
        genomes.append(row)

    payload = {
        "protocol": "pipeline/docs/SAVINGS_PROTOCOL.md",
        "addendum": "2026-09-27 same node",
        "git": "synthetic",
        "collection": collection,
        "mode": mode,
        "path": "paired",
        "paper": "token / whitespace-normalized identity, not byte identity",
        "primary": mode == "hmmsearch",
        "post_hoc": mode == "hmmscan",
        "host": {"hostname": "synthetic"},
        "cpu": 32,
        "fit": fit,
        "resumed": resumed,
        "genomes": genomes,
        "stopped": None,
        "decision": None,
    }
    if stop == "STOP_AUDIT" and audit_fail_at is not None:
        payload["stopped"] = {
            "stopped": True,
            "where": "audit",
            "collection": collection,
            "mode": mode,
            "position": audit_fail_at,
            "accession": f"GCF_SYNTH_{collection}_{audit_fail_at:03d}.1",
            "decision": "STOP_AUDIT",
        }
        payload["decision"] = "STOP_AUDIT"
        payload["genomes"] = [g for g in genomes if g["position"] <= (stop_at or audit_fail_at)]
    elif stop == "STOP_MATCH" and match_fail_at is not None:
        payload["stopped"] = {
            "stopped": True,
            "where": "cached MATCH",
            "collection": collection,
            "mode": mode,
            "position": match_fail_at,
            "decision": "STOP_MATCH",
        }
        payload["decision"] = "STOP_MATCH"
        payload["genomes"] = [g for g in genomes if g["position"] <= (stop_at or match_fail_at)]
    elif stop_at is not None:
        payload["genomes"] = [g for g in genomes if g["position"] <= stop_at]
        payload["resumed"] = True
    return payload


def _dump_jobs(td: Path, jobs: list[dict]) -> list[Path]:
    paths = []
    for job in jobs:
        dest = td / f"{job['collection']}_{job['mode']}.json"
        dest.write_text(json.dumps(job, indent=2) + "\n")
        paths.append(dest)
    return paths


def _pred() -> dict | None:
    return load_json(PRED) if PRED.is_file() else None


def _pred_p() -> dict | None:
    return load_json(PRED_P) if PRED_P.is_file() else None


def _run_main(jobs: list[Path], out: Path) -> int:
    argv = [
        "--jobs",
        *[str(p) for p in jobs],
        "--predicted",
        str(PRED),
        "--predicted-with-probe",
        str(PRED_P),
        "--out-json",
        str(out / "savings_summary.json"),
        "--out-md",
        str(out / "savings_summary.md"),
        "--fig-dir",
        str(out / "figures"),
    ]
    buf = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(err):
        return main(argv)


class ProbeFormulaTests(unittest.TestCase):
    def test_singleton_8_is_twelve_calls(self) -> None:
        self.assertEqual(PROBE_N, 8)
        self.assertEqual(PROBE_ACCOUNT, "singleton_8")
        self.assertEqual(PROBE_N_CALLS, 12)
        self.assertEqual(len(PROBE_SIZES), 12)
        self.assertEqual(PROBE_SIZES, (8, 8, 8, 8, 1, 1, 1, 1, 1, 1, 1, 1))

    def test_P_matches_locked_with_probe_file(self) -> None:
        pred_p = _pred_p()
        self.assertIsNotNone(pred_p)
        for mode in ("hmmsearch", "hmmscan"):
            computed = probe_cost_s(FIT[mode]["a"], FIT[mode]["b"])
            listed = pred_p["P"][mode]["singleton_8"]["P_s"]
            self.assertAlmostEqual(computed, listed, places=6, msg=mode)
            self.assertEqual(pred_p["P"][mode]["singleton_8"]["n_calls"], 12)


class FixtureSchemaTests(unittest.TestCase):
    def test_sample_fixture_is_runner_schema(self) -> None:
        raw = load_json(FIX / "sample_A_hmmsearch.json")
        self.assertEqual(raw["collection"], "A")
        self.assertEqual(raw["mode"], "hmmsearch")
        self.assertTrue(raw["primary"])
        self.assertFalse(raw["post_hoc"])
        self.assertEqual(len(raw["genomes"]), 3)
        g1 = raw["genomes"][0]
        self.assertIn("stock_wall_s", g1)
        self.assertIn("cached_wall_s", g1)
        self.assertIn("N_i", g1)
        g3 = raw["genomes"][2]
        self.assertIsNone(g3.get("stock_wall_s"))
        self.assertTrue(g3["audit"]["ok"])

    def test_sample_fixture_analyzes_as_partial(self) -> None:
        raw = load_json(FIX / "sample_A_hmmsearch.json")
        row = analyze_job(raw, predicted=_pred(), predicted_p=_pred_p(), source="fixture")
        self.assertEqual(row["n_complete"], 3)
        self.assertFalse(row["complete_collection"])
        self.assertTrue(row["primary"])
        self.assertTrue(row["gates"]["ok"])
        self.assertIsNone(row["stop"])
        self.assertAlmostEqual(row["probe"]["P_s"], probe_cost_s(FIT["hmmsearch"]["a"], FIT["hmmsearch"]["b"]))


class PassRunTests(unittest.TestCase):
    def test_pass_cli_writes_only_to_explicit_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jobs_dir = td / "jobs"
            out = td / "out"
            jobs_dir.mkdir()
            out.mkdir()
            default_summary = PIPE / "results" / "savings_summary.json"
            before = default_summary.read_bytes() if default_summary.is_file() else None
            jobs = _dump_jobs(
                jobs_dir,
                [
                    make_job("A", "hmmsearch", cached_frac=0.22),
                    make_job("A", "hmmscan", cached_frac=0.22),
                    make_job("B", "hmmsearch", cached_frac=0.15),
                    make_job("B", "hmmscan", cached_frac=0.12),
                ],
            )
            code = _run_main(jobs, out)
            self.assertEqual(code, 0)
            summary = json.loads((out / "savings_summary.json").read_text())
            md = (out / "savings_summary.md").read_text()
            self.assertFalse(summary["invented"])
            self.assertEqual(summary["primary"], PRIMARY)
            self.assertEqual(summary["paper_uses"], "hmmsearch")
            self.assertTrue(summary["gates_ok"])
            self.assertFalse(summary["diverse_collection_headline_fails"])
            self.assertIn("hmmsearch (PRIMARY)", md)
            self.assertIn("hmmscan (post-hoc)", md)
            self.assertIn("singleton_8", md)
            self.assertIn("probe_n = 8", md)
            self.assertNotIn("paper_uses = hmmscan", md.lower().replace("`", ""))
            figs = list((out / "figures").glob("*.png"))
            names = {p.name for p in figs}
            self.assertEqual(
                names,
                {
                    "25_savings_cum_wall.png",
                    "26_savings_speedup_vs_k.png",
                    "27_savings_cum_with_without_P.png",
                    "28_savings_stock_pred_error.png",
                },
            )
            results_savings = PIPE / "results" / "savings"
            if results_savings.is_dir():
                leaked = list(results_savings.glob("savings_A*")) + list(results_savings.glob("savings_B*"))
                self.assertEqual(leaked, [])
            default_summary = PIPE / "results" / "savings_summary.json"
            after = default_summary.read_bytes() if default_summary.is_file() else None
            self.assertEqual(before, after)

    def test_pass_formulas(self) -> None:
        job = make_job("A", "hmmsearch", cached_frac=0.2, fit_err=0.0)
        row = analyze_job(job, predicted=_pred(), predicted_p=_pred_p(), source="mem")
        pred = _stock_pred("hmmsearch")
        n = EXPECTED_N["A"]
        # Genome 1 cached = stock (all misses); others cached_frac * ramp.
        cached = 0.0
        stock = 0.0
        for g in job["genomes"]:
            stock += g.get("stock_wall_s") or pred
            cached += g["cached_wall_s"]
        self.assertAlmostEqual(row["cumulative"]["stock_wall_s"], stock)
        self.assertAlmostEqual(row["cumulative"]["cached_wall_s"], cached)
        p_s = probe_cost_s(FIT["hmmsearch"]["a"], FIT["hmmsearch"]["b"])
        self.assertAlmostEqual(row["probe"]["P_s"], p_s)
        self.assertAlmostEqual(row["cumulative"]["cached_with_P_wall_s"], p_s + cached)
        self.assertAlmostEqual(
            row["cumulative"]["cum_speedup_wall"],
            stock / cached,
        )
        self.assertAlmostEqual(
            row["cumulative"]["cum_speedup_wall_with_P"],
            stock / (p_s + cached),
        )
        self.assertEqual(row["n_complete"], n)
        self.assertTrue(row["complete_collection"])
        self.assertEqual(row["fit_error_flags"], [])
        # k = position - 1; Part 2 lookup starts at k >= 1.
        g2 = row["per_genome"][1]
        self.assertEqual(g2["k"], 1)
        self.assertIsNotNone(g2["predicted_speedup_part2"])
        self.assertGreater(g2["measured_speedup"], 1.0)


class StopAuditTests(unittest.TestCase):
    def test_stop_audit_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jobs_dir = td / "jobs"
            out = td / "out"
            jobs_dir.mkdir()
            out.mkdir()
            job = make_job(
                "A",
                "hmmsearch",
                stop="STOP_AUDIT",
                audit_fail_at=3,
                stop_at=3,
            )
            paths = _dump_jobs(jobs_dir, [job])
            code = _run_main(paths, out)
            self.assertEqual(code, 3)
            summary = json.loads((out / "savings_summary.json").read_text())
            md = (out / "savings_summary.md").read_text()
            self.assertIn("STOP_AUDIT", summary["stops"])
            self.assertFalse(summary["gates_ok"])
            self.assertFalse(summary["headline_ok"])
            self.assertIn("STOP_AUDIT", md)
            row = summary["jobs"][0]
            self.assertEqual(row["stop"], "STOP_AUDIT")
            self.assertEqual(row["n_complete"], 3)
            self.assertFalse(row["complete_collection"])
            self.assertEqual(row["gates"]["audit_failures"][0]["position"], 3)


class PartialResumeTests(unittest.TestCase):
    def test_partial_prefix_not_evaluable_for_kill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jobs_dir = td / "jobs"
            out = td / "out"
            jobs_dir.mkdir()
            out.mkdir()
            job = make_job("A", "hmmscan", n=8, stop_at=8, resumed=True, cached_frac=0.2)
            # make_job with n=8 already truncates; mark resumed.
            job["resumed"] = True
            paths = _dump_jobs(jobs_dir, [job])
            code = _run_main(paths, out)
            self.assertEqual(code, 0)
            summary = json.loads((out / "savings_summary.json").read_text())
            md = (out / "savings_summary.md").read_text()
            row = summary["jobs"][0]
            self.assertTrue(row["resumed"])
            self.assertEqual(row["n_complete"], 8)
            self.assertFalse(row["complete_collection"])
            self.assertFalse(row["kill"]["evaluable"])
            self.assertIn("incomplete", row["kill"]["reason"])
            self.assertFalse(summary["diverse_collection_headline_fails"])
            self.assertIn("Not yet evaluable", md)
            self.assertIn("No 3× sentence", md)


class KillRuleTests(unittest.TestCase):
    def test_kill_trips_when_cached_not_below_half(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            jobs_dir = td / "jobs"
            out = td / "out"
            jobs_dir.mkdir()
            out.mkdir()
            # cached_frac=0.70 keeps cumulative cached ≥ 50% of stock
            # even after genome-1 ≈ stock (the first term is large).
            job = make_job("A", "hmmscan", cached_frac=0.70, fit_err=0.0)
            pred = _stock_pred("hmmscan")
            stock = sum(g.get("stock_wall_s") or pred for g in job["genomes"])
            cached = sum(g["cached_wall_s"] for g in job["genomes"])
            self.assertGreaterEqual(cached, KILL_FRAC * stock)
            paths = _dump_jobs(jobs_dir, [job])
            code = _run_main(paths, out)
            self.assertEqual(code, 0)
            summary = json.loads((out / "savings_summary.json").read_text())
            md = (out / "savings_summary.md").read_text()
            self.assertTrue(summary["diverse_collection_headline_fails"])
            self.assertTrue(summary["kill"]["fails"])
            self.assertFalse(summary["kill"]["includes_P"])
            self.assertFalse(summary["headline_ok"])
            self.assertIn("Diverse-collection headline fails", md)
            self.assertIn("Stop talking about 3× on A", md)
            # Kill uses totals without P.
            row = summary["jobs"][0]
            self.assertAlmostEqual(row["kill"]["cached_over_stock"], cached / stock)

    def test_kill_does_not_trip_when_cached_below_half(self) -> None:
        job = make_job("A", "hmmscan", cached_frac=0.20, fit_err=0.0)
        row = analyze_job(job, predicted=_pred(), predicted_p=_pred_p(), source="mem")
        self.assertTrue(row["kill"]["evaluable"])
        self.assertFalse(row["kill"]["fails"])
        self.assertLess(row["kill"]["cached_over_stock"], KILL_FRAC)


class FitErrorAndMatchTests(unittest.TestCase):
    def test_sampled_error_over_10_percent_is_flagged(self) -> None:
        job = make_job("A", "hmmsearch", fit_err=0.15, cached_frac=0.2)
        row = analyze_job(job, predicted=_pred(), predicted_p=_pred_p(), source="mem")
        self.assertTrue(row["fit_error_flags"])
        for flag in row["fit_error_flags"]:
            self.assertGreater(flag["rel_error"], ERROR_FLAG)
            self.assertIn(flag["genome"], STOCK_POS["A"])

    def test_stop_match(self) -> None:
        job = make_job("A", "hmmsearch", stop="STOP_MATCH", match_fail_at=1, stop_at=1)
        row = analyze_job(job, predicted=_pred(), predicted_p=_pred_p(), source="mem")
        self.assertEqual(row["stop"], "STOP_MATCH")
        self.assertFalse(row["gates"]["ok"])
        self.assertEqual(row["gates"]["match_failures"][0]["position"], 1)


class IsolationTests(unittest.TestCase):
    def test_discover_ignores_summary_and_job_dump_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            (td / "savings_summary.json").write_text(json.dumps({"collection": "A", "mode": "hmmsearch", "genomes": []}))
            (td / "savings_A_hmmsearch.json").write_text(
                json.dumps({"collection": "A", "mode": "hmmsearch", "genomes": [{"position": 1, "N_i": 1}]})
            )
            (td / "A_hmmsearch.json").write_text(json.dumps(make_job("A", "hmmsearch", n=2)))
            found = discover_jobs([td])
            self.assertEqual([p.name for p in found], ["A_hmmsearch.json"])

    def test_no_jobs_exits_2_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            empty = td / "empty"
            empty.mkdir()
            out_json = td / "savings_summary.json"
            argv = [
                "--jobs",
                str(empty),
                "--out-json",
                str(out_json),
                "--out-md",
                str(td / "savings_summary.md"),
                "--fig-dir",
                str(td / "fig"),
            ]
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                code = main(argv)
            self.assertEqual(code, 2)
            self.assertIn("refusing to invent numbers", err.getvalue())
            self.assertFalse(out_json.exists())

    def test_refuses_job_dump_output_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job = td / "A_hmmsearch.json"
            job.write_text(json.dumps(make_job("A", "hmmsearch", n=2)))
            argv = [
                "--jobs",
                str(job),
                "--out-json",
                str(td / "savings_A_hmmsearch.json"),
                "--out-md",
                str(td / "savings_summary.md"),
                "--fig-dir",
                str(td / "fig"),
            ]
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                code = main(argv)
            self.assertEqual(code, 2)
            self.assertIn("refusing to write job-dump name", err.getvalue())
            self.assertFalse((td / "savings_A_hmmsearch.json").exists())

    def test_markdown_does_not_promote_hmmscan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job = make_job("A", "hmmscan", cached_frac=0.2)
            path = _dump_jobs(td, [job])[0]
            summary = analyze([path], predicted=_pred(), predicted_p=_pred_p())
            md = write_markdown(summary)
            self.assertIn("hmmscan (post-hoc)", md)
            self.assertIn("`paper_uses`:** hmmsearch", md)
            self.assertIn("hmmscan is post-hoc", md)
            figs = write_figures(summary, td / "fig")
            self.assertTrue(all(name.startswith(("25_", "26_", "27_", "28_")) for name in figs))
            self.assertEqual(DEFAULT_JOB_NAMES[0], "A_hmmsearch.json")


if __name__ == "__main__":
    unittest.main()
