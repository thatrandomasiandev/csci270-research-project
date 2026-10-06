"""Probe-only FASTA → table inference. No per-tool branches. No LLM."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from acts.fasta import FastaRec, perturb_fasta, shuffle_fasta, write_fasta
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
from acts.table import (
    TableLayout,
    body_lines,
    bodies_equal,
    detect_delim,
    body_mismatch_count,
    infer_table_layout,
    join_row,
    layout_pad_widths,
    meta_lines,
    render_table,
    split_body_rows,
    split_body_rows_n,
)

MISSING_DESC = ("", "-", ".")

PROBE_N = 500

run_table_tool = run_vcf_tool


@dataclass
class TableContract:
    kind: str
    argv: list[str]
    query_col: int
    desc_cols: list[int]
    produced_cols: list[int]
    delim: str
    match: str
    n_cols: int
    pad_widths: list[int] = field(default_factory=list)
    empty_desc: str = ""
    match_ws: bool = False
    desc_span: bool = False
    desc_trailing: bool = False
    layout: dict = field(default_factory=dict)
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
    def load(cls, path: Path) -> TableContract:
        raw = json.loads(path.read_text())
        raw.setdefault("late_key_probes", [])
        raw.setdefault("widen_history", [])
        raw.setdefault("pad_widths", [])
        raw.setdefault("empty_desc", "")
        raw.setdefault("match_ws", False)
        raw.setdefault("desc_span", False)
        raw.setdefault("desc_trailing", False)
        raw.setdefault("layout", {})
        raw.setdefault("traced_files", [])
        raw.setdefault("trace_status", "unavailable")
        raw.setdefault("probe_seed", PROBE_SEED)
        raw.setdefault("subset_mode", "batched")
        raw.setdefault("tool_calls", 0)
        raw.setdefault("tool_call_sizes", [])
        return cls(**raw)


def layout_is_pinned(contract: TableContract) -> bool:
    layout = contract.layout or {}
    if isinstance(layout, dict):
        return bool(layout.get("pinned"))
    return bool(getattr(layout, "pinned", False))


def contract_satisfies(contract: TableContract, expected_match: str) -> tuple[bool, str]:
    """Accept `expected_match` under whitespace MATCH or a stricter pinned byte MATCH.

    True iff `contract.match == expected_match` and (`match_ws` or the layout
    is pinned). A pinned layout is what makes inference set `match_ws` false
    and check body lines for byte equality (`tables_match` with `match_ws`
    false: list equality for order, `Counter` equality for multiset). That
    check implies whitespace-normalized equality of the **same** match type,
    because `ws_line` (`" ".join(line.split())`) is a function of each body
    line: equal lists stay equal in order, and equal multisets stay equal
    after the function is applied elementwise. Collisions under `ws_line`
    can only make the whitespace relation weaker, never stronger, so the
    converse is false. An unpinned contract with `match_ws` false is neither
    relation and is refused. There is no fallback from a failed byte check
    to whitespace.
    """
    got = contract.match
    if got != expected_match:
        return False, f"match {got!r} != expected {expected_match!r}"
    pinned = layout_is_pinned(contract)
    if contract.match_ws or pinned:
        parts: list[str] = []
        if contract.match_ws:
            parts.append("whitespace-normalized MATCH")
        if pinned:
            parts.append("pinned byte MATCH")
        return True, "match agrees; " + " and ".join(parts)
    return False, "unpinned contract with match_ws false"


def _max_cols(rows: list[list[str]]) -> int:
    return max((len(r) for r in rows), default=0)


# Placeholder for a description echoed as a whitespace-token span.
DESC_SENTINEL = "\x01ACTS_DESC\x01"


def _bounded_positions(line: str, token: str) -> list[int]:
    """Start offsets where `token` occurs with whitespace (or line edge) on both sides."""
    out: list[int] = []
    if not token:
        return out
    start = 0
    while True:
        i = line.find(token, start)
        if i < 0:
            return out
        left = line[i - 1] if i else " "
        j = i + len(token)
        right = line[j] if j < len(line) else " "
        if left.isspace() and right.isspace():
            out.append(i)
        start = i + 1


def _subst_last(line: str, old: str, new: str) -> str:
    """Replace the LAST whitespace-bounded occurrence of `old`.

    Free-text fields such as a description sit at the end of a table row, and an
    empty marker like "-" can also appear earlier (e.g. an accession column).
    """
    pos = _bounded_positions(line, old)
    if not pos:
        return line
    i = pos[-1]
    return line[:i] + new + line[i + len(old):]


def _desc_token(desc: str, empty_desc: str) -> str:
    return desc if desc else empty_desc


def swap_desc_raw(line: str, old_desc: str, new_desc: str, contract: "TableContract") -> str:
    """Put the new record's description into a cached raw output line."""
    if contract.delim == "tab":
        if not contract.desc_cols:
            return line
        parts = line.split("\t")
        for i in contract.desc_cols:
            if i < len(parts):
                parts[i] = new_desc or contract.empty_desc
        return "\t".join(parts)
    if not (contract.desc_span or contract.desc_cols):
        return line
    old = _desc_token(old_desc, contract.empty_desc)
    new = _desc_token(new_desc, contract.empty_desc)
    if old == new:
        return line
    if old:
        return _subst_last(line, old, new)
    # Empty old description printed as nothing: only valid for a trailing field.
    return line.rstrip() + (" " + new if new else "")


def detect_desc_span(
    pert: list[FastaRec], pert_groups_raw: dict[str, list[str]]
) -> bool:
    """True if every perturbed record that produced lines echoes its (multi-word)
    description verbatim in each of those lines."""
    seen = False
    for rec in pert:
        lines = pert_groups_raw.get(rec.name, [])
        if not lines or not rec.description:
            continue
        seen = True
        if not all(_bounded_positions(ln, rec.description) for ln in lines):
            return False
    return seen


def _normalize_desc_lines(
    recs: list[FastaRec], groups_raw: dict[str, list[str]], empty_markers: tuple[str, ...]
) -> dict[str, list[str]]:
    """Replace each record's echoed description (or empty marker) with DESC_SENTINEL."""
    out: dict[str, list[str]] = {}
    for rec in recs:
        lines = []
        for ln in groups_raw.get(rec.name, []):
            if rec.description:
                ln = _subst_last(ln, rec.description, DESC_SENTINEL)
            else:
                for marker in empty_markers:
                    if marker and _bounded_positions(ln, marker):
                        ln = _subst_last(ln, marker, DESC_SENTINEL)
                        break
                else:
                    # The tool printed nothing for an empty description.
                    ln = ln.rstrip() + " " + DESC_SENTINEL
            lines.append(ln)
        out[rec.name] = lines
    return out


def _split_body(text: str, delim: str | None = None) -> tuple[str, list[list[str]]]:
    body = body_lines(text)
    used = delim or detect_delim(body)
    return used, split_body_rows(body, used)


def _group(rows: list[list[str]], query_col: int) -> dict[str, list[list[str]]]:
    groups: dict[str, list[list[str]]] = defaultdict(list)
    for row in rows:
        if query_col >= len(row):
            raise InferError("REFUSE_AMBIGUOUS", "row shorter than query column")
        groups[row[query_col]].append(row)
    return groups


def _group_raw(
    raw: list[str], rows: list[list[str]], query_col: int
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for ln, row in zip(raw, rows):
        if query_col >= len(row):
            raise InferError("REFUSE_AMBIGUOUS", "row shorter than query column")
        groups[row[query_col]].append(ln)
    return groups


def find_query_col(
    names: list[str],
    rows: list[list[str]],
    pert_names: list[str],
    pert_rows: list[list[str]],
) -> int:
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
        raise InferError("REFUSE_AMBIGUOUS", "no column followed the renamed records")
    return hits[0]


def _echoes_desc(val: str | None, desc: str) -> bool:
    if val is None:
        return False
    if desc:
        return val == desc
    return val in MISSING_DESC


def _remainder(line: str, name: str, desc: str) -> str:
    out = _subst_token(line, name, " ")
    if desc:
        out = out.replace(desc, " ", 1)
    return " ".join(out.split())


def classify_columns(
    names: list[str],
    descs: list[str],
    rows: list[list[str]],
    pert_names: list[str],
    pert_descs: list[str],
    pert_rows: list[list[str]],
    query_col: int,
    raw: list[str] | None = None,
    pert_raw: list[str] | None = None,
) -> tuple[list[int], list[int]]:
    g1 = _group(rows, query_col)
    g2 = _group(pert_rows, query_col)
    g1r = _group_raw(raw, rows, query_col) if raw is not None else None
    g2r = _group_raw(pert_raw, pert_rows, query_col) if pert_raw is not None else None
    n_cols = max(_max_cols(rows), _max_cols(pert_rows))
    desc_cols: list[int] = []
    produced: list[int] = []
    for i in range(n_cols):
        if i == query_col:
            continue
        roles: list[str] = []
        raw_ok = True
        for n, p, d0, d1 in zip(names, pert_names, descs, pert_descs):
            a_rows = g1.get(n, [])
            b_rows = g2.get(p, [])
            if len(a_rows) != len(b_rows):
                raise InferError("REFUSE_AMBIGUOUS", f"line count changed for {n}")
            if g1r is not None and g2r is not None:
                for a_ln, b_ln in zip(g1r.get(n, []), g2r.get(p, [])):
                    if _remainder(a_ln, n, d0) != _remainder(b_ln, p, d1):
                        raw_ok = False
            for a, b in zip(a_rows, b_rows):
                va = a[i] if i < len(a) else None
                vb = b[i] if i < len(b) else None
                if va is None or vb is None:
                    roles.append("ambiguous")
                    continue
                if vb == p and va == n:
                    roles.append("name")
                    continue
                if _echoes_desc(va, d0) and _echoes_desc(vb, d1):
                    roles.append("desc")
                    continue
                if va == vb:
                    roles.append("produced")
                    continue
                roles.append("depends")
        if not roles:
            continue
        kinds = set(roles)
        if kinds == {"desc"}:
            desc_cols.append(i)
        elif kinds == {"produced"}:
            produced.append(i)
        elif kinds == {"name"}:
            continue
        elif raw_ok and g1r is not None:
            produced.append(i)
        else:
            raise InferError(
                "REFUSE_AMBIGUOUS",
                f"column {i} still DEPENDS-ON-NON-KEY ({sorted(kinds)})",
            )
    return desc_cols, produced


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


def _count_fasta_records(path: Path) -> int:
    return sum(1 for ln in path.read_text().splitlines() if ln.startswith(">"))


def assert_subset_invariant(
    argv: list[str],
    recs: list[FastaRec],
    full_text: str,
    query_col: int,
    delim: str,
    work: Path,
    *,
    subset_mode: str = "batched",
    runner=None,
    seed: int = BATCHED_SUBSET_SEED,
) -> None:
    if subset_mode not in SUBSET_MODES:
        raise ValueError(f"subset_mode must be one of {SUBSET_MODES}, got {subset_mode!r}")
    run = runner or run_table_tool
    raw_full = body_lines(full_text)
    _, rows = _split_body(full_text, delim)
    groups = _group_raw(raw_full, rows, query_col)
    work.mkdir(parents=True, exist_ok=True)

    if subset_mode == "singleton":
        solo_dir = work / "singleton"
        solo_dir.mkdir(parents=True, exist_ok=True)
        for i, rec in enumerate(recs):
            path = write_fasta(solo_dir / f"{i}.fa", [rec])
            out = run(argv, path)
            got = body_lines(out)
            expected = groups.get(rec.name, [])
            if got != expected:
                raise InferError(
                    "REFUSE_GLOBAL",
                    f"output depends on the rest of the file (singleton {i})",
                )
        return

    batches = work / "batched"
    batches.mkdir(parents=True, exist_ok=True)
    for g, indices in enumerate(batched_index_groups(len(recs), seed=seed)):
        batch = [recs[i] for i in indices]
        path = write_fasta(batches / f"g{g}_n{len(indices)}.fa", batch)
        out = run(argv, path)
        got_raw = body_lines(out)
        _, got_rows = _split_body(out, delim)
        got_groups = _group_raw(got_raw, got_rows, query_col)
        for rec in batch:
            if got_groups.get(rec.name, []) != groups.get(rec.name, []):
                raise InferError(
                    "REFUSE_GLOBAL",
                    f"output depends on the rest of the file (batch {g} n={len(indices)})",
                )


def infer_table_contract(
    argv: list[str],
    recs: list[FastaRec],
    work: Path,
    *,
    probe_n: int = PROBE_N,
    probe_seed: int = PROBE_SEED,
    subset_mode: str = "batched",
) -> TableContract:
    if subset_mode not in SUBSET_MODES:
        raise ValueError(f"subset_mode must be one of {SUBSET_MODES}, got {subset_mode!r}")
    probe = sample_records(recs, min(probe_n, len(recs)), seed=probe_seed)
    if not probe:
        raise InferError("REFUSE_AMBIGUOUS", "empty FASTA")
    work.mkdir(parents=True, exist_ok=True)
    meter = _CallMeter(_count_fasta_records)
    run = meter.run

    try:
        p1 = write_fasta(work / "probe.fa", probe)
        out1, traced_files, trace_status = run_traced(
            argv, input_path=p1, work=work / "trace", runner=run
        )
        out2 = run(argv, p1)
        if not bodies_equal(out1, out2):
            raise InferError("REFUSE_NONDETERMINISTIC", "tool body differs across two identical runs")

        delim, rows1 = _split_body(out1)
        pert = perturb_fasta(probe)
        out_p = run(argv, write_fasta(work / "probe_pert.fa", pert))
        _, rows_p = _split_body(out_p, delim)
        names = [r.name for r in probe]
        pert_names = [r.name for r in pert]
        query_col = find_query_col(names, rows1, pert_names, rows_p)

        shuffled = shuffle_fasta(probe)
        out_sh = run(argv, write_fasta(work / "probe_shuffle.fa", shuffled))
        _, rows_sh = _split_body(out_sh, delim)
        g1 = _group_raw(body_lines(out1), rows1, query_col)
        gsh = _group_raw(body_lines(out_sh), rows_sh, query_col)
        for rec in probe:
            if g1.get(rec.name, []) != gsh.get(rec.name, []):
                raise InferError("REFUSE_NEIGHBORS", "shuffle test failed; neighbors leak")

        assert_subset_invariant(
            argv,
            probe,
            out1,
            query_col,
            delim,
            work,
            subset_mode=subset_mode,
            runner=run,
        )

        gp = _group_raw(body_lines(out_p), rows_p, query_col)
        # Tab tables keep a description in one cell; spans only arise in whitespace tables.
        desc_span = delim != "tab" and detect_desc_span(pert, gp)
        if desc_span:
            empty_desc = _infer_empty_marker(pert, gp) or _infer_empty_from_probe(probe, g1) or "-"
            markers = (empty_desc,) + tuple(m for m in MISSING_DESC if m and m != empty_desc)
            n1 = _normalize_desc_lines(probe, g1, markers)
            np_ = _normalize_desc_lines(pert, gp, markers)
            raw_n1 = [ln for r in probe for ln in n1.get(r.name, [])]
            raw_np = [ln for r in pert for ln in np_.get(r.name, [])]
            rows_n1 = split_body_rows(raw_n1, delim)
            rows_np = split_body_rows(raw_np, delim)
            desc_trailing = all(r and r[-1] == DESC_SENTINEL for r in rows_n1 + rows_np)
            desc_cols, produced = classify_columns(
                names,
                [DESC_SENTINEL] * len(probe),
                rows_n1,
                pert_names,
                [DESC_SENTINEL] * len(pert),
                rows_np,
                query_col,
                raw=raw_n1,
                pert_raw=raw_np,
            )
        else:
            desc_cols, produced = classify_columns(
                names,
                [r.description for r in probe],
                rows1,
                pert_names,
                [r.description for r in pert],
                rows_p,
                query_col,
                raw=body_lines(out1),
                pert_raw=body_lines(out_p),
            )
            empty_desc = _infer_empty_desc(rows1, desc_cols)
            desc_trailing = False
        match = order_kind(names, rows1, query_col)
        hit_names = {row[query_col] for row in rows1}
        layout_text = out1
        if desc_span and desc_trailing:
            # Collapse each description to one cell so column positions are stable.
            marker = empty_desc or "-"
            layout_text = "\n".join(
                [ln.replace(DESC_SENTINEL, marker) for ln in raw_n1]
            ) + "\n"
        layout = infer_layout_probe(
            argv,
            probe,
            query_col,
            delim,
            work / "align",
            layout_text,
            hit_names=hit_names,
            runner=run,
        )
        layout_d = layout.to_dict()
        pad_widths = layout_pad_widths(layout)
        n_cols = _max_cols(rows1)
        if desc_span and not desc_trailing:
            # A free-text span followed by other fields shifts token positions per
            # record: rebuild from raw lines; MATCH is whitespace-normalized.
            layout_d = {**layout_d, "pinned": False}
            pad_widths = []
            match_ws = delim != "tab"
        else:
            if desc_span:
                n_cols = _max_cols(rows_n1)  # description is one trailing cell
            match_ws = delim != "tab" and not layout.pinned
        contract = TableContract(
            kind="fasta",
            argv=list(argv),
            query_col=query_col,
            desc_cols=desc_cols,
            produced_cols=produced,
            delim=delim,
            match=match,
            n_cols=n_cols,
            pad_widths=pad_widths,
            empty_desc=empty_desc,
            match_ws=match_ws,
            desc_span=desc_span,
            desc_trailing=desc_trailing,
            layout=layout_d,
            traced_files=traced_files,
            trace_status=trace_status,
            probe_n=len(probe),
            probe_seed=probe_seed,
            subset_mode=subset_mode,
            tool_calls=meter.n,
            tool_call_sizes=list(meter.sizes),
            decision="OK",
            reason="probe passed",
        )
        verify_roundtrip(probe, pert, g1, rows_by_name(rows1, query_col), gp, contract)
        return contract
    except InferError as exc:
        exc.tool_calls = meter.n
        exc.tool_call_sizes = list(meter.sizes)
        raise


def _subst_token(line: str, old: str, new: str) -> str:
    if not old or old == new:
        return line
    parts = line.split(old)
    if len(parts) < 2:
        return line
    # Replace the first whole-token occurrence; keep surrounding whitespace.
    out: list[str] = []
    seen = False
    i = 0
    while i < len(line):
        if not seen and line.startswith(old, i):
            left = line[i - 1] if i else " "
            right = line[i + len(old)] if i + len(old) < len(line) else " "
            if left.isspace() and right.isspace():
                out.append(new)
                i += len(old)
                seen = True
                continue
        out.append(line[i])
        i += 1
    return "".join(out) if seen else line


def extract_rows(
    raw: list[str], rows: list[list[str]], contract: TableContract, desc: str = ""
) -> dict:
    packed = []
    for ln, row in zip(raw, rows):
        produced = {
            str(i): row[i]
            for i in contract.produced_cols
            if i < len(row)
        }
        packed.append(
            {
                "raw": ln,
                "name": row[contract.query_col] if contract.query_col < len(row) else "",
                "produced": produced,
                "n": len(row),
                "desc": desc,
            }
        )
    return {"rows": packed, "desc": desc}


def layout_from_contract(contract: TableContract) -> TableLayout:
    return TableLayout.from_dict(contract.layout)


def preflight_stock_outputs(
    contract: TableContract, stocks: list[tuple[str, str]]
) -> dict:
    """Rebuild archived stock bodies under this contract before any genome run.

    Each stock text is split with the contract's column count, re-rendered
    with its layout, and compared under its MATCH (`match` and `match_ws`).
    A pinned layout is a byte check. An unpinned layout is the
    whitespace-normalized MATCH. `ok` is false when any file has a mismatch;
    the caller stops with STOP_PREFLIGHT and does not spend the collection.
    No stock files is ok: there is nothing on disk that can refute the contract.
    """
    layout = layout_from_contract(contract)
    files: list[dict] = []
    for label, text in stocks:
        lines = body_lines(text)
        rows = split_body_rows_n(lines, contract.delim, contract.n_cols)
        rendered = render_table(rows, layout, query_col=contract.query_col)
        n_mis = body_mismatch_count(
            rendered, lines, contract.match, match_ws=contract.match_ws
        )
        files.append({"label": label, "n_rows": len(lines), "n_mismatch": n_mis})
    ok = all(row["n_mismatch"] == 0 for row in files)
    if not stocks:
        reason = "no stock outputs available"
    elif ok:
        counts = ",".join(str(row["n_mismatch"]) for row in files)
        reason = (
            f"0 mismatches on {len(files)} stock file(s) "
            f"under match={contract.match} match_ws={contract.match_ws} "
            f"pinned={layout.pinned} ({counts})"
        )
    else:
        bad = ", ".join(
            f"{row['label']} {row['n_mismatch']}/{row['n_rows']}"
            for row in files
            if row["n_mismatch"]
        )
        reason = f"stock rebuild mismatches: {bad}"
    return {
        "ok": ok,
        "reason": reason,
        "files": files,
        "pinned": layout.pinned,
        "match_ws": contract.match_ws,
    }


def reassemble_cells(
    rec: FastaRec, payload: dict, contract: TableContract
) -> list[list[str]]:
    rows: list[list[str]] = []
    for item in payload.get("rows", []):
        if contract.desc_span:
            n = max(contract.n_cols, contract.query_col + 1)
        else:
            # A row keeps its own width. contract.n_cols can grow via late-key probes
            # (e.g. a longer multi-word produced field); padding every row to it
            # appended empty cells, i.e. trailing spaces (2026-10-03 hmmscan repro).
            n = max(item.get("n", 0), contract.query_col + 1)
        cells = [""] * n
        for i, val in item.get("produced", {}).items():
            idx = int(i)
            while len(cells) <= idx:
                cells.append("")
            cells[idx] = val
        cells[contract.query_col] = rec.name
        for i in contract.desc_cols:
            while len(cells) <= i:
                cells.append("")
            cells[i] = rec.description or contract.empty_desc
        rows.append(cells)
    return rows


def reassemble_rows(rec: FastaRec, payload: dict, contract: TableContract) -> list[str]:
    layout = layout_from_contract(contract)
    use_raw = (not layout.pinned and not contract.pad_widths) or (
        contract.desc_span and not contract.desc_trailing
    )
    if not use_raw:
        cells = reassemble_cells(rec, payload, contract)
        if layout.pinned:
            return render_table(cells, layout, query_col=contract.query_col)
        return [join_row(row, contract.delim) for row in cells]
    lines: list[str] = []
    for item in payload.get("rows", []):
        raw = item.get("raw")
        if raw and use_raw:
            ln = raw
            old = item.get("name") or ""
            if old and old != rec.name:
                ln = _subst_token(ln, old, rec.name)
            ln = swap_desc_raw(
                ln, item.get("desc") or payload.get("desc") or "", rec.description, contract
            )
            lines.append(ln)
            continue
        n = max(item.get("n", 0), contract.n_cols, contract.query_col + 1)
        cells = [""] * n
        for i, val in item.get("produced", {}).items():
            idx = int(i)
            while len(cells) <= idx:
                cells.append("")
            cells[idx] = val
        cells[contract.query_col] = rec.name
        for i in contract.desc_cols:
            while len(cells) <= i:
                cells.append("")
            cells[i] = rec.description or contract.empty_desc
        lines.append(join_row(cells, contract.delim))
    return lines


def desc_view_rows(
    recs: list[FastaRec], groups_raw: dict[str, list[str]], contract: TableContract
) -> list[list[str]]:
    """Rows as inference saw them: an echoed description collapsed to one cell."""
    if not contract.desc_span:
        lines = [ln for r in recs for ln in groups_raw.get(r.name, [])]
        return split_body_rows(lines, contract.delim)
    markers = (contract.empty_desc or "-",) + tuple(
        m for m in MISSING_DESC if m and m != contract.empty_desc
    )
    norm = _normalize_desc_lines(recs, groups_raw, markers)
    return split_body_rows([ln for r in recs for ln in norm.get(r.name, [])], contract.delim)


def uses_cells_path(contract: TableContract) -> bool:
    """Cells/re-render path vs raw-line substitution path (shared by memo and guard)."""
    pinned = layout_from_contract(contract).pinned or bool(contract.pad_widths)
    return pinned and (not contract.desc_span or contract.desc_trailing)


def rows_by_name(rows: list[list[str]], query_col: int) -> dict[str, list[list[str]]]:
    return _group(rows, query_col)


def _infer_empty_marker(pert: list[FastaRec], gp: dict[str, list[str]]) -> str:
    """Empty-description marker, from perturbed records given an empty description."""
    seen: set[str] = set()
    for rec in pert:
        if rec.description:
            continue
        for ln in gp.get(rec.name, []):
            toks = ln.split()
            if toks and toks[-1] in MISSING_DESC:
                seen.add(toks[-1])
    return seen.pop() if len(seen) == 1 else ""


def _infer_empty_from_probe(probe: list[FastaRec], g1: dict[str, list[str]]) -> str:
    return _infer_empty_marker(probe, g1)


def _ws_norm(lines: list[str]) -> list[str]:
    return sorted(" ".join(ln.split()) for ln in lines)


def verify_roundtrip(
    probe: list[FastaRec],
    pert: list[FastaRec],
    g1_raw: dict[str, list[str]],
    g1_rows: dict[str, list[list[str]]],
    gp_raw: dict[str, list[str]],
    contract: TableContract,
) -> None:
    """Class-level guard: reassembling each probe record from its cached payload, with
    the PERTURBED name and description, must reproduce the tool's perturbed output.
    A field misclassified as produced (or copied) fails here, before any caching."""
    for rec, twin in zip(probe, pert):
        payload = extract_rows(
            g1_raw.get(rec.name, []), g1_rows.get(rec.name, []), contract, desc=rec.description
        )
        if not uses_cells_path(contract):
            got = reassemble_rows(twin, payload, contract)
        else:
            got = [join_row(c, contract.delim) for c in reassemble_cells(twin, payload, contract)]
        want = gp_raw.get(twin.name, [])
        if _ws_norm(got) != _ws_norm(want):
            raise InferError(
                "REFUSE_AMBIGUOUS",
                f"reassembly round-trip failed on probe record {rec.name!r}",
            )


def unclassified_cols(rows: list[list[str]], contract: TableContract) -> list[int]:
    extra: list[int] = []
    known = {contract.query_col, *contract.desc_cols, *contract.produced_cols}
    for row in rows:
        for i in range(len(row)):
            if i not in known and i not in extra:
                extra.append(i)
    return extra


def probe_late_cols(
    argv: list[str],
    carriers: list[FastaRec],
    contract: TableContract,
    work: Path,
    new_cols: list[int],
) -> None:
    if not carriers or not new_cols:
        return
    subset = carriers[:200]
    work.mkdir(parents=True, exist_ok=True)
    orig = write_fasta(work / "late_orig.fa", subset)
    out_o = run_table_tool(argv, orig)
    pert = perturb_fasta(subset)
    out_p = run_table_tool(argv, write_fasta(work / "late_pert.fa", pert))
    _, rows_o = _split_body(out_o, contract.delim)
    _, rows_p = _split_body(out_p, contract.delim)
    if contract.desc_span:
        go = _group_raw(body_lines(out_o), rows_o, contract.query_col)
        gp = _group_raw(body_lines(out_p), rows_p, contract.query_col)
        markers = (contract.empty_desc or "-",) + tuple(
            m for m in MISSING_DESC if m and m != contract.empty_desc
        )
        no = _normalize_desc_lines(subset, go, markers)
        np_ = _normalize_desc_lines(pert, gp, markers)
        raw_o = [ln for r in subset for ln in no.get(r.name, [])]
        raw_p = [ln for r in pert for ln in np_.get(r.name, [])]
        desc_cols, produced = classify_columns(
            [r.name for r in subset],
            [DESC_SENTINEL] * len(subset),
            split_body_rows(raw_o, contract.delim),
            [r.name for r in pert],
            [DESC_SENTINEL] * len(pert),
            split_body_rows(raw_p, contract.delim),
            contract.query_col,
            raw=raw_o,
            pert_raw=raw_p,
        )
    else:
        desc_cols, produced = classify_columns(
            [r.name for r in subset],
            [r.description for r in subset],
            rows_o,
            [r.name for r in pert],
            [r.description for r in pert],
            rows_p,
            contract.query_col,
            raw=body_lines(out_o),
            pert_raw=body_lines(out_p),
        )
    for i in new_cols:
        if i in desc_cols and i not in contract.desc_cols:
            contract.desc_cols.append(i)
        elif i in produced and i not in contract.produced_cols:
            contract.produced_cols.append(i)
        contract.n_cols = max(contract.n_cols, i + 1)
        tag = str(i)
        if tag not in contract.late_key_probes:
            contract.late_key_probes.append(tag)


def load_or_infer_table(
    argv: list[str],
    recs: list[FastaRec],
    work: Path,
    contract_path: Path,
    *,
    probe_n: int = PROBE_N,
    probe_seed: int = PROBE_SEED,
    subset_mode: str = "batched",
) -> TableContract:
    if contract_path.is_file():
        saved = TableContract.load(contract_path)
        if saved.argv == list(argv) and saved.kind == "fasta" and saved.decision == "OK":
            return saved
    contract = infer_table_contract(
        argv,
        recs,
        work,
        probe_n=probe_n,
        probe_seed=probe_seed,
        subset_mode=subset_mode,
    )
    contract.save(contract_path)
    return contract


def _infer_empty_desc(rows: list[list[str]], desc_cols: list[int]) -> str:
    for i in desc_cols:
        for row in rows:
            if i < len(row) and row[i] in MISSING_DESC:
                return row[i]
    return ""


def infer_layout_probe(
    argv: list[str],
    recs: list[FastaRec],
    query_col: int,
    delim: str,
    work: Path,
    probe_text: str,
    hit_names: set[str] | None = None,
    runner=None,
) -> TableLayout:
    """SHORT vs LONG vs mixed names, plus probe values. No tool names."""
    body = body_lines(probe_text)
    _, rows = _split_body(probe_text, delim)
    samples = [{"name": "probe", "lines": body, "rows": rows}]
    if delim == "tab" or not recs:
        return infer_table_layout(samples, query_col, delim)

    carriers = [r for r in recs if not hit_names or r.name in hit_names][:16]
    if not carriers:
        carriers = recs[: min(16, len(recs))]
    work.mkdir(parents=True, exist_ok=True)
    run = runner or run_table_tool
    short = [
        FastaRec(chr(65 + i) if i < 26 else f"S{i}", "", r.seq)
        for i, r in enumerate(carriers)
    ]
    long = [FastaRec(f"L{i:024d}", "", r.seq) for i, r in enumerate(carriers)]
    mixed: list[FastaRec] = []
    for i, r in enumerate(carriers):
        if i % 2 == 0:
            mixed.append(FastaRec(chr(65 + (i // 2) % 26) if i < 52 else f"M{i}", "", r.seq))
        else:
            mixed.append(FastaRec(f"L{i:024d}", "", r.seq))

    def _sample(tag: str, rec_list: list[FastaRec], path: Path) -> None:
        text = run(argv, write_fasta(path, rec_list))
        lines = body_lines(text)
        _, got = _split_body(text, delim)
        samples.append({"name": tag, "lines": lines, "rows": got})

    _sample("short", short, work / "short.fa")
    _sample("long", long, work / "long.fa")
    if len(carriers) >= 2:
        _sample("mixed", mixed, work / "mixed.fa")
    return infer_table_layout(samples, query_col, delim)


def infer_alignment(
    argv: list[str],
    recs: list[FastaRec],
    query_col: int,
    delim: str,
    work: Path,
    hit_names: set[str] | None = None,
    runner=None,
) -> tuple[list[int], bool]:
    """Compat wrapper: pad floors from the layout probe, else unpinned."""
    dummy = "\n".join(
        []
    )
    layout = infer_layout_probe(
        argv,
        recs,
        query_col,
        delim,
        work,
        dummy,
        hit_names=hit_names,
        runner=runner,
    )
    if layout.pinned and layout.delim != "tab":
        return layout_pad_widths(layout), False
    return [], not layout.pinned


def refuse_table(exc: InferError, argv: list[str]) -> TableContract:
    return TableContract(
        kind="fasta",
        argv=list(argv),
        query_col=0,
        desc_cols=[],
        produced_cols=[],
        delim="tab",
        match="order",
        n_cols=0,
        subset_mode="batched",
        tool_calls=getattr(exc, "tool_calls", 0),
        tool_call_sizes=list(getattr(exc, "tool_call_sizes", []) or []),
        decision=exc.decision,
        reason=exc.reason,
    )
