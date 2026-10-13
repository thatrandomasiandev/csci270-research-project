"""Exact mode: pinned-normalizer replay (docs/EXACT_REPLAY_PROTOCOL.md)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.reference_formats import parse_entryline, parse_reference, read_records, write_entries
from acts.reference_run import (
    ReferenceIncremental,
    RunError,
    body_lines,
    pin_tokens,
    slack_rewrite,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "reference_fitter"
HITS = {"e1", "e3", "e4"}
ARGV = ["law", "{reference}", "{input}", "{output}"]


def _render(records, entries, scale: float, *, hits=HITS, footer: str = "", fmt: str = ".3g") -> dict[str, str]:
    lines = ["# record entry evalue"]
    for rec in records:
        for entry in entries:
            if entry.primary not in hits:
                continue
            lines.append(f"{rec.key} {entry.primary} {format(scale * float(rec.description), fmt)}")
    if footer:
        lines.append(f"# {footer}")
    return {"out": "\n".join(lines) + "\n"}


def stock(records, entries):
    return _render(records, entries, len(entries), footer=f"run on {len(entries)} entries")


def honest_pin(records, entries, values):
    return _render(records, entries, values["entry_count"], footer="pinned")


def ignores_pin(records, entries, values):
    return _render(records, entries, len(entries))


class ExactReplayTests(unittest.TestCase):
    def _two_releases(self, tmp: Path) -> tuple[Path, Path]:
        ref1 = FIX / "ab.entryline"
        ref2 = tmp / "v2.entryline"
        keep = [e for e in parse_reference(ref1) if e.primary in {"e0", "e1", "e3"}]
        write_entries(keep + parse_entryline("e4 5\n") + parse_entryline("e5 3\n"), ref2)
        return ref1, ref2

    def _run(
        self,
        tmp: Path,
        ref: Path,
        pin_runner,
        *,
        pin="-Z {entry_count}",
        verify="full",
        runner=stock,
        slack=None,
        slack_runner=None,
        argv=None,
    ):
        return ReferenceIncremental(
            argv=argv or ARGV,
            input_path=FIX / "ab.faa",
            out_dir=tmp / ref.stem,
            reference=ref,
            cache_path=tmp / "cache.sqlite",
            verify=verify,
            runner=runner,
            pin=pin,
            pin_runner=pin_runner,
            slack=slack,
            slack_runner=slack_runner,
        ).run()

    def test_pin_tokens_expand_and_reject_unknown(self) -> None:
        values = {"entry_count": 7, "total_entry_length": 99}
        self.assertEqual(pin_tokens("-Z {entry_count}", values), ["-Z", "7"])
        self.assertEqual(pin_tokens("--dbsize={total_entry_length}", values), ["--dbsize=99"])
        with self.assertRaises(RunError):
            pin_tokens("-Z {nonsense}", values)

    def test_release_update_is_byte_identical_to_stock(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1, ref2 = self._two_releases(tmp)
            first = self._run(tmp, ref1, honest_pin)
            self.assertEqual(first.decision, "SHIP", first.reason)
            second = self._run(tmp, ref2, honest_pin)
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertEqual(second.extra["mode"], "exact")
            self.assertGreater(int(second.extra["reused_rows"]), 0)
            got = (tmp / "v2" / "tables" / "out").read_text()
            want = stock(
                __import__("acts.reference_formats", fromlist=["read_records"]).read_records(FIX / "ab.faa"),
                parse_reference(ref2),
            )["out"]
            self.assertEqual(body_lines(got), body_lines(want))
            # Replay touched only candidate entries (e1, e3, e4), not e0 or e5.
            self.assertEqual(int(second.extra["replay_entries"]), 3)
            # Coverage is (entry, record set), not per pair.
            import sqlite3

            con = sqlite3.connect(tmp / "cache.sqlite")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM coverage").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(DISTINCT recset_id) FROM recsets").fetchone()[0], 1)
            con.close()

    def test_legacy_pair_coverage_is_still_read(self) -> None:
        from acts.reference_cache import connect_cache

        with tempfile.TemporaryDirectory() as raw:
            cache = connect_cache(Path(raw) / "c.sqlite")
            with cache._conn:
                cache._conn.execute("INSERT INTO coverage VALUES ('ns', 'h1', 'r0')")
            cache.cover_and_replace("ns", ["out"], ["h2"], ["r0", "r1"], {})
            self.assertEqual(cache.coverage_map("ns"), {"h1": {"r0"}, "h2": {"r0", "r1"}})
            cache.drop_hashes("ns", {"h1", "h2"})
            self.assertEqual(cache.coverage_map("ns"), {})
            cache.close()

    def test_pin_that_does_not_set_the_normalizer_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1, _ = self._two_releases(tmp)
            rec = self._run(tmp, ref1, ignores_pin)
            self.assertEqual(rec.decision, "REFUSE_PIN", rec.reason)
            self.assertIn("pin check failed", rec.reason)

    def test_pin_missing_fitted_member_refuses(self) -> None:
        def by_length(records, entries):
            total = sum(e.length for e in entries)
            return _render(records, entries, total, hits={"e1", "e3", "e5"}, fmt=".9g")

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1 = tmp / "lens.entryline"
            ref1.write_text("e0 1\ne1 3\ne2 8\ne3 2\ne4 13\ne5 4\n")
            rec = self._run(tmp, ref1, honest_pin, runner=by_length)
            self.assertEqual(rec.decision, "REFUSE_PIN", rec.reason)
            self.assertIn("total_entry_length", rec.reason)

    def test_size_dependent_reporting_never_ships(self) -> None:
        # Reporting threshold reads the reference size (E-value cutoff): the
        # hit set of a sub-reference is not the full run's. Must not SHIP.
        def thresholded(records, entries):
            hits = HITS if len(entries) >= 4 else HITS | {"e0", "e2"}
            return _render(records, entries, len(entries), hits=hits)

        def thresholded_pin(records, entries, values):
            hits = HITS if values["entry_count"] >= 4 else HITS | {"e0", "e2"}
            return _render(records, entries, values["entry_count"], hits=hits)

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1, _ = self._two_releases(tmp)
            rec = self._run(tmp, ref1, thresholded_pin, runner=thresholded)
            self.assertTrue(rec.decision.startswith("REFUSE"), rec.decision)


ARGV_E = ["law", "-E", "10", "{reference}", "{input}", "{output}"]
# P is the entry length. Report when P·N ≤ 10. N is the reference size, or the pin.
_SMALL = [("e0", 1), ("e1", 2), ("e2", 4), ("e3", 1)]
_LARGE = _SMALL + [("e4", 1), ("e5", 1)]


def _write_ref(tmp: Path, name: str, pairs: list[tuple[str, int]]) -> Path:
    path = tmp / name
    write_entries(parse_entryline("".join(f"{ident} {length}\n" for ident, length in pairs)), path)
    return path


def _e_rows(records, entries, n: int, thresh: float) -> dict[str, str]:
    lines = ["# record entry score evalue"]
    for rec in records:
        for entry in entries:
            p = entry.length
            e = p * n
            if e <= thresh:
                lines.append(f"{rec.key} {entry.primary} {p} {e}")
    return {"out": "\n".join(lines) + "\n"}


def _tool(thresh: float, pinned: bool):
    def run(records, entries, values=None):
        n = values["entry_count"] if pinned else len(entries)
        return _e_rows(records, entries, n, thresh)
    return run


class EValueSlackTests(unittest.TestCase):
    def test_slack_rewrite_multiplies_and_rejects_a_split_factor(self) -> None:
        argv = ["law", "-E", "10", "--domE", "10", "{reference}"]
        rewritten, factor = slack_rewrite(argv, "-E {E*2} --domE {domE*2}")
        self.assertEqual(factor, 2)
        self.assertEqual(rewritten, ["law", "-E", "20", "--domE", "20", "{reference}"])
        literal, factor = slack_rewrite(argv, "-E 20 --domE 20")
        self.assertEqual(factor, 2.0)
        self.assertEqual(literal, rewritten)
        with self.assertRaises(RunError):
            slack_rewrite(argv, "-E {E*2} --domE {domE*3}")
        with self.assertRaises(RunError):
            slack_rewrite(argv, "-E {E*0.5}")

    def test_growth_is_exact(self) -> None:
        pin, plain = _tool(10, True), _tool(10, False)
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            small = _write_ref(tmp, "small.entryline", _SMALL)
            large = _write_ref(tmp, "large.entryline", _LARGE)
            kw = dict(runner=plain, slack="-E {E*1}", slack_runner=plain, argv=ARGV_E)
            first = self._run(tmp, small, pin, **kw)
            self.assertEqual(first.decision, "SHIP", first.reason)
            second = self._run(tmp, large, pin, **kw)
            self.assertEqual(second.decision, "SHIP", second.reason)
            records = read_records(FIX / "ab.faa")
            got = (tmp / "large" / "tables" / "out").read_text()
            want = _e_rows(records, parse_reference(large), 6, 10)["out"]
            self.assertEqual(body_lines(got), body_lines(want))
            old = _e_rows(records, parse_reference(small), 4, 10)["out"]
            self.assertTrue(any(line.split()[1] == "e1" for line in body_lines(old)))
            self.assertFalse(any(line.split()[1] == "e1" for line in body_lines(want)))

    def test_shrink_with_slack_is_exact(self) -> None:
        pin, plain, wide = _tool(10, True), _tool(10, False), _tool(20, False)
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            small = _write_ref(tmp, "small.entryline", _SMALL)
            large = _write_ref(tmp, "large.entryline", _LARGE)
            kw = dict(runner=plain, slack="-E {E*2}", slack_runner=wide, argv=ARGV_E)
            first = self._run(tmp, large, pin, **kw)
            self.assertEqual(first.decision, "SHIP", first.reason)
            second = self._run(tmp, small, pin, **kw)
            self.assertEqual(second.decision, "SHIP", second.reason)
            records = read_records(FIX / "ab.faa")
            got = (tmp / "small" / "tables" / "out").read_text()
            want = _e_rows(records, parse_reference(small), 4, 10)["out"]
            self.assertEqual(body_lines(got), body_lines(want))
            self.assertTrue(any(line.split()[1] == "e1" for line in body_lines(want)))

    def test_shrink_without_slack_refuses(self) -> None:
        pin, plain = _tool(10, True), _tool(10, False)
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            large = _write_ref(tmp, "large.entryline", _LARGE)
            rec = self._run(tmp, large, pin, runner=plain, argv=ARGV_E)
            self.assertTrue(rec.decision.startswith("REFUSE"), rec.decision)
            self.assertIn("row-key", rec.reason)

    def test_shrink_beyond_recorded_slack_is_a_full_run(self) -> None:
        pin, plain = _tool(10, True), _tool(10, False)
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            small = _write_ref(tmp, "small.entryline", _SMALL)
            large = _write_ref(tmp, "large.entryline", _LARGE)
            kw = dict(runner=plain, slack="-E {E*1}", slack_runner=plain, argv=ARGV_E)
            first = self._run(tmp, large, pin, **kw)
            self.assertEqual(first.decision, "SHIP", first.reason)
            second = self._run(tmp, small, pin, **kw)
            self.assertEqual(second.decision, "REFUSE", second.reason)
            self.assertIn("exceeds slack", second.reason)
            self.assertTrue(second.extra.get("fallback_full_scan"))

    def _run(self, tmp, ref, pin_runner, **kw):
        return ExactReplayTests()._run(tmp, ref, pin_runner, **kw)


if __name__ == "__main__":
    unittest.main()
