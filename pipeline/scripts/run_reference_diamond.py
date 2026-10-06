#!/usr/bin/env python3
"""DIAMOND blastp as the second reference-side tool.

The fitter is the shipped one. This file is the experiment driver: it
names the argv that the pre-registration locked, and it calls acts/.
It does not add a normalizer and it does not special-case a column.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.fasta import parse_fasta  # noqa: E402
from acts.predict import fit_ab  # noqa: E402
from acts.provenance import provenance  # noqa: E402
from acts.reference_cache import argv_namespace, connect_cache  # noqa: E402
from acts.reference_fit import (  # noqa: E402
    PROBE_N,
    PROBE_SEED,
    index_rows,
    parse_table_text,
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


def s1_argv(diamond: str, *, k: str) -> list[str]:
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
        THREADS,
        "--outfmt",
        "6",
        *OUTFMT,
    ]


def prep_command(diamond: str) -> str:
    return f"{diamond} makedb --in {{reference}} --db {{reference}} --threads {THREADS}"


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


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _base_provenance(diamond_version: str) -> dict:
    block = {}
    try:
        block.update(provenance())
    except Exception as exc:  # a copied tree may have no git repo
        block["provenance_error"] = str(exc)
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
    return block


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)


def _diamond_version(diamond: str) -> str:
    proc = _run([diamond, "version"])
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or "2.2.5" not in text:
        raise SystemExit(f"diamond version is not 2.2.5:\n{text}")
    return text.strip()


def _makedb(diamond: str, fasta: Path) -> None:
    proc = _run(
        [diamond, "makedb", "--in", str(fasta), "--db", str(fasta), "--threads", THREADS]
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


def _time_blast(diamond: str, db: Path, query: Path, out: Path, *, k: str) -> float:
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
        THREADS,
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


def _write_sample(records_path: Path, dest: Path, n: int) -> int:
    records = read_records(records_path)
    if len(records) != N_FULL:
        raise SystemExit(f"query file has {len(records)} records, protocol locks {N_FULL}")
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


def _ref_merge_files(stock_text: str, ours_text: str, fit: dict) -> dict:
    tables = fit.get("tables") or []
    if not tables:
        return {"ok": False, "why": "no fitted table"}
    table = tables[0]
    stock = parse_table_text("stock", stock_text)
    ours = parse_table_text("ours", ours_text)
    try:
        stock_rows = index_rows(
            stock.rows, int(table["record_col"]), int(table["entry_col"]), table.get("index_col")
        )
        our_rows = index_rows(
            ours.rows, int(table["record_col"]), int(table["entry_col"]), table.get("index_col")
        )
    except ValueError as exc:
        return {"ok": False, "why": str(exc)}
    from acts.reference_fit import ColumnReport

    columns = [
        ColumnReport(
            index=int(col["index"]),
            role=str(col["role"]),
            member=col.get("member"),
            count_table=col.get("count_table"),
        )
        for col in table.get("columns") or []
    ]
    ok, why = ref_merge_rows(stock_rows, our_rows, columns)
    return {"ok": ok, "why": why}


def _gunzip_if_needed(path: Path, dest: Path) -> Path:
    if not path.name.endswith(".gz"):
        return path
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    with gzip.open(path, "rb") as src, dest.open("wb") as out:
        shutil.copyfileobj(src, out)
    return dest


def run(args: argparse.Namespace) -> int:
    diamond = str(args.diamond)
    version = _diamond_version(diamond)
    base = _base_provenance(version)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    work = args.work
    work.mkdir(parents=True, exist_ok=True)
    old_fa = _gunzip_if_needed(args.old, work / "sprot_2026_01.fasta")
    new_fa = _gunzip_if_needed(args.new, work / "sprot_2026_03.fasta")
    queries = args.queries

    old_md5 = file_md5(args.old)
    new_md5 = file_md5(args.new)
    base["old_fasta"] = {
        "path": str(args.old),
        "bytes": args.old.stat().st_size,
        "md5": old_md5,
        "release": "2026_01",
    }
    base["new_fasta"] = {
        "path": str(args.new),
        "bytes": args.new.stat().st_size,
        "md5": new_md5,
        "release": "2026_03",
        "url": "https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.fasta.gz",
        "expected_md5": "bc9d398533e6df582b563c6c03093bd0",
        "expected_bytes": 93801562,
    }
    if new_md5 != "bc9d398533e6df582b563c6c03093bd0":
        raise SystemExit(f"2026_03 FASTA md5 is {new_md5}, not the metalink value")
    if args.new.stat().st_size != 93801562 and args.new.name.endswith(".gz"):
        raise SystemExit(f"2026_03 FASTA size is {args.new.stat().st_size}")

    print("D0 makedb and letters", flush=True)
    _makedb(diamond, old_fa)
    _makedb(diamond, new_fa)
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

    argv = s1_argv(diamond, k="0")
    prep = prep_command(diamond)
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
    argv_k = s1_argv(diamond, k="25")
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

    print("D3 timing", flush=True)
    sample_fa = work / "queries_300.fasta"
    _write_sample(queries, sample_fa, QUERY_N_FIT)
    # Discarded cold start, then the six fit runs. Not the alternating means.
    cold = _time_blast(diamond, new_fa, queries, work / "cold.m8", k="0")
    fit_walls = []
    for i in range(3):
        fit_walls.append(
            {
                "n": QUERY_N_FIT,
                "wall_s": _time_blast(diamond, new_fa, sample_fa, work / f"fit300_{i}.m8", k="0"),
            }
        )
    for i in range(3):
        fit_walls.append(
            {
                "n": N_FULL,
                "wall_s": _time_blast(diamond, new_fa, queries, work / f"fit5117_{i}.m8", k="0"),
            }
        )
    a, b = fit_ab([row["n"] for row in fit_walls], [row["wall_s"] for row in fit_walls])
    predicted = speedup(a, b, c, N_FULL)

    warm = None
    cache_snapshot = work / "cache_after_warm.sqlite"
    if fit.decision == "SHIP":
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

    ns = [QUERY_N_FIT, QUERY_N_FIT, QUERY_N_FIT, N_FULL, N_FULL, N_FULL]
    assert [row["n"] for row in fit_walls] == ns

    order = [
        ("stock", "ACTS", "iSeqSearch"),
        ("ACTS", "iSeqSearch", "stock"),
        ("iSeqSearch", "stock", "ACTS"),
    ]
    arms: list[dict] = []
    stock_texts: list[str] = []
    acts_texts: list[str] = []
    iseq_texts: list[str] = []
    iseq_error = None
    if fresh:
        _makedb(diamond, delta_fa)
        try:
            delta_letters = _letters(diamond, delta_fa)
        except SystemExit as exc:
            delta_letters = None
            iseq_error = str(exc)
    else:
        delta_letters = 0

    def stock_arm(tag: str) -> dict:
        dest = work / f"{tag}.m8"
        wall = _time_blast(diamond, new_fa, queries, dest, k="0")
        text = dest.read_text()
        stock_texts.append(text)
        return {"arm": "stock", "wall_s": wall, "bytes": dest.stat().st_size}

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
        text = table.read_text() if table.is_file() else ""
        acts_texts.append(text)
        return {
            "arm": "ACTS",
            "wall_s": wall,
            "decision": rec.decision,
            "reason": rec.reason,
            "extra": rec.extra,
        }

    def iseq_arm(tag: str) -> dict:
        nonlocal iseq_error
        if iseq_error and delta_letters is None:
            return {"arm": "iSeqSearch", "ran": False, "why": iseq_error}
        started = time.perf_counter()
        delta_out = work / f"{tag}_delta.m8"
        if fresh and delta_letters:
            _time_blast(diamond, delta_fa, queries, delta_out, k="0")
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
                args.iseq,
                old_m8,
                delta_out,
                merged,
                old_letters,
                int(delta_letters or 0),
            )
        merge_s = time.perf_counter() - merge_started
        if why:
            iseq_error = why
            return {
                "arm": "iSeqSearch",
                "ran": False,
                "why": why,
                "search_s": search_s,
                "wall_s": search_s + merge_s,
            }
        text = merged.read_text()
        iseq_texts.append(text)
        return {
            "arm": "iSeqSearch",
            "ran": True,
            "wall_s": search_s + merge_s,
            "search_s": search_s,
            "merge_s": merge_s,
            "commit": "7e862bf3afa52b65b3cca4255de66ab4cb764fe3",
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
    stock_text = stock_texts[0] if stock_texts else ""
    matches = []
    for i, text in enumerate(acts_texts):
        if not stock_text or not text:
            matches.append({"i": i, "ok": False, "why": "missing output"})
            continue
        row = _ref_merge_files(stock_text, text, fit_dict)
        row["i"] = i
        matches.append(row)
    iseq_bars = []
    for i, text in enumerate(iseq_texts):
        if not stock_text or not text:
            continue
        bar = _published_bar(stock_text, text)
        bar["ref_merge"] = _ref_merge_files(stock_text, text, fit_dict)
        bar["i"] = i
        iseq_bars.append(bar)
    d3 = {
        **base,
        "stage": "D3",
        "setting": "S1",
        "discarded_cold_start_s": cold,
        "fit_walls": fit_walls,
        "a": a,
        "b": b,
        "c": c,
        "n": N_FULL,
        "predicted_speedup": predicted,
        "formula": "(a + b*5117) / (a + c*b*5117)",
        "assumptions": [
            "a does not shrink on the smaller reference",
            "per-record cost scales with D1 entry-count c, not c_length",
            "merge and rescale stay inside the ACTS wall",
            "the probe and the six fit runs are outside the alternating means",
        ],
        "warm": warm,
        "arms": arms,
        "stock_mean_s": stock_mean,
        "acts_mean_s": acts_mean,
        "iseq_mean_s": (sum(iseq_walls) / len(iseq_walls)) if iseq_walls else None,
        "measured_speedup": measured,
        "confirmed": confirmed(stock_mean, acts_mean, predicted),
        "ref_merge_acts": matches,
        "iseq": {
            "ran": bool(iseq_walls),
            "why": iseq_error,
            "bars": iseq_bars,
            "commit": "7e862bf3afa52b65b3cca4255de66ab4cb764fe3",
        },
        "d2_decision": fit.decision,
        "d2n_decision": fit_k.decision,
        "d0_letters_equal": {"old": d0["old_equal"], "new": d0["new_equal"]},
    }
    _write(out / "reference_diamond_d3.json", d3)
    print(json.dumps({"confirmed": d3["confirmed"], "predicted": predicted, "measured": measured}), flush=True)
    return 0


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
    parser.add_argument("--diamond", type=Path, required=True)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--iseq", type=Path)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
