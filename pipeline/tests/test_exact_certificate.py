"""IC2 predicate, from the DX2 known-bad hole and the HMMER positive control.

The bodies are small. They reproduce the row pattern, not the tool files.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.exact_certificate import judge
from acts.reference_fit import PROBE_N, PROBE_SEED, sample_record_indices
from acts.reference_formats import write_entries, parse_entryline
from acts.reference_run import ReferenceIncremental

FIX = Path(__file__).resolve().parent / "fixtures" / "reference_fitter"


class CertificatePredicateTests(unittest.TestCase):
    def test_dx2_known_bad_extra_candidate_row_fails(self) -> None:
        # DX2-E1: R+ put a stock row back on a candidate subject (VHUA_METVO
        # and NUOI2_GEOMG). The old predicate ignored that line. IC2 does not.
        replay = "qA s_kept 40\n"
        plus = "qA s_kept 40\nqA s_kept 78.2\n"
        verdict = judge(replay, plus, {"s_kept"}, {"s_pad"}, 1)
        self.assertFalse(verdict["pass"])
        self.assertEqual(verdict["fail_mode"], "extra_candidate")
        self.assertEqual(verdict["extra_candidate_rows"], 1)
        self.assertEqual(verdict["pad_hit_rows"], 0)

    def test_hmmer_positive_identical_body_passes(self) -> None:
        # HMMER E1 shape: tblout target name in column 0, same lines in R and
        # R+, and the pad model is absent. The DX3 pilot re-judge passed.
        body = "PF00001.1 - q0 - 1.2e-5 20.1 0.1\nPF00002.1 - q1 - 3.4e-4 15.0 0.2\n"
        verdict = judge(body, body, {"PF00001.1", "PF00002.1"}, {"PF00999.1"}, 0)
        self.assertTrue(verdict["pass"])
        self.assertEqual(verdict["fail_mode"], "pass")
        self.assertEqual(verdict["missing_candidate_rows"], 0)
        self.assertEqual(verdict["extra_candidate_rows"], 0)


class CertificateExactModeTests(unittest.TestCase):
    def test_neighbor_coupling_outside_the_probe_is_refused(self) -> None:
        n = PROBE_N + 1
        held_out = set(range(n)) - set(sample_record_indices(n, PROBE_N, PROBE_SEED))
        self.assertEqual(len(held_out), 1)
        held_key = f"r{next(iter(held_out)):03d}"
        hits = {"e1", "e3"}

        def render(records, entries, scale: float) -> dict[str, str]:
            present = {entry.primary for entry in entries}
            lines = ["# record entry evalue"]
            for rec in records:
                for entry in entries:
                    if entry.primary not in hits:
                        continue
                    lines.append(f"{rec.key} {entry.primary} {scale * float(rec.description):.6f}")
                if rec.key == held_key and "e0" in present and "e9" in present:
                    lines.append(f"{rec.key} e9 {scale * float(rec.description):.6f}")
            return {"out": "\n".join(lines) + "\n"}

        def runner(records, entries):
            return render(records, entries, len(entries))

        def pinned(records, entries, values):
            return render(records, entries, values["entry_count"])

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            query = tmp / "q.faa"
            query.write_text("".join(f">r{i:03d} 1.0\nM\n" for i in range(n)))
            reference = tmp / "ref.entryline"
            write_entries(
                parse_entryline("e0 1\ne1 2\ne2 1\ne3 2\ne9 2\n"),
                reference,
            )
            result = ReferenceIncremental(
                argv=["law", "{reference}", "{input}", "{output}"],
                input_path=query,
                out_dir=tmp / "out",
                reference=reference,
                cache_path=tmp / "cache.sqlite",
                verify="audit",
                runner=runner,
                pin="-Z {entry_count}",
                pin_runner=pinned,
            ).run()
            self.assertEqual(result.decision, "REFUSE", result.reason)
            self.assertIn("IC2", result.reason)
            self.assertIn("extra_candidate", result.reason)
            self.assertFalse((tmp / "out" / "tables" / "out").exists())


if __name__ == "__main__":
    unittest.main()
