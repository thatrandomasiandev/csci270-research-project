"""Two-input runs: F(records, reference).

Amdahl, written before any constant-shaving. A scan whose measured cost is
T = a + b·n (a = 31.959641573764316 s, b = 0.7228553909794854 s/record,
n = 4192; results/headline_screen.json) follows the pre-registered
break-even model T_stock = a + b·n, T_inc = a + c·b·n. The dominant term
of one incremental re-annotation is b·n_changed. The wrapper and the merge
are not in that model. The probe is paid once. Do not micro-optimize them.

Index files (the sidecars a tool writes beside a reference before it will
read it) are not discovered by tracing. Tracing here is Linux-only and
records reads, while the index has to be built for every sub-reference
before the tool runs, including on a Mac. The caller declares that build
with --prep, a command containing {reference}. The command is data. No
tool name is compiled into this module.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import shlex
import subprocess
import time
from pathlib import Path
from collections.abc import Callable, Sequence

from acts.audit import AUDIT_FLOOR, AUDIT_P, AUDIT_SEED, pick_audit
from acts.fasta import FastaRec, write_fasta
from acts.reference_cache import ReferenceCache, argv_namespace, connect_cache
from acts.reference_fit import (
    PROBE_K,
    PROBE_N,
    PROBE_SEED,
    BYTE,
    IDENTITY,
    ColumnReport,
    FitResult,
    TableReport,
    column_phi,
    disambiguating_indices,
    dump_rescale_provenance,
    fit_observations,
    index_rows,
    parse_table_text,
    partition_indices,
    per_record_counts,
    ref_merge_rows,
    rescale_cells,
    resolve_ties,
    sample_record_indices,
)
from acts.reference_formats import (
    Entry,
    FormatError,
    RecordItem,
    alias_map,
    parse_reference,
    parses_as_entries,
    read_records,
    write_entries,
)
from acts.strategies.base import Strategy, StrategyResult
from acts.table import TableLayout, detect_delim, infer_table_layout, render_table

Invoke = Callable[[Sequence[RecordItem], Sequence[Entry]], dict[str, str]]
PinnedInvoke = Callable[[Sequence[RecordItem], Sequence[Entry], dict[str, int]], dict[str, str]]

# Normalizer members the caller's --pin template can set. per_key_row_count is
# not here: the tool derives it from its own reported set, which replay
# reproduces. See docs/EXACT_REPLAY_PROTOCOL.md.
PIN_PLACEHOLDERS = {"entry_count": "{entry_count}", "total_entry_length": "{total_entry_length}"}


class RunError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def detect_reference(argv: list[str], input_path: Path, override: Path | None) -> Path:
    """The argv-named file that is not the record input and parses as entries."""
    if override is not None:
        return override
    try:
        input_res = input_path.resolve()
    except OSError:
        input_res = input_path
    found: list[Path] = []
    for token in argv:
        if token.startswith("{") or token.startswith("-"):
            continue
        path = Path(token)
        if not path.is_file():
            continue
        try:
            if path.resolve() == input_res:
                continue
        except OSError:
            continue
        if parses_as_entries(path):
            found.append(path)
    if len(found) == 1:
        return found[0]
    if not found:
        raise RunError("no argv-named reference parses as entries; pass --reference")
    raise RunError("more than one argv file parses as entries; pass --reference")


def _same(token: str, path: Path | None) -> bool:
    if path is None or token.startswith("-") or token.startswith("{"):
        return False
    try:
        return Path(token).expanduser().resolve() == path.resolve()
    except OSError:
        return False


def materialize_argv(
    argv: list[str],
    *,
    input_slot: Path,
    input_file: Path,
    reference_slot: Path,
    reference_file: Path,
    work: Path,
) -> tuple[list[str], dict[str, Path]]:
    outputs: dict[str, Path] = {}
    cmd: list[str] = []
    for token in argv:
        if token == "{input}" or _same(token, input_slot):
            cmd.append(str(input_file))
        elif token == "{reference}" or _same(token, reference_slot):
            cmd.append(str(reference_file))
        elif token == "{output}":
            dest = work / "out"
            outputs["out"] = dest
            cmd.append(str(dest))
        elif token.startswith("{output:") and token.endswith("}"):
            name = token[len("{output:") : -1]
            if not name or "/" in name or name in {".", ".."}:
                raise RunError(f"bad output placeholder {token}")
            dest = work / name
            outputs[name] = dest
            cmd.append(str(dest))
        else:
            cmd.append(token)
    return cmd, outputs


def run_prep(prep: str | None, reference_file: Path) -> None:
    if not prep:
        return
    cmd = [part.replace("{reference}", str(reference_file)) for part in shlex.split(prep)]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-500:]
        raise RunError(f"prep failed ({proc.returncode}): {err}")


def write_record_file(records: Sequence[RecordItem], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if any(rec.sequence for rec in records):
        write_fasta(
            path,
            [FastaRec(rec.name, rec.description, rec.sequence) for rec in records],
        )
        return path
    path.write_text("".join(f"{rec.key}\n" for rec in records))
    return path


def _clock_add(clock: dict[str, float], name: str, dt: float) -> None:
    clock[name] = clock.get(name, 0.0) + float(dt)


def subprocess_invoke(
    argv: list[str],
    *,
    input_slot: Path,
    reference_slot: Path,
    prep: str | None,
    scratch: Path,
    clock: dict[str, float] | None = None,
    full_entries: int | None = None,
) -> Invoke:
    """`full_entries`: a call on that many entries first tries the caller's own
    reference as is (it is prepared for the stock command), with no rewrite and
    no prep. If the tool fails on it, that call and later ones fall back to a
    written and prepared copy, as for every sub-reference."""
    counter = {"n": 0}
    state = {"original_ok": True}
    phase = clock if clock is not None else {}

    def attempt(records, entries, work: Path, use_original: bool) -> dict[str, str]:
        started = time.perf_counter()
        rec_path = write_record_file(records, work / "records")
        ref_path = reference_slot if use_original else write_entries(list(entries), work / "reference")
        _clock_add(phase, "subref_build_s", time.perf_counter() - started)
        started = time.perf_counter()
        if not use_original:
            run_prep(prep, ref_path)
        _clock_add(phase, "prep_s", time.perf_counter() - started)
        cmd, outputs = materialize_argv(
            argv,
            input_slot=input_slot,
            input_file=rec_path,
            reference_slot=reference_slot,
            reference_file=ref_path,
            work=work,
        )
        started = time.perf_counter()
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        _clock_add(phase, "tool_s", time.perf_counter() - started)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "")[-500:]
            raise RunError(f"tool failed ({proc.returncode}): {err}")
        tables: dict[str, str] = {}
        started = time.perf_counter()
        if outputs:
            for name, dest in outputs.items():
                if not dest.is_file():
                    raise RunError(f"tool did not write output {name}")
                tables[name] = dest.read_text()
        else:
            tables["stdout"] = proc.stdout
        _clock_add(phase, "read_output_s", time.perf_counter() - started)
        return tables

    def invoke(records: Sequence[RecordItem], entries: Sequence[Entry]) -> dict[str, str]:
        counter["n"] += 1
        work = scratch / f"call{counter['n']}"
        work.mkdir(parents=True, exist_ok=True)
        whole = full_entries is not None and len(entries) == full_entries
        if whole and state["original_ok"]:
            try:
                return attempt(records, entries, work, True)
            except RunError:
                state["original_ok"] = False
        return attempt(records, entries, work, False)

    return invoke


def _subset(entries: Sequence[Entry], indices: Sequence[int]) -> list[Entry]:
    return [entries[i] for i in sorted(indices)]


def _layout_dict(text: str, record_col: int) -> dict:
    parsed = parse_table_text("layout", text)
    if not parsed.raw_lines:
        return TableLayout(delim="ws", pinned=False, reason="empty body").to_dict()
    layout = infer_table_layout(
        [{"name": "probe", "lines": parsed.raw_lines, "rows": parsed.rows}],
        record_col,
        detect_delim(parsed.raw_lines),
    )
    return layout.to_dict()


def tables_from_dict(raw_tables: list[dict]) -> list[TableReport]:
    reports: list[TableReport] = []
    for raw in raw_tables:
        columns = [
            ColumnReport(
                index=int(col["index"]),
                role=str(col["role"]),
                member=col.get("member"),
                count_table=col.get("count_table"),
                primary_fits=list(col.get("primary_fits") or []),
                tie=list(col.get("tie") or []),
                tie_break=col.get("tie_break"),
            )
            for col in raw.get("columns") or []
        ]
        reports.append(
            TableReport(
                name=str(raw["name"]),
                record_col=int(raw["record_col"]),
                entry_col=int(raw["entry_col"]),
                index_col=raw.get("index_col"),
                meta=list(raw.get("meta") or []),
                columns=columns,
                layout=dict(raw.get("layout") or {}),
            )
        )
    return reports


def probe_fit(
    entries: Sequence[Entry],
    records: Sequence[RecordItem],
    invoke: Invoke,
    *,
    seed: int = PROBE_SEED,
    n_p: int = PROBE_N,
    k: int = PROBE_K,
    primary_parts: list[list[int]] | None = None,
    baseline: str | None = None,
    sample: bool = True,
    monotone: bool = False,
) -> FitResult:
    """Run the pre-registered probe and fit or refuse. Does not splice probe rows."""
    if len(entries) < 2:
        return FitResult(decision="REFUSE", reason="fewer than 2 reference entries")
    if not records:
        return FitResult(decision="REFUSE", reason="record input is empty")
    parts = primary_parts if primary_parts is not None else partition_indices(len(entries), k, seed)
    if sample:
        chosen = sample_record_indices(len(records), min(n_p, len(records)), seed)
        probe_records = [records[i] for i in chosen]
    else:
        probe_records = list(records)
    try:
        whole = invoke(probe_records, list(entries))
        part_tables = [invoke(probe_records, _subset(entries, indices)) for indices in parts]
    except RunError as exc:
        return FitResult(decision="REFUSE", reason=exc.reason)
    try:
        aliases = alias_map(list(entries))
    except FormatError as exc:
        return FitResult(decision="REFUSE", reason=str(exc))
    lengths = [entry.length for entry in entries]
    result = fit_observations(
        entries_n=len(entries),
        lengths=lengths,
        part_index_lists=parts,
        record_ids={rec.key for rec in probe_records},
        alias_to_index=aliases,
        whole_tables=whole,
        part_tables=part_tables,
        baseline=baseline,
        monotone=monotone,
    )
    if result.decision == "TIE":
        if baseline == "gestore":
            result.decision = "REFUSE"
            result.reason = "baseline does not infer a normalizer"
            return result
        split = disambiguating_indices(lengths, [entry.content_hash for entry in entries])
        if split is None:
            result.decision = "REFUSE"
            result.reason = "tie stands; the disambiguating partition is empty"
            return result
        left, right = split
        try:
            tie_tables = [
                invoke(probe_records, _subset(entries, left)),
                invoke(probe_records, _subset(entries, right)),
            ]
        except RunError as exc:
            result.decision = "REFUSE"
            result.reason = exc.reason
            return result
        result = resolve_ties(
            result,
            entries_n=len(entries),
            lengths=lengths,
            tie_parts=[left, right],
            record_ids={rec.key for rec in probe_records},
            alias_to_index=aliases,
            whole_tables=whole,
            tie_tables=tie_tables,
            monotone=monotone,
        )
    if result.decision == "SHIP":
        for table in result.tables:
            table.layout = _layout_dict(whole.get(table.name, ""), table.record_col)
            if not table.meta:
                table.meta = parse_table_text(table.name, whole.get(table.name, "")).meta
    return result


def _entry_order(entries: Sequence[Entry]) -> dict[str, int]:
    order: dict[str, int] = {}
    for index, entry in enumerate(entries):
        for token in entry.keys:
            order.setdefault(token, index)
    return order


def render_table_text(
    table: TableReport,
    rows: list[list[str]],
) -> str:
    layout = TableLayout.from_dict(table.layout)
    body = render_table(rows, layout, query_col=table.record_col)
    lines = list(table.meta) + body
    return "\n".join(lines) + ("\n" if lines else "")


def _basis(entries: Sequence[Entry], counts: dict[str, dict[str, int]], record_key: str) -> dict:
    return {
        "entry_count": len(entries),
        "total_entry_length": sum(entry.length for entry in entries),
        "row_count": {name: per.get(record_key, 0) for name, per in counts.items()},
    }


def _rows_from_run(
    texts: dict[str, str],
    tables: list[TableReport],
    entries: Sequence[Entry],
) -> list[dict]:
    aliases = alias_map(list(entries))
    indexed: dict[str, dict] = {}
    for table in tables:
        parsed = parse_table_text(table.name, texts.get(table.name, ""))
        try:
            indexed[table.name] = index_rows(
                parsed.rows, table.record_col, table.entry_col, table.index_col
            )
        except ValueError as exc:
            raise RunError(str(exc)) from exc
    counts = {name: per_record_counts(indexed[name]) for name in indexed}
    held: list[dict] = []
    for table in tables:
        for (record_key, entry_token, row_index), cells in indexed[table.name].items():
            if entry_token not in aliases:
                raise RunError(f"{table.name}: entry token {entry_token!r} is not in this reference")
            entry = entries[aliases[entry_token]]
            held.append(
                {
                    "table": table.name,
                    "record_key": record_key,
                    "entry_hash": entry.content_hash,
                    "entry_token": entry_token,
                    "row_index": row_index,
                    "cells": list(cells),
                    "basis": _basis(entries, counts, record_key),
                }
            )
    return held


def _rescale_held(
    held: list[dict],
    tables: list[TableReport],
    new_entry_count: int,
    new_length: int,
) -> list[dict]:
    by_table = {table.name: table for table in tables}
    new_counts: dict[str, dict[str, int]] = {}
    for row in held:
        new_counts.setdefault(row["table"], {})
        bucket = new_counts[row["table"]]
        bucket[row["record_key"]] = bucket.get(row["record_key"], 0) + 1
    out: list[dict] = []
    for row in held:
        table = by_table[row["table"]]
        basis = row["basis"]
        phis: dict[int, float] = {}
        for col in table.columns:
            if col.role != "numeric" or col.member in (None, IDENTITY, BYTE):
                continue
            phi = column_phi(
                col.member or "",
                col.count_table,
                basis_entry_count=int(basis["entry_count"]),
                basis_length=int(basis["total_entry_length"]),
                basis_row_count={k: int(v) for k, v in basis.get("row_count", {}).items()},
                new_entry_count=new_entry_count,
                new_length=new_length,
                new_row_count={
                    name: per.get(row["record_key"], 0) for name, per in new_counts.items()
                },
            )
            if phi != phi:  # NaN
                raise RunError(
                    f"{table.name}: column {col.index} has a zero normalizer denominator"
                )
            if phi == 1.0:
                continue
            phis[col.index] = phi
        cells, cell_prov = rescale_cells(list(row["cells"]), table.columns, phis)
        saved = dict(row)
        saved["cells"] = cells
        saved["basis"] = {
            "entry_count": new_entry_count,
            "total_entry_length": new_length,
            "row_count": {name: per.get(row["record_key"], 0) for name, per in new_counts.items()},
        }
        # In-memory only. _row_for_cache drops this so the sqlite payload
        # keeps the keys a cache filled before this checker can still load.
        if cell_prov:
            saved["rescale"] = cell_prov
        out.append(saved)
    return out


_CACHE_ROW_KEYS = (
    "table",
    "record_key",
    "entry_hash",
    "entry_token",
    "row_index",
    "cells",
    "basis",
)


def _row_for_cache(row: dict) -> dict:
    """Payload written to sqlite. Rescale provenance is not part of the format."""
    return {key: row[key] for key in _CACHE_ROW_KEYS}


def _provenance_held(
    held: list[dict], table: TableReport
) -> dict[tuple[str, str, str], dict[int, tuple[str, float]]]:
    """Sidecar for one table. Per-key-count phi is the post-merge value recorded at rescale."""
    out: dict[tuple[str, str, str], dict[int, tuple[str, float]]] = {}
    for row in held:
        if row.get("table") != table.name:
            continue
        prov = row.get("rescale") or {}
        if not prov:
            continue
        key = (row["record_key"], row["entry_token"], row.get("row_index") or "")
        out[key] = {
            int(index): (str(source), float(phi)) for index, (source, phi) in prov.items()
        }
    return out


def _order_rows(
    held: list[dict],
    table: TableReport,
    entries: Sequence[Entry],
    records: Sequence[RecordItem],
) -> list[list[str]]:
    entry_pos = _entry_order(entries)
    record_pos = {rec.key: i for i, rec in enumerate(records)}
    rows = [row for row in held if row["table"] == table.name]
    rows.sort(
        key=lambda row: (
            entry_pos.get(row["entry_token"], 10**12),
            record_pos.get(row["record_key"], 10**12),
            row.get("row_index") or "",
        )
    )
    return [row["cells"] for row in rows]


def _index_held(held: list[dict], table: TableReport) -> dict[tuple[str, str, str], list[str]]:
    out: dict[tuple[str, str, str], list[str]] = {}
    for row in held:
        if row["table"] != table.name:
            continue
        key = (row["record_key"], row["entry_token"], row.get("row_index") or "")
        out[key] = row["cells"]
    return out


def pin_tokens(pin: str, values: dict[str, int]) -> list[str]:
    """Expand a caller-declared pin template, e.g. '-Z {entry_count}'. Data, not tool code."""
    out: list[str] = []
    for token in shlex.split(pin):
        for name, placeholder in PIN_PLACEHOLDERS.items():
            token = token.replace(placeholder, str(int(values[name])))
        if "{" in token and "}" in token:
            raise RunError(f"pin token {token!r} has an unknown placeholder")
        out.append(token)
    return out


def pin_values(entries: Sequence[Entry]) -> dict[str, int]:
    return {
        "entry_count": len(entries),
        "total_entry_length": sum(entry.length for entry in entries),
    }


_SLACK_FACTOR = re.compile(r"^\{[A-Za-z0-9]*\*([0-9]+(?:\.[0-9]+)?)\}$")


def _fmt_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return format(value, ".12g")


def _flag_value(argv: Sequence[str], flag: str) -> str | None:
    for index, token in enumerate(argv):
        if token.startswith("-") and "=" in token:
            name, raw = token.split("=", 1)
            if name == flag:
                return raw
        elif token == flag and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _replace_flags(argv: Sequence[str], values: dict[str, str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    index = 0
    while index < len(argv):
        token = argv[index]
        flag = None
        inline = False
        if token.startswith("-") and "=" in token:
            flag, _raw = token.split("=", 1)
            inline = True
        elif token in values:
            flag = token
        if flag is not None and flag in values:
            seen.add(flag)
            if inline:
                out.append(f"{flag}={values[flag]}")
                index += 1
                continue
            if index + 1 >= len(argv):
                raise RunError(f"argv flag {flag} needs a value")
            out.extend((flag, values[flag]))
            index += 2
            continue
        out.append(token)
        index += 1
    missing = [flag for flag in values if flag not in seen]
    if missing:
        raise RunError("slack flag not in argv: " + ", ".join(missing))
    return out


def slack_rewrite(argv: Sequence[str], slack: str) -> tuple[list[str], float]:
    """Relaxed reporting flags for cache fill and discovery, plus the one factor.

    `{name*2}` multiplies the argv value of that flag by 2. A literal value
    is allowed when argv already sets the flag; the factor is the ratio.
    Every flag in one template must share that factor, and it must be ≥ 1.
    """
    tokens = shlex.split(slack)
    if not tokens:
        raise RunError("slack is empty")
    pairs: list[tuple[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("-"):
            raise RunError(f"slack token {token!r} is not a flag")
        if "=" in token:
            flag, raw = token.split("=", 1)
            pairs.append((flag, raw))
            index += 1
            continue
        if index + 1 >= len(tokens) or tokens[index + 1].startswith("-"):
            raise RunError(f"slack flag {token} needs a value")
        pairs.append((token, tokens[index + 1]))
        index += 2
    factors: list[float] = []
    replacements: dict[str, str] = {}
    for flag, raw in pairs:
        current = _flag_value(argv, flag)
        match = _SLACK_FACTOR.match(raw)
        if match:
            factor = float(match.group(1))
            if current is None:
                raise RunError(f"slack scales {flag}, which argv does not set")
            try:
                number = float(current)
            except ValueError as exc:
                raise RunError(f"argv value for {flag} is not a number") from exc
            factors.append(factor)
            replacements[flag] = _fmt_number(number * factor)
            continue
        if current is None:
            raise RunError(
                f"slack sets {flag} to a literal and argv does not set it; "
                "use {name*factor} to declare the factor"
            )
        try:
            base = float(current)
            literal = float(raw)
        except ValueError as exc:
            raise RunError(f"slack value for {flag} is not a number") from exc
        if base == 0:
            raise RunError(f"argv value for {flag} is zero")
        factors.append(literal / base)
        replacements[flag] = raw
    if any(factor < 1 for factor in factors):
        raise RunError("slack factor is below 1")
    if any(abs(factor - factors[0]) > 1e-9 for factor in factors):
        raise RunError("slack flags do not share one factor")
    return _replace_flags(argv, replacements), factors[0]


def namespace_for(
    argv: list[str],
    reference: Path | None,
    baseline: str | None,
    pin: str | None,
    slack: str | None,
) -> str:
    ns = argv_namespace(argv, reference, baseline)
    if not pin and not slack:
        return ns
    extra = ns + "\0pin:" + (pin or "") + "\0slack:" + (slack or "")
    return hashlib.sha256(extra.encode()).hexdigest()[:16]


def uncovered_members(tables: Sequence[TableReport], pin: str) -> list[str]:
    """Fitted normalizer members the pin template does not set."""
    missing: list[str] = []
    for table in tables:
        for col in table.columns:
            if col.role != "numeric" or col.member in (None, IDENTITY, BYTE):
                continue
            placeholder = PIN_PLACEHOLDERS.get(col.member or "")
            if placeholder is None:
                continue  # per-key counts: derived by the tool from its reported set
            if placeholder not in pin:
                missing.append(f"{table.name} column {col.index} ({col.member})")
    return missing


def body_lines(text: str) -> list[str]:
    """MATCH unit for exact mode: every non-empty line not starting with '#'."""
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def _body_record_filter(text: str, record_col: int, keep: set[str]) -> list[str]:
    out: list[str] = []
    for line in body_lines(text):
        fields = line.split()
        if record_col < len(fields) and fields[record_col] in keep:
            out.append(line)
    return out


def replay_plan(
    held: Sequence[dict],
    entries: Sequence[Entry],
    records: Sequence[RecordItem],
) -> tuple[list[RecordItem], list[Entry], dict[str, set[str]]]:
    """Records with any candidate, and the union of candidate entries in release order."""
    aliases = alias_map(list(entries))
    cand: dict[str, set[str]] = {}
    for row in held:
        token = row["entry_token"]
        if token not in aliases:
            raise RunError(f"candidate entry {token!r} is not in this reference")
        cand.setdefault(row["record_key"], set()).add(token)
    chosen_idx = sorted({aliases[token] for tokens in cand.values() for token in tokens})
    replay_records = [rec for rec in records if rec.key in cand]
    return replay_records, [entries[i] for i in chosen_idx], cand


class ReferenceIncremental(Strategy):
    """F(records, reference). Fit once per argv; reuse unchanged entries afterwards."""

    name = "reference"

    def __init__(
        self,
        *,
        argv: list[str],
        input_path: Path,
        out_dir: Path,
        reference: Path | None = None,
        prep: str | None = None,
        baseline: str | None = None,
        cache_path: Path | None = None,
        verify: str = "audit",
        audit_p: float | None = None,
        audit_seed: int = AUDIT_SEED,
        primary_parts: list[list[int]] | None = None,
        sample: bool = True,
        runner: Invoke | None = None,
        pin: str | None = None,
        pin_runner: PinnedInvoke | None = None,
        slack: str | None = None,
        slack_runner: Invoke | None = None,
    ):
        self.argv = list(argv)
        self.input_path = input_path
        self.out_dir = out_dir
        self.reference = reference
        self.prep = prep
        self.baseline = baseline
        self.cache_path = cache_path
        self.verify = verify if verify in {"audit", "full"} else "audit"
        self.audit_p = AUDIT_P if audit_p is None and self.verify == "audit" else (audit_p or 0.0)
        self.audit_seed = audit_seed
        self.primary_parts = primary_parts
        self.sample = sample
        self.runner = runner
        self.pin = pin
        self.pin_runner = pin_runner
        self.slack = slack
        self.slack_runner = slack_runner
        self._slack_factor: float | None = None
        if slack:
            _argv, self._slack_factor = slack_rewrite(self.argv, slack)
        self.clock: dict[str, float] = {}
        self._n_entries: int | None = None
        self._t_all = 0.0

    def run(self) -> StrategyResult:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._t_all = time.perf_counter()
        try:
            started = time.perf_counter()
            reference = detect_reference(self.argv, self.input_path, self.reference)
            entries = parse_reference(reference)
            records = read_records(self.input_path)
            self._n_entries = len(entries)
            _clock_add(self.clock, "parse_s", time.perf_counter() - started)
        except (RunError, FormatError, OSError, UnicodeError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            return self._finish("REFUSE", reason, self._phase_extra({}))

        cache = connect_cache(self.cache_path or (self.out_dir / "reference.sqlite"))
        ns = namespace_for(self.argv, reference, self.baseline, self.pin, self.slack)
        try:
            return self._run_cached(cache, ns, reference, entries, records)
        finally:
            cache.close()

    def _invoke(self, reference: Path) -> Invoke:
        if self.runner is not None:
            return self.runner
        return subprocess_invoke(
            self.argv,
            input_slot=self.input_path,
            reference_slot=reference,
            prep=self.prep,
            scratch=self.out_dir / "calls",
            clock=self.clock,
            full_entries=self._n_entries,
        )

    def _pinned(self, reference: Path) -> PinnedInvoke:
        if self.pin_runner is not None:
            return self.pin_runner
        assert self.pin is not None
        counter = {"n": 0}

        def call(records: Sequence[RecordItem], entries: Sequence[Entry], values: dict[str, int]) -> dict[str, str]:
            counter["n"] += 1
            argv = self.argv[:1] + pin_tokens(self.pin or "", values) + self.argv[1:]
            inner = subprocess_invoke(
                argv,
                input_slot=self.input_path,
                reference_slot=reference,
                prep=self.prep,
                scratch=self.out_dir / "calls_pinned" / f"r{counter['n']}",
                clock=self.clock,
                full_entries=self._n_entries,
            )
            return inner(records, entries)

        return call

    def _slack_call(self, reference: Path) -> Invoke:
        """Cache fill and discovery. Unpinned, with the caller's relaxed flags."""
        if self.slack_runner is not None:
            return self.slack_runner
        assert self.slack is not None
        argv, _factor = slack_rewrite(self.argv, self.slack)
        return subprocess_invoke(
            argv,
            input_slot=self.input_path,
            reference_slot=reference,
            prep=self.prep,
            scratch=self.out_dir / "calls_slack",
            clock=self.clock,
            full_entries=self._n_entries,
        )

    def _phase_extra(self, extra: dict, *, probe_wall: float = 0.0, probe_phases: dict | None = None) -> dict:
        payload = dict(extra)
        payload["phases"] = {
            **self.clock,
            "total_s": time.perf_counter() - self._t_all,
            "probe_wall_s": probe_wall,
        }
        payload["probe_phases"] = dict(probe_phases or {})
        return payload

    def _run_cached(
        self,
        cache: ReferenceCache,
        ns: str,
        reference: Path,
        entries: list[Entry],
        records: list[RecordItem],
    ) -> StrategyResult:
        invoke = self._invoke(reference)
        stored = cache.load_contract(ns)
        probe_wall = 0.0
        probe_phases: dict[str, float] = {}
        if stored is None:
            started = time.perf_counter()
            fitted = probe_fit(
                entries,
                records,
                invoke,
                primary_parts=self.primary_parts,
                baseline=self.baseline,
                sample=self.sample,
                k=PROBE_K,
                n_p=PROBE_N,
                seed=PROBE_SEED,
                monotone=bool(self.pin and self.slack),
            )
            probe_wall = time.perf_counter() - started
            probe_phases = dict(self.clock)
            self.clock.clear()
            # parse_s happened before the probe and belongs to this invocation,
            # not to the probe. Keep it on the post-probe clock.
            if "parse_s" in probe_phases:
                self.clock["parse_s"] = probe_phases.pop("parse_s")
            if not fitted.reason.startswith(("tool failed", "prep failed")):
                payload = fitted.as_dict()
                if self.pin and self._slack_factor is not None:
                    payload["slack_factor"] = self._slack_factor
                cache.save_contract(ns, payload)
            stored = fitted.as_dict()
            if self.pin and self._slack_factor is not None:
                stored["slack_factor"] = self._slack_factor
        decision = stored.get("decision")
        tables = tables_from_dict(stored.get("tables") or [])
        if decision != "SHIP":
            try:
                self._dump_raw(invoke(records, entries))
            except RunError as exc:
                return self._finish(
                    "REFUSE",
                    f"{stored.get('reason') or 'fit refused'}; full run failed: {exc.reason}",
                    self._phase_extra(
                        {
                            "verify": self.verify,
                            "reused_rows": 0,
                            "n_entries": len(entries),
                            "fallback_full_scan": False,
                        },
                        probe_wall=probe_wall,
                        probe_phases=probe_phases,
                    ),
                )
            return self._finish(
                "REFUSE",
                str(stored.get("reason") or "fit refused"),
                self._phase_extra(
                    {
                        "verify": self.verify,
                        "reused_rows": 0,
                        "n_entries": len(entries),
                        "fallback_full_scan": True,
                    },
                    probe_wall=probe_wall,
                    probe_phases=probe_phases,
                ),
            )
        if not tables and stored.get("tables") is None:
            return self._finish(
                "REFUSE",
                "stored contract has no tables",
                self._phase_extra({}, probe_wall=probe_wall, probe_phases=probe_phases),
            )
        try:
            fill = self._slack_call(reference) if (self.pin and self.slack) else invoke
            held, reused, stats = self._incremental(cache, ns, fill, entries, records, tables)
        except RunError as exc:
            return self._finish(
                "REFUSE",
                exc.reason,
                self._phase_extra({}, probe_wall=probe_wall, probe_phases=probe_phases),
            )
        if self.pin:
            return self._run_exact(
                cache, ns, stored, reference, invoke, entries, records, tables, held, reused, stats,
                probe_wall=probe_wall, probe_phases=probe_phases,
            )
        started = time.perf_counter()
        self._write_tables(tables, held, entries, records)
        _clock_add(self.clock, "render_s", time.perf_counter() - started)
        extra = {"verify": self.verify, "reused_rows": reused, "rows": len(held), **stats}
        if self.verify == "full":
            ok, why = self._verify_full(invoke, records, entries, tables, held)
            if not ok:
                return self._finish(
                    "REFUSE_MATCH",
                    why,
                    self._phase_extra(extra, probe_wall=probe_wall, probe_phases=probe_phases),
                )
        elif self.verify == "audit" and reused:
            ok, why, report = self._verify_audit(invoke, records, entries, tables, held)
            extra["audit_checked"] = report
            if not ok:
                return self._finish(
                    "REFUSE_AUDIT",
                    why,
                    self._phase_extra(extra, probe_wall=probe_wall, probe_phases=probe_phases),
                )
        return self._finish(
            "SHIP",
            str(stored.get("reason") or "reference incrementality fitted"),
            self._phase_extra(extra, probe_wall=probe_wall, probe_phases=probe_phases),
        )

    # ----- exact mode: pinned-normalizer replay (docs/EXACT_REPLAY_PROTOCOL.md) -----

    def _run_exact(
        self, cache, ns, stored, reference, invoke, entries, records, tables, held, reused, stats,
        *, probe_wall: float, probe_phases: dict,
    ) -> StrategyResult:
        base = {"verify": self.verify, "mode": "exact", "match": "body-bytes", "reused_rows": reused, **stats}

        def done(decision: str, why: str, extra: dict) -> StrategyResult:
            return self._finish(decision, why, self._phase_extra(extra, probe_wall=probe_wall, probe_phases=probe_phases))

        missing = uncovered_members(tables, self.pin or "")
        if missing:
            return done("REFUSE_PIN", "pin does not set fitted normalizer: " + "; ".join(missing), base)
        pinned = self._pinned(reference)
        checks = dict(stored.get("pin_checks") or {})
        if self.pin not in checks:
            started = time.perf_counter()
            ok, why = self._pin_check(invoke, pinned, entries, records, tables)
            _clock_add(self.clock, "pin_check_s", time.perf_counter() - started)
            checks[self.pin] = {"ok": ok, "reason": why}
            stored = dict(stored)
            stored["pin_checks"] = checks
            cache.save_contract(ns, stored)
        if not checks[self.pin]["ok"]:
            return done("REFUSE_PIN", f"pin check failed: {checks[self.pin]['reason']}", base)
        if self.slack and stats.get("basis_entry_count_max") is not None:
            factor = stored.get("slack_factor")
            if factor is None:
                factor = self._slack_factor
            factor = float(factor if factor is not None else 0)
            z_old = int(stats["basis_entry_count_max"])
            z_new = len(entries)
            base["slack_factor"] = factor
            if z_new and z_old > factor * z_new + 1e-9:
                try:
                    self._dump_raw(invoke(records, entries))
                except RunError as exc:
                    return done("REFUSE", f"slack exceeded and full run failed: {exc.reason}", base)
                return done(
                    "REFUSE",
                    f"entry-count ratio {z_old}/{z_new} exceeds slack factor {factor:g}",
                    {**base, "fallback_full_scan": True},
                )
        try:
            started = time.perf_counter()
            rep_records, rep_entries, cand = replay_plan(held, entries, records)
            _clock_add(self.clock, "replay_plan_s", time.perf_counter() - started)
            texts = pinned(rep_records, rep_entries, pin_values(entries)) if rep_records else {}
        except RunError as exc:
            return done("REFUSE", exc.reason, base)
        extra = {**base, "replay_records": len(rep_records), "replay_entries": len(rep_entries),
                 "candidate_pairs": sum(len(v) for v in cand.values())}
        # Soundness tripwire: a replay row outside the candidate set means a
        # full run could also report pairs the cache never saw.
        for table in tables:
            for line in body_lines(texts.get(table.name, "")):
                fields = line.split()
                rec_key, ent = fields[table.record_col], fields[table.entry_col]
                if ent not in cand.get(rec_key, set()):
                    return done("REFUSE_MATCH", f"{table.name}: replay reported a non-candidate pair ({rec_key}, {ent})", extra)
        started = time.perf_counter()
        dest = self.out_dir / "tables"
        dest.mkdir(parents=True, exist_ok=True)
        for table in tables:
            text = texts.get(table.name)
            if text is None:
                text = "\n".join(table.meta) + ("\n" if table.meta else "")
            (dest / table.name).write_text(text)
        _clock_add(self.clock, "render_s", time.perf_counter() - started)
        if self.verify == "full":
            stock = invoke(records, entries)
            for table in tables:
                if body_lines(stock.get(table.name, "")) != body_lines(texts.get(table.name, "")):
                    return done("REFUSE_MATCH", f"{table.name}: body differs from a full run", extra)
        elif self.verify == "audit" and reused:
            keys = [rec.key for rec in rep_records]
            chosen = set(pick_audit(keys, p=self.audit_p, floor=AUDIT_FLOOR, rng=random.Random(self.audit_seed)))
            extra["audit_checked"] = len(chosen)
            if chosen:
                stock = invoke([rec for rec in records if rec.key in chosen], entries)
                for table in tables:
                    a = _body_record_filter(stock.get(table.name, ""), table.record_col, chosen)
                    b = _body_record_filter(texts.get(table.name, ""), table.record_col, chosen)
                    if a != b:
                        return done("REFUSE_AUDIT", f"{table.name}: audited records differ from a full run", extra)
        return done("SHIP", "exact replay under pinned normalizer", extra)

    def _pin_check(self, invoke, pinned, entries, records, tables) -> tuple[bool, str]:
        """In-situ E1 on the probe sample: oracle candidates, pinned replay, body bytes."""
        chosen = sample_record_indices(len(records), min(PROBE_N, len(records)), PROBE_SEED)
        sample = [records[i] for i in chosen]
        try:
            whole = invoke(sample, entries)
            held = _rows_from_run(whole, tables, entries)
            if not held:
                return False, "no rows on the probe sample; pin cannot be checked"
            rep_records, rep_entries, _ = replay_plan(held, entries, sample)
            texts = pinned(rep_records, rep_entries, pin_values(entries))
        except RunError as exc:
            return False, exc.reason
        for table in tables:
            if body_lines(whole.get(table.name, "")) != body_lines(texts.get(table.name, "")):
                return False, f"{table.name}: pinned replay body differs from the whole run"
        return True, ""

    def _full(self, invoke, records, entries, tables) -> list[dict]:
        if not tables:
            try:
                texts = invoke(records, entries)
            except RunError:
                return []
            self._dump_raw(texts)
            return []
        texts = invoke(records, entries)
        return _rows_from_run(texts, tables, entries)

    def _incremental(self, cache, ns, invoke, entries, records, tables) -> tuple[list[dict], int, dict]:
        record_keys = {rec.key for rec in records}
        present = {entry.content_hash for entry in entries}
        started = time.perf_counter()
        coverage = cache.coverage_map(ns)
        removed = set(coverage) - present
        cache.drop_hashes(ns, removed)
        _clock_add(self.clock, "coverage_read_s", time.perf_counter() - started)
        stable: list[Entry] = []
        fresh: list[Entry] = []
        partial: list[Entry] = []
        missing_keys: set[str] = set()
        started = time.perf_counter()
        for entry in entries:
            covered = coverage.get(entry.content_hash, set())
            if not covered:
                fresh.append(entry)
            elif record_keys <= covered:
                stable.append(entry)
            else:
                partial.append(entry)
                missing_keys |= record_keys - covered
        _clock_add(self.clock, "diff_s", time.perf_counter() - started)
        stats = {
            "n_entries": len(entries),
            "n_stable": len(stable),
            "n_fresh": len(fresh),
            "n_partial": len(partial),
            "length_entries": sum(entry.length for entry in entries),
            "length_fresh": sum(entry.length for entry in fresh),
            "length_partial": sum(entry.length for entry in partial),
        }
        held: list[dict] = []
        started = time.perf_counter()
        kept_partial = record_keys - missing_keys
        stable_hashes = {entry.content_hash for entry in stable}
        partial_hashes = {entry.content_hash for entry in partial}
        for table in tables:
            held.extend(cache.load_table_rows(ns, table.name, stable_hashes, record_keys))
            if partial_hashes and kept_partial:
                held.extend(cache.load_table_rows(ns, table.name, partial_hashes, kept_partial))
        _clock_add(self.clock, "cache_load_s", time.perf_counter() - started)
        reused = len(held)
        ran_rows: list[dict] = []
        if fresh:
            ran_rows.extend(_rows_from_run(invoke(records, fresh), tables, fresh))
        if partial and missing_keys:
            subset = [rec for rec in records if rec.key in missing_keys]
            ran_rows.extend(_rows_from_run(invoke(subset, partial), tables, partial))
        held.extend(ran_rows)
        if reused:
            bases = [
                int(row["basis"]["entry_count"])
                for row in held[:reused]
                if row.get("basis") and "entry_count" in row["basis"]
            ]
            if bases:
                stats["basis_entry_count_max"] = max(bases)
        new_length = sum(entry.length for entry in entries)
        started = time.perf_counter()
        scaled = _rescale_held(held, tables, len(entries), new_length)
        _clock_add(self.clock, "merge_rescale_s", time.perf_counter() - started)
        started = time.perf_counter()
        # Persist the cells the tool printed and the basis they were produced
        # under. The reprint is for this render only. Storing it would make the
        # next render see phi 1, drop the source, and byte-compare a reprint.
        self._store(cache, ns, tables, records, entries, stable, fresh, partial, missing_keys, held)
        _clock_add(self.clock, "cache_store_s", time.perf_counter() - started)
        return scaled, reused, stats

    def _store(self, cache, ns, tables, records, entries, stable, fresh, partial, missing_keys, source_rows) -> None:
        # Newly answerable: fresh entries x all records, partial entries x all
        # records (the missing ones were just run). Stable entries are already
        # covered and their rows did not change, so they are not rewritten.
        # The stored basis stays the one the cells were produced under.
        hashes = [entry.content_hash for entry in fresh] + [entry.content_hash for entry in partial]
        if not hashes:
            return
        wanted = set(hashes)
        by_table: dict[str, list[dict]] = {table.name: [] for table in tables}
        for row in source_rows:
            if row["entry_hash"] in wanted and row["table"] in by_table:
                by_table[row["table"]].append(_row_for_cache(row))
        cache.cover_and_replace(
            ns, [table.name for table in tables], hashes, [rec.key for rec in records], by_table
        )

    def _verify_full(self, invoke, records, entries, tables, held) -> tuple[bool, str]:
        stock = invoke(records, entries)
        for table in tables:
            parsed = parse_table_text(table.name, stock.get(table.name, ""))
            try:
                stock_rows = index_rows(
                    parsed.rows, table.record_col, table.entry_col, table.index_col
                )
            except ValueError as exc:
                return False, str(exc)
            ok, why = ref_merge_rows(
                stock_rows, _index_held(held, table), table.columns, _provenance_held(held, table)
            )
            if not ok:
                return False, f"{table.name}: {why}"
        return True, ""

    def _verify_audit(self, invoke, records, entries, tables, held) -> tuple[bool, str, int]:
        reused_keys = []
        seen: set[str] = set()
        # Audit records that still have a cached contribution. The caller passes
        # reused count separately; here every record with a row is eligible when
        # the run reused something. The strategy only calls this when reused > 0.
        for row in held:
            if row["record_key"] not in seen:
                seen.add(row["record_key"])
                reused_keys.append(row["record_key"])
        chosen = pick_audit(
            reused_keys,
            p=self.audit_p,
            floor=AUDIT_FLOOR,
            rng=random.Random(self.audit_seed),
        )
        if not chosen:
            return True, "", 0
        subset = [rec for rec in records if rec.key in set(chosen)]
        stock = invoke(subset, entries)
        wanted = set(chosen)
        for table in tables:
            parsed = parse_table_text(table.name, stock.get(table.name, ""))
            try:
                stock_rows = index_rows(
                    parsed.rows, table.record_col, table.entry_col, table.index_col
                )
            except ValueError as exc:
                return False, str(exc), len(chosen)
            ours = {
                key: cells
                for key, cells in _index_held(held, table).items()
                if key[0] in wanted
            }
            stock_kept = {key: cells for key, cells in stock_rows.items() if key[0] in wanted}
            prov = {
                key: cols
                for key, cols in _provenance_held(held, table).items()
                if key[0] in wanted
            }
            ok, why = ref_merge_rows(stock_kept, ours, table.columns, prov)
            if not ok:
                return False, f"{table.name}: {why}", len(chosen)
        return True, "", len(chosen)

    def _write_tables(self, tables, held, entries, records) -> None:
        dest = self.out_dir / "tables"
        dest.mkdir(parents=True, exist_ok=True)
        for table in tables:
            text = render_table_text(table, _order_rows(held, table, entries, records))
            (dest / table.name).write_text(text)
            sidecar = dump_rescale_provenance(_provenance_held(held, table))
            (dest / f"{table.name}.provenance.json").write_text(
                json.dumps(sidecar, indent=2) + "\n"
            )

    def _dump_raw(self, texts: dict[str, str]) -> None:
        dest = self.out_dir / "tables"
        dest.mkdir(parents=True, exist_ok=True)
        for name, text in texts.items():
            (dest / name).write_text(text)

    def _finish(self, decision: str, reason: str, extra: dict) -> StrategyResult:
        rec = StrategyResult(self.name, decision, reason, extra)
        rec.write(self.out_dir / "decision.txt")
        return rec
