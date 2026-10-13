"""Infer a normalizer pin and reporting thresholds from help text and probes.

The procedure is docs/KNOB_INFERENCE_PROTOCOL.md. This module does not name
a tool and does not contain a flag literal. The option tokens come from the
help text the caller passes in.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence

from acts.reference_fit import ColumnReport, TableReport, parse_finite, parse_table_text, row_key
from acts.reference_formats import Entry, RecordItem

SIZE_MEMBERS = ("entry_count", "total_entry_length")
SLACK = 4.0
MAX_CALLS = 96

# Placeholder names that denote one numeric argument. File and string
# placeholders are absent on purpose.
_PLACEHOLDER_NAMES = frozenset(
    {
        "x",
        "n",
        "num",
        "int",
        "float",
        "double",
        "integer",
        "number",
        "real",
        "size",
        "count",
        "value",
    }
)
_BARE_PLACEHOLDERS = frozenset({"N", "NUM", "INT", "FLOAT", "NUMBER"})
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_OPTION_RE = re.compile(
    r"(?P<opt>--?[A-Za-z0-9][\w-]*)"
    r"(?:=|\s+)"
    r"(?:<(?P<bracket>[A-Za-z][A-Za-z0-9_]*)>|(?P<bare>N|NUM|INT|FLOAT|NUMBER)\b)"
)
_BRACKET_DEFAULT_RE = re.compile(rf"\[\s*({_NUMBER})\s*\]")
_PAREN_DEFAULT_RE = re.compile(rf"\(\s*default\s*[:=]?\s*({_NUMBER})\s*\)", re.IGNORECASE)
_WORD_DEFAULT_RE = re.compile(rf"\bdefault\s*[:=]\s*({_NUMBER})", re.IGNORECASE)

Invoke = Callable[[Sequence[RecordItem], Sequence[Entry], Sequence[str]], dict[str, str]]

_IDENTITY = frozenset({"identity", "byte"})


class _Cap(Exception):
    """The probe budget is spent. Not an acceptance."""


def parse_help_options(text: str) -> list[dict]:
    """Options that take one numeric argument, in help order.

    Each item is ``{"option", "default", "help_line"}``. ``default`` is a
    float or ``None``. A repeated option token keeps the first line.
    """
    found: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = _OPTION_RE.search(line)
        if match is None:
            continue
        bracket = match.group("bracket")
        bare = match.group("bare")
        if bracket is not None:
            if bracket.lower() not in _PLACEHOLDER_NAMES:
                continue
        elif bare not in _BARE_PLACEHOLDERS:
            continue
        option = match.group("opt")
        if option in seen:
            continue
        seen.add(option)
        found.append(
            {
                "option": option,
                "default": _default_on_line(line),
                "help_line": line.strip(),
            }
        )
    return found


def capture_help(executable: str) -> str:
    """``executable -h``, or ``--help`` when ``-h`` yields no numeric option.

    The process exit code is ignored. Stdout and stderr are concatenated.
    """
    primary = _help_text(executable, "-h")
    if parse_help_options(primary):
        return primary
    return _help_text(executable, "--help")


def apply_extra_argv(base: Sequence[str], extra: Sequence[str]) -> list[str]:
    """Append ``extra`` and drop an earlier copy of each option it sets.

    A probed value has to be the one in effect when the base command already
    carries the same option.
    """
    extra_list = list(extra)
    replaced: set[str] = set()
    index = 0
    while index < len(extra_list):
        replaced.add(extra_list[index])
        index += 1
        if index < len(extra_list) and not str(extra_list[index]).startswith("-"):
            index += 1
    out: list[str] = []
    index = 0
    base_list = list(base)
    while index < len(base_list):
        token = base_list[index]
        if token in replaced:
            index += 1
            if index < len(base_list) and not str(base_list[index]).startswith("-"):
                index += 1
            continue
        out.append(token)
        index += 1
    return out + extra_list


def member_value(member: str, entries: Sequence[Entry]) -> int:
    """``M(reference)`` for a size member. Other members are not pins."""
    if member == "entry_count":
        return len(entries)
    if member == "total_entry_length":
        return sum(entry.length for entry in entries)
    raise ValueError(f"not a size member: {member}")


def format_probe_value(value: float) -> str:
    """Integer decimal when the value is integral, otherwise a short round-trip."""
    nearest = round(value)
    if abs(value - nearest) <= 1e-9 * max(1.0, abs(value)):
        return str(int(nearest))
    return format(value, ".12g")


def infer_knobs(
    help_text: str,
    records: Sequence[RecordItem],
    whole: Sequence[Entry],
    half: Sequence[Entry],
    contract: Sequence[TableReport] | Sequence[dict],
    invoke: Invoke,
    *,
    slack: float = SLACK,
    max_calls: int = MAX_CALLS,
) -> dict:
    """Return the pin, the thresholds, the rejections, and ``tool_calls``."""
    if slack <= 1:
        raise ValueError("slack must be greater than 1")
    if not records or not whole or not half:
        raise ValueError("records, whole, and half must be non-empty")
    tables = _coerce_tables(contract)
    candidates = parse_help_options(help_text)
    half_ids = {token for entry in half for token in entry.keys}
    calls = {"n": 0}
    cache: dict[tuple, dict[str, str]] = {}

    def run(entries: Sequence[Entry], extra: Sequence[str]) -> dict[str, str]:
        key = (tuple(entry.content_hash for entry in entries), tuple(extra))
        if key in cache:
            return cache[key]
        if calls["n"] >= max_calls:
            raise _Cap()
        calls["n"] += 1
        result = invoke(records, entries, extra)
        cache[key] = result
        return result

    try:
        half_out = run(half, ())
        whole_out = run(whole, ())
    except _Cap:
        return _empty("cap", calls["n"], candidates)
    except Exception as exc:  # baseline failure: nothing to compare
        return _empty(f"tool failed: {exc}", calls["n"], candidates)

    fitted = [
        member
        for member in SIZE_MEMBERS
        if any(col.member == member for table in tables for col in table.columns)
    ]
    member_notes: dict[str, dict] = {}
    normalizer_reason: dict[tuple[str, str], str] = {}

    for member in fitted:
        if not _member_visible(tables, half_out, whole_out, half_ids, member):
            member_notes[member] = {"status": "no knob", "reason": "probe cannot see M"}
            continue
        value = member_value(member, whole)
        passed: list[str] = []
        try:
            for candidate in candidates:
                option = candidate["option"]
                try:
                    probed = run(half, _option_argv(option, float(value)))
                except _Cap:
                    for rest in candidates[candidates.index(candidate) :]:
                        normalizer_reason[(rest["option"], member)] = "cap"
                    raise
                except Exception as exc:
                    normalizer_reason[(option, member)] = f"tool failed: {exc}"
                    continue
                reason = _normalizer_reason(tables, probed, whole_out, half_ids, member)
                if reason is None:
                    passed.append(option)
                    normalizer_reason[(option, member)] = "accept"
                else:
                    normalizer_reason[(option, member)] = reason
        except _Cap:
            member_notes[member] = {"status": "no knob", "reason": "cap"}
            continue
        if any(normalizer_reason.get((c["option"], member)) == "cap" for c in candidates):
            member_notes[member] = {"status": "no knob", "reason": "cap"}
            continue
        try:
            chosen = _tie_break(tables, passed, half, whole_out, half_ids, value, run)
        except _Cap:
            member_notes[member] = {"status": "no knob", "reason": "cap"}
            continue
        if len(chosen) == 1:
            option = chosen[0]
            template = f"{option} {{{member}}}"
            member_notes[member] = {"status": "pinned", "option": option, "template": template}
            for option_name in passed:
                if option_name != option:
                    normalizer_reason[(option_name, member)] = "tie"
        else:
            reason = "tie" if passed else "no knob"
            member_notes[member] = {"status": "no knob", "reason": reason}
            for option_name in passed:
                normalizer_reason[(option_name, member)] = "tie"

    if not fitted:
        pin = "no knob"
        pin_reason = "no fitted size member"
    elif any(member_notes[member]["status"] != "pinned" for member in fitted):
        pin = "no knob"
        pin_reason = "; ".join(
            f"{member}: {member_notes[member].get('reason', 'no knob')}" for member in fitted
        )
    else:
        pin = " ".join(member_notes[member]["template"] for member in fitted)
        pin_reason = ""

    thresholds: list[dict] = []
    threshold_reason: dict[str, str] = {}
    capped = False
    for candidate in candidates:
        option = candidate["option"]
        default = candidate["default"]
        if default is None:
            threshold_reason[option] = "no numeric default"
            continue
        if capped:
            threshold_reason[option] = "cap"
            continue
        try:
            relaxed = run(whole, _option_argv(option, float(default) * slack))
        except _Cap:
            capped = True
            threshold_reason[option] = "cap"
            continue
        except Exception as exc:
            threshold_reason[option] = f"tool failed: {exc}"
            continue
        column, reason = _threshold_column(tables, whole_out, relaxed, float(default), slack)
        if reason is None and column is not None:
            threshold_reason[option] = "accept"
            thresholds.append({"option": option, "default": default, "column": column})
        else:
            threshold_reason[option] = reason or "no bounded column"

    rejected = _rejections(candidates, fitted, normalizer_reason, threshold_reason, member_notes)
    audited = []
    for candidate in candidates:
        option = candidate["option"]
        audited.append(
            {
                "option": option,
                "default": candidate["default"],
                "help_line": candidate["help_line"],
                "normalizer": {
                    member: normalizer_reason.get((option, member), "not probed")
                    for member in fitted
                },
                "threshold": threshold_reason.get(option, "not probed"),
            }
        )
    return {
        "pin": pin,
        "reason": pin_reason,
        "thresholds": thresholds,
        "rejected": rejected,
        "candidates": audited,
        "members": member_notes,
        "tool_calls": calls["n"],
    }


def _help_text(executable: str, flag: str) -> str:
    proc = subprocess.run(
        [executable, flag],
        check=False,
        capture_output=True,
        text=True,
    )
    return f"{proc.stdout or ''}{proc.stderr or ''}"


def _default_on_line(line: str) -> float | None:
    for pattern in (_BRACKET_DEFAULT_RE, _PAREN_DEFAULT_RE, _WORD_DEFAULT_RE):
        match = pattern.search(line)
        if match is not None:
            value = parse_finite(match.group(1))
            if value is not None:
                return value
    return None


def _coerce_tables(contract: Sequence[TableReport] | Sequence[dict]) -> list[TableReport]:
    tables: list[TableReport] = []
    for item in contract:
        if isinstance(item, TableReport):
            tables.append(item)
            continue
        columns = [
            ColumnReport(
                index=int(col["index"]),
                role=str(col.get("role") or ""),
                member=col.get("member"),
            )
            for col in item.get("columns") or []
        ]
        index_col = item.get("index_col")
        tables.append(
            TableReport(
                name=str(item["name"]),
                record_col=int(item["record_col"]),
                entry_col=int(item["entry_col"]),
                index_col=None if index_col is None else int(index_col),
                meta=list(item.get("meta") or []),
                columns=columns,
            )
        )
    return tables


def _option_argv(option: str, value: float) -> list[str]:
    return [option, format_probe_value(value)]


def _index_table(table: TableReport, text: str) -> dict[tuple[str, str, str], tuple[list[str], str]]:
    parsed = parse_table_text(table.name, text)
    indexed: dict[tuple[str, str, str], tuple[list[str], str]] = {}
    for cells, raw in zip(parsed.rows, parsed.raw_lines):
        key = row_key(cells, table.record_col, table.entry_col, table.index_col)
        if key in indexed:
            raise ValueError(f"duplicate row key {key}")
        indexed[key] = (cells, raw)
    return indexed


def _shared_keys(
    left: dict[tuple[str, str, str], tuple[list[str], str]],
    right: dict[tuple[str, str, str], tuple[list[str], str]],
    half_ids: set[str],
) -> list[tuple[str, str, str]]:
    keys = []
    for key in left:
        if key in right and key[1] in half_ids:
            keys.append(key)
    return keys


def _member_visible(
    tables: list[TableReport],
    half_out: dict[str, str],
    whole_out: dict[str, str],
    half_ids: set[str],
    member: str,
) -> bool:
    saw_row = False
    for table in tables:
        columns = [col.index for col in table.columns if col.member == member]
        if not columns:
            continue
        try:
            half_rows = _index_table(table, half_out.get(table.name, ""))
            whole_rows = _index_table(table, whole_out.get(table.name, ""))
        except ValueError:
            return False
        for key in _shared_keys(half_rows, whole_rows, half_ids):
            saw_row = True
            left, right = half_rows[key][0], whole_rows[key][0]
            for index in columns:
                if index >= len(left) or index >= len(right) or left[index] != right[index]:
                    return True
    return False


def _normalizer_reason(
    tables: list[TableReport],
    probed: dict[str, str],
    whole_out: dict[str, str],
    half_ids: set[str],
    member: str,
) -> str | None:
    saw = False
    for table in tables:
        wanted = [col.index for col in table.columns if col.member == member]
        identity = [col.index for col in table.columns if col.member in _IDENTITY]
        if not wanted and not identity:
            continue
        try:
            got = _index_table(table, probed.get(table.name, ""))
            whole_rows = _index_table(table, whole_out.get(table.name, ""))
        except ValueError as exc:
            return f"tool failed: {exc}"
        for key in _shared_keys(got, whole_rows, half_ids):
            saw = True
            cells, whole_cells = got[key][0], whole_rows[key][0]
            for index in wanted:
                if index >= len(cells) or index >= len(whole_cells) or cells[index] != whole_cells[index]:
                    return "m-columns differ"
            for index in identity:
                if index >= len(cells) or index >= len(whole_cells) or cells[index] != whole_cells[index]:
                    return "identity columns differ"
    if not saw:
        return "no shared rows"
    return None


def _tie_break(
    tables: list[TableReport],
    passed: list[str],
    half: Sequence[Entry],
    whole_out: dict[str, str],
    half_ids: set[str],
    value: int,
    run: Callable[[Sequence[Entry], Sequence[str]], dict[str, str]],
) -> list[str]:
    if len(passed) < 2:
        return list(passed)
    kept: list[str] = []
    for option in passed:
        try:
            probed = run(half, _option_argv(option, float(value)))
        except _Cap:
            raise
        except Exception:
            continue
        if _bodies_match(tables, probed, whole_out, half_ids):
            kept.append(option)
    return kept


def _bodies_match(
    tables: list[TableReport],
    probed: dict[str, str],
    whole_out: dict[str, str],
    half_ids: set[str],
) -> bool:
    saw = False
    for table in tables:
        try:
            got = _index_table(table, probed.get(table.name, ""))
            whole_rows = _index_table(table, whole_out.get(table.name, ""))
        except ValueError:
            return False
        for key in _shared_keys(got, whole_rows, half_ids):
            saw = True
            if got[key][1] != whole_rows[key][1]:
                return False
    return saw


def _threshold_column(
    tables: list[TableReport],
    baseline: dict[str, str],
    relaxed: dict[str, str],
    default: float,
    slack: float,
) -> tuple[str | None, str | None]:
    hi = default * slack
    qualified: list[str] = []
    added_any = False
    for table in tables:
        try:
            base_rows = _index_table(table, baseline.get(table.name, ""))
            rel_rows = _index_table(table, relaxed.get(table.name, ""))
        except ValueError as exc:
            return None, f"tool failed: {exc}"
        if not set(base_rows) <= set(rel_rows):
            return None, "rows dropped"
        for key, (cells, raw) in base_rows.items():
            if rel_rows[key][1] != raw or rel_rows[key][0] != cells:
                return None, "shared rows changed"
        added = [key for key in rel_rows if key not in base_rows]
        if not added:
            continue
        added_any = True
        width = min(len(rel_rows[key][0]) for key in added)
        for index in range(width):
            values: list[float] = []
            numeric = True
            for key in added:
                parsed = parse_finite(rel_rows[key][0][index])
                if parsed is None:
                    numeric = False
                    break
                values.append(parsed)
            if not numeric or not values:
                continue
            if all(default < value <= hi for value in values):
                qualified.append(f"{table.name}:{index}")
    if not added_any:
        return None, "row set unchanged"
    if not qualified:
        return None, "no bounded column"
    return ",".join(qualified), None


def _rejections(
    candidates: list[dict],
    fitted: list[str],
    normalizer_reason: dict[tuple[str, str], str],
    threshold_reason: dict[str, str],
    member_notes: dict[str, dict],
) -> list[dict]:
    rejected: list[dict] = []
    for member, note in member_notes.items():
        if note.get("reason") == "probe cannot see M":
            rejected.append(
                {"option": None, "role": "normalizer", "member": member, "reason": "probe cannot see M"}
            )
    for candidate in candidates:
        option = candidate["option"]
        for member in fitted:
            reason = normalizer_reason.get((option, member))
            if reason is None or reason == "accept":
                continue
            rejected.append(
                {"option": option, "role": "normalizer", "member": member, "reason": reason}
            )
        reason = threshold_reason.get(option)
        if reason is not None and reason != "accept":
            rejected.append({"option": option, "role": "threshold", "reason": reason})
    return rejected


def _empty(reason: str, tool_calls: int, candidates: list[dict]) -> dict:
    return {
        "pin": "no knob",
        "reason": reason,
        "thresholds": [],
        "rejected": [{"option": None, "role": "normalizer", "reason": reason}],
        "candidates": [
            {
                "option": item["option"],
                "default": item["default"],
                "help_line": item["help_line"],
                "normalizer": {},
                "threshold": "not probed",
            }
            for item in candidates
        ],
        "members": {},
        "tool_calls": tool_calls,
    }
