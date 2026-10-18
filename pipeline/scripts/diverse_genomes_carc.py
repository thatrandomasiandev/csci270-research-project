#!/usr/bin/env python3
"""Diverse-genome HMMER exactness on CARC.

One array task, one proteome. Stock hmmscan on Pfam 38.2, then a TARE
fill on 38.1 and an update on 38.2. The pilot also repeats stock and
runs the injected 5% model drop through the shipped check.

This file does not download proteomes and does not edit the paper.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import platform
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

DRAW_PATH = PIPE / "results" / "diverse_genomes" / "draw.json"
CPU = "8"
LARGE_PROTEINS = 8000
Z_OLD = 27481
Z_NEW = 30134
MD5_OLD = "dc814cc181ece09102c09c4e6c19f2fd"
MD5_NEW = "7ab3c4e215d0daaea3004e37c4e24f8a"
SEED_PILOT = 20261151
SEED_MEASURED = 20261152
SEED_DROP = 20261153
PAPER_N = 96902
LINE_FLOOR = 100
POOLED_FLOOR = 50_000
MIN_FREE = 40 * 1024**3
PRESS_RE = re.compile(r"Pressed and indexed (\d+) HMMs")

PAYLOAD: dict | None = None


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_out(payload: dict) -> None:
    dest = Path(os.environ["ACTS_OUT"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(dest)
    log(f"wrote {dest}")


def stop(reason: str, payload: dict, code: int = 2) -> None:
    payload["stopped"] = reason
    payload["outcome"] = "FAIL"
    payload["claim_class"] = "INCONCLUSIVE"
    write_out(payload)
    print(f"STOP: {reason}", file=sys.stderr, flush=True)
    raise SystemExit(code)


def _on_term(signum: int, _frame: object) -> None:
    if PAYLOAD is not None:
        PAYLOAD["stopped"] = f"signal {signum}"
        PAYLOAD["outcome"] = "FAIL"
        PAYLOAD["claim_class"] = "INCONCLUSIVE"
        PAYLOAD["scored"] = False
        write_out(PAYLOAD)
    raise SystemExit(2)


def body_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def read_body(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return body_lines(path.read_text(errors="replace"))


def row_key(tokens: list[str], kind: str) -> tuple:
    need = 3 if kind == "tbl" else 19
    if len(tokens) < need:
        return ("short-line", kind, len(tokens))
    if kind == "tbl":
        return (tokens[0], tokens[2])
    return (tokens[0], tokens[3], tokens[15], tokens[16], tokens[17], tokens[18])


def classify(replay: list[str], stock_lines: list[str], kind: str) -> dict:
    byte_equal = replay == stock_lines
    rt = [line.split() for line in replay]
    st = [line.split() for line in stock_lines]
    out: dict = {
        "lines_replay": len(replay),
        "lines_stock": len(stock_lines),
        "byte_equal": byte_equal,
        "token_equal": rt == st,
        "classes": [],
    }
    if byte_equal:
        return out
    if rt == st:
        out["classes"] = ["whitespace-only"]
        return out
    rc = Counter(row_key(toks, kind) for toks in rt)
    sc = Counter(row_key(toks, kind) for toks in st)
    missing = sum(1 for key in sc if sc[key] > rc[key])
    extra = sum(1 for key in rc if rc[key] > sc[key])
    classes: list[str] = []
    if missing:
        classes.append("missing")
    if extra:
        classes.append("extra")
    if not missing and not extra:
        rk = [row_key(toks, kind) for toks in rt]
        sk = [row_key(toks, kind) for toks in st]
        if rk != sk:
            classes.append("order")
    value = False
    buckets: dict[tuple, list[list[str]]] = {}
    for toks in rt:
        buckets.setdefault(row_key(toks, kind), []).append(toks)
    for toks in st:
        group = buckets.get(row_key(toks, kind))
        if not group:
            continue
        if group.pop(0) != toks:
            value = True
    if value:
        classes.append("value-only")
    out["classes"] = classes
    out["missing_keys"] = missing
    out["extra_keys"] = extra
    return out


def compare_pair(replay_tbl: Path, replay_dom: Path, stock_tbl: Path, stock_dom: Path) -> dict:
    tbl = classify(read_body(replay_tbl), read_body(stock_tbl), "tbl")
    dom = classify(read_body(replay_dom), read_body(stock_dom), "dom")
    return {
        "tbl": tbl,
        "dom": dom,
        "byte_equal": tbl["byte_equal"] and dom["byte_equal"],
        "classes": sorted(set(tbl["classes"]) | set(dom["classes"])),
    }


def parse_decision(path: Path) -> dict:
    out: dict = {"raw": ""}
    if not path.is_file():
        return out
    text = path.read_text(errors="replace")
    out["raw"] = text
    phases: dict = {}
    for line in text.splitlines():
        if line.startswith("phases: "):
            raw = line[len("phases: ") :]
            try:
                phases = ast.literal_eval(raw)
            except (SyntaxError, ValueError):
                out["phases_raw"] = raw[:500]
                phases = {}
        elif ": " in line:
            key, value = line.split(": ", 1)
            out[key.strip()] = value.strip()
    out["phases"] = phases if isinstance(phases, dict) else {}
    return out


def check_status(fill: dict, update: dict) -> dict:
    """Which shipped checks ran. Skips keep the decision's own sentence."""
    fill_phases = fill.get("phases") or {}
    phases = update.get("phases") or {}
    why = str(update.get("why") or "")
    neighbor = "not_reached"
    if (
        "ic2_neighbor_s" in phases
        or why.startswith("IC2 neighbor")
        or update.get("ic2") == "pass"
        or any(str(key).startswith("ic2_random_") for key in phases)
    ):
        neighbor = "ran"
    random_note = str(update.get("random_pads") or "")
    if random_note.startswith("skipped"):
        random_pads = random_note
    elif any(str(key).startswith("ic2_random_") for key in phases):
        random_pads = "ran"
    else:
        random_pads = "not_reached"
    audit_note = str(update.get("audit") or "")
    if audit_note.startswith("skipped"):
        audit = audit_note
    elif audit_note.startswith("checked") or (
        "verify_s" in phases and update.get("verify") == "audit"
    ):
        audit = "ran"
    else:
        audit = "not_reached"
    in_situ = "not_reached"
    if (
        "pin_check_s" in fill_phases
        or fill.get("decision") == "REFUSE_PIN"
        or fill.get("mode") == "exact"
    ):
        in_situ = "ran"
    return {
        "neighbor_pad": neighbor,
        "random_pads": random_pads,
        "audit": audit,
        "in_situ": in_situ,
    }


def claim_class(decision: str, compared: dict | None, tbl_lines: int, finished: bool) -> str:
    if not finished:
        return "INCONCLUSIVE"
    if tbl_lines < LINE_FLOOR:
        return "INCONCLUSIVE"
    body_written = compared is not None and (
        compared["tbl"]["lines_replay"] > 0 or compared["dom"]["lines_replay"] > 0
        or (compared["byte_equal"] and tbl_lines == 0)
    )
    # A written empty replay is still a body. Missing files are not.
    files_present = compared is not None and compared.get("files_present", True)
    if decision == "SHIP" and files_present and compared and compared["byte_equal"]:
        return "pass"
    if decision == "SHIP" and files_present and compared and not compared["byte_equal"]:
        return "UNSAFE"
    if decision.startswith("REFUSE") and files_present and compared and compared["byte_equal"]:
        return "needless_refusal"
    if decision.startswith("REFUSE"):
        return "refusal"
    return "INCONCLUSIVE"


def scan_headers(path: Path) -> dict:
    import gzip

    names: list[str] = []
    lengths: list[int] = []
    max_desc = 0
    token = ""
    seq_len = 0
    opener = gzip.open if path.suffix == ".gz" or path.name.endswith(".gz") else open
    with opener(path, "rt") as fh:
        for line in fh:
            if line.startswith(">"):
                if token:
                    names.append(token)
                    lengths.append(seq_len)
                header = line[1:].rstrip("\r\n")
                parts = header.split(None, 1)
                token = parts[0] if parts else ""
                desc = parts[1] if len(parts) > 1 else ""
                if len(desc) > max_desc:
                    max_desc = len(desc)
                seq_len = 0
            else:
                seq_len += len(line.strip())
        if token:
            names.append(token)
            lengths.append(seq_len)
    counts = Counter(names)
    duplicates = sorted(name for name, n in counts.items() if n > 1)
    total = sum(lengths)
    longest = max(lengths) if lengths else 0
    return {
        "fasta_records": len(names),
        "duplicate_names": duplicates[:20],
        "duplicate_name_count": len(duplicates),
        "max_name_token_len": max((len(name) for name in names), default=0),
        "max_description_len": max_desc,
        "residues": total,
        "max_protein_length": longest,
        "file_residue_cap_binds": bool(total) and any(2 * length > total for length in lengths),
    }


def domain_stress(dom_path: Path) -> dict:
    """domtblout column 10 is the per-query domain count printed with %3d."""
    max_of = 0
    queries_over_20 = 0
    seen: set[str] = set()
    max_coord = 0
    for line in read_body(dom_path):
        tokens = line.split()
        if len(tokens) < 19:
            continue
        query = tokens[3]
        try:
            of = int(tokens[10])
            coords = [int(tokens[i]) for i in (15, 16, 17, 18)]
        except ValueError:
            continue
        if query not in seen:
            seen.add(query)
            if of > 20:
                queries_over_20 += 1
        max_of = max(max_of, of)
        max_coord = max(max_coord, max(coords))
    return {
        "max_domain_of": max_of,
        "queries_with_more_than_20_domains": queries_over_20,
        "multi_domain_stress_exercised": max_of > 20,
        "max_domtblout_coordinate": max_coord,
    }


def cohort_rows(draw: dict, cohort: str, size: str) -> list[dict]:
    if cohort not in {"pilot", "measured"}:
        raise SystemExit(f"unknown cohort {cohort}")
    if size not in {"small", "large"}:
        raise SystemExit(f"unknown size {size}")
    rows = list(draw[cohort])
    chosen = []
    for row in rows:
        count = row.get("ncbi_protein_coding_gene_count")
        if not isinstance(count, int):
            raise SystemExit(f"{row.get('accession')} has no integer NCBI protein count")
        large = count > LARGE_PROTEINS
        if (size == "large" and large) or (size == "small" and not large):
            chosen.append(row)
    return chosen


def tool_argv() -> list[str]:
    return [
        "hmmscan",
        "--cut_ga",
        "--noali",
        "--cpu",
        CPU,
        "--tblout",
        "{output:tblout}",
        "--domtblout",
        "{output:domtblout}",
        "-o",
        "/dev/null",
        "{reference}",
        "{input}",
    ]


def stock_scan(db: Path, queries: Path, tbl: Path, dom: Path) -> dict:
    cmd = [
        "hmmscan",
        "--cut_ga",
        "--noali",
        "--cpu",
        CPU,
        "--tblout",
        str(tbl),
        "--domtblout",
        str(dom),
        "-o",
        os.devnull,
        str(db),
        str(queries),
    ]
    log(" ".join(cmd))
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        raise SystemExit(f"hmmscan failed ({proc.returncode}): {(proc.stderr or proc.stdout)[-800:]}")
    log(f"stock {tbl.name} {wall:.1f}s lines={len(read_body(tbl))}")
    return {"wall_s": wall, "argv": cmd, "tbl": str(tbl), "dom": str(dom)}


def press_models(db: Path) -> int:
    log(f"hmmpress {db.name}")
    proc = subprocess.run(
        ["hmmpress", "-f", str(db)],
        check=False,
        capture_output=True,
        text=True,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise SystemExit(f"hmmpress failed: {text[-800:]}")
    match = PRESS_RE.search(text)
    if not match:
        raise SystemExit(f"hmmpress reported no model count: {text[-400:]}")
    return int(match.group(1))


def tare_run(reference: Path, queries: Path, cache: Path, out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    cmd = [
        sys.executable,
        "-m",
        "acts",
        "run",
        "--strategy",
        "reference",
        "--pin",
        "-Z {entry_count}",
        "--verify",
        "audit",
        "--prep",
        "hmmpress -f {reference}",
        "--input",
        str(queries),
        "--reference",
        str(reference),
        "--cache",
        str(cache),
        "-o",
        str(out),
        "--",
        *tool_argv(),
    ]
    log(f"tare {reference.name} -> {out.name}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=PIPE, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    calls = out / "calls"
    if calls.is_dir():
        shutil.rmtree(calls, ignore_errors=True)
    for folder in ("calls_pinned", "calls_infer", "calls_slack"):
        path = out / folder
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    decision = parse_decision(out / "decision.txt")
    log(f"tare {out.name} rc={proc.returncode} {decision.get('decision')} {wall:.1f}s")
    if proc.returncode not in (0, 1):
        raise SystemExit(
            f"acts crashed ({proc.returncode}): {(proc.stderr or proc.stdout)[-1500:]}"
        )
    if "decision" not in decision:
        raise SystemExit(f"acts wrote no decision: {(proc.stderr or proc.stdout)[-1500:]}")
    return {
        "wall_s": wall,
        "returncode": proc.returncode,
        "argv": cmd,
        "decision": decision.get("decision"),
        "why": decision.get("why"),
        "parsed": {key: value for key, value in decision.items() if key != "raw"},
        "raw_decision": decision.get("raw", ""),
        "stdout_tail": (proc.stdout or "")[-800:],
        "stderr_tail": (proc.stderr or "")[-800:],
        "tbl": str(out / "tables" / "tblout"),
        "dom": str(out / "tables" / "domtblout"),
    }


def negative_control(
    pfam: Path,
    queries: Path,
    cache: Path,
    stock_tbl: Path,
    stock_dom: Path,
    dest: Path,
) -> dict:
    """Drop 5% of stock target names and run the shipped neighbor/random check."""
    from acts.reference_cache import connect_cache
    from acts.reference_formats import parse_reference, read_records
    from acts.reference_run import ReferenceIncremental, _batched_replay, tables_from_dict

    models = sorted({line.split()[0] for line in read_body(stock_tbl) if line.split()})
    report: dict = {
        "seed": SEED_DROP,
        "candidate_models": len(models),
        "round": "python3 round",
    }
    if not models:
        report["control"] = "INCONCLUSIVE"
        report["reason"] = "stock tblout has no candidate models"
        return report
    k = max(1, round(0.05 * len(models)))
    dropped = sorted(random.Random(SEED_DROP).sample(models, k))
    dropped_set = set(dropped)
    cand: dict[str, set[str]] = {}
    for line in read_body(stock_tbl):
        fields = line.split()
        if len(fields) < 3 or fields[0] in dropped_set:
            continue
        cand.setdefault(fields[2], set()).add(fields[0])
    cand = {key: names for key, names in cand.items() if names}
    report["dropped"] = k
    report["dropped_names"] = dropped
    report["queries_kept"] = len(cand)
    log(f"negative drop {k} of {len(models)}")
    entries = parse_reference(pfam)
    if len(entries) != Z_NEW:
        report["control"] = "INCONCLUSIVE"
        report["reason"] = f"parsed {len(entries)} models, expected {Z_NEW}"
        return report
    known = {entry.primary for entry in entries}
    unknown = sorted({name for names in cand.values() for name in names if name not in known})
    if unknown:
        report["control"] = "INCONCLUSIVE"
        report["reason"] = f"{len(unknown)} candidate names are not Pfam NAME fields"
        report["unknown_names"] = unknown[:20]
        return report
    records = read_records(queries)
    rep_records = [rec for rec in records if rec.key in cand]
    stored_tables = None
    cache_obj = connect_cache(cache)
    try:
        rows = cache_obj._conn.execute("SELECT payload FROM contracts").fetchall()
    finally:
        cache_obj.close()
    for (blob,) in rows:
        stored = json.loads(blob)
        if stored.get("tables"):
            stored_tables = tables_from_dict(stored["tables"])
            break
    if not stored_tables:
        report["control"] = "INCONCLUSIVE"
        report["reason"] = "the fill cache has no fitted tables"
        return report
    by_name = {table.name: table for table in stored_tables}
    if "tblout" not in by_name or "domtblout" not in by_name:
        report["control"] = "INCONCLUSIVE"
        report["reason"] = "fitted tables are " + ", ".join(sorted(by_name))
        return report
    if by_name["tblout"].record_col != 2 or by_name["tblout"].entry_col != 0:
        report["control"] = "INCONCLUSIVE"
        report["reason"] = (
            "tblout columns "
            f"record={by_name['tblout'].record_col} entry={by_name['tblout'].entry_col}"
        )
        return report
    if by_name["domtblout"].record_col != 3 or by_name["domtblout"].entry_col != 0:
        report["control"] = "INCONCLUSIVE"
        report["reason"] = (
            "domtblout columns "
            f"record={by_name['domtblout'].record_col} entry={by_name['domtblout'].entry_col}"
        )
        return report
    dest.mkdir(parents=True, exist_ok=True)
    memo = ReferenceIncremental(
        argv=tool_argv(),
        input_path=queries,
        out_dir=dest,
        reference=pfam,
        prep="hmmpress -f {reference}",
        cache_path=cache,
        verify="audit",
        pin="-Z {entry_count}",
    )
    memo._n_entries = len(entries)
    memo._entry_names = {key for entry in entries for key in entry.keys}
    memo.clock = {}
    memo._t_all = time.perf_counter()
    pinned = memo._pinned(pfam)
    t0 = time.perf_counter()
    texts, n_batches = _batched_replay(
        pinned, rep_records, entries, cand, entries, stored_tables
    )
    report["replay_wall_s"] = time.perf_counter() - t0
    report["n_batches"] = n_batches
    (dest / "tblout").write_text(texts.get("tblout", ""))
    (dest / "domtblout").write_text(texts.get("domtblout", ""))
    compared = compare_pair(dest / "tblout", dest / "domtblout", stock_tbl, stock_dom)
    compared["files_present"] = True
    report["vs_stock"] = compared
    report["differs"] = not compared["byte_equal"]
    why = memo._ic2(pinned, entries, rep_records, texts, stored_tables, cand)
    report["check_why"] = why
    report["check_refused"] = bool(why)
    report["budget"] = dict(getattr(memo, "_budget_fields", {}) or {})
    report["phases"] = dict(memo.clock)
    if not report["differs"]:
        report["control"] = "INCONCLUSIVE"
        report["reason"] = "dropped replay is byte-identical to stock"
    elif not why:
        report["control"] = "UNSAFE"
        report["reason"] = "dropped replay differs and the shipped check accepted it"
    else:
        report["control"] = "pass"
        report["reason"] = "body differs and the shipped check refused"
    log(f"negative {report['control']} differs={report['differs']} why={why}")
    return report


def genome_record(row: dict, cohort: str) -> dict:
    return {
        "accession": row["accession"],
        "group": row["group"],
        "role": row["role"],
        "organism": row.get("organism"),
        "ncbi_protein_coding_gene_count": row["ncbi_protein_coding_gene_count"],
        "cohort": cohort,
    }


def run_genome(row: dict, cohort: str, scratch: Path, old_db: Path, new_db: Path) -> dict:
    accession = row["accession"]
    queries = Path(os.environ["ACTS_GENOMES"]) / f"{accession}_protein.faa.gz"
    if not queries.is_file():
        raise SystemExit(f"missing proteome {queries}")
    if queries.stat().st_size != int(row["bytes"]):
        raise SystemExit(
            f"{accession} is {queries.stat().st_size} bytes, draw records {row['bytes']}"
        )
    work = scratch / accession
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    record = genome_record(row, cohort)
    record["proteome_md5"] = md5_file(queries)
    record["proteome_bytes"] = queries.stat().st_size
    record["headers"] = scan_headers(queries)
    record["finished"] = False
    log(f"headers {accession} records={record['headers']['fasta_records']}")

    stock_a = stock_scan(new_db, queries, work / "stock_a.tbl", work / "stock_a.dom")
    record["stock"] = stock_a
    record["domain_stress"] = domain_stress(work / "stock_a.dom")
    record["stock_tbl_lines"] = len(read_body(work / "stock_a.tbl"))
    record["stock_dom_lines"] = len(read_body(work / "stock_a.dom"))

    if cohort == "pilot":
        stock_b = stock_scan(new_db, queries, work / "stock_b.tbl", work / "stock_b.dom")
        identity = compare_pair(
            work / "stock_b.tbl", work / "stock_b.dom", work / "stock_a.tbl", work / "stock_a.dom"
        )
        identity["files_present"] = True
        record["stock_repeat"] = {"wall_s": stock_b["wall_s"], "compare": identity}
        if not identity["byte_equal"]:
            record["finished"] = True
            record["outcome"] = "indeterminism"
            record["claim_class"] = "INCONCLUSIVE"
            record["scored"] = False
            record["tare_scored"] = False
            record["reason"] = "stock-vs-stock bodies differ at --cpu 8"
            log(f"INDETERMINISM {accession}")
            return record

    cache = work / "cache.sqlite"
    fill = tare_run(old_db, queries, cache, work / "fill")
    update = tare_run(new_db, queries, cache, work / "update")
    tbl = Path(update["tbl"])
    dom = Path(update["dom"])
    files_present = tbl.is_file() and dom.is_file()
    compared = None
    if files_present:
        compared = compare_pair(tbl, dom, work / "stock_a.tbl", work / "stock_a.dom")
        compared["files_present"] = True
    record["fill"] = {
        "wall_s": fill["wall_s"],
        "returncode": fill["returncode"],
        "decision": fill["decision"],
        "why": fill["why"],
        "parsed": fill["parsed"],
    }
    record["update"] = {
        "wall_s": update["wall_s"],
        "returncode": update["returncode"],
        "decision": update["decision"],
        "why": update["why"],
        "argv": update["argv"],
        "parsed": update["parsed"],
    }
    record["compare"] = compared
    record["checks"] = check_status(fill["parsed"], update["parsed"])
    decision = str(update["decision"] or "")
    record["claim_class"] = claim_class(
        decision, compared, record["stock_tbl_lines"], True
    )
    record["decision"] = decision
    record["finished"] = True
    record["tare_scored"] = cohort != "pilot"
    if cohort == "pilot":
        record["negative"] = negative_control(
            new_db, queries, cache, work / "stock_a.tbl", work / "stock_a.dom", work / "drop"
        )
        if record["negative"]["control"] == "UNSAFE":
            record["claim_class"] = "UNSAFE"
    record["outcome"] = record["claim_class"]
    log(f"done {accession} {record['claim_class']} checks={record['checks']}")
    return record


def list_cohort() -> int:
    cohort = sys.argv[2]
    size = sys.argv[3]
    draw = json.loads(DRAW_PATH.read_text())
    rows = cohort_rows(draw, cohort, size)
    print(json.dumps([
        {
            "accession": row["accession"],
            "group": row["group"],
            "ncbi_protein_coding_gene_count": row["ncbi_protein_coding_gene_count"],
            "bytes": row["bytes"],
        }
        for row in rows
    ]))
    return 0


def merge_results(directory: Path, dest: Path) -> dict:
    rows = []
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(".partial") or path.name == dest.name:
            continue
        payload = json.loads(path.read_text())
        genome = payload.get("genome")
        if isinstance(genome, dict) and genome.get("accession"):
            rows.append(genome)
    return rows  # type: ignore[return-value]


def summarize(rows: list[dict], cohort: str) -> dict:
    groups: dict[str, dict] = {}
    unsafe = []
    needless = []
    passed_lines = 0
    for row in rows:
        if row.get("cohort") != cohort and row.get("role") != cohort:
            continue
        group = str(row.get("group") or "?")
        bucket = groups.setdefault(
            group,
            {
                "genomes": 0,
                "pass": 0,
                "UNSAFE": 0,
                "needless_refusal": 0,
                "refusal": 0,
                "INCONCLUSIVE": 0,
                "indeterminism": 0,
                "tbl_lines": 0,
                "dom_lines": 0,
            },
        )
        bucket["genomes"] += 1
        kind = row.get("outcome") or row.get("claim_class") or "INCONCLUSIVE"
        if kind not in bucket:
            kind = "INCONCLUSIVE"
        bucket[kind] += 1
        bucket["tbl_lines"] += int(row.get("stock_tbl_lines") or 0)
        bucket["dom_lines"] += int(row.get("stock_dom_lines") or 0)
        if kind == "UNSAFE":
            unsafe.append(row.get("accession"))
        if kind == "needless_refusal":
            needless.append({"accession": row.get("accession"), "decision": row.get("decision")})
        if kind == "pass" and cohort == "measured":
            passed_lines += int(row.get("stock_tbl_lines") or 0) + int(row.get("stock_dom_lines") or 0)
    summary: dict = {
        "cohort": cohort,
        "genomes": [row.get("accession") for row in rows if row.get("role") == cohort or row.get("cohort") == cohort],
        "by_group": groups,
        "unsafe": unsafe,
        "needless_refusals": needless,
        "passed_lines_L": passed_lines if cohort == "measured" else 0,
    }
    if cohort == "measured" and not unsafe:
        n_new = PAPER_N + passed_lines
        summary["N_new"] = n_new
        summary["p_up"] = None if n_new <= 0 else 1.0 - (0.05 ** (1.0 / n_new))
        summary["pooled_floor"] = POOLED_FLOOR
        summary["pooled"] = "pass" if passed_lines >= POOLED_FLOOR else "INCONCLUSIVE"
    elif cohort == "measured":
        summary["p_up"] = None
        summary["pooled"] = "UNSAFE"
    return summary


def main() -> None:
    global PAYLOAD
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("STOP: this run executes only under sbatch")
    task_raw = os.environ.get("SLURM_ARRAY_TASK_ID")
    if task_raw is None or not task_raw.isdigit():
        raise SystemExit("STOP: SLURM_ARRAY_TASK_ID is required")
    task = int(task_raw)
    cohort = os.environ["ACTS_COHORT"]
    size = os.environ["ACTS_SIZE"]
    scratch = Path(os.environ["ACTS_SCRATCH"])
    scratch.mkdir(parents=True, exist_ok=True)
    draw = json.loads(DRAW_PATH.read_text())
    rows = cohort_rows(draw, cohort, size)
    if task >= len(rows):
        raise SystemExit(f"task {task} is outside the {cohort}/{size} cohort of {len(rows)}")
    row = rows[task]
    out_path = Path(os.environ["ACTS_OUT_DIR"]) / f"{cohort}_{size}_{task:02d}_{row['accession']}.json"
    os.environ["ACTS_OUT"] = str(out_path)
    free = shutil.disk_usage(scratch).free
    version = subprocess.run(["hmmscan", "-h"], check=False, capture_output=True, text=True)
    version_lines = (version.stdout or version.stderr or "").splitlines()[:3]
    payload: dict = {
        "test": "diverse-genomes",
        "system": "TARE",
        "package": "acts",
        "package_version": __import__("acts").__version__,
        "cohort": cohort,
        "size": size,
        "task": task,
        "seed": SEED_PILOT if cohort == "pilot" else SEED_MEASURED,
        "drop_seed": SEED_DROP if cohort == "pilot" else None,
        "job_id": os.environ.get("SLURM_ARRAY_JOB_ID") or os.environ.get("SLURM_JOB_ID"),
        "array_task_id": task,
        "git_head": os.environ.get("ACTS_GIT_HEAD", ""),
        "git_dirty": os.environ.get("ACTS_GIT_DIRTY", ""),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version,
        "hmmer_version_lines": version_lines,
        "hmmer_tarball_sha256": os.environ.get("ACTS_HMMER_SHA256", ""),
        "scratch": str(scratch),
        "scratch_free_bytes_start": free,
        "argv_stock": f"hmmscan --cut_ga --noali --cpu {CPU} --tblout --domtblout -o /dev/null",
        "argv_acts": (
            "python3 -m acts run --strategy reference --pin '-Z {entry_count}' "
            "--verify audit --prep 'hmmpress -f {reference}' -- "
            f"hmmscan --cut_ga --noali --cpu {CPU}"
        ),
        "cpu": int(CPU),
        "not_a_speedup_claim": True,
    }
    PAYLOAD = payload
    signal.signal(signal.SIGTERM, _on_term)
    if free < MIN_FREE:
        stop(f"scratch {scratch} has {free} bytes free, need {MIN_FREE}", payload)
    if not any("HMMER 3.4" in line for line in version_lines):
        stop(f"hmmscan is not HMMER 3.4: {version_lines}", payload)
    old_src = Path(os.environ["ACTS_PFAM_OLD"])
    new_src = Path(os.environ["ACTS_PFAM_NEW"])
    for path in (old_src, new_src):
        if not path.is_file():
            stop(f"missing {path}", payload)
    payload["input_md5"] = {"pfam38.1": md5_file(old_src), "pfam38.2": md5_file(new_src)}
    if payload["input_md5"]["pfam38.1"] != MD5_OLD or payload["input_md5"]["pfam38.2"] != MD5_NEW:
        stop(
            f"Pfam md5 {payload['input_md5']} != {(MD5_OLD, MD5_NEW)}",
            payload,
        )
    old_db = scratch / "Pfam-A.38.1.hmm.gz"
    new_db = scratch / "Pfam-A.38.2.hmm.gz"
    if not old_db.is_file():
        log(f"copy {old_src.name}")
        shutil.copy2(old_src, old_db)
    if not new_db.is_file():
        log(f"copy {new_src.name}")
        shutil.copy2(new_src, new_db)
    pressed = {"38.1": press_models(old_db), "38.2": press_models(new_db)}
    payload["pressed_models"] = pressed
    if pressed["38.1"] != Z_OLD or pressed["38.2"] != Z_NEW:
        stop(f"press counts {pressed} != {(Z_OLD, Z_NEW)}; arm INCONCLUSIVE", payload)
    try:
        payload["genome"] = run_genome(row, cohort, scratch, old_db, new_db)
    except SystemExit:
        raise
    except Exception as exc:
        payload["crashed"] = f"{type(exc).__name__}: {exc}"[:2000]
        payload["outcome"] = "FAIL"
        payload["claim_class"] = "INCONCLUSIVE"
        write_out(payload)
        raise
    genome = payload["genome"]
    payload["input_md5"]["proteome"] = genome.get("proteome_md5")
    payload["outcome"] = genome.get("outcome")
    payload["claim_class"] = genome.get("claim_class")
    payload["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_out(payload)
    # The pressed copies are large and the JSON is already on the project disk.
    shutil.rmtree(scratch / row["accession"], ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        raise SystemExit(list_cohort())
    try:
        main()
    except BaseException as exc:
        if PAYLOAD is not None and "outcome" not in PAYLOAD:
            PAYLOAD["crashed"] = f"{type(exc).__name__}: {exc}"[:2000]
            PAYLOAD["outcome"] = "FAIL"
            PAYLOAD["claim_class"] = "INCONCLUSIVE"
            PAYLOAD["scored"] = False
            write_out(PAYLOAD)
        raise
