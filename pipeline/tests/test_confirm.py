"""Tests for the confirmatory hmmscan prediction machinery.

No downloads. No timing. Does not write results/confirm_*.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "scripts"))

from confirm_predict import (  # noqa: E402
    CACHED_FRAC_MAX,
    PRIMARY_MODE,
    PROBE_ACCOUNT,
    PROBE_N,
    REL_TOL,
    SCREEN_N,
    arm_prediction,
    confirmation_verdict,
    criteria_verbatim,
    probe_cost_P,
    series_from_m,
    singleton_8_sizes,
    within_band,
)
from confirm_select import (  # noqa: E402
    CONFIRM_E_SEED,
    C_ORDERING0_PREFIX30,
    COLLECTION_IDS,
    K12_RE,
    N_GENOMES,
    RECURRENCE_SEED,
    STOCK_POS,
    Assembly,
    c_prefix_indices,
    confirm_e_pool,
    draw_confirm_e,
    excluded_accessions,
    miss_along_order,
    run_order_indices,
)
import predict_hmmer_probe_cost as probe  # noqa: E402
import predict_hmmer_speedup as pred  # noqa: E402
import run_hmmer_savings as sav  # noqa: E402

ACC = PIPE / "results" / "recurrence_accessions.json"
CURVES = PIPE / "results" / "recurrence_curves.json"
SCREEN = PIPE / "results" / "headline_screen.json"
PRED_P = PIPE / "results" / "hmmer_predicted_speedup_with_probe.json"


def _asm(acc: str, strain: str = "", organism: str = "Escherichia coli") -> Assembly:
    return Assembly(
        accession=acc,
        organism=organism,
        strain=strain,
        isolate="",
        version_status="latest",
        assembly_level="Complete Genome",
        genome_rep="Full",
        asm_name="x",
        ftp_path="https://example.invalid/x",
    )


class ProtocolLockTests(unittest.TestCase):
    def test_seed_is_not_recurrence_seed(self) -> None:
        self.assertEqual(CONFIRM_E_SEED, 20260927)
        self.assertEqual(RECURRENCE_SEED, 20260926)
        self.assertNotEqual(CONFIRM_E_SEED, RECURRENCE_SEED)

    def test_primary_is_hmmscan_only(self) -> None:
        self.assertEqual(PRIMARY_MODE, "hmmscan")
        self.assertEqual(COLLECTION_IDS, ("confirm_E", "confirm_C"))

    def test_stock_probe_audit_cited_from_savings(self) -> None:
        self.assertEqual(STOCK_POS, (1, 2, 5, 10, 20, 30))
        self.assertEqual(set(STOCK_POS), sav.STOCK_POS["A"])
        self.assertEqual(PROBE_N, sav.PROBE_N)
        self.assertEqual(PROBE_N, 8)
        self.assertEqual(sav.AUDIT_SEED, 20260927)
        self.assertEqual(sav.AUDIT_P, 0.02)
        self.assertEqual(sav.AUDIT_NONEMPTY_FLOOR, 20)
        self.assertEqual(sav.EXPECTED_MATCH["hmmscan"], "order")

    def test_k12_regex_matches_protocol(self) -> None:
        self.assertTrue(K12_RE.search("Escherichia coli K-12 MG1655"))
        self.assertTrue(K12_RE.search("strain=BW25113"))
        self.assertTrue(K12_RE.search("W3110"))
        self.assertFalse(K12_RE.search("Escherichia coli O157:H7 Sakai"))

    def test_savings_runner_importable_without_main(self) -> None:
        self.assertIn("A", sav.ORDER)
        self.assertNotIn("confirm_E", sav.ORDER)


class ExclusionAndDrawTests(unittest.TestCase):
    def test_excludes_every_a_and_b_accession(self) -> None:
        raw = json.loads(ACC.read_text())
        excluded = excluded_accessions(raw)
        self.assertGreaterEqual(len(excluded), 70)
        for cid in ("A", "B"):
            for genome in raw["collections"][cid]["genomes"]:
                self.assertIn(genome["accession"], excluded)

    def test_pool_drops_excluded_and_k12_keeps_one_per_strain(self) -> None:
        excluded = {"GCF_000000001.1"}
        rows = [
            _asm("GCF_000000001.1", "S1"),
            _asm("GCF_000000002.1", "S1"),
            _asm("GCF_000000003.1", "MG1655", "Escherichia coli K-12"),
            _asm("GCF_000000004.1", "S2"),
            _asm("GCF_000000005.1", "S3"),
        ]
        pool = confirm_e_pool(rows, excluded)
        accs = [r.accession for r in pool]
        self.assertEqual(accs, ["GCF_000000002.1", "GCF_000000004.1", "GCF_000000005.1"])

    def test_draw_is_deterministic_and_accession_sorted(self) -> None:
        pool = [_asm(f"GCF_{i:09d}.1", f"S{i}") for i in range(1, 80)]
        a = draw_confirm_e(pool)
        b = draw_confirm_e(pool)
        self.assertEqual(len(a), N_GENOMES)
        self.assertEqual([r.accession for r in a], [r.accession for r in b])
        self.assertEqual([r.accession for r in a], sorted(r.accession for r in a))

    def test_run_order_is_a_permutation_of_30(self) -> None:
        order = run_order_indices()
        self.assertEqual(len(order), 30)
        self.assertEqual(sorted(order), list(range(30)))
        self.assertEqual(order, run_order_indices())
        self.assertNotEqual(order, list(range(30)))


class CollectionCLockTests(unittest.TestCase):
    def test_prefix_matches_curves_and_protocol(self) -> None:
        curves = json.loads(CURVES.read_text())
        prefix = c_prefix_indices(curves)
        self.assertEqual(prefix, C_ORDERING0_PREFIX30)
        self.assertEqual(len(prefix), 30)
        self.assertEqual(curves["collections"]["C"]["order_seeds"][0], RECURRENCE_SEED)


class MissAndPredictTests(unittest.TestCase):
    def test_miss_along_order_matches_recurrence_definition(self) -> None:
        keysets = [
            {"a", "b", "c"},
            {"b", "c", "d"},
            {"d", "e"},
        ]
        miss = miss_along_order(keysets, [0, 1, 2])
        self.assertEqual(len(miss), 2)
        self.assertAlmostEqual(miss[0], 1.0 - 2.0 / 3.0)
        self.assertAlmostEqual(miss[1], 0.5)

    def test_formula_matches_predict_hmmer_speedup(self) -> None:
        a, b, w, n, m = 10.0, 2.0, 0.5, 100.0, 0.25
        self.assertAlmostEqual(pred.stock_wall(a, b, n), 10.0 + 200.0)
        self.assertAlmostEqual(pred.cached_wall(a, b, w, n, m), 10.0 + 50.0 + 0.5)
        per, cum = series_from_m(a, b, w, [n, n], [m])
        self.assertAlmostEqual(per[0]["cached_wall_s"], 210.0)
        self.assertAlmostEqual(per[1]["cached_wall_s"], 60.5)
        self.assertAlmostEqual(cum[1]["cum_speedup"], 420.0 / (210.0 + 60.5))

    def test_P_matches_locked_singleton_8_file(self) -> None:
        screen = json.loads(SCREEN.read_text())
        params = pred.mode_params(screen)["hmmscan"]
        rec = probe_cost_P(params["a"], params["b"])
        locked = json.loads(PRED_P.read_text())["P"]["hmmscan"]["singleton_8"]
        self.assertEqual(singleton_8_sizes(), locked["sizes"])
        self.assertEqual(rec["n_calls"], 12)
        self.assertEqual(PROBE_ACCOUNT, "singleton_8")
        self.assertAlmostEqual(rec["P_s"], locked["P_s"])
        self.assertAlmostEqual(
            rec["P_s"],
            probe.probe_cost(params["a"], params["b"], locked["sizes"])["P_s"],
        )

    def test_arm_marks_hmmsearch_unscored(self) -> None:
        screen = json.loads(SCREEN.read_text())
        params = pred.mode_params(screen)
        n_list = [SCREEN_N] * 30
        m_along = [0.4] * 29
        scan = arm_prediction(
            mode="hmmscan", params=params["hmmscan"], n_list=n_list, m_along=m_along
        )
        search = arm_prediction(
            mode="hmmsearch", params=params["hmmsearch"], n_list=n_list, m_along=m_along
        )
        self.assertTrue(scan["primary"])
        self.assertTrue(scan["scored"])
        self.assertFalse(search["primary"])
        self.assertFalse(search["scored"])
        self.assertEqual(search["label"], "secondary / not scored")
        self.assertEqual(scan["n_genomes"], 30)
        self.assertAlmostEqual(scan["cached_frac_at_k30"], scan["cum_cached_s"] / scan["cum_stock_s"])


class CriteriaTests(unittest.TestCase):
    def test_verbatim_and_constants(self) -> None:
        lines = criteria_verbatim()
        self.assertEqual(len(lines), 2)
        self.assertIn("±20%", lines[0])
        self.assertIn("0.50", lines[1])
        self.assertEqual(REL_TOL, 0.20)
        self.assertEqual(CACHED_FRAC_MAX, 0.50)

    def test_band_and_frac(self) -> None:
        self.assertTrue(within_band(1.0, 1.0))
        self.assertTrue(within_band(0.80, 1.0))
        self.assertTrue(within_band(1.20, 1.0))
        self.assertFalse(within_band(0.79, 1.0))
        self.assertFalse(within_band(1.21, 1.0))
        ok = confirmation_verdict(
            measured_speedup_with_P=2.9,
            predicted_speedup_with_P=3.0,
            cached_frac=0.49,
        )
        self.assertTrue(ok["confirmed"])
        miss_band = confirmation_verdict(
            measured_speedup_with_P=2.0,
            predicted_speedup_with_P=3.0,
            cached_frac=0.10,
        )
        self.assertFalse(miss_band["confirmed"])
        miss_frac = confirmation_verdict(
            measured_speedup_with_P=3.0,
            predicted_speedup_with_P=3.0,
            cached_frac=0.50,
        )
        self.assertFalse(miss_frac["criterion_2_holds"])
        self.assertFalse(miss_frac["confirmed"])


if __name__ == "__main__":
    unittest.main()
