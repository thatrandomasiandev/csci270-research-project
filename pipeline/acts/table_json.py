"""JSON-records output format (opt-in).

Rows are elements of one top-level array; cells are flattened scalar fields
(dotted paths) so exact-token column inference finds record and entry ids.
Rendering uses Semgrep's compact JSON form: ``separators=(',', ':')``,
key order preserved, ``ensure_ascii=False``. Selected only via
``--output-format json-records``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from acts.reference_formats import FormatError

JSON_RECORDS = "json-records"
JSON_BLOB_COL = "__json__"
SEMGREP_SEPARATORS = (",", ":")


@dataclass
class JsonRecordsDoc:
    """Parsed JSON-records document."""

    rows_key: str
    envelope: dict[str, Any]  # top-level fields except rows_key
    key_order: list[str]  # original top-level key order
    rows: list[dict[str, Any]]  # original row objects
    flat_rows: list[list[str]]  # flattened scalar cells + trailing __json__
    columns: list[str]  # flat column names including __json__


def _flatten(obj: Any, prefix: str = "") -> dict[str, str]:
    """Flatten nested dicts to dotted scalar paths. Lists and empty dicts skipped."""
    out: dict[str, str] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                out.update(_flatten(value, path))
            elif isinstance(value, list):
                continue
            elif value is None:
                out[path] = "null"
            elif isinstance(value, bool):
                out[path] = "true" if value else "false"
            elif isinstance(value, (int, float, str)):
                out[path] = str(value)
            else:
                out[path] = str(value)
    return out


def dumps_semgrep(obj: Any) -> str:
    """Serialize like Semgrep's JSON formatter (compact, no ASCII escape)."""
    return json.dumps(obj, separators=SEMGREP_SEPARATORS, ensure_ascii=False)


def strip_volatile(obj: dict[str, Any], volatile: tuple[str, ...]) -> dict[str, Any]:
    if not volatile:
        return obj
    return {k: v for k, v in obj.items() if k not in volatile}


def parse_json_records(text: str, *, rows_key: str = "results") -> JsonRecordsDoc:
    if not text:
        raise FormatError("empty json-records")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FormatError(f"json-records is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise FormatError("json-records top level must be an object")
    if rows_key not in data:
        raise FormatError(f"json-records missing rows key {rows_key!r}")
    rows = data[rows_key]
    if not isinstance(rows, list):
        raise FormatError(f"json-records key {rows_key!r} must be an array")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise FormatError(f"json-records row {index} is not an object")

    key_order = list(data.keys())
    envelope = {k: v for k, v in data.items() if k != rows_key}

    # Union of flattened keys across rows, stable by first-seen order.
    col_order: list[str] = []
    seen: set[str] = set()
    flats: list[dict[str, str]] = []
    for row in rows:
        flat = _flatten(row)
        flats.append(flat)
        for key in flat:
            if key not in seen:
                seen.add(key)
                col_order.append(key)
    columns = col_order + [JSON_BLOB_COL]
    flat_rows: list[list[str]] = []
    for row, flat in zip(rows, flats):
        cells = [flat.get(col, "") for col in col_order]
        cells.append(dumps_semgrep(row))
        flat_rows.append(cells)

    return JsonRecordsDoc(
        rows_key=rows_key,
        envelope=envelope,
        key_order=key_order,
        rows=list(rows),
        flat_rows=flat_rows,
        columns=columns,
    )


def to_line_table(doc: JsonRecordsDoc) -> str:
    """Tab-separated table with a header line for the fitter/cache path."""
    lines = ["#" + "\t".join(doc.columns)]
    for row in doc.flat_rows:
        lines.append("\t".join(row))
    return "\n".join(lines) + ("\n" if lines else "")


def rows_from_line_table(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse the synthetic table produced by ``to_line_table``."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("#"):
        raise FormatError("json-records line table missing header")
    columns = lines[0][1:].split("\t")
    rows = [ln.split("\t") for ln in lines[1:]]
    return columns, rows


def render_json_records(
    *,
    envelope: dict[str, Any],
    key_order: list[str],
    rows_key: str,
    row_objects: list[dict[str, Any]],
) -> str:
    """Build a Semgrep-shaped JSON document from envelope + row objects."""
    out: dict[str, Any] = {}
    placed = set()
    for key in key_order:
        if key == rows_key:
            out[key] = row_objects
            placed.add(key)
        elif key in envelope:
            out[key] = envelope[key]
            placed.add(key)
    if rows_key not in placed:
        out[rows_key] = row_objects
    for key, value in envelope.items():
        if key not in placed:
            out[key] = value
    return dumps_semgrep(out)


def row_objects_from_table(text: str) -> list[dict[str, Any]]:
    columns, rows = rows_from_line_table(text)
    if JSON_BLOB_COL not in columns:
        raise FormatError("json-records table missing __json__ column")
    blob_i = columns.index(JSON_BLOB_COL)
    objects: list[dict[str, Any]] = []
    for row in rows:
        if blob_i >= len(row):
            raise FormatError("json-records row missing __json__ cell")
        objects.append(json.loads(row[blob_i]))
    return objects


def sort_semgrep_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Match Semgrep RuleMatch.ordering_key: path, start, end, check_id, message."""

    def key(row: dict[str, Any]):
        start = row.get("start") or {}
        end = row.get("end") or {}
        extra = row.get("extra") or {}
        return (
            str(row.get("path", "")),
            int(start.get("line", 0)),
            int(start.get("col", 0)),
            int(end.get("line", 0)),
            int(end.get("col", 0)),
            str(row.get("check_id", "")),
            str(extra.get("message", "")),
        )

    return sorted(rows, key=key)


def round_trip_bytes(text: str, *, rows_key: str = "results") -> str:
    """parse then render; used to prove Semgrep byte identity."""
    doc = parse_json_records(text, rows_key=rows_key)
    return render_json_records(
        envelope=doc.envelope,
        key_order=doc.key_order,
        rows_key=doc.rows_key,
        row_objects=doc.rows,
    )


def equal_except_volatile(a: str, b: str, volatile: tuple[str, ...], *, rows_key: str = "results") -> bool:
    """True when a and b match after dropping caller-declared volatile fields."""
    try:
        da = json.loads(a)
        db = json.loads(b)
    except json.JSONDecodeError:
        return False
    if not isinstance(da, dict) or not isinstance(db, dict):
        return False
    return strip_volatile(da, volatile) == strip_volatile(db, volatile)


def prove_round_trip(text: str, *, rows_key: str = "results", volatile: tuple[str, ...] = ()) -> None:
    """Raise FormatError unless render(parse(x)) equals x (volatile-aware).

    Semgrep's ``time`` object contains floats whose shortest JSON form can
    differ from Python's ``json.dumps`` (e.g. ``...329e-06`` vs ``...33e-06``).
    With ``volatile=('time',)``, equality is required on the compact dump of
    every other top-level field, including ``results``.
    """
    rendered = round_trip_bytes(text, rows_key=rows_key)
    if volatile:
        da = strip_volatile(json.loads(text), volatile)
        db = strip_volatile(json.loads(rendered), volatile)
        # Drop volatile keys from key order so dumps match byte-for-byte.
        if dumps_semgrep(da) != dumps_semgrep(db):
            raise FormatError("json-records round-trip diverged after stripping volatile fields")
        return
    if rendered != text and rendered + "\n" != text and rendered != text + "\n":
        raise FormatError("json-records round-trip is not byte-identical")
