"""Text tables: '#' metadata, body MATCH (order or multiset)."""

from __future__ import annotations

from collections import Counter


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
    if n <= 1:
        return [[" ".join(r)] if r else [] for r in raw]
    return [r[: n - 1] + [" ".join(r[n - 1 :])] for r in raw]


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
