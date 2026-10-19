"""Infer a normalizer pin and reporting thresholds from help text and probes.

The procedure is docs/KNOB_INFERENCE_PROTOCOL.md. This module does not name
a tool and does not contain a flag literal. The option tokens come from the
help text the caller passes in.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from collections.abc import Callable, Sequence

from acts.reference_fit import ColumnReport, TableReport, index_rows, parse_finite, parse_table_text
from acts.reference_formats import Entry, RecordItem

SIZE_MEMBERS = ("entry_count", "total_entry_length")
PER_KEY = "per_key_row_count"
SLACK = 4.0
MAX_CALLS = 96
# Threshold probes tighten a printed default. They do not relax it.
TIGHTEN_FACTORS = (10, 100, 1000)
MIN_REMOVED = 3
_INTEGER = re.compile(r"[+-]?\d+")
_NOT_A_THRESHOLD_REJECTION = frozenset(
    {"accept", "inconclusive", "non-reporting threshold", "no numeric default", "not probed"}
)

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


def _first_option_index(argv: Sequence[str]) -> int:
    """Index of the first option token after the program, or ``len(argv)``."""
    for index, token in enumerate(argv):
        if index > 0 and str(token).startswith("-"):
            return index
    return len(argv)


def _argv_text(argv: Sequence[str]) -> str:
    proc = subprocess.run(list(argv), check=False, capture_output=True, text=True)
    return f"{proc.stdout or ''}{proc.stderr or ''}"


def capture_help_argv(argv: Sequence[str]) -> str:
    """Help text for a command that may have subcommands before its options.

    ``j`` runs from 1 through the index of the first option token. For each
    ``j``, try ``argv[:j] + ['--help']`` and then ``argv[:j] + ['-h']``.
    Return the first text that contains a numeric-argument option.

    If none do, try the bare prefixes ``argv[:j]`` in the same order. Some
    programs print usage when required arguments are absent and reject a
    help flag as an unknown option. Return the first bare text that
    contains a numeric-argument option.

    If that also fails, return the last bare prefix's text. Parsing it is
    the caller's job. An empty candidate list is not an acceptance.
    """
    if not argv or not str(argv[0]):
        raise ValueError("argv is empty")
    end = _first_option_index(argv)
    if end < 1:
        end = 1
    last = ""
    for j in range(1, end + 1):
        prefix = list(argv[:j])
        for flag in ("--help", "-h"):
            last = _argv_text([*prefix, flag])
            if parse_help_options(last):
                return last
    for j in range(1, end + 1):
        last = _argv_text(list(argv[:j]))
        if parse_help_options(last):
            return last
    return last


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

    structural = _structural_columns(tables, whole_out)
    thresholds: list[dict] = []
    threshold_reason: dict[str, str] = {}
    threshold_probes: dict[str, list] = {}
    capped = False
    for candidate in candidates:
        option = candidate["option"]
        default = candidate["default"]
        if default is None:
            threshold_reason[option] = "no numeric default"
            threshold_probes[option] = []
            continue
        if capped:
            threshold_reason[option] = "cap"
            threshold_probes[option] = []
            continue
        status, found, probes, hit_cap = _tighten_option(
            tables, structural, whole_out, whole, option, float(default), run
        )
        if hit_cap:
            capped = True
        threshold_reason[option] = status
        threshold_probes[option] = probes
        thresholds.extend(found)

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
                "probes": threshold_probes.get(option, []),
            }
        )
    return {
        "pin": pin,
        "reason": pin_reason,
        "thresholds": thresholds,
        "structural": structural,
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
    order = index_rows(parsed.rows, table.record_col, table.entry_col, table.index_col)
    # index_rows keeps file order, which is the order of raw_lines.
    return {
        key: (cells, raw)
        for (key, cells), raw in zip(order.items(), parsed.raw_lines, strict=True)
    }


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


def _body_rows(text: str) -> list[list[str]]:
    return parse_table_text("", text).rows


def _integer_token(token: str) -> int | None:
    if _INTEGER.fullmatch(token) is None:
        return None
    return int(token)


def _structural_columns(tables: list[TableReport], default_out: dict[str, str]) -> dict[str, list[dict]]:
    """Integer columns that are a row count or a within-group rank on the default run."""
    parsed = {table.name: _body_rows(default_out.get(table.name, "")) for table in tables}
    pair_counts: dict[str, Counter] = {}
    record_counts: dict[str, Counter] = {}
    for table in tables:
        pairs: Counter = Counter()
        records: Counter = Counter()
        rec, ent = table.record_col, table.entry_col
        for row in parsed[table.name]:
            if rec >= len(row) or ent >= len(row):
                continue
            pairs[(row[rec], row[ent])] += 1
            records[row[rec]] += 1
        pair_counts[table.name] = pairs
        record_counts[table.name] = records
    found: dict[str, list[dict]] = {}
    for table in tables:
        rows = parsed[table.name]
        columns: list[dict] = []
        if not rows:
            found[table.name] = columns
            continue
        width = min(len(row) for row in rows)
        for index in range(width):
            if index in (table.record_col, table.entry_col):
                continue
            values = [_integer_token(row[index]) for row in rows]
            if any(value is None for value in values):
                continue
            kind = _structural_kind(
                table, rows, index, values, pair_counts, record_counts, tables
            )
            if kind is not None:
                columns.append({"index": index, **kind})
        found[table.name] = columns
    return found


def _structural_kind(
    table: TableReport,
    rows: list[list[str]],
    index: int,
    values: list[int | None],
    pair_counts: dict[str, Counter],
    record_counts: dict[str, Counter],
    tables: list[TableReport],
) -> dict | None:
    if _is_rank(table, rows, values):
        return {"kind": "rank"}
    rec, ent = table.record_col, table.entry_col
    for other in tables:
        pairs = pair_counts[other.name]
        records = record_counts[other.name]
        if all(
            pairs[(row[rec], row[ent])] == value
            for row, value in zip(rows, values)
            if rec < len(row) and ent < len(row)
        ) and len(rows) == sum(1 for row in rows if rec < len(row) and ent < len(row)):
            return {"kind": "count", "key": "record,entry", "count_table": other.name}
        if all(
            records[row[rec]] == value
            for row, value in zip(rows, values)
            if rec < len(row)
        ) and len(rows) == sum(1 for row in rows if rec < len(row)):
            return {"kind": "count", "key": "record", "count_table": other.name}
    return None


def _is_rank(table: TableReport, rows: list[list[str]], values: list[int | None]) -> bool:
    groups: dict[tuple[str, str], list[int]] = {}
    rec, ent = table.record_col, table.entry_col
    for row, value in zip(rows, values):
        if value is None or rec >= len(row) or ent >= len(row):
            return False
        groups.setdefault((row[rec], row[ent]), []).append(value)
    if not groups:
        return False
    return all(seen == list(range(1, len(seen) + 1)) for seen in groups.values())


def _identity_drop(table: TableReport, structural: dict[str, list[dict]]) -> set[int]:
    drop = {int(item["index"]) for item in structural.get(table.name, [])}
    for col in table.columns:
        if col.member == PER_KEY:
            drop.add(col.index)
    return drop


def _identity(cells: list[str], drop: set[int]) -> tuple[str, ...]:
    return tuple(cell for index, cell in enumerate(cells) if index not in drop)


def _align(
    default_rows: list[list[str]],
    tight_rows: list[list[str]],
    drop: set[int],
) -> tuple[list[tuple[int, int]], list[int]] | None:
    """Pair tight rows to default rows by identity. None when a tight identity is new."""
    used = [False] * len(default_rows)
    default_ids = [_identity(row, drop) for row in default_rows]
    pairs: list[tuple[int, int]] = []
    for tight_index, row in enumerate(tight_rows):
        ident = _identity(row, drop)
        found = None
        for default_index, did in enumerate(default_ids):
            if not used[default_index] and did == ident:
                found = default_index
                break
        if found is None:
            return None
        used[found] = True
        pairs.append((found, tight_index))
    removed = [index for index, flag in enumerate(used) if not flag]
    return pairs, removed


def _removed_count(default_rows: list[list[str]], tight_rows: list[list[str]], drop: set[int]) -> int:
    default_ids = Counter(_identity(row, drop) for row in default_rows)
    tight_ids = Counter(_identity(row, drop) for row in tight_rows)
    return sum(max(0, default_ids[key] - tight_ids[key]) for key in default_ids)


def _drop_cells_differ(
    default_rows: list[list[str]],
    tight_rows: list[list[str]],
    pairs: list[tuple[int, int]],
    drop: set[int],
) -> bool:
    for default_index, tight_index in pairs:
        left, right = default_rows[default_index], tight_rows[tight_index]
        for index in drop:
            if index >= len(left) or index >= len(right) or left[index] != right[index]:
                return True
    return False


def _bound_columns(
    table_name: str,
    default_rows: list[list[str]],
    tight_rows: list[list[str]],
    pairs: list[tuple[int, int]],
    removed: list[int],
    threshold: float,
) -> list[str]:
    if not removed:
        return []
    width = max(len(default_rows[index]) for index in removed)
    qualified: list[str] = []
    for index in range(width):
        if not _cuts_at(default_rows, tight_rows, pairs, removed, index, threshold):
            continue
        qualified.append(f"{table_name}:{index}")
    return qualified


def _cuts_at(
    default_rows: list[list[str]],
    tight_rows: list[list[str]],
    pairs: list[tuple[int, int]],
    removed: list[int],
    index: int,
    threshold: float,
) -> bool:
    for default_index in removed:
        row = default_rows[default_index]
        if index >= len(row):
            return False
        value = parse_finite(row[index])
        if value is None or not value > threshold:
            return False
    for default_index, tight_index in pairs:
        for row in (default_rows[default_index], tight_rows[tight_index]):
            if index >= len(row):
                return False
            value = parse_finite(row[index])
            if value is None or not value <= threshold:
                return False
    return True


def _table_tighten(
    table: TableReport,
    default_text: str,
    tight_text: str,
    drop: set[int],
    threshold: float,
) -> dict:
    default_rows = _body_rows(default_text)
    tight_rows = _body_rows(tight_text)
    aligned = _align(default_rows, tight_rows, drop)
    if aligned is None:
        removed = _removed_count(default_rows, tight_rows, drop)
        return {
            "removed": removed,
            "outcome": "shared rows changed",
            "reason": "shared rows changed",
            "columns": [],
        }
    pairs, removed = aligned
    removed_n = len(removed)
    if removed_n == 0:
        if _drop_cells_differ(default_rows, tight_rows, pairs, drop):
            return {
                "removed": 0,
                "outcome": "non-reporting threshold",
                "reason": "non-reporting threshold",
                "columns": [],
            }
        return {"removed": 0, "outcome": "unchanged", "reason": "unchanged", "columns": []}
    if removed_n < MIN_REMOVED:
        return {
            "removed": removed_n,
            "outcome": "inconclusive",
            "reason": "inconclusive",
            "columns": [],
        }
    columns = _bound_columns(table.name, default_rows, tight_rows, pairs, removed, threshold)
    if not columns:
        return {
            "removed": removed_n,
            "outcome": "no exact bound",
            "reason": "no exact bound",
            "columns": [],
        }
    return {"removed": removed_n, "outcome": "accept", "reason": "accept", "columns": columns}


def _tighten_option(
    tables: list[TableReport],
    structural: dict[str, list[dict]],
    default_out: dict[str, str],
    whole: Sequence[Entry],
    option: str,
    default: float,
    run: Callable[[Sequence[Entry], Sequence[str]], dict[str, str]],
) -> tuple[str, list[dict], list[dict], bool]:
    """Walk the tighten ladder. The bool is whether the probe cap was hit."""
    accepted: dict[str, dict] = {}
    probes: list[dict] = []
    saw_removed = False
    saw_column_only = False
    saw_throw = False
    reject_reason = "no exact bound"
    hit_cap = False
    for factor in TIGHTEN_FACTORS:
        if tables and all(table.name in accepted for table in tables):
            break
        threshold = float(default) / float(factor)
        try:
            tight = run(whole, _option_argv(option, threshold))
        except _Cap:
            hit_cap = True
            probes.append({"factor": factor, "t": threshold, "outcome": "cap", "reason": "cap", "tables": {}})
            break
        except Exception as exc:
            saw_throw = True
            reason = f"tool failed: {exc}"
            probes.append(
                {"factor": factor, "t": threshold, "outcome": reason, "reason": reason, "tables": {}}
            )
            continue
        per_table: dict[str, dict] = {}
        factor_removed = False
        factor_column_only = False
        for table in tables:
            if table.name in accepted:
                per_table[table.name] = {
                    "removed": 0,
                    "outcome": "accept",
                    "reason": "accept",
                    "columns": accepted[table.name]["columns"],
                }
                continue
            judged = _table_tighten(
                table,
                default_out.get(table.name, ""),
                tight.get(table.name, ""),
                _identity_drop(table, structural),
                threshold,
            )
            per_table[table.name] = judged
            if judged["outcome"] == "accept":
                columns = list(judged["columns"])
                accepted[table.name] = {
                    "option": option,
                    "default": default,
                    "table": table.name,
                    "column": ",".join(columns),
                    "factor": factor,
                    "t": threshold,
                    "columns": columns,
                }
            elif judged["removed"] >= MIN_REMOVED:
                factor_removed = True
                reject_reason = str(judged["reason"])
            elif judged["outcome"] == "non-reporting threshold":
                factor_column_only = True
        saw_removed = saw_removed or factor_removed or any(
            item["removed"] >= MIN_REMOVED and item["outcome"] != "accept" for item in per_table.values()
        )
        if factor_removed:
            reject_reason = next(
                (
                    item["reason"]
                    for item in per_table.values()
                    if item["removed"] >= MIN_REMOVED and item["outcome"] != "accept"
                ),
                reject_reason,
            )
        identities_stable = all(
            item["outcome"] in {"unchanged", "non-reporting threshold"}
            for item in per_table.values()
        )
        if identities_stable and factor_column_only:
            saw_column_only = True
        probes.append(
            {
                "factor": factor,
                "t": threshold,
                "outcome": _factor_outcome(per_table),
                "reason": _factor_outcome(per_table),
                "tables": per_table,
            }
        )
    found = []
    for table in tables:
        if table.name not in accepted:
            continue
        item = dict(accepted[table.name])
        item.pop("columns", None)
        found.append(item)
    if hit_cap and not accepted and not saw_removed and not saw_column_only:
        return "cap", found, probes, True
    if accepted:
        return "accept", found, probes, hit_cap
    if saw_removed:
        return reject_reason, [], probes, hit_cap
    if saw_column_only:
        return "non-reporting threshold", [], probes, hit_cap
    if saw_throw:
        thrown = next(item["reason"] for item in probes if str(item["reason"]).startswith("tool failed"))
        return thrown, [], probes, hit_cap
    if hit_cap:
        return "cap", [], probes, True
    return "inconclusive", [], probes, False


def _factor_outcome(per_table: dict[str, dict]) -> str:
    if any(item["outcome"] == "accept" for item in per_table.values()):
        return "accept"
    for name in ("shared rows changed", "no exact bound", "non-reporting threshold"):
        if any(item["outcome"] == name for item in per_table.values()):
            return name
    if any(item["outcome"] == "inconclusive" for item in per_table.values()):
        return "inconclusive"
    return "unchanged"


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
        if reason is not None and reason not in _NOT_A_THRESHOLD_REJECTION:
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
