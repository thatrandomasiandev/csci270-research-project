from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.table import (
    TableLayout,
    bodies_ws_equal,
    body_lines,
    body_mismatch_count,
    infer_table_layout,
    render_table,
    split_body_rows,
    tables_match,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "savings"


def _sample(name: str, lines: list[str]) -> dict:
    return {"name": name, "lines": lines, "rows": split_body_rows(lines, "ws")}


class TableMatchTests(unittest.TestCase):
    def test_byte_match_is_the_success_path(self) -> None:
        a = "# h\nfoo   12\n"
        b = "# h\nfoo   12\n"
        self.assertTrue(tables_match(a, b, "order"))
        self.assertFalse(tables_match(a, "# h\nfoo  12\n", "order"))
        self.assertTrue(tables_match(a, "# h\nfoo  12\n", "order", match_ws=True))

    def test_ws_fallback_still_ignores_pad(self) -> None:
        a = "name   1.2e-40  12.5\n"
        b = "name 1.2e-40 12.5\n"
        self.assertTrue(bodies_ws_equal(a, b))
        self.assertTrue(tables_match(a, b, "order", match_ws=True))
        self.assertFalse(tables_match(a, b, "order", match_ws=False))


class LayoutInferTests(unittest.TestCase):
    def test_right_aligned_fixed_min(self) -> None:
        def rows(names: list[str], scores: list[int]) -> list[str]:
            return [f"{n.ljust(10)} {str(s).rjust(6)} -" for n, s in zip(names, scores)]

        # 1234567 overflows the width-6 floor inside one file, so per-file
        # max is refuted and fixed_min is the only remaining rule.
        short = rows(["A", "B"], [3, 1234567])
        long = rows(["L" * 24, "M" * 24], [3, 1234567])
        mixed = rows(["A", "L" * 24], [3, 1234567])
        probe = rows(["alpha", "beta"], [12, 1234567])
        layout = infer_table_layout(
            [
                _sample("probe", probe),
                _sample("short", short),
                _sample("long", long),
                _sample("mixed", mixed),
            ],
            query_col=0,
            delim="ws",
        )
        self.assertTrue(layout.pinned, layout.reason)
        self.assertEqual(layout.scope, "fixed")
        self.assertEqual(layout.columns[1].align, "right")
        rebuilt = render_table(
            split_body_rows(probe, "ws"), layout, query_col=0
        )
        self.assertEqual(rebuilt, probe)

    def test_per_file_max_name_width(self) -> None:
        def rows(names: list[str]) -> list[str]:
            w = max([8] + [len(n) for n in names])
            return [f"{n.ljust(w)} 9 -" for n in names]

        short = rows(["A", "B"])
        long = rows(["LONGNAME0000", "LONGNAME0001"])
        mixed = rows(["A", "LONGNAME0000"])
        layout = infer_table_layout(
            [
                _sample("probe", rows(["alpha", "beta"])),
                _sample("short", short),
                _sample("long", long),
                _sample("mixed", mixed),
            ],
            query_col=0,
            delim="ws",
        )
        self.assertTrue(layout.pinned, layout.reason)
        self.assertEqual(layout.scope, "per_file")
        self.assertEqual(layout.columns[0].width_rule, "max_value")
        self.assertEqual(render_table(split_body_rows(mixed, "ws"), layout), mixed)

    def test_per_query_max_value_width(self) -> None:
        def emit(groups: dict[str, list[int]]) -> list[str]:
            lines = []
            for name, scores in groups.items():
                w = max(len(str(s)) for s in scores)
                for s in scores:
                    lines.append(f"{name} {str(s).rjust(w)} x")
            return lines

        probe = emit({"alpha": [1, 2], "beta": [100, 2000]})
        short = emit({"A": [1, 2], "B": [100, 2000]})
        long = emit({"L" * 24: [1, 2], "M" * 24: [100, 2000]})
        mixed = emit({"A": [1, 2], "L" * 24: [100, 2000]})
        layout = infer_table_layout(
            [
                _sample("probe", probe),
                _sample("short", short),
                _sample("long", long),
                _sample("mixed", mixed),
            ],
            query_col=0,
            delim="ws",
        )
        self.assertTrue(layout.pinned, layout.reason)
        self.assertEqual(layout.scope, "per_query")
        self.assertEqual(layout.columns[1].align, "right")
        self.assertEqual(layout.columns[1].width_rule, "max_value")
        self.assertEqual(render_table(split_body_rows(probe, "ws"), layout), probe)

    def test_tabs_are_pinned(self) -> None:
        lines = ["q1\t12\thit", "q2\t4\thit"]
        layout = infer_table_layout(
            [{"name": "probe", "lines": lines, "rows": [ln.split("\t") for ln in lines]}],
            query_col=0,
            delim="tab",
        )
        self.assertTrue(layout.pinned)
        self.assertEqual(layout.delim, "tab")
        self.assertFalse(layout.match_ws if hasattr(layout, "match_ws") else False)

    def test_irregular_gaps_unpinned(self) -> None:
        def emit(names: list[str]) -> list[str]:
            out = []
            for n in names:
                extra = 2 + (len(n) * 3) % 9
                out.append(f"{n}{' ' * extra}9 hit")
            return out

        layout = infer_table_layout(
            [
                _sample("probe", emit(["alpha", "beta", "gamma"])),
                _sample("short", emit(["A", "B", "C"])),
                _sample("long", emit(["L" * 24, "M" * 24, "N" * 24])),
                _sample("mixed", emit(["A", "L" * 24, "C"])),
            ],
            query_col=0,
            delim="ws",
        )
        self.assertFalse(layout.pinned, layout.reason)
        self.assertIn("pin", layout.reason.lower())

    def test_archived_hmmscan_rows_do_not_pin_the_old_floor(self) -> None:
        """2026-10-06: the cached hmmscan contract pinned fixed_min 20.

        These rows are the 11 queries in A_hmmscan_01_stock.tbl whose target
        names are wider than that floor, plus four queries that are not.
        The historical layout mis-renders the widened rows. Inference now
        refuses to pin, because the accession column is still explained by
        more than one width rule.
        """
        import json

        text = (FIXTURES / "A_hmmscan_01_widen.tbl").read_text()
        lines = body_lines(text)
        rows = split_body_rows(lines, "ws")
        old = TableLayout.from_dict(json.loads((FIXTURES / "A_hmmscan_old_layout.json").read_text()))
        self.assertTrue(old.pinned)
        self.assertEqual(old.columns[0].width_rule, "fixed_min")
        self.assertEqual(old.columns[0].min_width, 20)
        rendered = render_table(rows, old, query_col=2)
        self.assertEqual(body_mismatch_count(rendered, lines, "order"), 22)
        layout = infer_table_layout(
            [{"name": "probe", "lines": lines, "rows": rows}],
            query_col=2,
            delim="ws",
        )
        if layout.pinned:
            self.assertEqual(layout.scope, "per_query")
            self.assertEqual(layout.columns[0].width_rule, "max_value")
            got = render_table(rows, layout, query_col=2)
            self.assertEqual(body_mismatch_count(got, lines, "order"), 0)
        else:
            self.assertIn("unique", layout.reason)
            self.assertIn("pin", layout.reason.lower())
            got = render_table(rows, layout, query_col=2)
            self.assertEqual(
                body_mismatch_count(got, lines, "order", match_ws=True), 0
            )


if __name__ == "__main__":
    unittest.main()
