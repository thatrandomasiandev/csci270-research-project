"""Knob inference: help parsing and fake-tool probes. No real binary."""

from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.infer_knobs import (  # noqa: E402
    apply_extra_argv,
    capture_help,
    infer_knobs,
    parse_help_options,
)
from acts.reference_fit import ColumnReport, TableReport  # noqa: E402
from acts.reference_formats import RecordItem, parse_entryline  # noqa: E402

HELP_SHAPES = """
Usage: tool [-options] <db> <seqfile>
  -h : show brief help
  -o <f>           : direct output to file <f>, not stdout
  --noali          : don't output alignments
  -E <x>     : report rows <= this threshold in output  [10.0]  (x>0)
  --domE <x> : report parts <= this threshold in output  [10.0]  (x>0)
  --cut_ga : use the entry's own cutoffs
  --F1 <x> : stage 1 threshold  [0.02]
  --F2 <x> : stage 2 threshold  [1e-3]
  -Z <x>        : set the comparison count
  --domZ <x>    : set the per-record count
  --seed <n>    : set RNG seed to <n>  [42]
  --qformat <s> : assert format <s>
  --cpu <n>     : workers  [0]
  --opt=N       something (default: 10)
  --limit N     another form [1e-3]
  -E <x>        : repeated, ignored  [99]
  --alpha=N     parenthetical default (default=0.5)
"""


def _entries():
    return parse_entryline("e0 1\ne1 2\ne2 1\ne3 2\n")


def _records():
    return [
        RecordItem("r0", "r0", "1", ""),
        RecordItem("r1", "r1", "6", ""),
    ]


def _contract(member: str = "entry_count", extra: ColumnReport | None = None):
    columns = [
        ColumnReport(0, "byte", member="byte"),
        ColumnReport(1, "byte", member="byte"),
        ColumnReport(2, "numeric", member=member),
        ColumnReport(3, "numeric", member="identity"),
    ]
    if extra is not None:
        columns.append(extra)
    return [
        TableReport(
            name="out",
            record_col=0,
            entry_col=1,
            index_col=None,
            meta=[],
            columns=columns,
        )
    ]


def _opts(extra: list[str]) -> dict[str, float]:
    parsed: dict[str, float] = {}
    cursor = iter(extra)
    for token in cursor:
        parsed[token] = float(next(cursor))
    return parsed


def _scaled_invoke(scale: str, knob: str):
    """E-value is payload times the reference measure, unless `knob` sets it."""

    def invoke(records, entries, extra):
        opts = _opts(list(extra))
        if knob in opts:
            factor = opts[knob]
        elif scale == "count":
            factor = float(len(entries))
        else:
            factor = float(sum(entry.length for entry in entries))
        thresh = opts.get("-E", 10.0)
        warp = opts.get("--warp", 0.0)
        lines = ["# record entry evalue score"]
        for rec in records:
            payload = float(rec.description)
            evalue = payload * factor
            if evalue > thresh:
                continue
            score = payload + warp
            for entry in entries:
                lines.append(f"{rec.key} {entry.primary} {evalue:.6f} {score:.6f}")
        return {"out": "\n".join(lines) + "\n"}

    return invoke


class ParseHelpTests(unittest.TestCase):
    def test_several_canned_formats(self) -> None:
        found = {item["option"]: item for item in parse_help_options(HELP_SHAPES)}
        self.assertEqual(
            list(found),
            ["-E", "--domE", "--F1", "--F2", "-Z", "--domZ", "--seed", "--cpu", "--opt", "--limit", "--alpha"],
        )
        self.assertEqual(found["-E"]["default"], 10.0)
        self.assertEqual(found["--domE"]["default"], 10.0)
        self.assertEqual(found["--F1"]["default"], 0.02)
        self.assertEqual(found["--F2"]["default"], 0.001)
        self.assertIsNone(found["-Z"]["default"])
        self.assertIsNone(found["--domZ"]["default"])
        self.assertEqual(found["--seed"]["default"], 42.0)
        self.assertEqual(found["--cpu"]["default"], 0.0)
        self.assertEqual(found["--opt"]["default"], 10.0)
        self.assertEqual(found["--limit"]["default"], 0.001)
        self.assertEqual(found["--alpha"]["default"], 0.5)
        self.assertNotIn("-o", found)
        self.assertNotIn("--noali", found)
        self.assertNotIn("--cut_ga", found)
        self.assertNotIn("--qformat", found)
        self.assertNotIn("-h", found)

    def test_capture_help_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tool"
            path.write_text(
                "#!/bin/sh\n"
                'if [ "$1" = "-h" ]; then echo usage; exit 3; fi\n'
                "echo '--limit N   a cap  [3]'\n"
            )
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
            found = parse_help_options(capture_help(str(path)))
        self.assertEqual(found[0]["option"], "--limit")
        self.assertEqual(found[0]["default"], 3.0)

    def test_apply_extra_argv_replaces_same_option(self) -> None:
        base = ["tool", "--cpu", "1", "--tblout", "T", "ref", "qry"]
        merged = apply_extra_argv(base, ["--cpu", "4"])
        self.assertEqual(merged, ["tool", "--tblout", "T", "ref", "qry", "--cpu", "4"])


class ProbeTests(unittest.TestCase):
    def test_size_knob_found_and_threshold_only_adds_rows(self) -> None:
        entries = _entries()
        result = infer_knobs(
            "  -Z <x>        : set the comparison count\n"
            "  -E <x>        : reporting threshold  [10.0]\n"
            "  --warp <x>    : add to the score  [1.0]\n",
            _records(),
            entries,
            entries[:2],
            _contract(),
            _scaled_invoke("count", "-Z"),
        )
        self.assertEqual(result["pin"], "-Z {entry_count}")
        self.assertEqual(result["thresholds"], [{"option": "-E", "default": 10.0, "column": "out:2"}])
        warp = next(item for item in result["candidates"] if item["option"] == "--warp")
        self.assertEqual(warp["threshold"], "shared rows changed")
        self.assertNotEqual(warp["normalizer"]["entry_count"], "accept")
        self.assertEqual(result["tool_calls"], 7)

    def test_length_member_uses_that_placeholder(self) -> None:
        entries = _entries()
        result = infer_knobs(
            "  --size <x> : set the length total\n",
            _records(),
            entries,
            entries[:2],
            _contract("total_entry_length"),
            _scaled_invoke("length", "--size"),
        )
        self.assertEqual(result["pin"], "--size {total_entry_length}")
        self.assertEqual(result["thresholds"], [])

    def test_no_knob_when_nothing_sets_the_measure(self) -> None:
        entries = _entries()

        def invoke(records, entries, extra):
            lines = ["# record entry evalue score"]
            factor = float(len(entries))
            for rec in records:
                payload = float(rec.description)
                for entry in entries:
                    lines.append(
                        f"{rec.key} {entry.primary} {payload * factor:.6f} {payload:.6f}"
                    )
            return {"out": "\n".join(lines) + "\n"}

        result = infer_knobs(
            "  --seed <n> : seed  [42]\n",
            _records(),
            entries,
            entries[:2],
            _contract(),
            invoke,
        )
        self.assertEqual(result["pin"], "no knob")
        self.assertEqual(result["thresholds"], [])
        seed = result["candidates"][0]
        self.assertEqual(seed["option"], "--seed")
        self.assertNotEqual(seed["normalizer"]["entry_count"], "accept")
        self.assertEqual(seed["threshold"], "row set unchanged")

    def test_decoy_that_changes_scores_is_rejected(self) -> None:
        entries = _entries()

        def invoke(records, entries, extra):
            opts = _opts(list(extra))
            factor = float(len(entries))
            lines = ["# record entry evalue score"]
            for rec in records:
                payload = float(rec.description)
                score = opts["--decoy"] * 9 + 0.123 if "--decoy" in opts else payload
                for entry in entries:
                    lines.append(f"{rec.key} {entry.primary} {payload * factor:.6f} {score:.6f}")
            return {"out": "\n".join(lines) + "\n"}

        result = infer_knobs(
            "  --decoy <x> : perturb a score  [1.5]\n",
            _records(),
            entries,
            entries[:2],
            _contract(),
            invoke,
        )
        self.assertEqual(result["pin"], "no knob")
        self.assertEqual(result["thresholds"], [])
        decoy = result["candidates"][0]
        self.assertEqual(decoy["threshold"], "shared rows changed")
        self.assertNotEqual(decoy["normalizer"]["entry_count"], "accept")
        self.assertTrue(any(item["option"] == "--decoy" for item in result["rejected"]))

    def test_knob_that_changes_shared_rows_is_not_a_threshold(self) -> None:
        entries = _entries()
        result = infer_knobs(
            "  --warp <x> : rewrite the score  [1.0]\n",
            _records(),
            entries,
            entries[:2],
            _contract(),
            _scaled_invoke("count", "-Z"),
        )
        self.assertEqual(result["thresholds"], [])
        self.assertEqual(result["candidates"][0]["threshold"], "shared rows changed")

    def test_tie_break_keeps_the_body_match(self) -> None:
        entries = _entries()

        def invoke(records, entries, extra):
            opts = _opts(list(extra))
            factor = opts.get("-A", opts.get("-B", float(len(entries))))
            side = "9.000000" if "-B" in opts else "1.000000"
            lines = ["# record entry evalue score side"]
            for rec in records:
                payload = float(rec.description)
                evalue = payload * factor
                if evalue > 10:
                    continue
                for entry in entries:
                    lines.append(
                        f"{rec.key} {entry.primary} {evalue:.6f} {payload:.6f} {side}"
                    )
            return {"out": "\n".join(lines) + "\n"}

        contract = _contract(extra=ColumnReport(4, "numeric", member="per_key_row_count"))
        result = infer_knobs(
            "  -A <x> : size\n  -B <x> : size with a side effect\n",
            _records(),
            entries,
            entries[:2],
            contract,
            invoke,
        )
        self.assertEqual(result["pin"], "-A {entry_count}")
        self.assertEqual(result["candidates"][1]["normalizer"]["entry_count"], "tie")

    def test_two_full_matches_refuse(self) -> None:
        entries = _entries()

        def invoke(records, entries, extra):
            opts = _opts(list(extra))
            factor = opts.get("-A", opts.get("-C", float(len(entries))))
            lines = ["# record entry evalue score"]
            for rec in records:
                payload = float(rec.description)
                evalue = payload * factor
                if evalue > 10:
                    continue
                for entry in entries:
                    lines.append(f"{rec.key} {entry.primary} {evalue:.6f} {payload:.6f}")
            return {"out": "\n".join(lines) + "\n"}

        result = infer_knobs(
            "  -A <x> : size\n  -C <x> : the same size\n",
            _records(),
            entries,
            entries[:2],
            _contract(),
            invoke,
        )
        self.assertEqual(result["pin"], "no knob")
        self.assertIn("tie", result["reason"])

    def test_cap_does_not_ship_a_partial_pin(self) -> None:
        entries = _entries()
        result = infer_knobs(
            "  -Z <x> : size\n  --other <x> : other\n",
            _records(),
            entries,
            entries[:2],
            _contract(),
            _scaled_invoke("count", "-Z"),
            max_calls=3,
        )
        self.assertEqual(result["pin"], "no knob")
        self.assertIn("cap", result["reason"])


if __name__ == "__main__":
    unittest.main()
