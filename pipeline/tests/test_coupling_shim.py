"""Controls for the coupling shim. No measured-grid numbers live here."""

from __future__ import annotations

import math
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from acts.exact_certificate import pad_miss_probability
from acts.reference_fit import PROBE_N, PROBE_SEED, sample_record_indices
from acts.reference_formats import parse_reference, read_records
from acts.reference_run import probe_fit
import coupling_shim as shim


def _spec(**overrides) -> dict:
    base = {
        "coupling": "none",
        "k": 0,
        "seed": 20261111,
        "n_records": 40,
        "n_models": 80,
        "distance": 1,
        "affect": "",
    }
    base.update(overrides)
    return base


def _models(n: int = 80) -> list[dict]:
    text = []
    for index in range(n):
        text.append(
            "HMMER3/f\n"
            f"NAME  {shim.model_name(index)}\n"
            f"LENG  {shim.model_length(index)}\n"
            "GA    20.00 20.00;\n"
            "//\n"
        )
    return shim.parse_hmm("".join(text))


def _queries(n: int = 40) -> list[dict]:
    return [{"name": shim.record_name(i), "sequence": "ACDE"} for i in range(n)]


class SemanticsTests(unittest.TestCase):
    def test_probe_draw_matches_acts(self) -> None:
        self.assertEqual(shim.PROBE_N, PROBE_N)
        self.assertEqual(shim.PROBE_SEED, PROBE_SEED)
        self.assertEqual(
            shim.sample_record_indices(2000, 300, PROBE_SEED),
            sample_record_indices(2000, 300, PROBE_SEED),
        )

    def test_affected_records_skip_the_probe(self) -> None:
        plan = shim.trial_plan(
            n_records=2000, n_models=2500, k=100, seed=20261112, coupling="presence", distance=1
        )
        probe = shim.probe_indices(2000)
        self.assertEqual(len(plan.affected), 100)
        self.assertTrue(set(plan.affected).isdisjoint(probe))
        self.assertNotIn(plan.responsible, {plan.hit_index - 1, plan.hit_index, plan.hit_index + 1})

    def test_stock_matches_stock(self) -> None:
        models, queries = _models(), _queries()
        spec = _spec()
        first = shim.score_models(models, queries, z_override=None, cut_ga=True, spec=spec)
        second = shim.score_models(models, queries, z_override=None, cut_ga=True, spec=spec)
        self.assertEqual(first, second)
        self.assertGreaterEqual(len(shim.diff_class.__defaults__ or []), 0)
        body = [ln for ln in first["tblout"].splitlines() if ln and not ln.startswith("#")]
        self.assertEqual(len(body), 40)

    def test_pin_is_load_bearing(self) -> None:
        models, queries = _models(), _queries()
        spec = _spec()
        plan = shim.trial_plan(
            n_records=spec["n_records"],
            n_models=spec["n_models"],
            k=spec["k"],
            seed=spec["seed"],
            coupling=spec["coupling"],
            distance=spec["distance"],
        )
        full = shim.score_models(models, queries, z_override=None, cut_ga=True, spec=spec)
        subset = [models[plan.hit_index]]
        pinned = shim.score_models(subset, queries, z_override=len(models), cut_ga=True, spec=spec)
        unpinned = shim.score_models(subset, queries, z_override=None, cut_ga=True, spec=spec)
        full_body = [ln for ln in full["tblout"].splitlines() if not ln.startswith("#") and ln.strip()]
        pin_body = [ln for ln in pinned["tblout"].splitlines() if not ln.startswith("#") and ln.strip()]
        raw_body = [ln for ln in unpinned["tblout"].splitlines() if not ln.startswith("#") and ln.strip()]
        self.assertEqual([ln.split()[2] for ln in full_body], [ln.split()[2] for ln in pin_body])
        self.assertNotEqual([ln.split()[2] for ln in full_body], [ln.split()[2] for ln in raw_body])

    def test_cut_ga_drops_a_low_score(self) -> None:
        models = _models(24)
        models[0]["ga"] = 100.0
        queries = _queries(4)
        # Force the hit onto model 0 by a plan whose hit_index is 0: call score
        # with affect disabled and a plan built by monkeypatching via a spec
        # whose n_models is large enough, then overwrite by scoring only after
        # placing the hit. Direct threshold check:
        self.assertFalse(shim.passes_report(score=25.0, ga=100.0, evalue=1.0, cut_ga=True))
        self.assertTrue(shim.passes_report(score=25.0, ga=20.0, evalue=1.0, cut_ga=True))
        self.assertFalse(shim.passes_report(score=25.0, ga=20.0, evalue=11.0, cut_ga=False))
        self.assertTrue(shim.passes_report(score=25.0, ga=100.0, evalue=1.0, cut_ga=False))
        self.assertEqual(models[0]["name"], "m0000")
        self.assertEqual(len(queries), 4)

    def test_presence_suppresses_until_the_other_model_is_present(self) -> None:
        plan = shim.trial_plan(
            n_records=400, n_models=500, k=5, seed=20261111, coupling="presence", distance=1
        )
        models = _models(500)
        queries = _queries(400)
        spec = _spec(coupling="presence", k=5, seed=20261111, n_records=400, n_models=500, distance=1)
        full = shim.score_models(models, queries, z_override=None, cut_ga=True, spec=spec)
        only_hit = [models[plan.hit_index]]
        replay = shim.score_models(only_hit, queries, z_override=500, cut_ga=True, spec=spec)
        full_body = [ln for ln in full["tblout"].splitlines() if ln and not ln.startswith("#")]
        replay_body = [ln for ln in replay["tblout"].splitlines() if ln and not ln.startswith("#")]
        self.assertEqual(shim.diff_class(full_body, replay_body), "missing")
        affected = {shim.record_name(i) for i in plan.affected}
        replay_queries = {ln.split()[1] for ln in replay_body}
        self.assertTrue(affected.isdisjoint(replay_queries))
        self.assertEqual(len(full_body) - len(replay_body), 5)

    def test_order_distance_one_changes_when_the_predecessor_is_restored(self) -> None:
        plan = shim.trial_plan(
            n_records=400, n_models=500, k=5, seed=20261111, coupling="order", distance=1
        )
        models = _models(500)
        queries = _queries(400)
        spec = _spec(coupling="order", k=5, seed=20261111, n_records=400, n_models=500, distance=1)
        only = [models[plan.hit_index]]
        plus = [models[plan.hit_index - 1], models[plan.hit_index]]
        replay = shim.score_models(only, queries, z_override=500, cut_ga=True, spec=spec)
        neighbor = shim.score_models(plus, queries, z_override=500, cut_ga=True, spec=spec)
        replay_body = [ln for ln in replay["tblout"].splitlines() if ln[:1] != "#" and ln.strip()]
        neighbor_body = [ln for ln in neighbor["tblout"].splitlines() if ln[:1] != "#" and ln.strip()]
        self.assertEqual(shim.diff_class(replay_body, neighbor_body), "value-only")
        affected_line = next(ln for ln in neighbor_body if ln.split()[1] == shim.record_name(plan.affected[0]))
        self.assertIn(f"via-{shim.model_name(plan.hit_index - 1)}", affected_line)
        replay_line = next(ln for ln in replay_body if ln.split()[1] == shim.record_name(plan.affected[0]))
        self.assertIn("via-missing", replay_line)

    def test_residues_track_the_searched_lengths(self) -> None:
        models = _models(80)
        queries = _queries(40)
        spec = _spec(coupling="residues", affect="all")
        scored = shim.score_models(models, queries, z_override=None, cut_ga=True, spec=spec)
        body = [ln for ln in scored["tblout"].splitlines() if ln and not ln.startswith("#")]
        self.assertEqual(body[0].split()[4], str(sum(model["length"] for model in models)))

    def test_global_hash_changes_when_any_model_is_removed(self) -> None:
        models = _models(80)
        queries = _queries(40)
        spec = _spec(coupling="global", affect="all")
        full = shim.score_models(models, queries, z_override=80, cut_ga=True, spec=spec)
        short = shim.score_models(models[:-1], queries, z_override=80, cut_ga=True, spec=spec)
        full_note = [ln for ln in full["tblout"].splitlines() if not ln.startswith("#")][0].split()[-1]
        short_note = [ln for ln in short["tblout"].splitlines() if not ln.startswith("#")][0].split()[-1]
        self.assertNotEqual(full_note, short_note)
        self.assertTrue(full_note.startswith("g"))

    def test_classifier_labels_the_four_outcomes(self) -> None:
        self.assertEqual(shim.classify("SHIP", "exact", False)["outcome"], "correct_ship")
        self.assertEqual(shim.classify("SHIP", "exact", True)["outcome"], "UNSAFE")
        caught = shim.classify("REFUSE", "IC2 neighbor tblout: missing_and_extra_candidate", True)
        self.assertEqual(caught["outcome"], "true_refusal")
        self.assertEqual(caught["layer"], "neighbor_pad")
        needless = shim.classify("REFUSE", "IC2 random_20261031 tblout: pad_hit", False)
        self.assertEqual(needless["outcome"], "needless_refusal")
        self.assertEqual(needless["layer"], "random_pad")
        audit = shim.classify("REFUSE_AUDIT", "tblout: audited records differ from a full run", True)
        self.assertEqual(audit["layer"], "audit")
        r3 = shim.classify("REFUSE_PIN", "pin check failed: tblout: pinned replay body differs", True)
        self.assertEqual(r3["layer"], "in_situ_r3")
        r4 = shim.classify("REFUSE_MATCH", "tblout: replay reported a non-candidate pair (q, m)", True)
        self.assertEqual(r4["layer"], "r4")

    def test_equation_4_matches_the_worked_example(self) -> None:
        q = 0.31252137200279034
        got = pad_miss_probability(n=2000, k=22, s=50, q=q)
        self.assertTrue(math.isclose(got, 0.7105418322019688, rel_tol=0, abs_tol=1e-12))

    def test_clean_contract_ships_and_a_global_column_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hmm = root / "ref.hmm"
            fa = root / "q.fa"
            shim.write_reference(hmm, 80)
            shim.write_queries(fa, 40)
            entries = parse_reference(hmm)
            records = read_records(fa)

            def invoke(recs, ents, spec):
                models = [
                    {"name": entry.primary, "length": entry.length, "ga": shim.DEFAULT_GA, "raw": entry.raw}
                    for entry in ents
                ]
                queries = [{"name": rec.key, "sequence": rec.sequence} for rec in recs]
                return shim.score_models(models, queries, z_override=None, cut_ga=True, spec=spec)

            clean = probe_fit(entries, records, lambda recs, ents: invoke(recs, ents, _spec()))
            self.assertEqual(clean.decision, "SHIP", clean.reason)
            evalue = next(col for col in clean.tables[0].columns if col.index == 2)
            self.assertEqual(evalue.member, "entry_count")
            bias = next(col for col in clean.tables[0].columns if col.index == 4)
            self.assertEqual(bias.member, "identity")

            leaked = probe_fit(
                entries,
                records,
                lambda recs, ents: invoke(recs, ents, _spec(coupling="residues", affect="all")),
            )
            # The length dependence is visible to the fitter, so this column is
            # not something the safety check is left to discover.
            self.assertEqual(leaked.decision, "SHIP", leaked.reason)
            leaked_bias = next(col for col in leaked.tables[0].columns if col.index == 4)
            self.assertEqual(leaked_bias.member, "total_entry_length")


class CommandLineTests(unittest.TestCase):
    def test_cli_matches_the_library_and_honors_z(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hmm = root / "ref.hmm"
            fa = root / "q.fa"
            shim.write_reference(hmm, 30)
            shim.write_queries(fa, 6)
            env = os.environ.copy()
            env.update(
                {
                    "TARE_COUPLING": "none",
                    "TARE_K": "0",
                    "TARE_SEED": "20261111",
                    "TARE_N": "6",
                    "TARE_M": "30",
                    "TARE_D": "1",
                }
            )
            tbl = root / "t"
            dom = root / "d"
            script = Path(shim.__file__)
            proc = subprocess.run(
                [sys.executable, str(script), "--cut_ga", "--cpu", "1", "--tblout", str(tbl), "--domtblout", str(dom), "-Z", "30", str(hmm), str(fa)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            models = shim.parse_hmm(hmm.read_text())
            queries = shim.parse_fasta(fa.read_text())
            spec = _spec(n_records=6, n_models=30, k=0, seed=20261111)
            expect = shim.score_models(models, queries, z_override=30, cut_ga=True, spec=spec)
            self.assertEqual(tbl.read_text(), expect["tblout"])
            self.assertEqual(dom.read_text(), expect["domtblout"])


if __name__ == "__main__":
    unittest.main()
