"""Text tables: '#' metadata, body MATCH (order or multiset)."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field


def is_meta(line: str) -> bool:
    return line.startswith("#")


def body_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln and not is_meta(ln)]


def meta_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if is_meta(ln)]


def detect_delim(rows: list[str]) -> str:
    if any("\t" in ln for ln in rows):
        return "tab"
    return "ws"


def split_row(line: str, delim: str) -> list[str]:
    if delim == "tab":
        return line.split("\t")
    return line.split()


def split_body_rows(lines: list[str], delim: str) -> list[list[str]]:
    """Whitespace tables: last field may contain spaces; collapse from the min width."""
    if delim == "tab":
        return [split_row(ln, delim) for ln in lines]
    raw = [ln.split() for ln in lines]
    if not raw:
        return []
    n = min(len(r) for r in raw)
    return _collapse_last(raw, n)


def split_body_rows_n(lines: list[str], delim: str, n_cols: int) -> list[list[str]]:
    """Split body lines into `n_cols` cells. The last cell keeps internal spaces.

    Use the contract's column count so a trailing free-text field is one cell
    even when some lines have more tokens than others.
    """
    if n_cols <= 0:
        return split_body_rows(lines, delim)
    if delim == "tab":
        rows = []
        for ln in lines:
            parts = ln.split("\t")
            if len(parts) <= n_cols:
                rows.append(parts)
            else:
                rows.append(parts[: n_cols - 1] + ["\t".join(parts[n_cols - 1 :])])
        return rows
    raw = [ln.split() for ln in lines]
    return _collapse_last(raw, n_cols)


def _collapse_last(raw: list[list[str]], n: int) -> list[list[str]]:
    if not raw:
        return []
    if n <= 1:
        return [[" ".join(r)] if r else [] for r in raw]
    out: list[list[str]] = []
    for row in raw:
        if len(row) <= n:
            out.append(row)
        else:
            out.append(row[: n - 1] + [" ".join(row[n - 1 :])])
    return out


def join_row(cells: list[str], delim: str) -> str:
    if delim == "tab":
        return "\t".join(cells)
    return " ".join(cells)


def bodies_equal(a: str, b: str) -> bool:
    return body_lines(a) == body_lines(b)


def bodies_multiset_equal(a: str, b: str) -> bool:
    return Counter(body_lines(a)) == Counter(body_lines(b))


def ws_line(line: str) -> str:
    return " ".join(line.split())


def bodies_ws_equal(a: str, b: str) -> bool:
    return [ws_line(ln) for ln in body_lines(a)] == [ws_line(ln) for ln in body_lines(b)]


def bodies_ws_multiset_equal(a: str, b: str) -> bool:
    return Counter(ws_line(ln) for ln in body_lines(a)) == Counter(ws_line(ln) for ln in body_lines(b))


def tables_match(a: str, b: str, match: str, *, match_ws: bool = False) -> bool:
    if match_ws:
        if match == "multiset":
            return bodies_ws_multiset_equal(a, b)
        return bodies_ws_equal(a, b)
    if match == "multiset":
        return bodies_multiset_equal(a, b)
    return bodies_equal(a, b)


def body_mismatch_count(
    got: list[str], want: list[str], match: str, *, match_ws: bool = False
) -> int:
    """Rows that fail `match` between two body-line lists. Zero is MATCH."""
    norm = ws_line if match_ws else (lambda line: line)
    if match == "multiset":
        cg = Counter(norm(ln) for ln in got)
        cw = Counter(norm(ln) for ln in want)
        keys = set(cg) | set(cw)
        return sum(abs(cg[k] - cw[k]) for k in keys) // 2
    n = max(len(got), len(want))
    bad = 0
    for i in range(n):
        left = norm(got[i]) if i < len(got) else None
        right = norm(want[i]) if i < len(want) else None
        if left != right:
            bad += 1
    return bad


def token_starts(line: str, cells: list[str]) -> list[int] | None:
    starts: list[int] = []
    pos = 0
    for cell in cells:
        i = line.find(cell, pos)
        if i < 0:
            return None
        starts.append(i)
        pos = i + len(cell)
    return starts


def measure_widths(line: str, cells: list[str]) -> list[int] | None:
    starts = token_starts(line, cells)
    if starts is None:
        return None
    widths = [len(c) for c in cells]
    for i in range(len(cells) - 1):
        widths[i] = starts[i + 1] - starts[i]
    return widths


def merge_widths(rows: list[list[int]]) -> list[int]:
    n = max((len(r) for r in rows), default=0)
    out = [0] * n
    for row in rows:
        for i, w in enumerate(row):
            if w > out[i]:
                out[i] = w
    return out


def align_body(lines: list[str], delim: str, min_widths: list[int]) -> list[str]:
    """Left-justify whitespace columns to max(min_width, cell) for this body."""
    if delim == "tab" or not min_widths or not lines:
        return lines
    rows = split_body_rows(lines, delim)
    n = max(len(min_widths), max((len(r) for r in rows), default=0))
    widths = list(min_widths) + [0] * (n - len(min_widths))
    for row in rows:
        for i, cell in enumerate(row[:-1] if len(row) > 1 else []):
            need = len(cell) + 1
            if need > widths[i]:
                widths[i] = need
    out: list[str] = []
    for row in rows:
        if len(row) <= 1:
            out.append(join_row(row, delim))
            continue
        parts: list[str] = []
        for i, cell in enumerate(row[:-1]):
            w = widths[i] if i < len(widths) else len(cell)
            parts.append(cell.ljust(w))
        parts.append(row[-1])
        out.append("".join(parts))
    return out


@dataclass
class ColLayout:
    """One non-last column: alignment and how its field width is chosen."""

    align: str
    width_rule: str
    min_width: int


@dataclass
class TableLayout:
    """Generic column layout. Last column is always unpadded."""

    delim: str
    scope: str = "fixed"
    columns: list[ColLayout] = field(default_factory=list)
    pinned: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "delim": self.delim,
            "scope": self.scope,
            "columns": [asdict(c) for c in self.columns],
            "pinned": self.pinned,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, raw: dict | None) -> TableLayout:
        if not raw:
            return cls(delim="ws", pinned=False, reason="no layout")
        cols = [
            ColLayout(
                align=str(c.get("align", "left")),
                width_rule=str(c.get("width_rule", "fixed_min")),
                min_width=int(c.get("min_width", 0)),
            )
            for c in raw.get("columns") or []
        ]
        return cls(
            delim=str(raw.get("delim") or "ws"),
            scope=str(raw.get("scope") or "fixed"),
            columns=cols,
            pinned=bool(raw.get("pinned")),
            reason=str(raw.get("reason") or ""),
        )


def pad_cell(cell: str, width: int, align: str) -> str:
    if width <= 0 or len(cell) >= width:
        return cell
    return cell.rjust(width) if align == "right" else cell.ljust(width)


def _row_widths(
    rows: list[list[str]], columns: list[ColLayout]
) -> list[int]:
    widths: list[int] = []
    for i, col in enumerate(columns):
        if col.width_rule == "max_value":
            mx = max((len(row[i]) for row in rows if i < len(row)), default=0)
            widths.append(max(col.min_width, mx))
        else:
            widths.append(col.min_width)
    return widths


def _render_row(row: list[str], layout: TableLayout, widths: list[int]) -> str:
    if layout.delim == "tab":
        return "\t".join(row)
    if len(row) <= 1:
        return row[0] if row else ""
    parts: list[str] = []
    for i, cell in enumerate(row[:-1]):
        if i < len(layout.columns):
            spec = layout.columns[i]
            w = widths[i] if i < len(widths) else spec.min_width
            if spec.width_rule == "fixed_min":
                w = max(spec.min_width, len(cell))
            else:
                w = max(w, len(cell))
            parts.append(pad_cell(cell, w, spec.align))
        else:
            parts.append(cell)
    parts.append(row[-1])
    return " ".join(parts)


def render_table(
    rows: list[list[str]],
    layout: TableLayout,
    query_col: int = 0,
) -> list[str]:
    """Re-render cells under an inferred layout. Whole-body for per-file scope."""
    if not rows:
        return []
    if layout.delim == "tab" or not layout.pinned:
        join = "\t" if layout.delim == "tab" else " "
        return [join.join(row) for row in rows]
    if layout.scope == "per_query":
        groups: dict[str, list[list[str]]] = defaultdict(list)
        order: list[str] = []
        for row in rows:
            q = row[query_col] if query_col < len(row) else ""
            if q not in groups:
                order.append(q)
            groups[q].append(row)
        out: list[str] = []
        for q in order:
            subset = groups[q]
            widths = _row_widths(subset, layout.columns)
            out.extend(_render_row(r, layout, widths) for r in subset)
        return out
    widths = _row_widths(rows, layout.columns)
    return [_render_row(r, layout, widths) for r in rows]


@dataclass
class _Obs:
    line: str
    cells: list[str]
    starts: list[int]
    sample: str
    query: str


def _scope_keys(scope: str, queries: list[str], samples: list[str]) -> list[str]:
    if scope == "per_query":
        return [f"{s}\0{q}" for s, q in zip(samples, queries)]
    if scope == "per_file":
        return list(samples)
    return ["all"] * len(queries)


def _lengths_vary(keys: list[str], lengths: list[int]) -> bool:
    seen: dict[str, int] = {}
    for key, ln in zip(keys, lengths):
        prev = seen.get(key)
        if prev is None:
            seen[key] = ln
        elif prev != ln:
            return True
    return False


def _fit_width_rule(
    lengths: list[int],
    field_ws: list[int],
    queries: list[str],
    samples: list[str],
) -> tuple[tuple[str, int, str] | None, list[tuple[str, int, str]]]:
    """Return (unique rule, every rule that explains these widths).

    A layout may be pinned only when one rule survives. `fixed_min` used to
    win whenever it fit, including when a per-query or per-file max explained
    the same probe. Rules that implement the same function on this probe are
    one rule: a max-value rule whose groups never contain two cell lengths
    is the same renderer as `fixed_min` with that floor. A max-value rule
    that still fits after the probe has shown two lengths in one group is a
    real competitor, and the column stays unpinned.
    """
    if len(lengths) != len(field_ws) or not lengths:
        return None, []
    if any(fw < ln for fw, ln in zip(field_ws, lengths)):
        return None, []

    def fixed_min() -> tuple[str, int, str] | None:
        extras = [fw for fw, ln in zip(field_ws, lengths) if fw > ln]
        if extras:
            w = min(extras)
            if any(fw > ln and fw != w for fw, ln in zip(field_ws, lengths)):
                return None
            if any(fw != max(w, ln) for fw, ln in zip(field_ws, lengths)):
                return None
            return ("fixed_min", w, "fixed")
        return ("fixed_min", 0, "fixed")

    def grouped_max(keys: list[str], scope: str) -> tuple[str, int, str] | None:
        buckets: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for key, fw, ln in zip(keys, field_ws, lengths):
            buckets[key].append((fw, ln))
        revealed: list[int] = []
        for pairs in buckets.values():
            fws = {fw for fw, _ln in pairs}
            if len(fws) != 1:
                return None
            f = next(iter(fws))
            mx = max(ln for _fw, ln in pairs)
            if f < mx:
                return None
            if f > mx:
                revealed.append(f)
        if revealed and len(set(revealed)) != 1:
            return None
        w0 = revealed[0] if revealed else 0
        for pairs in buckets.values():
            f = next(iter({fw for fw, _ln in pairs}))
            mx = max(ln for _fw, ln in pairs)
            if f != max(w0, mx):
                return None
        return ("max_value", w0, scope)

    fits: list[tuple[str, int, str]] = []
    fm = fixed_min()
    if fm is not None:
        fits.append(fm)
    pq = grouped_max(_scope_keys("per_query", queries, samples), "per_query")
    if pq is not None:
        fits.append(pq)
    pf = grouped_max(_scope_keys("per_file", queries, samples), "per_file")
    if pf is not None:
        fits.append(pf)
    if not fits:
        return None, []

    fixed = next((rule for rule in fits if rule[0] == "fixed_min"), None)
    kept: list[tuple[str, int, str]] = []
    for rule, width, scope in fits:
        if (
            rule == "max_value"
            and fixed is not None
            and fixed[1] == width
            and not _lengths_vary(_scope_keys(scope, queries, samples), lengths)
        ):
            continue
        kept.append((rule, width, scope))
    per_query = next((rule for rule in kept if rule[2] == "per_query"), None)
    per_file = next((rule for rule in kept if rule[2] == "per_file"), None)
    if per_query is not None and per_file is not None and per_query[1] == per_file[1]:
        by_sample: dict[str, set[str]] = defaultdict(set)
        for sample, query in zip(samples, queries):
            by_sample[sample].add(query)
        if all(len(names) <= 1 for names in by_sample.values()):
            kept = [rule for rule in kept if rule[2] != "per_file"]
    if len(kept) == 1:
        return kept[0], kept
    return None, kept


def _rule_tag(rule: tuple[str, int, str]) -> str:
    name, width, scope = rule
    return f"{name}/{width}/{scope}"


def _layout_scope(cols: list[tuple[ColLayout, str]]) -> str | None:
    votes = {vote for _col, vote in cols if _col.width_rule == "max_value"}
    if not votes:
        return "fixed"
    if votes == {"per_file"}:
        return "per_file"
    if votes == {"per_query"}:
        return "per_query"
    if votes <= {"per_query", "fixed"}:
        return "per_query"
    if votes <= {"per_file", "fixed"}:
        return "per_file"
    return None


def infer_table_layout(
    samples: list[dict],
    query_col: int,
    delim: str,
) -> TableLayout:
    """Pin a column layout from SHORT/LONG/mixed probe bodies, or fall back."""
    if delim == "tab":
        n = 0
        for sample in samples:
            for row in sample.get("rows") or []:
                n = max(n, len(row))
        cols = [ColLayout("left", "fixed_min", 0) for _ in range(max(0, n - 1))]
        return TableLayout(
            delim="tab",
            scope="fixed",
            columns=cols,
            pinned=True,
            reason="tab delimiter; no pad",
        )

    obs: list[_Obs] = []
    for sample in samples:
        name = str(sample.get("name") or "probe")
        lines: list[str] = list(sample.get("lines") or [])
        rows: list[list[str]] = list(sample.get("rows") or [])
        for line, row in zip(lines, rows):
            if not row:
                continue
            starts = token_starts(line, row)
            if starts is None or len(starts) != len(row):
                continue
            q = row[query_col] if query_col < len(row) else ""
            obs.append(_Obs(line, row, starts, name, q))
    if not obs:
        return TableLayout(
            delim=delim,
            pinned=True,
            reason="empty body; no pad",
        )

    n_cols = min(len(o.cells) for o in obs)
    if n_cols <= 1:
        return TableLayout(
            delim="ws",
            pinned=True,
            reason="single column; no pad",
        )
    if any(len(o.cells) != n_cols for o in obs):
        return TableLayout(
            delim="ws",
            pinned=False,
            reason="ragged column count",
        )

    budget = {"left": 8000}
    ambiguous: list[tuple[int, list[tuple[str, int, str]]]] = []

    def dfs(
        col: int,
        field_starts: list[int],
        specs: list[tuple[ColLayout, str]],
    ) -> TableLayout | None:
        budget["left"] -= 1
        if budget["left"] < 0:
            return None
        if col == n_cols - 1:
            if any(o.starts[col] != field_starts[i] for i, o in enumerate(obs)):
                return None
            scope = _layout_scope(specs)
            if scope is None:
                return None
            layout = TableLayout(
                delim="ws",
                scope=scope,
                columns=[c for c, _v in specs],
                pinned=True,
                reason="",
            )
            if _layout_reproduces(obs, layout, query_col, samples):
                return layout
            return None

        lengths = [len(o.cells[col]) for o in obs]
        queries = [o.query for o in obs]
        sample_ids = [o.sample for o in obs]
        tries: list[tuple[str, list[int], list[int]]] = []

        left_ok = all(o.starts[col] == field_starts[i] for i, o in enumerate(obs))
        if left_ok:
            flush_ws = [o.starts[col + 1] - field_starts[i] - 1 for i, o in enumerate(obs)]
            next_lens = [len(o.cells[col + 1]) for o in obs]
            if all(w >= ln for w, ln in zip(flush_ws, lengths)):
                tries.append(("left", flush_ws, [o.starts[col + 1] for o in obs]))
            zero_next = [field_starts[i] + lengths[i] + 1 for i in range(len(obs))]
            if all(zero_next[i] <= obs[i].starts[col + 1] for i in range(len(obs))):
                tries.append(("left", list(lengths), zero_next))
            for total in sorted({flush_ws[i] + next_lens[i] for i in range(len(obs))}):
                if total < 0 or total > 40:
                    continue
                for wc in range(0, total + 1):
                    wn = total - wc
                    field_ws = [max(wc, ln) for ln in lengths]
                    if any(
                        flush_ws[i]
                        != field_ws[i] + max(wn, next_lens[i]) - next_lens[i]
                        for i in range(len(obs))
                    ):
                        continue
                    next_fs = [
                        field_starts[i] + field_ws[i] + 1 for i in range(len(obs))
                    ]
                    if any(
                        next_fs[i] > obs[i].starts[col + 1]
                        or next_fs[i] < obs[i].starts[col] + lengths[i] + 1
                        for i in range(len(obs))
                    ):
                        continue
                    tries.append(("left", field_ws, next_fs))

        right_ok = all(o.starts[col] >= field_starts[i] for i, o in enumerate(obs))
        if right_ok:
            field_ws = [
                o.starts[col] + lengths[i] - field_starts[i] for i, o in enumerate(obs)
            ]
            next_fs = [o.starts[col] + lengths[i] + 1 for i, o in enumerate(obs)]
            if all(fw >= ln for fw, ln in zip(field_ws, lengths)):
                tries.append(("right", field_ws, next_fs))

        seen: set[tuple] = set()
        for align, field_ws, next_fs in tries:
            key = (align, tuple(field_ws), tuple(next_fs))
            if key in seen:
                continue
            seen.add(key)
            unique, kept = _fit_width_rule(lengths, field_ws, queries, sample_ids)
            if unique is None:
                if len(kept) > 1 and not any(col == seen_col for seen_col, _ in ambiguous):
                    ambiguous.append((col, kept))
                continue
            rule, min_w, vote = unique
            spec = ColLayout(align=align, width_rule=rule, min_width=min_w)
            found = dfs(col + 1, next_fs, specs + [(spec, vote)])
            if found is not None:
                return found
        return None

    found = dfs(0, [0] * len(obs), [])
    if found is not None:
        found.reason = (
            f"pinned {found.scope}; "
            + ", ".join(
                f"{i}:{c.align}/{c.width_rule}/{c.min_width}"
                for i, c in enumerate(found.columns)
            )
        )
        return found
    if ambiguous:
        parts = [
            f"col {col} fits " + ", ".join(_rule_tag(rule) for rule in kept)
            for col, kept in ambiguous
        ]
        return TableLayout(
            delim="ws",
            pinned=False,
            reason="could not pin a unique width rule: " + "; ".join(parts),
        )
    extra = _mixed_width_inconsistency(obs, query_col, samples)
    reason = "probe could not pin alignment, width rule, or scope"
    if extra:
        reason = f"{reason} ({extra})"
    return TableLayout(
        delim="ws",
        pinned=False,
        reason=reason,
    )


def _mixed_width_inconsistency(
    obs: list[_Obs], query_col: int, samples: list[dict]
) -> str:
    mixed = [o for o in obs if o.sample == "mixed"]
    if len(mixed) < 2 or query_col < 0:
        return ""
    widths: dict[str, set[int]] = defaultdict(set)
    for o in mixed:
        if query_col >= len(o.starts) or query_col >= len(o.cells):
            continue
        if query_col + 1 >= len(o.starts):
            continue
        fw = o.starts[query_col + 1] - o.starts[query_col]
        key = "short" if len(o.cells[query_col]) < fw - 1 else "long"
        widths[key].add(fw)
    if len(widths.get("short") or []) > 1:
        return (
            "mixed-sample field widths for short names are not a single "
            "per-row, per-query, or per-file rule"
        )
    return ""


def _layout_reproduces(
    obs: list[_Obs],
    layout: TableLayout,
    query_col: int,
    samples: list[dict],
) -> bool:
    by_sample: dict[str, list[_Obs]] = defaultdict(list)
    for o in obs:
        by_sample[o.sample].append(o)
    for sample in samples:
        name = str(sample.get("name") or "probe")
        group = by_sample.get(name) or []
        if not group:
            continue
        got = render_table([o.cells for o in group], layout, query_col=query_col)
        want = [o.line for o in group]
        if got != want:
            return False
    return True


def layout_pad_widths(layout: TableLayout) -> list[int]:
    """Compat: start-to-start floors (printf width + one-space separator)."""
    if not layout.pinned or layout.delim == "tab":
        return []
    return [c.min_width + 1 for c in layout.columns]
