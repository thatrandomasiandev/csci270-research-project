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
    infer_table_layout,
    join_row,
    layout_pad_widths,
    meta_lines,
    render_table,
    split_body_rows,
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
        raw.setdefault("layout", {})
        raw.setdefault("traced_files", [])
        raw.setdefault("trace_status", "unavailable")
        raw.setdefault("probe_seed", PROBE_SEED)
        raw.setdefault("subset_mode", "batched")
        raw.setdefault("tool_calls", 0)
        raw.setdefault("tool_call_sizes", [])
        return cls(**raw)


def _max_cols(rows: list[list[str]]) -> int:
    return max((len(r) for r in rows), default=0)


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
        match = order_kind(names, rows1, query_col)
        empty_desc = _infer_empty_desc(rows1, desc_cols)
        hit_names = {row[query_col] for row in rows1}
        layout = infer_layout_probe(
            argv,
            probe,
            query_col,
            delim,
            work / "align",
            out1,
            hit_names=hit_names,
            runner=run,
        )
        match_ws = delim != "tab" and not layout.pinned
        return TableContract(
            kind="fasta",
            argv=list(argv),
            query_col=query_col,
            desc_cols=desc_cols,
            produced_cols=produced,
            delim=delim,
            match=match,
            n_cols=_max_cols(rows1),
            pad_widths=layout_pad_widths(layout),
            empty_desc=empty_desc,
            match_ws=match_ws,
            layout=layout.to_dict(),
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
    raw: list[str], rows: list[list[str]], contract: TableContract
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
            }
        )
    return {"rows": packed}


def layout_from_contract(contract: TableContract) -> TableLayout:
    return TableLayout.from_dict(contract.layout)


def reassemble_cells(
    rec: FastaRec, payload: dict, contract: TableContract
) -> list[list[str]]:
    rows: list[list[str]] = []
    for item in payload.get("rows", []):
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
        rows.append(cells)
    return rows


def reassemble_rows(rec: FastaRec, payload: dict, contract: TableContract) -> list[str]:
    layout = layout_from_contract(contract)
    use_raw = not layout.pinned and not contract.pad_widths
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
            for i in contract.desc_cols:
                old_desc = item.get("desc") or ""
                if old_desc and rec.description and old_desc != rec.description:
                    ln = _subst_token(ln, old_desc, rec.description)
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
