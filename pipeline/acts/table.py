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
