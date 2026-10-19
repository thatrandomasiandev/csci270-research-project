"""Cold-cache audit, the miss-probability sample size, and first-use checks.

The bodies are a small entry-local law. They are not a tool file.
"""

from __future__ import annotations

import math
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.audit import (
    AUDIT_EPSILON,
    AUDIT_K_MIN_FRACTION,
    AUDIT_SEED,
    audit_miss_probability,
    bounded_audit_size,
    with_replacement_miss,
)
from acts.exact_certificate import sample_keys
from acts.reference_cache import program_binary
from acts.reference_fit import PROBE_N, PROBE_SEED, sample_record_indices
from acts.reference_formats import parse_entryline, write_entries
from acts.reference_run import IC2_SAMPLE_SEED, IC2_SAMPLE_SIZE, ReferenceIncremental


def _law(drop_key: str | None, far: str, hit: str):
    def render(records, entries, scale: float) -> dict[str, str]:
        present = {entry.primary for entry in entries}
        lines = ["# record entry evalue"]
        for rec in records:
            if hit not in present:
                continue
            if drop_key is not None and rec.key == drop_key and far not in present:
                continue
            lines.append(f"{rec.key} {hit} {scale * float(rec.description):.6f}")
        return {"out": "\n".join(lines) + "\n"}

    def runner(records, entries):
        return render(records, entries, len(entries))

    def pinned(records, entries, values):
        return render(records, entries, values["entry_count"])

    return runner, pinned


def _queries(path: Path, n: int) -> None:
    path.write_text("".join(f">r{i:03d} 1.0\nM\n" for i in range(n)))


def _reference(path: Path, n_entries: int) -> None:
    # Unequal lengths, so an entry-count factor is not a length factor.
    text = "".join(f"e{i} {1 + (i % 2)}\n" for i in range(n_entries))
    write_entries(parse_entryline(text), path)


class BoundFormulaTests(unittest.TestCase):
    def test_default_constants_are_299(self) -> None:
        size = bounded_audit_size(10_000, epsilon=AUDIT_EPSILON, fraction=AUDIT_K_MIN_FRACTION)
        self.assertEqual(size, 299)
        self.assertLessEqual(with_replacement_miss(fraction=0.01, size=299), 0.05)
        self.assertGreater(with_replacement_miss(fraction=0.01, size=298), 0.05)
        raw = math.log(0.05) / math.log(0.99)
        self.assertEqual(size, math.ceil(raw - 1e-12))

    def test_hypergeometric_miss_is_at_most_the_bound(self) -> None:
        size = bounded_audit_size(10_000)
        miss = audit_miss_probability(n=10_000, k=100, s=size, skipped=False)
        self.assertLessEqual(miss, AUDIT_EPSILON)
        self.assertLessEqual(miss, with_replacement_miss(fraction=0.01, size=size))

    def test_size_is_capped_at_n(self) -> None:
        self.assertEqual(bounded_audit_size(10, epsilon=0.05, fraction=0.01), 10)
        self.assertEqual(bounded_audit_size(0), 0)


class ColdAuditTests(unittest.TestCase):
    def test_cold_cache_still_audits_a_correct_replay(self) -> None:
        runner, pinned = _law(None, "e9", "e1")
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            query = tmp / "q.faa"
            reference = tmp / "ref.entryline"
            _queries(query, 40)
            _reference(reference, 8)
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
            self.assertEqual(result.decision, "SHIP", result.reason)
            self.assertEqual(result.extra["reused_rows"], 0)
            self.assertGreater(result.extra["audit_checked"], 0)
            self.assertIn("checked", result.extra["audit"])
            self.assertNotIn("first_use", result.extra)
            self.assertEqual(result.extra["audit_mode"], "bernoulli")

    def test_cold_cache_audit_refuses_a_far_model_the_pads_do_not_see(self) -> None:
        n = PROBE_N + 20
        probe = set(sample_record_indices(n, PROBE_N, PROBE_SEED))
        keys = [f"r{i:03d}" for i in range(n)]
        pads = set(sample_keys(keys, IC2_SAMPLE_SIZE, IC2_SAMPLE_SEED))
        hidden = [keys[i] for i in range(n) if i not in probe and keys[i] not in pads]
        self.assertTrue(hidden, "the pilot complement must leave a record off both samples")
        affected = hidden[0]
        runner, pinned = _law(affected, "e11", "e5")
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            query = tmp / "q.faa"
            reference = tmp / "ref.entryline"
            _queries(query, n)
            _reference(reference, 12)
            result = ReferenceIncremental(
                argv=["law", "{reference}", "{input}", "{output}"],
                input_path=query,
                out_dir=tmp / "out",
                reference=reference,
                cache_path=tmp / "cache.sqlite",
                verify="audit",
                audit_p=1.0,
                runner=runner,
                pin="-Z {entry_count}",
                pin_runner=pinned,
            ).run()
            self.assertEqual(result.extra["reused_rows"], 0)
            self.assertEqual(result.decision, "REFUSE_AUDIT", result.reason)
            self.assertIn("audited records differ", result.reason)
            self.assertGreater(result.extra["audit_checked"], 0)

    def test_bounded_draw_uses_the_requested_size_on_a_cold_cache(self) -> None:
        runner, pinned = _law(None, "e9", "e1")
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            query = tmp / "q.faa"
            reference = tmp / "ref.entryline"
            _queries(query, 40)
            _reference(reference, 8)
            result = ReferenceIncremental(
                argv=["law", "{reference}", "{input}", "{output}"],
                input_path=query,
                out_dir=tmp / "out",
                reference=reference,
                cache_path=tmp / "cache.sqlite",
                verify="audit",
                audit_bound=True,
                audit_size=7,
                runner=runner,
                pin="-Z {entry_count}",
                pin_runner=pinned,
            ).run()
            self.assertEqual(result.decision, "SHIP", result.reason)
            self.assertEqual(result.extra["reused_rows"], 0)
            self.assertEqual(result.extra["audit_mode"], "bounded")
            self.assertEqual(result.extra["audit_checked"], 7)
            self.assertEqual(result.extra["audit_s_target"], 7)
            self.assertEqual(result.extra["audit_sizing"], "with-replacement")

    def test_one_record_still_skips_a_bounded_audit(self) -> None:
        runner, pinned = _law(None, "e9", "e1")
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            query = tmp / "q.faa"
            reference = tmp / "ref.entryline"
            _queries(query, 1)
            _reference(reference, 4)
            result = ReferenceIncremental(
                argv=["law", "{reference}", "{input}", "{output}"],
                input_path=query,
                out_dir=tmp / "out",
                reference=reference,
                cache_path=tmp / "cache.sqlite",
                verify="audit",
                audit_bound=True,
                runner=runner,
                pin="-Z {entry_count}",
                pin_runner=pinned,
            ).run()
            self.assertEqual(result.decision, "SHIP", result.reason)
            self.assertEqual(result.extra["audit"], "skipped, input below record granularity")
            self.assertEqual(result.extra["audit_checked"], 0)


class FirstUseTests(unittest.TestCase):
    def test_first_two_updates_are_full_and_the_third_is_sampled(self) -> None:
        runner, pinned = _law(None, "e9", "e1")
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            query = tmp / "q.faa"
            reference = tmp / "ref.entryline"
            _queries(query, 40)
            _reference(reference, 8)
            cache = tmp / "cache.sqlite"
            kwargs = dict(
                argv=["law", "{reference}", "{input}", "{output}"],
                input_path=query,
                reference=reference,
                cache_path=cache,
                verify="audit",
                audit_size=5,
                first_use_k=2,
                runner=runner,
                pin="-Z {entry_count}",
                pin_runner=pinned,
            )
            modes = []
            for index in range(3):
                result = ReferenceIncremental(out_dir=tmp / f"u{index}", **kwargs).run()
                self.assertEqual(result.decision, "SHIP", result.reason)
                modes.append(result.extra["first_use"])
            self.assertEqual([row["mode"] for row in modes], ["full", "full", "sampled"])
            self.assertEqual([row["index"] for row in modes], [0, 1, 2])
            self.assertEqual(modes[2]["k"], 2)
            third = ReferenceIncremental(out_dir=tmp / "again", **kwargs).run()
            # The third update already advanced the counter, so this is the fourth.
            self.assertEqual(third.extra["first_use"]["mode"], "sampled")
            self.assertEqual(third.extra["audit_checked"], 5)

    def test_a_new_binary_restarts_the_window(self) -> None:
        runner, pinned = _law(None, "e9", "e1")
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            query = tmp / "q.faa"
            reference = tmp / "ref.entryline"
            _queries(query, 30)
            _reference(reference, 6)
            cache = tmp / "cache.sqlite"
            first = tmp / "bin-a"
            second = tmp / "bin-b"
            first.write_text("alpha\n")
            second.write_text("beta\n")
            for path in (first, second):
                path.chmod(path.stat().st_mode | stat.S_IEXEC)
            self.assertNotEqual(program_binary([str(first)])["digest"], program_binary([str(second)])["digest"])

            def once(binary: Path, name: str):
                return ReferenceIncremental(
                    argv=[str(binary), "{reference}", "{input}", "{output}"],
                    input_path=query,
                    out_dir=tmp / name,
                    reference=reference,
                    cache_path=cache,
                    verify="audit",
                    audit_size=4,
                    first_use_k=2,
                    runner=runner,
                    pin="-Z {entry_count}",
                    pin_runner=pinned,
                ).run()

            opened = once(first, "a0")
            again = once(first, "a1")
            other = once(second, "b0")
            self.assertEqual(opened.extra["first_use"]["index"], 0)
            self.assertEqual(again.extra["first_use"]["index"], 1)
            self.assertEqual(other.extra["first_use"]["index"], 0)
            self.assertNotEqual(opened.extra["first_use"]["namespace"], other.extra["first_use"]["namespace"])
            self.assertEqual(opened.extra["first_use"]["mode"], "full")
            self.assertEqual(other.extra["first_use"]["mode"], "full")


if __name__ == "__main__":
    unittest.main()
