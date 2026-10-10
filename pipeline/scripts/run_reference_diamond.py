#!/usr/bin/env python3
"""DIAMOND blastp as the second reference-side tool.

The fitter is the shipped one. This file is the experiment driver: it
names the argv that the pre-registration locked, and it calls acts/.
It does not add a normalizer and it does not special-case a column.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import platform
import resource
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.fasta import copy_fasta_head, count_fasta_records, parse_fasta  # noqa: E402
from acts.inputs import (  # noqa: E402
    InputManifestError,
    InputSpec,
    ResolvedInput,
    check_manifest,
    check_requirement_pins,
)
from acts.predict import fit_ab  # noqa: E402
from acts.provenance import provenance  # noqa: E402
from acts.reference_cache import argv_namespace, connect_cache  # noqa: E402
from acts.reference_fit import (  # noqa: E402
    PROBE_N,
    PROBE_SEED,
    index_rows,
    load_rescale_provenance,
    parse_table_text,
    ref_merge_printed_rows,
    ref_merge_rows,
    sample_record_indices,
)
from acts.reference_formats import (  # noqa: E402
    length_weighted_churn,
    parse_reference,
    read_records,
    write_entries,
)
from acts.reference_run import (  # noqa: E402
    ReferenceIncremental,
    probe_fit,
    subprocess_invoke,
)

MIN_SCORE = "40"
THREADS = "32"
BLOCK = "2.0"
OUTFMT = (
    "qseqid sseqid pident length mismatch gapopen "
    "qstart qend sstart send evalue bitscore"
).split()
EVALUE_COL = OUTFMT.index("evalue")
N_FULL = 5117
QUERY_N_FIT = PROBE_N
PIN_FILE = ROOT / "requirements-diamond.txt"
SMOKE_DIR = "reference_diamond_smoke"
# Identities measured by CARC job 12863550 (md5sum on a01-04, 2026-10-09).
# 2026_03 matches the locked protocol row. The 2026_01 row is the extracted
# FASTA, not the tar. Recorded in the 2026-10-09 addendum.
EXPECTED = {
    "diamond": (28_553_136, "7de14b7f9f4c440ddfb5142ad96b1d8b"),
    "old": (93_457_057, "5245b19456d9a063b13c46602269bc5f"),
    "new": (93_801_562, "bc9d398533e6df582b563c6c03093bd0"),
    "queries": (1_074_926, "b170d133266427c46d87d99284e1fda3"),
    "iseq_main": (2477, "2c0762059f0229add06bf351edb2f979"),
}
_REPEAT_ORDER = (
    ("stock", "ACTS", "iSeqSearch"),
    ("ACTS", "iSeqSearch", "stock"),
    ("iSeqSearch", "stock", "ACTS"),
)


def timing_plan(smoke: bool) -> dict:
    """Real D3 is the locked plan. Smoke is one pass and is not a measurement."""
    if smoke:
        return {
            "smoke": True,
            "measurement": False,
            "threads": "4",
            "entries": 2000,
            "n_queries": 50,
            "fit": ((10, 1), (50, 1)),
            "repeats": 1,
            "formula": "(a + b*50) / (a + c*b*50)",
            "label": "not a measurement",
        }
    return {
        "smoke": False,
        "measurement": True,
        "threads": THREADS,
        "entries": None,
        "n_queries": N_FULL,
        "fit": ((QUERY_N_FIT, 3), (N_FULL, 3)),
        "repeats": 3,
        "formula": "(a + b*5117) / (a + c*b*5117)",
        "label": "D3",
    }


def repeat_order(repeats: int) -> tuple:
    if repeats == 3:
        return _REPEAT_ORDER
    if repeats == 1:
        return _REPEAT_ORDER[:1]
    raise ValueError(f"repeats must be 1 (smoke) or 3 (D3), not {repeats}")


def protocol_manifest(args: argparse.Namespace) -> list[InputSpec]:
    """Size and MD5 from the protocol addendum. Paths come from the caller."""
    iseq = "" if args.iseq is None else str(args.iseq)
    return [
        InputSpec("diamond", str(args.diamond), *EXPECTED["diamond"], executable=True),
        InputSpec("old", str(args.old), *EXPECTED["old"]),
        InputSpec("new", str(args.new), *EXPECTED["new"]),
        InputSpec("queries", str(args.queries), *EXPECTED["queries"]),
        InputSpec(
            "iseq",
            iseq,
            *EXPECTED["iseq_main"],
            kind="directory",
            member="source/main.py",
        ),
    ]


def check_output_dir(out: Path, smoke: bool) -> None:
    if not out.is_absolute():
        raise InputManifestError(f"output path is not absolute: {out}")
    if smoke and out.name != SMOKE_DIR:
        raise InputManifestError(
            "smoke refuses to write outside a directory named reference_diamond_smoke"
        )
    if not smoke and SMOKE_DIR in out.parts:
        raise InputManifestError("measurement refuses the smoke output directory")


PRIOR_STAGES = (
    ("D0", "reference_diamond_d0.json"),
    ("D1", "reference_diamond_d1.json"),
    ("D2", "reference_diamond_d2.json"),
    ("D2n", "reference_diamond_d2n.json"),
)


def filesystem_type(path: Path, mounts: str | None = None) -> str:
    """Filesystem type of the longest mount covering ``path``.

    Empty when ``/proc/mounts`` cannot be read. Callers treat only the
    explicit type ``tmpfs`` as the RAM disk.
    """
    if mounts is None:
        try:
            mounts = Path("/proc/mounts").read_text()
        except OSError:
            return ""
    try:
        target = str(path.resolve())
    except OSError:
        target = str(path)
    best = -1
    found = ""
    for line in mounts.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mount = parts[1].replace("\\040", " ")
        kind = parts[2]
        if target == mount or target.startswith(mount.rstrip("/") + "/"):
            if len(mount) > best:
                best = len(mount)
                found = kind
    return found


def require_durable_scratch(path: Path, *, allow_tmpfs: bool) -> str:
    """Refuse D3 when its scratch is a RAM disk.

    CARC compute-node ``/tmp`` is tmpfs. Files written there count against
    the job memory cgroup. ``allow_tmpfs`` is the explicit override.
    """
    kind = filesystem_type(path)
    if kind == "tmpfs" and not allow_tmpfs:
        raise SystemExit(
            f"STOP_SCRATCH: D3 scratch {path} is on tmpfs. "
            "That filesystem is RAM and counts against the job memory cgroup. "
            "Pass --allow-tmpfs-scratch to override."
        )
    return kind


def memory_snapshot() -> dict:
    """Host memory and this process's peak RSS, for the result JSON."""
    snap: dict = {
        "ru_maxrss_self": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "ru_maxrss_children": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "ru_maxrss_unit": "bytes" if sys.platform == "darwin" else "kilobytes",
    }
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        wanted = {"MemTotal:", "MemAvailable:"}
        for line in meminfo.read_text().splitlines():
            fields = line.split()
            if fields and fields[0] in wanted:
                snap[fields[0][:-1]] = int(fields[1])
                snap[fields[0][:-1] + "_unit"] = "kilobytes"
    return snap


def load_prior_stages(out: Path) -> dict[str, dict]:
    """Read committed D0–D2n. Does not write them."""
    loaded: dict[str, dict] = {}
    for stage, name in PRIOR_STAGES:
        path = out / name
        if not path.is_file():
            raise SystemExit(f"STOP_RESUME: {path} is missing; D3 was not started")
        try:
            payload = json.loads(path.read_text())
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SystemExit(f"STOP_RESUME: {path} is not readable JSON ({exc})") from None
        if payload.get("stage") != stage:
            raise SystemExit(
                f"STOP_RESUME: {path} stage is {payload.get('stage')!r}, expected {stage}"
            )
        loaded[stage] = payload
    return loaded


def index_out_file(
    path: Path,
    record_col: int,
    entry_col: int,
    index_col: int | None,
) -> dict[tuple[str, str, str], list[str]]:
    """Index an m8 one line at a time. The file text is not retained."""
    from acts.reference_fit import row_key

    indexed: dict[tuple[str, str, str], list[str]] = {}
    with path.open("rt") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip() or line.startswith("#"):
                continue
            cells = line.split()
            try:
                key = row_key(cells, record_col, entry_col, index_col)
            except IndexError as exc:
                raise ValueError(f"{path}:{line_no} has too few columns") from exc
            if key in indexed:
                raise ValueError(f"duplicate row key {key}")
            indexed[key] = cells
    return indexed


def _out_key_columns(fit: dict) -> tuple[int, int, int | None]:
    tables = fit.get("tables") or []
    if not tables:
        raise ValueError("no fitted table")
    table = tables[0]
    index = table.get("index_col")
    return (
        int(table["record_col"]),
        int(table["entry_col"]),
        None if index is None else int(index),
    )


def s1_argv(diamond: str, *, k: str, threads: str = THREADS) -> list[str]:
    """Locked S1 command. k is "0" for S1 and "25" for the negative control."""
    return [
        diamond,
        "blastp",
        "--db",
        "{reference}",
        "--query",
        "{input}",
        "--out",
        "{output}",
        "--min-score",
        MIN_SCORE,
        "-k",
        k,
        "--motif-masking",
        "0",
        "-b",
        BLOCK,
        "--comp-based-stats",
        "1",
        "--threads",
        threads,
        "--outfmt",
        "6",
        *OUTFMT,
    ]


def prep_command(diamond: str, threads: str = THREADS) -> str:
    return f"{diamond} makedb --in {{reference}} --db {{reference}} --threads {threads}"


def fitter_churn_c(report: dict) -> float:
    """Entry-count churn. Not the length-weighted fraction."""
    n_new = int(report["n_new"])
    if n_new <= 0:
        raise ValueError("new reference has no entries")
    return 1.0 - (int(report["n_unchanged_hash"]) / n_new)


def speedup(a: float, b: float, c: float, n: int = N_FULL) -> float | None:
    """Pre-registered speedup(c). None when the prediction is undefined."""
    if c <= 0 or b <= 0:
        return None
    denom = a + c * b * n
    if denom <= 0:
        return None
    return (a + b * n) / denom


def confirmed(stock_mean: float, acts_mean: float, predicted: float | None) -> bool:
    if predicted is None or predicted <= 0 or acts_mean <= 0:
        return False
    measured = stock_mean / acts_mean
    return abs(measured - predicted) <= 0.25 * predicted


def dbinfo_letters(text: str) -> int:
    for line in text.splitlines():
        if "Letters" not in line:
            continue
        token = line.split()[-1]
        if token.isdigit():
            return int(token)
    raise ValueError("dbinfo has no Letters count")


def residue_identity(raw: str) -> str:
    """Id token plus residue string. Descriptive only; not the reuse hash."""
    rec = parse_fasta(raw)[0]
    body = "".join(ch for ch in rec.seq if not ch.isspace())
    return rec.name + "\n" + body


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _base_provenance(
    diamond_version: str,
    *,
    versions: dict[str, str],
    resolved: dict[str, ResolvedInput],
    root: Path,
    plan: dict,
) -> dict:
    block = {}
    try:
        block.update(provenance(versions=versions))
    except Exception as exc:  # a copied tree may have no git repo
        block["provenance_error"] = str(exc)
        block["versions"] = dict(versions)
    env_hash = os.environ.get("ACTS_GIT_HASH", "").strip()
    hash_file = os.environ.get("ACTS_GIT_HASH_FILE", "").strip()
    if not env_hash and hash_file:
        try:
            env_hash = Path(hash_file).read_text().strip().splitlines()[0]
        except OSError:
            env_hash = ""
    if env_hash:
        block["git"] = env_hash
        block["git_dirty"] = False
    block["diamond_version"] = diamond_version
    block["host"] = block.get("host") or platform.node()
    block["python"] = block.get("python") or platform.python_version()
    block["release_pair"] = "2026_01 -> 2026_03"
    block["root"] = str(root)
    block["inputs"] = {name: item.as_dict() for name, item in sorted(resolved.items())}
    block["measurement"] = plan["measurement"]
    block["smoke"] = plan["smoke"]
    block["memory"] = memory_snapshot()
    if plan["smoke"]:
        block["smoke_label"] = plan["label"]
        block["smoke_plan"] = {
            "entries": plan["entries"],
            "queries": plan["n_queries"],
            "repeats": plan["repeats"],
            "threads": plan["threads"],
            "fit": [list(item) for item in plan["fit"]],
        }
    return block


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)


def _diamond_version(diamond: str) -> str:
    proc = _run([diamond, "version"])
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or "2.2.5" not in text:
        raise SystemExit(f"diamond version is not 2.2.5:\n{text}")
    return text.strip()


def _makedb(diamond: str, fasta: Path, threads: str) -> None:
    proc = _run(
        [diamond, "makedb", "--in", str(fasta), "--db", str(fasta), "--threads", threads]
    )
    if proc.returncode != 0:
        raise SystemExit(f"makedb failed for {fasta}:\n{(proc.stderr or proc.stdout)[-1000:]}")


def _letters(diamond: str, fasta: Path) -> int:
    proc = _run([diamond, "dbinfo", "--db", str(fasta)])
    if proc.returncode != 0:
        raise SystemExit(f"dbinfo failed for {fasta}:\n{(proc.stderr or proc.stdout)[-1000:]}")
    return dbinfo_letters(proc.stdout)


def _fasta_length_sum(path: Path) -> tuple[int, int]:
    entries = parse_reference(path)
    return len(entries), sum(entry.length for entry in entries)


def _time_blast(diamond: str, db: Path, query: Path, out: Path, *, k: str, threads: str) -> float:
    cmd = [
        diamond,
        "blastp",
        "--db",
        str(db),
        "--query",
        str(query),
        "--out",
        str(out),
        "--min-score",
        MIN_SCORE,
        "-k",
        k,
        "--motif-masking",
        "0",
        "-b",
        BLOCK,
        "--comp-based-stats",
        "1",
        "--threads",
        threads,
        "--outfmt",
        "6",
        *OUTFMT,
    ]
    started = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    elapsed = time.perf_counter() - started
    if proc.returncode != 0:
        raise SystemExit(f"blastp failed:\n{(proc.stderr or proc.stdout)[-1000:]}")
    return elapsed


def _write_sample(records_path: Path, dest: Path, n: int, *, expect: int) -> int:
    records = read_records(records_path)
    if len(records) != expect:
        raise SystemExit(
            f"STOP_INPUTS: query file has {len(records)} records, expected {expect}"
        )
    chosen = sample_record_indices(len(records), n, PROBE_SEED)
    picked = [records[i] for i in chosen]
    # write_entries is for reference entries. Queries go through the FASTA writer
    # the fitter uses, via a one-record-file helper already in reference_run.
    from acts.reference_run import write_record_file

    write_record_file(picked, dest)
    return len(picked)


def _assignment(fit: dict) -> list[dict]:
    rows = []
    for table in fit.get("tables") or []:
        for col in table.get("columns") or []:
            rows.append(
                {
                    "table": table.get("name"),
                    "index": col.get("index"),
                    "role": col.get("role"),
                    "member": col.get("member"),
                    "count_table": col.get("count_table"),
                }
            )
    return rows


def _expectation(fit: dict) -> dict:
    """True only for the pre-registered D2 assignment. Does not change the fit."""
    numeric = [
        col
        for table in fit.get("tables") or []
        for col in table.get("columns") or []
        if col.get("role") == "numeric"
    ]
    if not numeric:
        return {"matches": False, "why": "no numeric column was fitted"}
    evalue = [col for col in numeric if col.get("index") == EVALUE_COL]
    if len(evalue) != 1:
        return {"matches": False, "why": f"evalue column {EVALUE_COL} was not fitted once"}
    if evalue[0].get("member") != "total_entry_length":
        return {
            "matches": False,
            "why": f"evalue member is {evalue[0].get('member')}",
        }
    others = [col for col in numeric if col.get("index") != EVALUE_COL]
    bad = [col.get("index") for col in others if col.get("member") != "identity"]
    if bad:
        return {"matches": False, "why": f"non-evalue numeric columns {bad} are not identity"}
    return {"matches": True, "why": "evalue is total_entry_length; other numeric columns are identity"}


def _hit_pairs(text: str) -> dict[tuple[str, str], str]:
    """One evalue per (query, subject). A second row for a pair is a failure of max-hsps 1."""
    parsed = parse_table_text("out", text)
    out: dict[tuple[str, str], str] = {}
    for cells in parsed.rows:
        if len(cells) <= EVALUE_COL:
            continue
        key = (cells[0], cells[1])
        if key in out:
            raise ValueError(f"duplicate query-subject row {key}")
        out[key] = cells[EVALUE_COL]
    return out


def _published_bar(stock_text: str, other_text: str) -> dict:
    stock = _hit_pairs(stock_text)
    other = _hit_pairs(other_text)
    both = set(stock) & set(other)
    xs = []
    ys = []
    for key in both:
        try:
            xs.append(float(stock[key]))
            ys.append(float(other[key]))
        except ValueError:
            continue
    return {
        "n_stock": len(stock),
        "n_other": len(other),
        "n_intersection": len(both),
        "n_only_stock": len(set(stock) - set(other)),
        "n_only_other": len(set(other) - set(stock)),
        "evalue_pearson": pearson(xs, ys),
        "n_pearson": len(xs),
    }


def _column_reports(table: dict):
    from acts.reference_fit import ColumnReport

    return [
        ColumnReport(
            index=int(col["index"]),
            role=str(col["role"]),
            member=col.get("member"),
            count_table=col.get("count_table"),
        )
        for col in table.get("columns") or []
    ]


def _ref_merge_indexed(
    stock_rows: dict,
    our_rows: dict,
    fit: dict,
    provenance: dict | None = None,
    *,
    printed: bool = False,
) -> dict:
    tables = fit.get("tables") or []
    if not tables:
        return {"ok": False, "why": "no fitted table"}
    columns = _column_reports(tables[0])
    if printed:
        ok, why = ref_merge_printed_rows(stock_rows, our_rows, columns)
    elif provenance is None:
        return {"ok": False, "why": "rescale provenance is required"}
    else:
        ok, why = ref_merge_rows(stock_rows, our_rows, columns, provenance)
    return {"ok": ok, "why": why}


def _ref_merge_files(
    stock_text: str,
    ours_text: str,
    fit: dict,
    provenance: dict | None = None,
    *,
    printed: bool = False,
) -> dict:
    tables = fit.get("tables") or []
    if not tables:
        return {"ok": False, "why": "no fitted table"}
    table = tables[0]
    stock = parse_table_text("stock", stock_text)
    ours = parse_table_text("ours", ours_text)
    record_col = int(table["record_col"])
    entry_col = int(table["entry_col"])
    index_col = table.get("index_col")
    try:
        stock_rows = index_rows(stock.rows, record_col, entry_col, index_col)
        our_rows = index_rows(ours.rows, record_col, entry_col, index_col)
    except ValueError as exc:
        return {"ok": False, "why": str(exc)}
    return _ref_merge_indexed(
        stock_rows, our_rows, fit, provenance, printed=printed
    )


def _published_bar_indexed(
    stock_rows: dict[tuple[str, str, str], list[str]],
    other_rows: dict[tuple[str, str, str], list[str]],
) -> dict:
    """Pearson and hit counts from indexed rows. No second copy of the file text."""

    def pairs(indexed: dict[tuple[str, str, str], list[str]]) -> dict[tuple[str, str], str]:
        out: dict[tuple[str, str], str] = {}
        for (query, subject, _index), cells in indexed.items():
            key = (query, subject)
            if key in out:
                raise ValueError(f"duplicate query-subject row {key}")
            if len(cells) <= EVALUE_COL:
                continue
            out[key] = cells[EVALUE_COL]
        return out

    try:
        stock = pairs(stock_rows)
        other = pairs(other_rows)
    except ValueError as exc:
        return {"ok": False, "why": str(exc)}
    both = set(stock) & set(other)
    xs = []
    ys = []
    for key in both:
        try:
            xs.append(float(stock[key]))
            ys.append(float(other[key]))
        except ValueError:
            continue
    return {
        "n_stock": len(stock),
        "n_other": len(other),
        "n_intersection": len(both),
        "n_only_stock": len(set(stock) - set(other)),
        "n_only_other": len(set(other) - set(stock)),
        "evalue_pearson": pearson(xs, ys),
        "n_pearson": len(xs),
    }


def _gunzip_if_needed(path: Path, dest: Path) -> Path:
    if not path.name.endswith(".gz"):
        return path
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    with gzip.open(path, "rb") as src, dest.open("wb") as out:
        shutil.copyfileobj(src, out)
    return dest


def _open_text(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt")
    return path.open("rt")


def _count_records(path: Path) -> int:
    with _open_text(path) as handle:
        return count_fasta_records(handle)


def _head_fasta(src: Path, dest: Path, n: int) -> int:
    with _open_text(src) as handle:
        got = copy_fasta_head(handle, dest, n)
    if got != n:
        raise SystemExit(f"STOP_INPUTS: {src} has {got} FASTA records, smoke needs {n}")
    return got


def _gate(args: argparse.Namespace) -> tuple[dict[str, ResolvedInput], dict[str, str], dict]:
    """Resolve and check inputs. Returns before any DIAMOND invocation."""
    plan = timing_plan(bool(getattr(args, "smoke", False)))
    try:
        root = Path(args.root)
        resolved = check_manifest(protocol_manifest(args), root)
        check_output_dir(Path(args.out), plan["smoke"])
        work = Path(args.work)
        if not work.is_absolute():
            raise InputManifestError(f"work path is not absolute: {work}")
        if not plan["smoke"]:
            n_queries = _count_records(resolved["queries"].path)
            if n_queries != N_FULL:
                raise InputManifestError(
                    f"queries have {n_queries} records, protocol locks {N_FULL}"
                )
        versions = check_requirement_pins(PIN_FILE)
    except InputManifestError as exc:
        raise SystemExit(str(exc)) from None
    return resolved, versions, plan


def run(args: argparse.Namespace) -> int:
    resolved, versions, plan = _gate(args)
    work = Path(args.work)
    scratch_kind = ""
    if plan["measurement"]:
        work.mkdir(parents=True, exist_ok=True)
        scratch_kind = require_durable_scratch(
            work, allow_tmpfs=bool(getattr(args, "allow_tmpfs_scratch", False))
        )
        print(f"D3 scratch {work} fstype {scratch_kind}", flush=True)
    threads = plan["threads"]
    diamond = str(resolved["diamond"].path)
    version = _diamond_version(diamond)
    root = Path(args.root)
    base = _base_provenance(
        version, versions=versions, resolved=resolved, root=root, plan=plan
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    old_src = resolved["old"].path
    new_src = resolved["new"].path
    query_src = resolved["queries"].path
    iseq_repo = resolved["iseq"].path
    if plan["smoke"]:
        old_fa = work / "smoke_old.fasta"
        new_fa = work / "smoke_new.fasta"
        queries = work / "smoke_queries.fasta"
        _head_fasta(old_src, old_fa, int(plan["entries"]))
        _head_fasta(new_src, new_fa, int(plan["entries"]))
        _head_fasta(query_src, queries, int(plan["n_queries"]))
        base["smoke_truncated"] = {
            "old": str(old_fa),
            "new": str(new_fa),
            "queries": str(queries),
            "entries": plan["entries"],
            "n_queries": plan["n_queries"],
        }
    else:
        old_fa = _gunzip_if_needed(old_src, work / "sprot_2026_01.fasta")
        new_fa = _gunzip_if_needed(new_src, work / "sprot_2026_03.fasta")
        queries = query_src

    base["old_fasta"] = {
        "path": str(old_src),
        "bytes": resolved["old"].size,
        "md5": resolved["old"].md5,
        "release": "2026_01",
    }
    base["new_fasta"] = {
        "path": str(new_src),
        "bytes": resolved["new"].size,
        "md5": resolved["new"].md5,
        "release": "2026_03",
        "url": "https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.fasta.gz",
        "expected_md5": EXPECTED["new"][1],
        "expected_bytes": EXPECTED["new"][0],
    }
    base["scratch"] = {
        "path": str(work),
        "fstype": scratch_kind or filesystem_type(work),
    }
    if getattr(args, "resume_d3", False):
        if plan["smoke"]:
            raise SystemExit("STOP_RESUME: smoke cannot resume a measurement")
        return _resume_d3(
            diamond=diamond,
            threads=threads,
            plan=plan,
            work=work,
            out=out,
            queries=queries,
            new_fa=new_fa,
            old_fa=old_fa,
            base=base,
            iseq_repo=iseq_repo,
        )

    print("D0 makedb and letters", flush=True)
    _makedb(diamond, old_fa, threads)
    _makedb(diamond, new_fa, threads)
    old_letters = _letters(diamond, old_fa)
    new_letters = _letters(diamond, new_fa)
    old_n, old_sum = _fasta_length_sum(old_fa)
    new_n, new_sum = _fasta_length_sum(new_fa)
    d0 = {
        **base,
        "stage": "D0",
        "setting": "S1",
        "old": {"dbinfo_letters": old_letters, "n_entries": old_n, "fasta_length_sum": old_sum},
        "new": {"dbinfo_letters": new_letters, "n_entries": new_n, "fasta_length_sum": new_sum},
        "old_equal": old_letters == old_sum,
        "new_equal": new_letters == new_sum,
    }
    if old_letters > 2_000_000_000 or new_letters > 2_000_000_000:
        d0["stop"] = "dbinfo letters exceed the pinned block of 2e9"
        _write(out / "reference_diamond_d0.json", d0)
        raise SystemExit(d0["stop"])
    _write(out / "reference_diamond_d0.json", d0)
    print(json.dumps({"old_equal": d0["old_equal"], "new_equal": d0["new_equal"]}), flush=True)

    print("D1 churn", flush=True)
    old_entries = parse_reference(old_fa)
    new_entries = parse_reference(new_fa)
    churn = length_weighted_churn(old_entries, new_entries)
    old_hashes = {entry.content_hash for entry in old_entries}
    new_hashes = {entry.content_hash for entry in new_entries}
    n_removed = sum(1 for entry in old_entries if entry.content_hash not in new_hashes)
    n_added = sum(1 for entry in new_entries if entry.content_hash not in old_hashes)
    old_res = {residue_identity(entry.raw) for entry in old_entries}
    n_res = sum(1 for entry in new_entries if residue_identity(entry.raw) in old_res)
    c = fitter_churn_c(churn)
    fresh = [entry for entry in new_entries if entry.content_hash not in old_hashes]
    delta_fa = work / "delta_2026_03.fasta"
    if fresh:
        write_entries(fresh, delta_fa)
    else:
        delta_fa.write_text("")
    d1 = {
        **base,
        "stage": "D1",
        "setting": "S1",
        "c": c,
        "c_is": "1 - n_unchanged_hash / n_new, fitter content hash",
        "c_length_descriptive": churn["c_length"],
        "n_removed": n_removed,
        "n_added_or_changed": n_added,
        "residue_id_unchanged": n_res,
        "residue_id_unchanged_fraction": n_res / churn["n_new"],
        "library": churn,
    }
    _write(out / "reference_diamond_d1.json", d1)
    del old_entries, old_res
    print(json.dumps({"c": c, "c_length": churn["c_length"], "n_new": churn["n_new"]}), flush=True)

    argv = s1_argv(diamond, k="0", threads=threads)
    prep = prep_command(diamond, threads)
    print("D2 probe", flush=True)
    records = read_records(queries)
    invoke = subprocess_invoke(
        argv,
        input_slot=queries,
        reference_slot=new_fa,
        prep=prep,
        scratch=work / "d2",
    )
    fit = probe_fit(new_entries, records, invoke)
    fit_dict = fit.as_dict()
    d2 = {
        **base,
        "stage": "D2",
        "setting": "S1",
        "decision": fit.decision,
        "reason": fit.reason,
        "fit": fit_dict,
        "assignment": _assignment(fit_dict),
        "expectation": _expectation(fit_dict),
        "d0_letters_equal": d0["new_equal"],
    }
    _write(out / "reference_diamond_d2.json", d2)
    cache_path = work / "reference.sqlite"
    if fit.decision == "SHIP":
        cache = connect_cache(cache_path)
        try:
            cache.save_contract(argv_namespace(argv, new_fa, None), fit_dict)
        finally:
            cache.close()
    print(fit.decision, fit.reason, flush=True)

    print("D2n probe", flush=True)
    argv_k = s1_argv(diamond, k="25", threads=threads)
    invoke_k = subprocess_invoke(
        argv_k,
        input_slot=queries,
        reference_slot=new_fa,
        prep=prep,
        scratch=work / "d2n",
    )
    fit_k = probe_fit(new_entries, records, invoke_k)
    d2n = {
        **base,
        "stage": "D2n",
        "setting": "S1 with -k 25",
        "decision": fit_k.decision,
        "reason": fit_k.reason,
        "fit": fit_k.as_dict(),
        "must_refuse": True,
        "refused": fit_k.decision == "REFUSE",
    }
    _write(out / "reference_diamond_d2n.json", d2n)
    if fit_k.decision != "REFUSE":
        d2["expectation"] = {
            "matches": False,
            "why": "D2n shipped, so D2 carries no weight",
        }
        d2["d2n_shipped"] = True
        _write(out / "reference_diamond_d2.json", d2)
    print("D2n", fit_k.decision, flush=True)
    del new_entries, records

    has_fresh = bool(fresh)
    del fresh
    return _execute_d3(
        diamond=diamond,
        threads=threads,
        plan=plan,
        work=work,
        out=out,
        queries=queries,
        new_fa=new_fa,
        old_fa=old_fa,
        argv=argv,
        prep=prep,
        c=c,
        fit_decision=fit.decision,
        fit_dict=fit_dict,
        fit_k_decision=fit_k.decision,
        d0_old_equal=bool(d0["old_equal"]),
        d0_new_equal=bool(d0["new_equal"]),
        base=base,
        cache_path=cache_path,
        has_fresh=has_fresh,
        delta_fa=delta_fa,
        old_letters=old_letters,
        iseq_repo=iseq_repo,
        resumed_from=None,
    )


def _measured_then_unlink(path: Path) -> int:
    """Byte size of a scratch file, then delete it. Zero when it is absent."""
    if not path.is_file():
        return 0
    size = path.stat().st_size
    path.unlink()
    return size


def _execute_d3(
    *,
    diamond: str,
    threads: str,
    plan: dict,
    work: Path,
    out: Path,
    queries: Path,
    new_fa: Path,
    old_fa: Path,
    argv: list[str],
    prep: str,
    c: float,
    fit_decision: str,
    fit_dict: dict,
    fit_k_decision: str,
    d0_old_equal: bool,
    d0_new_equal: bool,
    base: dict,
    cache_path: Path,
    has_fresh: bool,
    delta_fa: Path,
    old_letters: int,
    iseq_repo: Path,
    resumed_from: dict | None,
) -> int:
    """Clocked D3. Indexes m8 files one at a time and does not keep their text."""
    print("D3 timing", flush=True)
    # Discarded cold start, then the fit runs. Not the alternating means.
    # The real plan is three walls at 300 and three at 5117. Smoke is one
    # wall at 10 and one at 50, labelled not a measurement.
    cold_path = work / "cold.m8"
    cold = _time_blast(diamond, new_fa, queries, cold_path, k="0", threads=threads)
    cold_bytes = _measured_then_unlink(cold_path)
    fit_walls = []
    for n_fit, times in plan["fit"]:
        # The full query set is the file already validated. A subset is a
        # sample. Rewriting the full file would change line wrapping.
        if int(n_fit) == int(plan["n_queries"]):
            sample_fa = queries
        else:
            sample_fa = work / f"queries_{n_fit}.fasta"
            _write_sample(queries, sample_fa, int(n_fit), expect=int(plan["n_queries"]))
        for i in range(int(times)):
            dest = work / f"fit{n_fit}_{i}.m8"
            wall = _time_blast(diamond, new_fa, sample_fa, dest, k="0", threads=threads)
            fit_walls.append(
                {
                    "n": int(n_fit),
                    "wall_s": wall,
                    "output_bytes": _measured_then_unlink(dest),
                }
            )
    a, b = fit_ab([row["n"] for row in fit_walls], [row["wall_s"] for row in fit_walls])
    predicted = speedup(a, b, c, int(plan["n_queries"]))

    warm = None
    cache_snapshot = work / "cache_after_warm.sqlite"
    if fit_decision == "SHIP":
        started = time.perf_counter()
        warm_rec = ReferenceIncremental(
            argv=argv,
            input_path=queries,
            out_dir=work / "warm_old",
            reference=old_fa,
            prep=prep,
            cache_path=cache_path,
            verify="audit",
            audit_p=0.0,
        ).run()
        warm = {
            "decision": warm_rec.decision,
            "reason": warm_rec.reason,
            "wall_s": time.perf_counter() - started,
            "extra": warm_rec.extra,
        }
        if warm_rec.decision != "SHIP":
            warm["note"] = "old-release load did not ship; the timed ACTS arm still runs"
        if cache_path.is_file():
            _checkpoint_cache(cache_path, cache_snapshot)

    expected_ns = [n for n, times in plan["fit"] for _ in range(times)]
    assert [row["n"] for row in fit_walls] == expected_ns

    order = repeat_order(int(plan["repeats"]))
    arms: list[dict] = []
    iseq_error = None
    if has_fresh:
        _makedb(diamond, delta_fa, threads)
        try:
            delta_letters = _letters(diamond, delta_fa)
        except SystemExit as exc:
            delta_letters = None
            iseq_error = str(exc)
    else:
        delta_letters = 0

    def stock_arm(tag: str) -> dict:
        dest = work / f"{tag}.m8"
        wall = _time_blast(diamond, new_fa, queries, dest, k="0", threads=threads)
        return {
            "arm": "stock",
            "tag": tag,
            "wall_s": wall,
            "bytes": dest.stat().st_size if dest.is_file() else 0,
            "output": str(dest) if dest.is_file() else "",
        }

    def acts_arm(tag: str) -> dict:
        if cache_snapshot.is_file():
            _restore_cache(cache_snapshot, cache_path)
        started = time.perf_counter()
        rec = ReferenceIncremental(
            argv=argv,
            input_path=queries,
            out_dir=work / tag,
            reference=new_fa,
            prep=prep,
            cache_path=cache_path,
            verify="audit",
            audit_p=0.0,
        ).run()
        wall = time.perf_counter() - started
        table = work / tag / "tables" / "out"
        return {
            "arm": "ACTS",
            "tag": tag,
            "wall_s": wall,
            "decision": rec.decision,
            "reason": rec.reason,
            "extra": rec.extra,
            "output": str(table) if table.is_file() else "",
            "bytes": table.stat().st_size if table.is_file() else 0,
        }

    def iseq_arm(tag: str) -> dict:
        nonlocal iseq_error
        if iseq_error and delta_letters is None:
            return {"arm": "iSeqSearch", "tag": tag, "ran": False, "why": iseq_error}
        started = time.perf_counter()
        delta_out = work / f"{tag}_delta.m8"
        if has_fresh and delta_letters:
            _time_blast(diamond, delta_fa, queries, delta_out, k="0", threads=threads)
        else:
            delta_out.write_text("")
        search_s = time.perf_counter() - started
        merged = work / f"{tag}_merged.m8"
        old_m8 = _raw_call_output(work / "warm_old" / "calls")
        merge_started = time.perf_counter()
        if old_m8 is None:
            why = "warm diamond output is absent, so the published merger was not run"
        else:
            why = _iseq_merge(
                iseq_repo,
                old_m8,
                delta_out,
                merged,
                old_letters,
                int(delta_letters or 0),
            )
        merge_s = time.perf_counter() - merge_started
        _measured_then_unlink(delta_out)
        if why:
            iseq_error = why
            return {
                "arm": "iSeqSearch",
                "tag": tag,
                "ran": False,
                "why": why,
                "search_s": search_s,
                "wall_s": search_s + merge_s,
            }
        return {
            "arm": "iSeqSearch",
            "tag": tag,
            "ran": True,
            "wall_s": search_s + merge_s,
            "search_s": search_s,
            "merge_s": merge_s,
            "commit": "7e862bf3afa52b65b3cca4255de66ab4cb764fe3",
            "output": str(merged) if merged.is_file() else "",
            "bytes": merged.stat().st_size if merged.is_file() else 0,
        }

    # Each ACTS repeat restores the post-warm cache, so a later repeat does not
    # reuse rows the previous repeat just stored for the new release.
    # iSeqSearch reads the raw diamond file from that warm call, not the
    # rendered table.
    for repeat, triple in enumerate(order, start=1):
        for name in triple:
            tag = f"r{repeat}_{name}"
            if name == "stock":
                arms.append({"repeat": repeat, **stock_arm(tag)})
            elif name == "ACTS":
                arms.append({"repeat": repeat, **acts_arm(tag)})
            else:
                arms.append({"repeat": repeat, **iseq_arm(tag)})
            print(arms[-1].get("arm"), arms[-1].get("wall_s"), flush=True)

    stock_walls = [row["wall_s"] for row in arms if row["arm"] == "stock"]
    acts_walls = [row["wall_s"] for row in arms if row["arm"] == "ACTS"]
    iseq_walls = [row["wall_s"] for row in arms if row["arm"] == "iSeqSearch" and row.get("ran")]
    stock_mean = sum(stock_walls) / len(stock_walls) if stock_walls else 0.0
    acts_mean = sum(acts_walls) / len(acts_walls) if acts_walls else 0.0
    measured = (stock_mean / acts_mean) if acts_mean else None
    matches = []
    iseq_bars = []
    stock_index = None
    stock_error = ""
    stock_arms = [row for row in arms if row["arm"] == "stock" and row.get("output")]
    if stock_arms:
        try:
            stock_index = index_out_file(Path(stock_arms[0]["output"]), *_out_key_columns(fit_dict))
        except (OSError, ValueError) as exc:
            stock_error = str(exc)
    else:
        stock_error = "missing output"
    for i, row in enumerate(arm for arm in arms if arm["arm"] == "ACTS"):
        output = row.get("output") or ""
        if stock_index is None or not output or not Path(output).is_file():
            matches.append({"i": i, "ok": False, "why": stock_error or "missing output"})
            continue
        prov_path = work / row["tag"] / "tables" / "out.provenance.json"
        if not prov_path.is_file():
            matches.append({"i": i, "ok": False, "why": "rescale provenance sidecar is missing"})
            continue
        try:
            rescale = load_rescale_provenance(json.loads(prov_path.read_text()))
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            matches.append({"i": i, "ok": False, "why": f"rescale provenance: {exc}"})
            continue
        try:
            ours = index_out_file(Path(output), *_out_key_columns(fit_dict))
        except (OSError, ValueError) as exc:
            matches.append({"i": i, "ok": False, "why": str(exc)})
            continue
        merged = _ref_merge_indexed(stock_index, ours, fit_dict, rescale)
        merged["i"] = i
        matches.append(merged)
        del ours
        _measured_then_unlink(Path(output))
    for i, row in enumerate(arm for arm in arms if arm["arm"] == "iSeqSearch" and row.get("output")):
        output = row.get("output") or ""
        if stock_index is None or not output or not Path(output).is_file():
            continue
        try:
            other = index_out_file(Path(output), *_out_key_columns(fit_dict))
        except (OSError, ValueError) as exc:
            iseq_bars.append({"i": i, "ok": False, "why": str(exc)})
            continue
        try:
            bar = _published_bar_indexed(stock_index, other)
        except ValueError as exc:
            bar = {"ok": False, "why": str(exc)}
        bar["ref_merge"] = _ref_merge_indexed(stock_index, other, fit_dict, printed=True)
        bar["i"] = i
        iseq_bars.append(bar)
        del other
        _measured_then_unlink(Path(output))
    for row in stock_arms:
        _measured_then_unlink(Path(row["output"]))
    del stock_index
    d3 = {
        **base,
        "stage": "D3",
        "setting": "S1",
        "discarded_cold_start_s": cold,
        "discarded_cold_start_bytes": cold_bytes,
        "fit_walls": fit_walls,
        "a": a,
        "b": b,
        "c": c,
        "n": int(plan["n_queries"]),
        "predicted_speedup": predicted,
        "formula": plan["formula"],
        "assumptions": (
            [
                "smoke truncates both releases to 2000 entries and the queries to 50",
                "one fit wall at n=10 and one at n=50; one alternating repeat",
                "these walls are not a D3 measurement",
            ]
            if plan["smoke"]
            else [
                "a does not shrink on the smaller reference",
                "per-record cost scales with D1 entry-count c, not c_length",
                "merge and rescale stay inside the ACTS wall",
                "the probe and the six fit runs are outside the alternating means",
            ]
        ),
        "warm": warm,
        "arms": arms,
        "stock_mean_s": stock_mean,
        "acts_mean_s": acts_mean,
        "iseq_mean_s": (sum(iseq_walls) / len(iseq_walls)) if iseq_walls else None,
        "measured_speedup": measured,
        "confirmed": None if plan["smoke"] else confirmed(stock_mean, acts_mean, predicted),
        "confirmed_note": (
            "smoke is not a measurement; the D3 predicate is not applied"
            if plan["smoke"]
            else None
        ),
        "ref_merge_acts": matches,
        "iseq": {
            "ran": bool(iseq_walls),
            "why": iseq_error,
            "bars": iseq_bars,
            "commit": "7e862bf3afa52b65b3cca4255de66ab4cb764fe3",
        },
        "d2_decision": fit_decision,
        "d2n_decision": fit_k_decision,
        "d0_letters_equal": {"old": d0_old_equal, "new": d0_new_equal},
        "memory": memory_snapshot(),
    }
    if resumed_from is not None:
        d3["resumed_from"] = resumed_from
    _write(out / "reference_diamond_d3.json", d3)
    print(json.dumps({"confirmed": d3["confirmed"], "predicted": predicted, "measured": measured}), flush=True)
    return 0


def _resume_d3(
    *,
    diamond: str,
    threads: str,
    plan: dict,
    work: Path,
    out: Path,
    queries: Path,
    new_fa: Path,
    old_fa: Path,
    base: dict,
    iseq_repo: Path,
) -> int:
    """Run D3 from committed D0–D2n. Does not rewrite those files."""
    prior = load_prior_stages(out)
    d0 = prior["D0"]
    d1 = prior["D1"]
    d2 = prior["D2"]
    d2n = prior["D2n"]
    print("D3 resume from committed D0-D2n", flush=True)
    _makedb(diamond, old_fa, threads)
    _makedb(diamond, new_fa, threads)
    old_letters = _letters(diamond, old_fa)
    new_letters = _letters(diamond, new_fa)
    if old_letters != int(d0["old"]["dbinfo_letters"]) or new_letters != int(
        d0["new"]["dbinfo_letters"]
    ):
        raise SystemExit(
            "STOP_RESUME: dbinfo letters "
            f"({old_letters}, {new_letters}) do not match committed D0 "
            f"({d0['old']['dbinfo_letters']}, {d0['new']['dbinfo_letters']})"
        )
    old_entries = parse_reference(old_fa)
    new_entries = parse_reference(new_fa)
    churn = length_weighted_churn(old_entries, new_entries)
    library = d1["library"]
    for key in ("n_new", "n_old", "n_unchanged_hash", "n_changed_and_new"):
        if int(churn[key]) != int(library[key]):
            raise SystemExit(
                f"STOP_RESUME: recomputed {key}={churn[key]} "
                f"does not match committed D1 {library[key]}"
            )
    c = fitter_churn_c(churn)
    if c != float(d1["c"]):
        raise SystemExit(f"STOP_RESUME: recomputed c {c} does not match committed D1 {d1['c']}")
    new_hashes = {entry.content_hash for entry in new_entries}
    old_hashes = {entry.content_hash for entry in old_entries}
    fresh = [entry for entry in new_entries if entry.content_hash not in old_hashes]
    removed = sum(1 for entry in old_entries if entry.content_hash not in new_hashes)
    if len(fresh) != int(d1["n_added_or_changed"]) or removed != int(d1["n_removed"]):
        raise SystemExit("STOP_RESUME: recomputed churn counts do not match committed D1")
    delta_fa = work / "delta_2026_03.fasta"
    if fresh:
        write_entries(fresh, delta_fa)
    else:
        delta_fa.write_text("")
    has_fresh = bool(fresh)
    del fresh, old_entries, new_entries, old_hashes, new_hashes
    argv = s1_argv(diamond, k="0", threads=threads)
    prep = prep_command(diamond, threads)
    fit_dict = d2["fit"]
    cache_path = work / "reference.sqlite"
    if d2.get("decision") == "SHIP":
        cache = connect_cache(cache_path)
        try:
            cache.save_contract(argv_namespace(argv, new_fa, None), fit_dict)
        finally:
            cache.close()
    return _execute_d3(
        diamond=diamond,
        threads=threads,
        plan=plan,
        work=work,
        out=out,
        queries=queries,
        new_fa=new_fa,
        old_fa=old_fa,
        argv=argv,
        prep=prep,
        c=float(d1["c"]),
        fit_decision=str(d2.get("decision")),
        fit_dict=fit_dict,
        fit_k_decision=str(d2n.get("decision")),
        d0_old_equal=bool(d0.get("old_equal")),
        d0_new_equal=bool(d0.get("new_equal")),
        base=base,
        cache_path=cache_path,
        has_fresh=has_fresh,
        delta_fa=delta_fa,
        old_letters=old_letters,
        iseq_repo=iseq_repo,
        resumed_from={
            "git": d0.get("git"),
            "host": d0.get("host"),
            "files": [name for _stage, name in PRIOR_STAGES],
            "c": float(d1["c"]),
            "d2_decision": d2.get("decision"),
            "d2n_decision": d2n.get("decision"),
            "note": (
                "D0-D2n were not re-run. c, the fitted assignment, and the "
                "letter counts are the committed files. This process repeats "
                "the untimed warm load, the discarded cold start, the six fit "
                "runs, and the alternating block."
            ),
        },
    )

def _checkpoint_cache(path: Path, snapshot: Path) -> None:
    """Copy a closed cache after folding the WAL back into the main file."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    shutil.copy(path, snapshot)


def _restore_cache(snapshot: Path, path: Path) -> None:
    shutil.copy(snapshot, path)
    for suffix in ("-wal", "-shm"):
        side = Path(str(path) + suffix)
        if side.exists():
            side.unlink()


def _raw_call_output(call_root: Path) -> Path | None:
    found = sorted(call_root.glob("call*/out"))
    if not found:
        return None
    return max(found, key=lambda item: item.stat().st_size)


def _iseq_merge(
    repo: Path | None,
    old_m8: Path,
    delta_m8: Path,
    dest: Path,
    old_letters: int,
    delta_letters: int,
) -> str | None:
    """Run the pinned merger. Return an error string, or None on success."""
    if repo is None or not (repo / "source" / "main.py").is_file():
        return "iSeqSearch checkout is absent"
    if not old_m8.is_file():
        return f"warm m8 is absent: {old_m8}"
    cmd = [
        sys.executable,
        str(repo / "source" / "main.py"),
        "--default",
        str(old_m8),
        str(delta_m8),
        str(dest),
        str(old_letters),
        str(delta_letters),
    ]
    proc = subprocess.run(cmd, cwd=repo / "source", check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-1000:]
        return f"merger exit {proc.returncode}: {err}"
    if not dest.is_file():
        return "merger wrote no output"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--diamond", type=Path, required=True)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--iseq", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument(
        "--resume-d3",
        action="store_true",
        help="Run D3 from committed D0-D2n JSON in --out. Does not rewrite those files.",
    )
    parser.add_argument(
        "--allow-tmpfs-scratch",
        action="store_true",
        help="Permit a measurement to start D3 with scratch on tmpfs.",
    )
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
