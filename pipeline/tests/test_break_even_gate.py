"""Update gate: run stock when the changed fraction cannot pay.

The fractions are the one-decimal release figures: 931/1000 and 134/1000.
The comparison is strict. A cold cache is a fill and is not gated.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.reference_cache import connect_cache
from acts.reference_formats import parse_entryline, parse_reference, read_records, write_entries
from acts.reference_run import (
    DEFAULT_BREAK_EVEN_F,
    ReferenceIncremental,
    body_lines,
    break_even_f,
    fallback_reason,
    namespace_for,
)

ARGV = ["law", "{reference}", "{input}", "{output}"]
PIN = "-Z {entry_count}"


def _entryline(n: int, fresh: int, *, edited: bool) -> str:
    # Lengths vary so entry count and total length are different fits.
    # Editing adds 50 only to the changed prefix, which moves those hashes.
    lines = []
    for index in range(n):
        length = (index % 5) + 1
        if edited and index < fresh:
            length += 50
        lines.append(f"e{index:04d} {length}")
    return "\n".join(lines) + "\n"


def _render(records, entries, scale: float, hit: str) -> dict[str, str]:
    lines = ["# record entry evalue"]
    for rec in records:
        for entry in entries:
            if entry.primary != hit:
                continue
            lines.append(f"{rec.key} {entry.primary} {scale * float(rec.description):.6f}")
    return {"out": "\n".join(lines) + "\n"}


class BreakEvenMathTests(unittest.TestCase):
    def test_laptop_coefficients_round_to_the_documented_default(self) -> None:
        self.assertEqual(DEFAULT_BREAK_EVEN_F, 0.80)
        threshold = break_even_f(1.06, 0.152)
        self.assertIsNotNone(threshold)
        self.assertEqual(f"{threshold:.6f}", "0.800000")
        self.assertIsNone(break_even_f(1.0, 1.0))
        self.assertIsNone(break_even_f(0.0, 0.1))
        self.assertIsNone(break_even_f(-1.0, 0.1))

    def test_history_mean_matches_the_cost_model(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cache = connect_cache(Path(raw) / "c.sqlite")
            # a = discovery / (f * stock) = 5 / (0.5 * 1) = 10; c = 0.
            cache.add_cost_observation(
                "ns", kind="update", f_delta=0.5, stock_s=1.0, tare_s=5.0, discovery_s=5.0
            )
            fit = cache.cost_fit("ns")
            self.assertEqual(fit["n"], 1)
            self.assertEqual(fit["a"], 10.0)
            self.assertEqual(fit["c"], 0.0)
            self.assertEqual(break_even_f(fit["a"], fit["c"]), 0.1)
            cache.add_cost_observation(
                "ns", kind="update", f_delta=0.0, stock_s=1.0, tare_s=1.0, discovery_s=1.0
            )
            self.assertEqual(cache.cost_fit("ns")["n"], 1)
            cache.close()


class BreakEvenGateTests(unittest.TestCase):
    def _world(self, tmp: Path, n: int, fresh: int):
        old = tmp / "old.entryline"
        new = tmp / "new.entryline"
        write_entries(parse_entryline(_entryline(n, fresh, edited=False)), old)
        write_entries(parse_entryline(_entryline(n, fresh, edited=True)), new)
        query = tmp / "q.faa"
        query.write_text(">r0 1.0\nM\n>r1 2.0\nA\n")
        calls: list[int] = []
        hit = f"e{n - 1:04d}"

        def runner(records, entries):
            calls.append(len(entries))
            return _render(records, entries, len(entries), hit)

        def pinned(records, entries, values):
            calls.append(len(entries))
            return _render(records, entries, values["entry_count"], hit)

        return old, new, query, calls, runner, pinned, hit

    def _run(self, tmp: Path, ref: Path, query: Path, runner, pinned, **kwargs):
        return ReferenceIncremental(
            argv=ARGV,
            input_path=query,
            out_dir=tmp / ref.stem,
            reference=ref,
            cache_path=tmp / "cache.sqlite",
            verify="audit",
            audit_p=0.0,
            runner=runner,
            pin=PIN,
            pin_runner=pinned,
            **kwargs,
        ).run()

    def _fill(self, tmp: Path, n: int, fresh: int, **kwargs):
        old, new, query, calls, runner, pinned, _hit = self._world(tmp, n, fresh)
        first = self._run(tmp, old, query, runner, pinned, **kwargs)
        self.assertEqual(first.decision, "SHIP", first.reason)
        self.assertNotIn("fallback:", first.reason)
        marked = len(calls)
        second = self._run(tmp, new, query, runner, pinned, **kwargs)
        return second, calls[marked:], new, query

    def test_high_fraction_runs_stock_and_matches_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            second, calls, new, query = self._fill(tmp, 1000, 931)
            self.assertEqual(second.decision, "FALLBACK", second.reason)
            self.assertEqual(second.reason, fallback_reason(931 / 1000, DEFAULT_BREAK_EVEN_F))
            self.assertEqual(second.extra["f_threshold_source"], "default")
            self.assertEqual(calls, [1000])
            text = (tmp / "new" / "decision.txt").read_text()
            self.assertIn("fallback: f_delta=0.931000 > threshold=0.800000", text)
            got = (tmp / "new" / "tables" / "out").read_text()
            want = _render(read_records(query), parse_reference(new), 1000, "e0999")["out"]
            self.assertEqual(body_lines(got), body_lines(want))
            self.assertTrue(any(line.startswith("r0 e0999 ") for line in body_lines(got)))

    def test_low_fraction_still_replays(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            second, calls, new, query = self._fill(tmp, 1000, 134)
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertIn("exact replay", second.reason)
            self.assertNotIn("fallback:", second.reason)
            self.assertEqual(f"{second.extra['f_delta']:.6f}", "0.134000")
            self.assertTrue(calls)
            self.assertNotIn(1000, calls)
            got = (tmp / "new" / "tables" / "out").read_text()
            want = _render(read_records(query), parse_reference(new), 1000, "e0999")["out"]
            self.assertEqual(body_lines(got), body_lines(want))
            self.assertTrue(any(line.startswith("r0 e0999 ") for line in body_lines(got)))

    def test_boundary_is_strict(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            equal, equal_calls, _, _ = self._fill(tmp, 10, 2, f_threshold=0.2)
            self.assertEqual(equal.decision, "SHIP", equal.reason)
            self.assertNotIn("fallback:", equal.reason)
            # Discovery of the two fresh entries runs. A fallback would be one full call.
            self.assertEqual(equal_calls[0], 2)
            self.assertNotEqual(equal_calls, [10])
            self.assertFalse(equal.extra.get("stock_fallback"))
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            above, above_calls, _, _ = self._fill(tmp, 10, 3, f_threshold=0.2)
            self.assertEqual(above.decision, "FALLBACK", above.reason)
            self.assertEqual(above.reason, fallback_reason(0.3, 0.2))
            self.assertEqual(above_calls, [10])
            self.assertIn("fallback: f_delta=0.300000 > threshold=0.200000", (tmp / "new" / "decision.txt").read_text())

    def test_flag_overrides_default_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            forced, calls, _, _ = self._fill(tmp, 1000, 134, f_threshold=0.10)
            self.assertEqual(forced.decision, "FALLBACK", forced.reason)
            self.assertEqual(forced.extra["f_threshold_source"], "flag")
            self.assertEqual(calls, [1000])
            self.assertIn("fallback: f_delta=0.134000 > threshold=0.100000", forced.reason)
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            old, new, query, calls, runner, pinned, _hit = self._world(tmp, 1000, 931)
            cache_path = tmp / "cache.sqlite"
            first = self._run(tmp, old, query, runner, pinned, f_threshold=0.95)
            self.assertEqual(first.decision, "SHIP", first.reason)
            ns = namespace_for(ARGV, old, None, PIN, None)
            cache = connect_cache(cache_path)
            cache.add_cost_observation(
                ns, kind="update", f_delta=0.5, stock_s=1.0, tare_s=5.0, discovery_s=5.0
            )
            cache.close()
            marked = len(calls)
            second = self._run(tmp, new, query, runner, pinned, f_threshold=0.95)
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertEqual(second.extra["f_threshold_source"], "flag")
            self.assertNotIn(1000, calls[marked:])

    def test_history_moves_the_threshold_and_a_useless_fit_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            old, new, query, calls, runner, pinned, _hit = self._world(tmp, 1000, 134)
            cache_path = tmp / "cache.sqlite"
            first = self._run(tmp, old, query, runner, pinned)
            self.assertEqual(first.decision, "SHIP", first.reason)
            ns = namespace_for(ARGV, old, None, PIN, None)
            cache = connect_cache(cache_path)
            cache.add_cost_observation(
                ns, kind="update", f_delta=0.5, stock_s=1.0, tare_s=5.0, discovery_s=5.0
            )
            cache.close()
            marked = len(calls)
            second = self._run(tmp, new, query, runner, pinned)
            self.assertEqual(second.decision, "FALLBACK", second.reason)
            self.assertEqual(second.extra["f_threshold_source"], "history")
            self.assertEqual(second.reason, fallback_reason(134 / 1000, 0.1))
            self.assertEqual(calls[marked:], [1000])
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            old, new, query, calls, runner, pinned, _hit = self._world(tmp, 1000, 931)
            cache_path = tmp / "cache.sqlite"
            first = self._run(tmp, old, query, runner, pinned)
            self.assertEqual(first.decision, "SHIP", first.reason)
            ns = namespace_for(ARGV, old, None, PIN, None)
            cache = connect_cache(cache_path)
            # c = 2, so (1-c)/a is not a positive break-even. Default stands.
            cache.add_cost_observation(
                ns, kind="update", f_delta=0.5, stock_s=1.0, tare_s=3.0, discovery_s=1.0
            )
            cache.close()
            second = self._run(tmp, new, query, runner, pinned)
            self.assertEqual(second.decision, "FALLBACK", second.reason)
            self.assertEqual(second.extra["f_threshold_source"], "default")
            self.assertIn("threshold=0.800000", second.reason)

    def test_flag_is_on_the_run_command(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "acts", "run", "--help"],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("--f-threshold", proc.stdout)
        self.assertIn("0.80", proc.stdout)


if __name__ == "__main__":
    unittest.main()
