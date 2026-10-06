"""Closed normalizer family and the decomposition decision.

Members, the probe, and the half-ULP predicate are the pre-registered
ones. This module does not run tools and does not name a tool.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field

MEMBERS = ("identity", "entry_count", "total_entry_length", "per_key_row_count")

PROBE_K = 2
PROBE_N = 300
PROBE_SEED = 20261006

IDENTITY = "identity"
ENTRY_COUNT = "entry_count"
TOTAL_LENGTH = "total_entry_length"
PER_KEY = "per_key_row_count"
BYTE = "byte"


def shuffled_indices(n: int, seed: int) -> list[int]:
    """Fisher–Yates using random.Random.random, not Random.shuffle."""
    rng = random.Random(seed)
    idx = list(range(n))
    for i in range(n - 1, 0, -1):
        j = int(rng.random() * (i + 1))
        idx[i], idx[j] = idx[j], idx[i]
    return idx


def partition_indices(n: int, k: int, seed: int) -> list[list[int]]:
    """k contiguous parts of a Fisher–Yates shuffle. Sizes differ by at most one."""
    if k < 1 or n < k:
        raise ValueError(f"cannot partition n={n} into k={k}")
    idx = shuffled_indices(n, seed)
    base, rem = divmod(n, k)
    parts: list[list[int]] = []
    start = 0
    for part in range(k):
        size = base + (1 if part < rem else 0)
        parts.append(idx[start : start + size])
        start += size
    return parts


def disambiguating_indices(
    lengths: list[int], hashes: list[str]
) -> tuple[list[int], list[int]] | None:
    """Longest-first part L until 2*sum(L) >= total, and its complement.

    Equal lengths break by content-hash ascending. Integer comparison only.
    Returns None when two non-empty parts cannot be formed.
    """
    n = len(lengths)
    if n < 2 or len(hashes) != n:
        return None
    order = sorted(range(n), key=lambda i: (-lengths[i], hashes[i]))
    total = sum(lengths)
    chosen: list[int] = []
    acc = 0
    for index in order:
        if len(chosen) >= n - 1:
            break
        chosen.append(index)
        acc += lengths[index]
        if acc * 2 >= total:
            break
    if not chosen or len(chosen) >= n or acc * 2 < total:
        return None
    chosen_set = set(chosen)
    rest = [i for i in range(n) if i not in chosen_set]
    if not rest:
        return None
    return chosen, rest


def half_ulp(printed: str) -> float:
    """Half a unit in the last printed digit of a mantissa."""
    lower = printed.lower()
    mant, sep, exp = lower.partition("e")
    dec = len(mant.split(".")[1]) if "." in mant else 0
    exponent = int(exp) if sep else 0
    return 0.5 * 10 ** (-dec) * (10 ** exponent)


def parse_finite(token: str) -> float | None:
    try:
        value = float(token)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def consistent(part_printed: str, whole_printed: str, phi: float) -> bool:
    """True when part * phi matches whole within the pre-registered tolerance."""
    if not math.isfinite(phi):
        return False
    part = parse_finite(part_printed)
    whole = parse_finite(whole_printed)
    if part is None or whole is None:
        return False
    residual = abs(part * phi - whole)
    tolerance = half_ulp(whole_printed) + half_ulp(part_printed) * abs(phi)
    return residual <= tolerance


def reprint_like(printed: str, value: float) -> str:
    """Re-print `value` with the same significant digits as `printed`."""
    lower = printed.lower()
    mant = lower.split("e")[0]
    if "e" in lower:
        digits = len(mant.replace(".", "").replace("-", "").lstrip("0")) or 1
        return f"{value:.{max(digits - 1, 0)}e}"
    decimals = len(mant.split(".")[1]) if "." in mant else 0
    return f"{value:.{decimals}f}"


def sample_record_indices(n: int, k: int, seed: int) -> list[int]:
    """Second Random(seed), independent of the partition stream. File order kept."""
    if k >= n:
        return list(range(n))
    rng = random.Random(seed)
    picked = set(rng.sample(range(n), k))
    return [i for i in range(n) if i in picked]


@dataclass
class ColumnReport:
    index: int
    role: str
    member: str | None = None
    count_table: str | None = None
    primary_fits: list[str] = field(default_factory=list)
    tie: list[str] = field(default_factory=list)
    tie_break: dict | None = None

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "role": self.role,
            "member": self.member,
            "count_table": self.count_table,
            "primary_fits": list(self.primary_fits),
            "tie": list(self.tie),
            "tie_break": self.tie_break,
        }


@dataclass
class TableReport:
    name: str
    record_col: int
    entry_col: int
    index_col: int | None
    meta: list[str]
    columns: list[ColumnReport]
    layout: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "record_col": self.record_col,
            "entry_col": self.entry_col,
            "index_col": self.index_col,
            "meta": list(self.meta),
            "columns": [col.as_dict() for col in self.columns],
            "layout": self.layout,
        }


@dataclass
class FitResult:
    decision: str
    reason: str
    tables: list[TableReport] = field(default_factory=list)
    used_tie_break: bool = False
    primary_key_equal: bool | None = None
    probe_invocations: int = 0

    @property
    def shipped(self) -> bool:
        return self.decision == "SHIP"

    def as_dict(self) -> dict:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "used_tie_break": self.used_tie_break,
            "primary_key_equal": self.primary_key_equal,
            "probe_invocations": self.probe_invocations,
            "tables": [table.as_dict() for table in self.tables],
        }


def refuse(reason: str, *, invocations: int = 0) -> FitResult:
    return FitResult(decision="REFUSE", reason=reason, probe_invocations=invocations)


@dataclass
class ParsedTable:
    name: str
    meta: list[str]
    rows: list[list[str]]
    raw_lines: list[str]


def parse_table_text(name: str, text: str) -> ParsedTable:
    meta: list[str] = []
    rows: list[list[str]] = []
    raw_lines: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            meta.append(line)
            continue
        rows.append(line.split())
        raw_lines.append(line)
    return ParsedTable(name=name, meta=meta, rows=rows, raw_lines=raw_lines)


def infer_key_columns(
    rows: list[list[str]],
    record_ids: set[str],
    entry_ids: set[str],
) -> tuple[int, int, int | None]:
    """Pick record, entry, and optional row-index columns from token overlap."""
    if not rows:
        raise ValueError("no data rows")
    width = min(len(row) for row in rows)
    if width < 2:
        raise ValueError("table has fewer than two columns")
    record_score = []
    entry_score = []
    for col in range(width):
        record_score.append(sum(1 for row in rows if row[col] in record_ids))
        entry_score.append(sum(1 for row in rows if row[col] in entry_ids))
    record_col = max(range(width), key=lambda c: (record_score[c], -c))
    entry_col = max(
        (c for c in range(width) if c != record_col),
        key=lambda c: (entry_score[c], -c),
    )
    if record_score[record_col] == 0 or entry_score[entry_col] == 0:
        raise ValueError("output columns do not match record and entry identifiers")
    groups: dict[tuple[str, str], int] = Counter()
    for row in rows:
        groups[(row[record_col], row[entry_col])] += 1
    if all(count == 1 for count in groups.values()):
        return record_col, entry_col, None
    for col in range(width):
        if col in (record_col, entry_col):
            continue
        if not all(row[col].lstrip("-").isdigit() for row in rows):
            continue
        triples = [(row[record_col], row[entry_col], row[col]) for row in rows]
        if len(triples) == len(set(triples)):
            return record_col, entry_col, col
    for col in range(width):
        if col in (record_col, entry_col):
            continue
        triples = [(row[record_col], row[entry_col], row[col]) for row in rows]
        if len(triples) == len(set(triples)):
            return record_col, entry_col, col
    raise ValueError("duplicate rows have no row-index column")


def row_key(cells: list[str], record_col: int, entry_col: int, index_col: int | None) -> tuple[str, str, str]:
    index = cells[index_col] if index_col is not None else ""
    return (cells[record_col], cells[entry_col], index)


def index_rows(
    rows: list[list[str]],
    record_col: int,
    entry_col: int,
    index_col: int | None,
) -> dict[tuple[str, str, str], list[str]]:
    out: dict[tuple[str, str, str], list[str]] = {}
    for cells in rows:
        key = row_key(cells, record_col, entry_col, index_col)
        if key in out:
            raise ValueError(f"duplicate row key {key}")
        out[key] = cells
    return out


def per_record_counts(indexed: dict[tuple[str, str, str], list[str]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record_key, _entry, _index in indexed:
        counts[record_key] += 1
    return dict(counts)


@dataclass
class Aligned:
    record_key: str
    entry_index: int
    part: int
    whole: list[str]
    part_cells: list[str]


@dataclass
class TableBundle:
    name: str
    meta: list[str]
    raw_lines: list[str]
    record_col: int
    entry_col: int
    index_col: int | None
    whole: dict[tuple[str, str, str], list[str]]
    parts: list[dict[tuple[str, str, str], list[str]]]
    aligned: list[Aligned]
    key_equal: bool
    key_reason: str


def _bundle_table(
    name: str,
    whole_text: str,
    part_texts: list[str],
    record_ids: set[str],
    entry_ids: set[str],
    alias_to_index: dict[str, int],
    part_of_entry: dict[int, int],
) -> TableBundle:
    whole = parse_table_text(name, whole_text)
    parts = [parse_table_text(name, text) for text in part_texts]
    if not whole.rows and all(not part.rows for part in parts):
        return TableBundle(
            name=name,
            meta=whole.meta,
            raw_lines=whole.raw_lines,
            record_col=0,
            entry_col=1,
            index_col=None,
            whole={},
            parts=[{} for _ in parts],
            aligned=[],
            key_equal=True,
            key_reason="",
        )
    source = whole.rows or next(part.rows for part in parts if part.rows)
    record_col, entry_col, index_col = infer_key_columns(source, record_ids, entry_ids)
    whole_idx = index_rows(whole.rows, record_col, entry_col, index_col)
    part_idx = [index_rows(part.rows, record_col, entry_col, index_col) for part in parts]
    union: set[tuple[str, str, str]] = set()
    overlap: set[tuple[str, str, str]] = set()
    for indexed in part_idx:
        overlap |= union & set(indexed)
        union |= set(indexed)
    key_equal = union == set(whole_idx) and not overlap
    key_reason = ""
    if overlap:
        key_reason = f"{name}: row key appears in two parts"
    elif union != set(whole_idx):
        key_reason = (
            f"{name}: row-key sets differ "
            f"(whole {len(whole_idx)}, union {len(union)}, "
            f"only-union {len(union - set(whole_idx))}, "
            f"only-whole {len(set(whole_idx) - union)})"
        )
    aligned: list[Aligned] = []
    for key, cells in whole_idx.items():
        producers = [i for i, indexed in enumerate(part_idx) if key in indexed]
        if len(producers) != 1:
            continue
        entry_token = cells[entry_col]
        if entry_token not in alias_to_index:
            raise ValueError(f"{name}: entry token {entry_token!r} is not in the reference")
        entry_index = alias_to_index[entry_token]
        entry_part = part_of_entry.get(entry_index)
        if entry_part is None or entry_part != producers[0]:
            raise ValueError(f"{name}: row emitted by a part that does not contain its entry")
        aligned.append(
            Aligned(
                record_key=cells[record_col],
                entry_index=entry_index,
                part=producers[0],
                whole=cells,
                part_cells=part_idx[producers[0]][key],
            )
        )
    return TableBundle(
        name=name,
        meta=whole.meta,
        raw_lines=whole.raw_lines,
        record_col=record_col,
        entry_col=entry_col,
        index_col=index_col,
        whole=whole_idx,
        parts=part_idx,
        aligned=aligned,
        key_equal=key_equal,
        key_reason=key_reason,
    )


def _phi_factory(
    kind: str,
    count_table: str | None,
    entry_counts: list[int],
    lengths: list[int],
    whole_entry_count: int,
    whole_length: int,
    part_counts: list[dict[str, dict[str, int]]],
    whole_counts: dict[str, dict[str, int]],
):
    def phi(row: Aligned) -> float:
        if kind == IDENTITY:
            return 1.0
        if kind == ENTRY_COUNT:
            part_n = entry_counts[row.part]
            if part_n == 0:
                return float("nan")
            return whole_entry_count / part_n
        if kind == TOTAL_LENGTH:
            part_l = lengths[row.part]
            if part_l == 0:
                return float("nan")
            return whole_length / part_l
        assert count_table is not None
        part_c = part_counts[row.part].get(count_table, {}).get(row.record_key, 0)
        whole_c = whole_counts.get(count_table, {}).get(row.record_key, 0)
        if part_c == 0:
            return float("nan")
        return whole_c / part_c

    return phi


def _residual_summary(rows: list[Aligned], col: int, phi_of) -> dict:
    residuals: list[float] = []
    n_ok = 0
    worst: dict | None = None
    for row in rows:
        whole = row.whole[col]
        part = row.part_cells[col]
        phi = phi_of(row)
        if not math.isfinite(phi) or parse_finite(whole) is None or parse_finite(part) is None:
            residual = float("inf")
            ok = False
        else:
            residual = abs(float(part) * phi - float(whole))
            tolerance = half_ulp(whole) + half_ulp(part) * abs(phi)
            ok = residual <= tolerance
        if ok:
            n_ok += 1
        residuals.append(residual)
        if worst is None or residual > worst["abs_residual"]:
            worst = {
                "record_key": row.record_key,
                "part": row.part,
                "part_printed": part,
                "whole_printed": whole,
                "phi": phi if math.isfinite(phi) else None,
                "abs_residual": residual if math.isfinite(residual) else None,
            }
    finite = [r for r in residuals if math.isfinite(r)]
    return {
        "n": len(rows),
        "n_consistent": n_ok,
        "fits": n_ok == len(rows) and len(rows) > 0,
        "max_abs_residual": max(finite) if finite else None,
        "mean_abs_residual": (sum(finite) / len(finite)) if finite else None,
        "worst": worst,
    }


def _predictions_match(rows: list[Aligned], col: int, phi_a, phi_b) -> bool:
    """True when the two factors agree on every aligned row within half-ULP."""
    if not rows:
        return False
    for row in rows:
        a = phi_a(row)
        b = phi_b(row)
        if not math.isfinite(a) or not math.isfinite(b):
            return False
        part = row.part_cells[col]
        whole = row.whole[col]
        pred_a = float(part) * a
        pred_b = float(part) * b
        tolerance = half_ulp(whole) + half_ulp(part) * max(abs(a), abs(b))
        if abs(pred_a - pred_b) > tolerance:
            return False
    return True


def _candidate_fits(rows: list[Aligned], col: int, phi_of, *, identity: bool) -> bool:
    if not rows:
        return False
    for row in rows:
        whole = row.whole[col]
        part = row.part_cells[col]
        if identity:
            if whole != part:
                return False
            continue
        if not consistent(part, whole, phi_of(row)):
            return False
    return True


@dataclass
class _Cand:
    label: str
    kind: str
    count_table: str | None
    phi_of: object


def _family(table_names: list[str]) -> list[tuple[str, str, str | None]]:
    out = [
        (IDENTITY, IDENTITY, None),
        (ENTRY_COUNT, ENTRY_COUNT, None),
        (TOTAL_LENGTH, TOTAL_LENGTH, None),
    ]
    for name in table_names:
        out.append((f"{PER_KEY}:{name}", PER_KEY, name))
    return out


def _fit_column(
    rows: list[Aligned],
    col: int,
    table_names: list[str],
    phi_for,
) -> tuple[str, list[_Cand], list[_Cand]]:
    """Return (status, fitting, non_identity). status is byte|mixed|numeric."""
    tokens = [row.whole[col] for row in rows] + [row.part_cells[col] for row in rows]
    parsed = [parse_finite(token) is not None for token in tokens]
    if not parsed:
        return "byte", [], []
    if any(parsed) and not all(parsed):
        return "mixed", [], []
    if not all(parsed):
        return "byte", [], []
    fitting: list[_Cand] = []
    for label, kind, count_table in _family(table_names):
        phi_of = phi_for(kind, count_table)
        if _candidate_fits(rows, col, phi_of, identity=(kind == IDENTITY)):
            fitting.append(_Cand(label, kind, count_table, phi_of))
    identity_phi = phi_for(IDENTITY, None)
    non_identity = [
        cand
        for cand in fitting
        if cand.kind != IDENTITY and not _predictions_match(rows, col, cand.phi_of, identity_phi)
    ]
    return "numeric", fitting, non_identity


def measures_of(
    n_entries: int,
    total_length: int,
    bundles: list[TableBundle],
) -> dict:
    return {
        "entry_count": n_entries,
        "total_entry_length": total_length,
        "row_count": {bundle.name: per_record_counts(bundle.whole) for bundle in bundles},
    }


def column_phi(
    member: str,
    count_table: str | None,
    *,
    basis_entry_count: int,
    basis_length: int,
    basis_row_count: dict[str, int],
    new_entry_count: int,
    new_length: int,
    new_row_count: dict[str, int],
) -> float:
    if member in (IDENTITY, BYTE):
        return 1.0
    if member == ENTRY_COUNT:
        if basis_entry_count == 0:
            return float("nan")
        return new_entry_count / basis_entry_count
    if member == TOTAL_LENGTH:
        if basis_length == 0:
            return float("nan")
        return new_length / basis_length
    if member == PER_KEY:
        if not count_table:
            return float("nan")
        basis = basis_row_count.get(count_table, 0)
        if basis == 0:
            return float("nan")
        return new_row_count.get(count_table, 0) / basis
    return float("nan")


def rescale_cells(
    cells: list[str],
    columns: list[ColumnReport],
    phi_of_index: dict[int, float],
) -> list[str]:
    by_index = {col.index: col for col in columns}
    out = list(cells)
    for index, phi in phi_of_index.items():
        col = by_index.get(index)
        if col is None or col.role != "numeric" or col.member in (None, IDENTITY):
            continue
        if index >= len(out) or not math.isfinite(phi):
            continue
        out[index] = reprint_like(out[index], float(out[index]) * phi)
    return out


def ref_merge_rows(
    stock: dict[tuple[str, str, str], list[str]],
    ours: dict[tuple[str, str, str], list[str]],
    columns: list[ColumnReport],
) -> tuple[bool, str]:
    """ref-merge at one reference: linear columns within half-ULP, others byte-identical."""
    if set(stock) != set(ours):
        return False, (
            f"row-key sets differ (stock {len(stock)}, ours {len(ours)}, "
            f"only-stock {len(set(stock) - set(ours))}, only-ours {len(set(ours) - set(stock))})"
        )
    numeric = {
        col.index: col
        for col in columns
        if col.role == "numeric" and col.member not in (None, IDENTITY, BYTE)
    }
    for key, left in stock.items():
        right = ours[key]
        width = min(len(left), len(right))
        for index in range(width):
            if left[index] == right[index]:
                continue
            col = numeric.get(index)
            if col is None or not consistent(right[index], left[index], 1.0):
                return False, f"column {index} mismatch on {key}"
        if " ".join(left[width:]) != " ".join(right[width:]):
            return False, f"trailing tokens mismatch on {key}"
    return True, ""


def fit_observations(
    *,
    entries_n: int,
    lengths: list[int],
    part_index_lists: list[list[int]],
    record_ids: set[str],
    alias_to_index: dict[str, int],
    whole_tables: dict[str, str],
    part_tables: list[dict[str, str]],
    baseline: str | None = None,
) -> FitResult:
    """Fit the closed family on one partition. Ties are reported, not guessed."""
    if entries_n < 2:
        return refuse("fewer than 2 reference entries")
    if len(part_index_lists) < 2:
        return refuse("partition has fewer than 2 parts")
    names = list(whole_tables)
    if any(set(part) != set(names) for part in part_tables):
        return refuse("probe runs did not write the same output tables")
    part_of: dict[int, int] = {}
    for part_i, indices in enumerate(part_index_lists):
        for index in indices:
            if index in part_of:
                return refuse("partition parts overlap")
            part_of[index] = part_i
    if set(part_of) != set(range(entries_n)):
        return refuse("partition does not cover the reference")
    entry_ids = set(alias_to_index)
    try:
        bundles = [
            _bundle_table(
                name,
                whole_tables[name],
                [part[name] for part in part_tables],
                record_ids,
                entry_ids,
                alias_to_index,
                part_of,
            )
            for name in names
        ]
    except ValueError as exc:
        return refuse(str(exc))

    key_reasons = [bundle.key_reason for bundle in bundles if not bundle.key_equal]
    part_entry_counts = [len(indices) for indices in part_index_lists]
    part_lengths = [sum(lengths[i] for i in indices) for indices in part_index_lists]
    whole_length = sum(lengths)
    whole_counts = {bundle.name: per_record_counts(bundle.whole) for bundle in bundles}
    part_counts = [
        {bundle.name: per_record_counts(bundle.parts[part_i]) for bundle in bundles}
        for part_i in range(len(part_index_lists))
    ]

    def phi_for(kind: str, count_table: str | None):
        return _phi_factory(
            kind,
            count_table,
            part_entry_counts,
            part_lengths,
            entries_n,
            whole_length,
            part_counts,
            whole_counts,
        )

    table_reports: list[TableReport] = []
    pending_ties: list[tuple[TableReport, ColumnReport, list[_Cand]]] = []
    refusals: list[str] = []
    for bundle in bundles:
        columns: list[ColumnReport] = []
        if not bundle.aligned:
            table_reports.append(
                TableReport(
                    name=bundle.name,
                    record_col=bundle.record_col,
                    entry_col=bundle.entry_col,
                    index_col=bundle.index_col,
                    meta=bundle.meta,
                    columns=columns,
                )
            )
            continue
        width = min(min(len(row.whole), len(row.part_cells)) for row in bundle.aligned)
        for row in bundle.aligned:
            if " ".join(row.whole[width:]) != " ".join(row.part_cells[width:]):
                refusals.append(f"{bundle.name}: trailing tokens are not byte-identical")
                break
        else:
            for col in range(width):
                status, fitting, non_identity = _fit_column(
                    bundle.aligned, col, names, phi_for
                )
                if status == "mixed":
                    refusals.append(f"{bundle.name}: column {col} is mixed numeric and text")
                    continue
                if status == "byte":
                    same = all(row.whole[col] == row.part_cells[col] for row in bundle.aligned)
                    if not same:
                        refusals.append(
                            f"{bundle.name}: non-numeric column {col} is not byte-identical"
                        )
                    columns.append(ColumnReport(index=col, role="byte", member=BYTE))
                    continue
                labels = [cand.label for cand in fitting]
                report = ColumnReport(
                    index=col,
                    role="numeric",
                    primary_fits=labels,
                )
                if baseline == "gestore":
                    identity_fits = any(cand.kind == IDENTITY for cand in fitting)
                    if not identity_fits:
                        refusals.append(
                            f"{bundle.name}: column {col} depends on the reference; "
                            "baseline does not infer a normalizer, so the row cannot be reused"
                        )
                    else:
                        report.member = IDENTITY
                    columns.append(report)
                    continue
                if not fitting:
                    refusals.append(f"{bundle.name}: column {col} matches no normalizer")
                    columns.append(report)
                    continue
                if not non_identity:
                    report.member = IDENTITY
                    columns.append(report)
                    continue
                if len(non_identity) == 1:
                    winner = non_identity[0]
                    report.member = winner.kind
                    report.count_table = winner.count_table
                    columns.append(report)
                    continue
                report.tie = [cand.label for cand in non_identity]
                columns.append(report)
        table_reports.append(
            TableReport(
                name=bundle.name,
                record_col=bundle.record_col,
                entry_col=bundle.entry_col,
                index_col=bundle.index_col,
                meta=bundle.meta,
                columns=columns,
            )
        )
    result = FitResult(
        decision="SHIP",
        reason="decomposition and normalizers fitted",
        tables=table_reports,
        used_tie_break=False,
        primary_key_equal=not key_reasons,
        probe_invocations=1 + len(part_index_lists),
    )
    # Attach aligned bundles for the tie-break driver via a private attribute.
    result._bundles = bundles  # type: ignore[attr-defined]
    result._phi_for = phi_for  # type: ignore[attr-defined]
    result._names = names  # type: ignore[attr-defined]
    result._key_reason = key_reasons[0] if key_reasons else ""  # type: ignore[attr-defined]
    if refusals:
        result.decision = "REFUSE"
        result.reason = refusals[0]
        return result
    if any(col.tie for table in table_reports for col in table.columns):
        if baseline == "gestore":
            result.decision = "REFUSE"
            result.reason = "baseline does not break normalizer ties"
            return result
        result.decision = "TIE"
        result.reason = "two or more normalizers fit; disambiguating probe required"
        return result
    if key_reasons:
        result.decision = "REFUSE"
        result.reason = key_reasons[0]
        return result
    return result


def resolve_ties(
    primary: FitResult,
    *,
    entries_n: int,
    lengths: list[int],
    tie_parts: list[list[int]],
    record_ids: set[str],
    alias_to_index: dict[str, int],
    whole_tables: dict[str, str],
    tie_tables: list[dict[str, str]],
) -> FitResult:
    """Keep a tied candidate only if it still fits the disambiguating partition."""
    if primary.decision != "TIE":
        return primary
    check = fit_observations(
        entries_n=entries_n,
        lengths=lengths,
        part_index_lists=tie_parts,
        record_ids=record_ids,
        alias_to_index=alias_to_index,
        whole_tables=whole_tables,
        part_tables=tie_tables,
    )
    check.used_tie_break = True
    check.probe_invocations = primary.probe_invocations + len(tie_parts)
    if not hasattr(check, "_bundles"):
        primary.decision = "REFUSE"
        primary.reason = check.reason or "disambiguating probe produced no rows"
        primary.used_tie_break = True
        primary.probe_invocations = primary.probe_invocations + len(tie_parts)
        return primary
    bundles = {bundle.name: bundle for bundle in check._bundles}  # type: ignore[attr-defined]
    phi_for = check._phi_for  # type: ignore[attr-defined]
    names = check._names  # type: ignore[attr-defined]
    refusals: list[str] = []
    for table in primary.tables:
        bundle = bundles.get(table.name)
        if bundle is None:
            refusals.append(f"{table.name}: missing from the disambiguating probe")
            continue
        for col in table.columns:
            if not col.tie:
                continue
            if not bundle.aligned or col.index >= min(len(row.whole) for row in bundle.aligned):
                refusals.append(
                    f"{table.name}: column {col.index} is absent on the disambiguating rows"
                )
                col.member = None
                continue
            survivors: list[_Cand] = []
            residual: dict[str, dict] = {}
            for label, kind, count_table in _family(names):
                if label not in col.tie:
                    continue
                phi_of = phi_for(kind, count_table)
                summary = _residual_summary(bundle.aligned, col.index, phi_of)
                residual[label] = summary
                if summary["fits"]:
                    survivors.append(_Cand(label, kind, count_table, phi_of))
            col.tie_break = residual
            identity_phi = phi_for(IDENTITY, None)
            non_identity = [
                cand
                for cand in survivors
                if cand.kind != IDENTITY
                and not _predictions_match(bundle.aligned, col.index, cand.phi_of, identity_phi)
            ]
            if not survivors and not non_identity:
                refusals.append(
                    f"{table.name}: column {col.index} tie-break eliminated every candidate"
                )
                col.member = None
                continue
            if not non_identity:
                col.member = IDENTITY
                col.count_table = None
                col.tie = []
                continue
            if len(non_identity) == 1:
                winner = non_identity[0]
                col.member = winner.kind
                col.count_table = winner.count_table
                col.tie = []
                continue
            refusals.append(
                f"{table.name}: column {col.index} tie-break still fits "
                + ", ".join(cand.label for cand in non_identity)
            )
            col.member = None
    # Key-set failure of the *primary* partition still refuses, even if columns resolved.
    if not primary.primary_key_equal:
        refusals.append(primary.reason if primary.decision == "REFUSE" else "primary row-key sets differ")
    # The primary result's key reason was stored only when decision was REFUSE.
    # fit_observations returns TIE before the key check when ties exist. Re-read it.
    if primary.primary_key_equal is False:
        # reason on a TIE result is the tie message, not the key message.
        # The driver must pass the key failure separately. Handled below via flag.
        pass
    merged = FitResult(
        decision="SHIP" if not refusals else "REFUSE",
        reason="decomposition and normalizers fitted" if not refusals else refusals[0],
        tables=primary.tables,
        used_tie_break=True,
        primary_key_equal=primary.primary_key_equal,
        probe_invocations=check.probe_invocations,
    )
    if primary.primary_key_equal is False:
        merged.decision = "REFUSE"
        key_reason = getattr(primary, "_key_reason", "")
        merged.reason = key_reason or "primary row-key sets differ"
    return merged
