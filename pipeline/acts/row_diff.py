"""Shared body-row difference classifier for reference-search tables.

Used by research scripts, the CLI, and (once landed) the console. One
implementation only — do not reimplement token keys elsewhere.

Table kinds:

- ``tbl`` — per-sequence rows; key is (target, query) at token indices 0 and 2
- ``dom`` — per-domain rows; key is (target, query, ali from/to) at indices
  0, 3, 15, 16, 17, 18

Difference classes:

- ``whitespace-only`` — same tokens, different spacing
- ``missing`` / ``extra`` — row-key multiset differs
- ``order`` — same keys, different order
- ``value-only`` — same keys, different remaining tokens
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any


def body_lines_from_text(text: str) -> list[str]:
    # Match acts.reference_run.body_lines (exact-mode MATCH unit).
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def read_body(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return body_lines_from_text(path.read_text())


def row_key(tokens: list[str], kind: str) -> tuple:
    """Stable identity for one body row.

    ``kind`` is ``tbl`` (per-sequence) or ``dom`` (per-domain).
    """
    need = 3 if kind == "tbl" else 19
    if len(tokens) < need:
        return ("short-line", kind, len(tokens))
    if kind == "tbl":
        return (tokens[0], tokens[2])
    return (tokens[0], tokens[3], tokens[15], tokens[16], tokens[17], tokens[18])


def classify(replay: list[str], stock_lines: list[str], kind: str) -> dict[str, Any]:
    """Compare two bodies of the same table kind.

    Returns counts and a ``classes`` list. Empty ``classes`` with
    ``byte_equal`` true means MATCH.
    """
    byte_equal = replay == stock_lines
    rt = [line.split() for line in replay]
    st = [line.split() for line in stock_lines]
    out: dict[str, Any] = {
        "kind": kind,
        "lines_replay": len(replay),
        "lines_stock": len(stock_lines),
        "byte_equal": byte_equal,
        "token_equal": rt == st,
        "classes": [],
        "missing_keys": 0,
        "extra_keys": 0,
    }
    if byte_equal or rt == st:
        if not byte_equal:
            out["classes"] = ["whitespace-only"]
        return out

    rc = Counter(row_key(toks, kind) for toks in rt)
    sc = Counter(row_key(toks, kind) for toks in st)
    missing = sum(1 for key in sc if sc[key] > rc[key])
    extra = sum(1 for key in rc if rc[key] > sc[key])
    classes: list[str] = []
    if missing:
        classes.append("missing")
    if extra:
        classes.append("extra")
    if not missing and not extra:
        rk = [row_key(toks, kind) for toks in rt]
        sk = [row_key(toks, kind) for toks in st]
        if rk != sk:
            classes.append("order")

    value = False
    buckets: dict[tuple, list[list[str]]] = {}
    for toks in rt:
        buckets.setdefault(row_key(toks, kind), []).append(toks)
    for toks in st:
        group = buckets.get(row_key(toks, kind))
        if not group:
            continue
        if group.pop(0) != toks:
            value = True
    if value:
        classes.append("value-only")

    out["classes"] = classes
    out["missing_keys"] = missing
    out["extra_keys"] = extra
    return out


def compare_pair(
    replay_tbl: Path,
    replay_dom: Path,
    stock_tbl: Path,
    stock_dom: Path,
) -> dict[str, Any]:
    tbl = classify(read_body(replay_tbl), read_body(stock_tbl), "tbl")
    dom = classify(read_body(replay_dom), read_body(stock_dom), "dom")
    return {
        "tbl": tbl,
        "dom": dom,
        "byte_equal": bool(tbl["byte_equal"] and dom["byte_equal"]),
    }
