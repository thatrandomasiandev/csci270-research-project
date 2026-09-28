"""Probe-only lines → table inference. No per-tool branches. No LLM.

CLI kind: ``linetable``. Protocol name: ``lines->table``.
"""

from __future__ import annotations

import csv
import io
import json
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from acts.infer_vcf import (
    BATCHED_SUBSET_SEED,
    InferError,
    SUBSET_MODES,
    _CallMeter,
    batched_index_groups,
    run_vcf_tool,
)
from acts.sample import PROBE_SEED, sample_records
from acts.trace import run_traced

PROBE_N = 500
run_linetable_tool = run_vcf_tool


@dataclass
class LineTableContract:
    kind: str
    argv: list[str]
    query_col: int
    produced_cols: list[int]
    delim: str
    match: str
    n_cols: int
    correspondence: str
    rows_per_record: int = 1
    widen_history: list[str] = field(default_factory=list)
    late_key_probes: list[str] = field(default_factory=list)
    traced_files: list[str] = field(default_factory=list)
    trace_status: str = "unavailable"
    probe_n: int = 0
    probe_seed: int = PROBE_SEED
    subset_mode: str = "batched"
    tool_calls: int = 0
    tool_call_sizes: list[int] = field(default_factory=list)
    decision: str = "OK"
    reason: str = ""

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> LineTableContract:
        raw = json.loads(path.read_text())
        raw.setdefault("late_key_probes", [])
        raw.setdefault("widen_history", [])
        raw.setdefault("traced_files", [])
        raw.setdefault("trace_status", "unavailable")
        raw.setdefault("probe_seed", PROBE_SEED)
        raw.setdefault("subset_mode", "batched")
        raw.setdefault("tool_calls", 0)
        raw.setdefault("tool_call_sizes", [])
        raw.setdefault("correspondence", "echo" if raw.get("query_col", -1) >= 0 else "order")
        raw.setdefault("rows_per_record", 1)
        return cls(**raw)


def read_lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


def write_lines(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""))
    return path


def _count_lines(path: Path) -> int:
    return len(read_lines(path))


def detect_table_delim(lines: list[str]) -> str:
    if any("\t" in ln for ln in lines):
        return "tab"
    if any("," in ln for ln in lines):
        return "comma"
    return "ws"


def parse_linetable(text: str) -> tuple[list[str], str, list[str], list[list[str]]]:
    """Header cells, delimiter name, raw body lines, parsed body rows."""
    rest: list[str] = []
    for ln in text.splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        rest.append(ln)
    if not rest:
        return [], "comma", [], []
    delim = detect_table_delim(rest)
    header_line, body_raw = rest[0], rest[1:]
    if delim == "ws":
        return header_line.split(), delim, body_raw, [ln.split() for ln in body_raw]
    dialect = "\t" if delim == "tab" else ","
    reader = csv.reader(io.StringIO("\n".join(rest) + "\n"), delimiter=dialect)
    parsed = list(reader)
    header = parsed[0] if parsed else []
    rows = parsed[1:]
    return header, delim, body_raw, rows


def header_and_body(text: str) -> tuple[list[str], list[str]]:
    header: list[str] = []
    body: list[str] = []
    seen_header = False
    for ln in text.splitlines():
        if not ln.strip() or ln.startswith("#"):
            if not seen_header:
                header.append(ln)
            continue
        if not seen_header:
            header.append(ln)
            seen_header = True
            continue
        body.append(ln)
    return header, body


def _max_cols(rows: list[list[str]]) -> int:
    return max((len(r) for r in rows), default=0)


def _group(rows: list[list[str]], query_col: int) -> dict[str, list[list[str]]]:
    groups: dict[str, list[list[str]]] = defaultdict(list)
    for row in rows:
        if query_col >= len(row):
            raise InferError("REFUSE_AMBIGUOUS", "row shorter than query column")
        groups[row[query_col]].append(row)
    return groups


def _group_raw(raw: list[str], rows: list[list[str]], query_col: int) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for ln, row in zip(raw, rows):
        if query_col >= len(row):
            raise InferError("REFUSE_AMBIGUOUS", "row shorter than query column")
        groups[row[query_col]].append(ln)
    return groups


def _positional_groups(lines: list[str], raw: list[str], k: int) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    if k <= 0:
        raise InferError("REFUSE_AMBIGUOUS", "rows_per_record must be ≥ 1")
    if len(raw) != k * len(lines):
        raise InferError("REFUSE_AMBIGUOUS", "positional row count mismatch")
    for i, line in enumerate(lines):
        groups[line].extend(raw[i * k : (i + 1) * k])
    return groups


def find_query_col(
    names: list[str],
    rows: list[list[str]],
    pert_names: list[str],
    pert_rows: list[list[str]],
) -> int | None:
    name_set = set(names)
    pert_set = set(pert_names)
    n1 = _max_cols(rows)
    n2 = _max_cols(pert_rows)
    hits: list[int] = []
    for i in range(min(n1, n2) if n1 and n2 else 0):
        vals = [r[i] for r in rows if i < len(r)]
        pvals = [r[i] for r in pert_rows if i < len(r)]
        if not vals and not pvals:
            continue
        if any(v not in name_set for v in vals):
            continue
        if any(v not in pert_set for v in pvals):
            continue
        g1 = _group(rows, i)
        g2 = _group(pert_rows, i)
        ok = True
        for n, p in zip(names, pert_names):
            if len(g1.get(n, [])) != len(g2.get(p, [])):
                ok = False
                break
        if ok:
            hits.append(i)
    if not hits:
        return None
    return hits[0]


def infer_positional(n_in: int, n_rows: int) -> int:
    if n_in <= 0:
        raise InferError("REFUSE_AMBIGUOUS", "empty lines input")
    if n_rows == n_in:
        return 1
    if n_rows > 0 and n_rows % n_in == 0:
        return n_rows // n_in
    raise InferError(
        "REFUSE_AMBIGUOUS",
        "no echoed input column and row count is not a constant multiple of n_in",
    )


def order_kind(names: list[str], rows: list[list[str]], query_col: int) -> str:
    seen: list[str] = []
    for row in rows:
        q = row[query_col]
        if not seen or seen[-1] != q:
            seen.append(q)
    counts: dict[str, int] = defaultdict(int)
    for q in seen:
        counts[q] += 1
        if counts[q] > 1:
            return "multiset"
    hit = [n for n in names if n in counts]
    if seen == hit:
        return "order"
    return "multiset"


def _record_raw(
    lines: list[str],
    raw: list[str],
    rows: list[list[str]],
    contract: LineTableContract,
) -> dict[str, list[str]]:
    if contract.correspondence == "echo":
        return _group_raw(raw, rows, contract.query_col)
    return _positional_groups(lines, raw, contract.rows_per_record)


def assert_subset_invariant(
    argv: list[str],
    lines: list[str],
    full_text: str,
    contract: LineTableContract,
    work: Path,
    *,
    subset_mode: str = "batched",
    runner=None,
    seed: int = BATCHED_SUBSET_SEED,
) -> None:
    if subset_mode not in SUBSET_MODES:
        raise ValueError(f"subset_mode must be one of {SUBSET_MODES}, got {subset_mode!r}")
    run = runner or run_linetable_tool
    _, _, raw_full, rows_full = parse_linetable(full_text)
    groups = _record_raw(lines, raw_full, rows_full, contract)
    work.mkdir(parents=True, exist_ok=True)

    def _check(batch: list[str], label: str, dest: Path) -> None:
        path = write_lines(dest, batch)
        out = run(argv, path)
        _, _, got_raw, got_rows = parse_linetable(out)
        got = _record_raw(batch, got_raw, got_rows, contract)
        for line in batch:
            if got.get(line, []) != groups.get(line, []):
                raise InferError(
                    "REFUSE_GLOBAL",
                    f"output depends on the rest of the file ({label})",
                )

    if subset_mode == "singleton":
        solo = work / "singleton"
        solo.mkdir(parents=True, exist_ok=True)
        for i, line in enumerate(lines):
            _check([line], f"singleton {i}", solo / f"{i}.txt")
        return

    batches = work / "batched"
    batches.mkdir(parents=True, exist_ok=True)
    for g, indices in enumerate(batched_index_groups(len(lines), seed=seed)):
        batch = [lines[i] for i in indices]
        _check(batch, f"batch {g} n={len(indices)}", batches / f"g{g}_n{len(indices)}.txt")


def classify_produced(n_cols: int, query_col: int) -> list[int]:
    return [i for i in range(n_cols) if i != query_col]


def infer_linetable_contract(
    argv: list[str],
    lines: list[str],
    work: Path,
    *,
    probe_n: int = PROBE_N,
    probe_seed: int = PROBE_SEED,
    subset_mode: str = "batched",
) -> LineTableContract:
    if subset_mode not in SUBSET_MODES:
        raise ValueError(f"subset_mode must be one of {SUBSET_MODES}, got {subset_mode!r}")
    probe = sample_records(lines, min(probe_n, len(lines)), seed=probe_seed)
    if not probe:
        raise InferError("REFUSE_AMBIGUOUS", "empty lines input")
    work.mkdir(parents=True, exist_ok=True)
    meter = _CallMeter(_count_lines)
    run = meter.run

    try:
        p1 = write_lines(work / "probe.txt", probe)
        out1, traced_files, trace_status = run_traced(
            argv, input_path=p1, work=work / "trace", runner=run
        )
        out2 = run(argv, p1)
        _, body1 = header_and_body(out1)
        _, body2 = header_and_body(out2)
        if body1 != body2:
            raise InferError("REFUSE_NONDETERMINISTIC", "tool body differs across two identical runs")

        delim, rows1 = parse_linetable(out1)[1], parse_linetable(out1)[3]
        raw1 = parse_linetable(out1)[2]
        pert = [f"PERTURB_{i}" for i in range(len(probe))]
        out_p = run(argv, write_lines(work / "probe_pert.txt", pert))
        _, _, _, rows_p = parse_linetable(out_p)
        query_col = find_query_col(probe, rows1, pert, rows_p)
        if query_col is None:
            k = infer_positional(len(probe), len(raw1))
            correspondence = "order"
            qcol = -1
            match = "order"
        else:
            k = 0
            correspondence = "echo"
            qcol = query_col
            match = order_kind(probe, rows1, qcol)

        shuffled = list(probe)
        random.Random(7).shuffle(shuffled)
        out_sh = run(argv, write_lines(work / "probe_shuffle.txt", shuffled))
        _, _, raw_sh, rows_sh = parse_linetable(out_sh)
        draft = LineTableContract(
            kind="linetable",
            argv=list(argv),
            query_col=qcol,
            produced_cols=[],
            delim=delim,
            match=match,
            n_cols=_max_cols(rows1),
            correspondence=correspondence,
            rows_per_record=k or 1,
        )
        g1 = _record_raw(probe, raw1, rows1, draft)
        gsh = _record_raw(shuffled, raw_sh, rows_sh, draft)
        for line in probe:
            if g1.get(line, []) != gsh.get(line, []):
                raise InferError("REFUSE_NEIGHBORS", "shuffle test failed; neighbors leak")

        produced = classify_produced(_max_cols(rows1), qcol)
        contract = LineTableContract(
            kind="linetable",
            argv=list(argv),
            query_col=qcol,
            produced_cols=produced,
            delim=delim,
            match=match,
            n_cols=_max_cols(rows1),
            correspondence=correspondence,
            rows_per_record=k or 1,
            traced_files=traced_files,
            trace_status=trace_status,
            probe_n=len(probe),
            probe_seed=probe_seed,
            subset_mode=subset_mode,
            tool_calls=0,
            tool_call_sizes=[],
            decision="OK",
            reason="probe passed",
        )
        assert_subset_invariant(
            argv,
            probe,
            out1,
            contract,
            work,
            subset_mode=subset_mode,
            runner=run,
        )
        contract.tool_calls = meter.n
        contract.tool_call_sizes = list(meter.sizes)
        return contract
    except InferError as exc:
        exc.tool_calls = meter.n
        exc.tool_call_sizes = list(meter.sizes)
        raise


def _subst_token(line: str, old: str, new: str) -> str:
    if not old or old == new:
        return line
    out: list[str] = []
    seen = False
    i = 0
    while i < len(line):
        if not seen and line.startswith(old, i):
            left = line[i - 1] if i else ","
            right = line[i + len(old)] if i + len(old) < len(line) else ","
            sep = left in ",\t " and right in ",\t "
            if sep or (i == 0 and right in ",\t "):
                out.append(new)
                i += len(old)
                seen = True
                continue
        out.append(line[i])
        i += 1
    return "".join(out) if seen else line


def extract_rows(
    raw: list[str], rows: list[list[str]], contract: LineTableContract
) -> dict:
    packed = []
    for ln, row in zip(raw, rows):
        produced = {str(i): row[i] for i in contract.produced_cols if i < len(row)}
        q = ""
        if contract.query_col >= 0 and contract.query_col < len(row):
            q = row[contract.query_col]
        packed.append({"raw": ln, "query": q, "produced": produced, "n": len(row)})
    return {"rows": packed}


def reassemble_rows(line: str, payload: dict, contract: LineTableContract) -> list[str]:
    lines: list[str] = []
    for item in payload.get("rows", []):
        raw = item.get("raw")
        if raw:
            ln = raw
            old = item.get("query") or ""
            if contract.correspondence == "echo" and old and old != line:
                ln = _subst_token(ln, old, line)
            lines.append(ln)
            continue
        n = max(item.get("n", 0), contract.n_cols, contract.query_col + 1)
        cells = [""] * n
        for i, val in item.get("produced", {}).items():
            idx = int(i)
            while len(cells) <= idx:
                cells.append("")
            cells[idx] = val
        if contract.query_col >= 0:
            while len(cells) <= contract.query_col:
                cells.append("")
            cells[contract.query_col] = line
        delim = "\t" if contract.delim == "tab" else "," if contract.delim == "comma" else " "
        buf = io.StringIO()
        csv.writer(buf, delimiter=delim if delim != " " else ",").writerow(cells)
        lines.append(buf.getvalue().rstrip("\r\n"))
    return lines


def unclassified_cols(rows: list[list[str]], contract: LineTableContract) -> list[int]:
    extra: list[int] = []
    known = set(contract.produced_cols)
    if contract.query_col >= 0:
        known.add(contract.query_col)
    for row in rows:
        for i in range(len(row)):
            if i not in known and i not in extra:
                extra.append(i)
    return extra


def probe_late_cols(
    argv: list[str],
    carriers: list[str],
    contract: LineTableContract,
    work: Path,
    new_cols: list[int],
) -> None:
    if not carriers or not new_cols:
        return
    subset = carriers[:200]
    work.mkdir(parents=True, exist_ok=True)
    out_o = run_linetable_tool(argv, write_lines(work / "late_orig.txt", subset))
    _, _, _, rows_o = parse_linetable(out_o)
    for i in new_cols:
        if i not in contract.produced_cols and i != contract.query_col:
            contract.produced_cols.append(i)
        contract.n_cols = max(contract.n_cols, i + 1)
        tag = str(i)
        if tag not in contract.late_key_probes:
            contract.late_key_probes.append(tag)
    del rows_o


def linetable_match(a: str, b: str, match: str) -> bool:
    body_a = header_and_body(a)[1]
    body_b = header_and_body(b)[1]
    if match == "multiset":
        from collections import Counter

        return Counter(body_a) == Counter(body_b)
    return body_a == body_b


def load_or_infer_linetable(
    argv: list[str],
    lines: list[str],
    work: Path,
    contract_path: Path,
    *,
    probe_n: int = PROBE_N,
    probe_seed: int = PROBE_SEED,
    subset_mode: str = "batched",
) -> LineTableContract:
    if contract_path.is_file():
        saved = LineTableContract.load(contract_path)
        if saved.argv == list(argv) and saved.kind == "linetable" and saved.decision == "OK":
            return saved
    contract = infer_linetable_contract(
        argv,
        lines,
        work,
        probe_n=probe_n,
        probe_seed=probe_seed,
        subset_mode=subset_mode,
    )
    contract.save(contract_path)
    return contract


def refuse_linetable(exc: InferError, argv: list[str]) -> LineTableContract:
    return LineTableContract(
        kind="linetable",
        argv=list(argv),
        query_col=-1,
        produced_cols=[],
        delim="comma",
        match="order",
        n_cols=0,
        correspondence="order",
        subset_mode="batched",
        tool_calls=getattr(exc, "tool_calls", 0),
        tool_call_sizes=list(getattr(exc, "tool_call_sizes", []) or []),
        decision=exc.decision,
        reason=exc.reason,
    )
