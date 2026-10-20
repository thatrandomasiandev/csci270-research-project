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
    filter_aux_text,
    parse_subset_aux,
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
        help_text=None,
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
            help_text=help_text,
        ).run()

    def test_pin_tokens_expand_and_reject_unknown(self) -> None:
        values = {"entry_count": 7, "total_entry_length": 99}
        self.assertEqual(pin_tokens("-Z {entry_count}", values), ["-Z", "7"])
        self.assertEqual(pin_tokens("--dbsize={total_entry_length}", values), ["--dbsize=99"])
        with self.assertRaises(RunError):
            pin_tokens("-Z {nonsense}", values)

    def test_pin_argv_lands_after_diamond_subcommand(self) -> None:
        """Linux diamond treats ``diamond --dbsize N blastp`` as command dbsize.

        Pins must merge into the blastp argv, matching probe extras.
        """
        from acts.infer_knobs import apply_extra_argv

        values = {"entry_count": 7, "total_entry_length": 99}
        base = [
            "/bin/diamond",
            "blastp",
            "--db",
            "{reference}",
            "--query",
            "{input}",
            "--threads",
            "4",
        ]
        pinned = apply_extra_argv(base, pin_tokens("--dbsize {total_entry_length}", values))
        self.assertEqual(pinned[0], "/bin/diamond")
        self.assertEqual(pinned[1], "blastp")
        self.assertNotEqual(pinned[2], "--dbsize")
        self.assertEqual(pinned[-2:], ["--dbsize", "99"])
        hmm = apply_extra_argv(
            ["hmmsearch", "--domtblout", "{output}", "{reference}", "{input}"],
            pin_tokens("-Z {entry_count}", values),
        )
        self.assertEqual(hmm[0], "hmmsearch")
        self.assertEqual(hmm[-2:], ["-Z", "7"])

    def test_release_update_is_byte_identical_to_stock(self) -> None:
        """E1-scale shape: the printed value is the reference size, and the pin sets it."""
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


_SIZE_HELP = "--size <x> : comparisons done, for the printed score [10]\n"
_NOTE_HELP = "--note <x> : recorded and ignored [1]\n"


def _scaled(records, entries, extra=()):
    """Six decimals, and only some entries hit, so the column is entry_count.

    Reporting every entry also fits a per-key row count, and that tie refuses.
    """
    scale = len(entries)
    if len(extra) >= 2:
        scale = float(extra[1])
    lines = ["# record entry evalue"]
    for rec in records:
        for entry in entries:
            if entry.primary not in HITS:
                continue
            lines.append(f"{rec.key} {entry.primary} {scale * float(rec.description):.6f}")
    return {"out": "\n".join(lines) + "\n"}


class InferredPinTests(unittest.TestCase):
    def test_inferred_pin_is_used_and_reused(self) -> None:
        seen: list[tuple[str, ...]] = []

        def law(records, entries, extra=()):
            seen.append(tuple(extra))
            return _scaled(records, entries, extra)

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1, ref2 = ExactReplayTests()._two_releases(tmp)
            first = ExactReplayTests()._run(
                tmp, ref1, None, pin="", runner=law, help_text=_SIZE_HELP
            )
            self.assertEqual(first.decision, "SHIP", first.reason)
            self.assertEqual(first.extra.get("inferred_pin"), "--size {entry_count}")
            self.assertEqual(first.extra.get("mode"), "exact")
            want = _scaled(
                __import__("acts.reference_formats", fromlist=["read_records"]).read_records(FIX / "ab.faa"),
                parse_reference(ref1),
            )["out"]
            self.assertEqual(body_lines((tmp / ref1.stem / "tables" / "out").read_text()), body_lines(want))
            ladder = [extra for extra in seen if len(extra) >= 2 and extra[1] in {"1", "0.1", "0.01"}]
            self.assertTrue(ladder)
            n = len(seen)
            second = ExactReplayTests()._run(
                tmp, ref2, None, pin="", runner=law, help_text=_SIZE_HELP
            )
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertEqual(second.extra.get("inferred_pin"), "--size {entry_count}")
            self.assertEqual(
                [extra for extra in seen[n:] if len(extra) >= 2 and extra[1] in {"1", "0.1", "0.01"}],
                [],
            )
            want2 = _scaled(
                __import__("acts.reference_formats", fromlist=["read_records"]).read_records(FIX / "ab.faa"),
                parse_reference(ref2),
            )["out"]
            self.assertEqual(body_lines((tmp / "v2" / "tables" / "out").read_text()), body_lines(want2))

    def test_inference_failure_refuses_pin(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1, _ = ExactReplayTests()._two_releases(tmp)
            rec = ExactReplayTests()._run(
                tmp,
                ref1,
                None,
                pin="",
                runner=lambda records, entries, extra=(): _scaled(records, entries),
                help_text=_NOTE_HELP,
            )
            self.assertEqual(rec.decision, "REFUSE_PIN", rec.reason)
            self.assertIn("no knob", rec.reason)

    def test_entry_count_without_a_pin_refuses(self) -> None:
        """A fitted size member and no pin template is REFUSE_PIN.

        Six decimals make entry_count separable from identity. No option in
        the help text sets it, so inference refuses instead of shipping.
        """

        def law(records, entries, extra=()):
            return _scaled(records, entries)

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1, _ = ExactReplayTests()._two_releases(tmp)
            rec = ExactReplayTests()._run(
                tmp, ref1, None, pin="", runner=law, help_text=_NOTE_HELP
            )
            self.assertEqual(rec.decision, "REFUSE_PIN", rec.reason)
            self.assertIn("no knob", rec.reason)
            self.assertNotIn("identity check", rec.reason)

    def test_e1_shape_without_a_pin_refuses(self) -> None:
        """The pinned E1 shape, with the pin omitted, does not ship."""

        def law(records, entries, extra=()):
            return stock(records, entries)

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1, _ = ExactReplayTests()._two_releases(tmp)
            rec = ExactReplayTests()._run(
                tmp, ref1, None, pin="", runner=law, help_text=_NOTE_HELP
            )
            self.assertEqual(rec.decision, "REFUSE_PIN", rec.reason)

    def test_identity_exact_ships_without_a_pin(self) -> None:
        def identity(records, entries, extra=()):
            return _render(records, entries, 1.0)

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1, ref2 = ExactReplayTests()._two_releases(tmp)
            first = ExactReplayTests()._run(tmp, ref1, None, pin="", runner=identity)
            self.assertEqual(first.decision, "SHIP", first.reason)
            self.assertEqual(first.extra.get("normalizer"), "identity")
            self.assertNotIn("inferred_pin", first.extra)
            records = read_records(FIX / "ab.faa")
            want = _render(records, parse_reference(ref1), 1.0)["out"]
            self.assertEqual(body_lines((tmp / ref1.stem / "tables" / "out").read_text()), body_lines(want))
            second = ExactReplayTests()._run(tmp, ref2, None, pin="", runner=identity)
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertGreater(int(second.extra["reused_rows"]), 0)
            want2 = _render(records, parse_reference(ref2), 1.0)["out"]
            self.assertEqual(body_lines((tmp / "v2" / "tables" / "out").read_text()), body_lines(want2))

    def test_explicit_pin_overrides_inference(self) -> None:
        def law(records, entries, extra=()):
            if extra:
                raise AssertionError(extra)
            return stock(records, entries)

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1, _ = ExactReplayTests()._two_releases(tmp)
            rec = ExactReplayTests()._run(
                tmp, ref1, honest_pin, runner=law, help_text=_SIZE_HELP
            )
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            self.assertNotIn("inferred_pin", rec.extra)


class SubsetAuxTests(unittest.TestCase):
    def test_filter_keeps_a_label_and_drops_a_short_line(self) -> None:
        names = {"e0", "e1", "e2"}
        text = "G1\te0\te1\nG2\te2\nLONER\n"
        got = filter_aux_text(text, names, {"e0"})
        self.assertEqual(got, "G1\te0\n")
        self.assertEqual(filter_aux_text("G2\te0\n", names, {"e0"}), "G2\te0\n")
        self.assertEqual(parse_subset_aux("{arg-after:--side}:tokens"), "--side")
        with self.assertRaises(RunError):
            parse_subset_aux("--side")

    def test_declared_rule_lets_a_subset_run_ship(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            side = tmp / "groups"
            side.write_text("G1 e0 e1\nG2 e2 e3\n")
            log = tmp / "seen"
            tool = tmp / "tool.py"
            tool.write_text(
                "import sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "side = Path(args[args.index('--side') + 1])\n"
                "log = Path(args[args.index('--log') + 1])\n"
                "ref = Path(args[args.index('--ref') + 1])\n"
                "rec = Path(args[args.index('--rec') + 1])\n"
                "dest = Path(args[args.index('--out') + 1])\n"
                "order = [line.split()[0] for line in ref.read_text().splitlines() if line.strip()]\n"
                "names = set(order)\n"
                "members = []\n"
                "for line in side.read_text().splitlines():\n"
                "    tokens = line.split()\n"
                "    members.extend(tokens[1:])\n"
                "    if any(token not in names for token in tokens[1:]):\n"
                "        sys.stderr.write('absent member\\n')\n"
                "        raise SystemExit(3)\n"
                "with log.open('a') as handle:\n"
                "    handle.write(str(side.resolve()) + '\\t' + str(len(members)) + '\\n')\n"
                "rows = []\n"
                "present = set(members)\n"
                "for record in rec.read_text().splitlines():\n"
                "    if not record.startswith('>'):\n"
                "        continue\n"
                "    name = record[1:].split()[0]\n"
                "    for entry in order:\n"
                "        if entry in present:\n"
                "            rows.append(f'{name} {entry} 1.000')\n"
                "dest.write_text('# record entry evalue\\n' + '\\n'.join(rows) + '\\n')\n"
            )
            argv = [
                sys.executable, str(tool),
                "--side", str(side),
                "--log", str(log),
                "--ref", "{reference}",
                "--rec", "{input}",
                "--out", "{output}",
            ]
            ref = FIX / "ab.entryline"
            bare = ReferenceIncremental(
                argv=argv,
                input_path=FIX / "ab.faa",
                out_dir=tmp / "bare",
                reference=ref,
                cache_path=tmp / "bare.sqlite",
                verify="full",
                pin="",
            ).run()
            self.assertTrue(bare.decision.startswith("REFUSE"), bare.reason)
            ruled = ReferenceIncremental(
                argv=argv,
                input_path=FIX / "ab.faa",
                out_dir=tmp / "ruled",
                reference=ref,
                cache_path=tmp / "ruled.sqlite",
                verify="full",
                pin="",
                subset_aux="{arg-after:--side}:tokens",
            ).run()
            self.assertEqual(ruled.decision, "SHIP", ruled.reason)
            self.assertEqual(side.read_text(), "G1 e0 e1\nG2 e2 e3\n")
            seen = [line.split("\t") for line in log.read_text().splitlines() if line.strip()]
            original = str(side.resolve())
            self.assertTrue(any(path == original for path, _count in seen))
            self.assertTrue(any(path != original for path, _count in seen))

    def test_pinned_release_is_unchanged_without_the_rule(self) -> None:
        """The size-member replay, with its pin and with no side-file rule, still ships."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1, ref2 = ExactReplayTests()._two_releases(tmp)
            first = ExactReplayTests()._run(tmp, ref1, honest_pin)
            self.assertEqual(first.decision, "SHIP", first.reason)
            second = ExactReplayTests()._run(tmp, ref2, honest_pin)
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertNotIn("normalizer", second.extra)


class RankColumnTests(unittest.TestCase):
    def test_a_presentation_rank_still_ships_exact(self) -> None:
        """Two hits per entry. The rank renumbers in a subset; the coordinate does not.

        Exact mode replays, so the rank is produced again. It is not a reason
        to refuse when the row keys still match.
        """

        def ranked(records, entries):
            lines = ["# record entry rank coord"]
            rank = 1
            for rec in records:
                present = [entry for entry in entries if entry.primary in {"e1", "e3"}]
                for entry in present:
                    for coord in (10, 20):
                        lines.append(f"{rec.key} {entry.primary} {rank} {coord}")
                        rank += 1
            return {"out": "\n".join(lines) + "\n"}

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            result = ReferenceIncremental(
                argv=ARGV,
                input_path=FIX / "ab.faa",
                out_dir=tmp / "rank",
                reference=FIX / "ab.entryline",
                cache_path=tmp / "cache.sqlite",
                verify="full",
                pin="",
                runner=ranked,
            ).run()
            self.assertEqual(result.decision, "SHIP", result.reason)
            self.assertEqual(result.extra.get("normalizer"), "identity")
            body = (tmp / "rank" / "tables" / "out").read_text()
            whole = ranked(read_records(FIX / "ab.faa"), parse_reference(FIX / "ab.entryline"))
            self.assertEqual(body_lines(body), body_lines(whole["out"]))


def _suppress_when_together(records, entries):
    """e1 is omitted while e0 is also searched. Removing e0 unmasks e1."""
    names = {entry.primary for entry in entries}
    lines = ["# record entry value"]
    for rec in records:
        for entry in entries:
            if entry.primary not in {"e0", "e1"}:
                continue
            if entry.primary == "e1" and "e0" in names:
                continue
            lines.append(f"{rec.key} {entry.primary} 1")
    return {"out": "\n".join(lines) + "\n"}


class GroupInvalidationTests(unittest.TestCase):
    def _pair(self, tmp: Path) -> tuple[Path, Path, Path]:
        ref1 = FIX / "ab.entryline"
        ref2 = tmp / "v2.entryline"
        kept = [entry for entry in parse_reference(ref1) if entry.primary != "e0"]
        write_entries(kept, ref2)
        groups = tmp / "groups.txt"
        groups.write_text("G e0 e1\n")
        return ref1, ref2, groups

    def _run(self, tmp: Path, ref: Path, groups: Path, *, rule: str | None, cache: Path):
        argv = ["law", "--group", str(groups), "{reference}", "{input}", "{output}"]
        return ReferenceIncremental(
            argv=argv,
            input_path=FIX / "ab.faa",
            out_dir=tmp / ref.stem,
            reference=ref,
            cache_path=cache,
            verify="full",
            pin="",
            runner=_suppress_when_together,
            invalidate_group=rule,
        ).run()

    def test_without_the_rule_a_removed_member_hides_its_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1, ref2, groups = self._pair(tmp)
            cache = tmp / "cache.sqlite"
            first = self._run(tmp, ref1, groups, rule=None, cache=cache)
            self.assertEqual(first.decision, "SHIP", first.reason)
            second = self._run(tmp, ref2, groups, rule=None, cache=cache)
            self.assertTrue(second.decision.startswith("REFUSE"), second.reason)

    def test_a_removed_member_rescans_its_group(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1, ref2, groups = self._pair(tmp)
            cache = tmp / "cache.sqlite"
            rule = "{arg-after:--group}"
            first = self._run(tmp, ref1, groups, rule=rule, cache=cache)
            self.assertEqual(first.decision, "SHIP", first.reason)
            second = self._run(tmp, ref2, groups, rule=rule, cache=cache)
            self.assertEqual(second.decision, "SHIP", second.reason)
            body = (tmp / ref2.stem / "tables" / "out").read_text()
            stock = _suppress_when_together(read_records(FIX / "ab.faa"), parse_reference(ref2))
            self.assertEqual(body_lines(body), body_lines(stock["out"]))
            self.assertTrue(any(" e1 " in line for line in body_lines(body)))

    def test_an_ungrouped_removal_does_not_rescan_other_groups(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref1 = FIX / "ab.entryline"
            ref2 = tmp / "v2.entryline"
            kept = [entry for entry in parse_reference(ref1) if entry.primary != "e2"]
            write_entries(kept, ref2)
            groups = tmp / "groups.txt"
            groups.write_text("G e0 e1\n")

            def emit(records, entries):
                lines = ["# record entry value"]
                for rec in records:
                    for entry in entries:
                        lines.append(f"{rec.key} {entry.primary} 1")
                return {"out": "\n".join(lines) + "\n"}

            cache = tmp / "cache.sqlite"
            rule = "{arg-after:--group}"
            argv = ["law", "--group", str(groups), "{reference}", "{input}", "{output}"]

            def run(ref: Path):
                return ReferenceIncremental(
                    argv=argv,
                    input_path=FIX / "ab.faa",
                    out_dir=tmp / ref.stem,
                    reference=ref,
                    cache_path=cache,
                    verify="full",
                    pin="",
                    runner=emit,
                    invalidate_group=rule,
                ).run()

            first = run(ref1)
            self.assertEqual(first.decision, "SHIP", first.reason)
            second = run(ref2)
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertEqual(second.extra.get("n_fresh"), 0)


if __name__ == "__main__":
    unittest.main()
