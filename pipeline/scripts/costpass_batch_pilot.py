#!/usr/bin/env python3
"""Pilot for per-record candidate replay on GCF_013315695.1.

The proteome is already pilot data. This is not a measured result.
An oracle batched replay is checked before the three CLI walls. The
injected drop and the unpinned replay are controls on that same batching.
"""
from __future__ import annotations

import ast
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.reference_run import body_lines  # noqa: E402
from acts.replay_batch import merge_bodies, plan_batches  # noqa: E402

WORK = Path("/Users/joshuaterranova/tmp/costpass_work")
HMMER = Path("/opt/homebrew/bin")
CPU = "4"
Z = "30134"
QUERIES = WORK / "GCF_013315695.1.faa"
PFAM = WORK / "pfam38.2.hmm"
STOCK_TBL = WORK / "stock_1.tbl"
STOCK_DOM = WORK / "stock_1.dom"
CACHE = WORK / "cache_38.1.sqlite"
MIN_FREE = 8 * 1024**3
DROP_SEED = 20261013


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def loadavg() -> list[float]:
    return [round(v, 2) for v in os.getloadavg()]


def require_free() -> None:
    free = shutil.disk_usage(WORK).free
    if free < MIN_FREE:
        raise SystemExit(f"stop: {free} bytes free, need {MIN_FREE}")


def index_models(path: Path) -> dict[str, tuple[int, int]]:
    spans: dict[str, tuple[int, int]] = {}
    start: int | None = None
    name: str | None = None
    with path.open(newline="") as fh:
        while True:
            line = fh.readline()
            if not line:
                break
            if line.startswith("HMMER3/"):
                start = fh.tell() - len(line)
                name = None
            elif line.startswith("NAME ") and start is not None:
                name = line.split(None, 1)[1].strip()
            elif line.startswith("//") and start is not None and name:
                spans[name] = (start, fh.tell())
                start = None
                name = None
    return spans


def index_fasta(path: Path) -> tuple[list[str], dict[str, tuple[int, int]]]:
    order: list[str] = []
    spans: dict[str, tuple[int, int]] = {}
    with path.open(newline="") as fh:
        start: int | None = None
        key: str | None = None
        while True:
            pos = fh.tell()
            line = fh.readline()
            if not line:
                if key is not None and start is not None:
                    spans[key] = (start, pos)
                break
            if line.startswith(">"):
                if key is not None and start is not None:
                    spans[key] = (start, pos)
                key = line[1:].split()[0]
                start = pos
                order.append(key)
    return order, spans


def write_span(src: Path, spans: list[tuple[int, int]], dest: Path) -> None:
    with src.open("rb") as inp, dest.open("wb") as out:
        for start, end in spans:
            inp.seek(start)
            out.write(inp.read(end - start))


def candidates(tbl: Path) -> dict[str, set[str]]:
    cand: dict[str, set[str]] = {}
    for line in body_lines(tbl.read_text()):
        fields = line.split()
        cand.setdefault(fields[2], set()).add(fields[0])
    return cand


def row_key(tokens: list[str], kind: str) -> tuple:
    if kind == "tbl":
        return (tokens[0], tokens[2])
    return (tokens[0], tokens[3], tokens[15], tokens[16], tokens[17], tokens[18])


def classify(replay: list[str], stock: list[str], kind: str) -> dict:
    byte_equal = replay == stock
    rt = [line.split() for line in replay]
    st = [line.split() for line in stock]
    out: dict = {
        "lines_replay": len(replay),
        "lines_stock": len(stock),
        "byte_equal": byte_equal,
        "token_equal": rt == st,
        "classes": [],
    }
    if byte_equal or rt == st:
        if not byte_equal:
            out["classes"] = ["whitespace-only"]
        return out
    rc, sc = Counter(row_key(toks, kind) for toks in rt), Counter(row_key(toks, kind) for toks in st)
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


def batched_scan(
    order: list[str],
    cand: dict[str, set[str]],
    model_spans: dict[str, tuple[int, int]],
    fasta_spans: dict[str, tuple[int, int]],
    dest: Path,
    *,
    pin: bool,
) -> dict:
    """Run the same batch plan the CLI uses. Deletes each batch directory."""
    if dest.is_dir() and (dest / "tblout").is_file() and (dest / "done.json").is_file():
        log(f"reuse batched {dest.name}")
        return json.loads((dest / "done.json").read_text())
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    keys = [key for key in order if cand.get(key)]
    batches = plan_batches(keys, cand, startup_pairs=2000.0, press_pairs=84.0)
    tbl_parts: list[str] = []
    dom_parts: list[str] = []
    require_free()
    load_before = loadavg()
    log(f"batched {dest.name} batches={len(batches)} pin={pin} load={load_before}")
    t0 = time.perf_counter()
    for index, batch in enumerate(batches):
        work = dest / f"b{index}"
        work.mkdir()
        union = sorted({model for key in batch for model in cand[key]}, key=lambda name: model_spans[name][0])
        write_span(PFAM, [model_spans[name] for name in union], work / "db.hmm")
        write_span(QUERIES, [fasta_spans[key] for key in batch], work / "q.faa")
        press = subprocess.run(
            [str(HMMER / "hmmpress"), "-f", str(work / "db.hmm")],
            check=False,
            capture_output=True,
            text=True,
        )
        if press.returncode != 0:
            raise SystemExit(f"hmmpress failed: {(press.stderr or press.stdout)[-400:]}")
        cmd = [str(HMMER / "hmmscan"), "--cut_ga", "--noali", "--cpu", CPU]
        if pin:
            cmd.extend(["-Z", Z])
        cmd.extend(
            [
                "--tblout",
                str(work / "tbl"),
                "--domtblout",
                str(work / "dom"),
                "-o",
                os.devnull,
                str(work / "db.hmm"),
                str(work / "q.faa"),
            ]
        )
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(f"hmmscan failed ({proc.returncode}): {(proc.stderr or proc.stdout)[-400:]}")
        tbl_parts.append((work / "tbl").read_text())
        dom_parts.append((work / "dom").read_text())
        shutil.rmtree(work)
    wall = time.perf_counter() - t0
    tbl = merge_bodies(tbl_parts, 2, keys)
    dom = merge_bodies(dom_parts, 3, keys)
    (dest / "tblout").write_text(tbl)
    (dest / "domtblout").write_text(dom)
    stock_tbl = body_lines(STOCK_TBL.read_text())
    stock_dom = body_lines(STOCK_DOM.read_text())
    report = {
        "n_batches": len(batches),
        "n_records": len(keys),
        "wall_s": wall,
        "load_before": load_before,
        "load_after": loadavg(),
        "pin": pin,
        "tbl": classify(body_lines(tbl), stock_tbl, "tbl"),
        "dom": classify(body_lines(dom), stock_dom, "dom"),
    }
    (dest / "done.json").write_text(json.dumps(report) + "\n")
    log(
        f"batched {dest.name} {wall:.1f}s tbl={report['tbl']['byte_equal']} "
        f"dom={report['dom']['byte_equal']} classes tbl={report['tbl']['classes']} dom={report['dom']['classes']}"
    )
    return report


def parse_decision(path: Path) -> dict:
    out: dict = {}
    phases = {}
    for line in path.read_text().splitlines():
        if line.startswith("phases: "):
            phases = ast.literal_eval(line[len("phases: ") :])
        elif ": " in line:
            key, value = line.split(": ", 1)
            out[key.strip()] = value.strip()
    out["phases"] = phases
    return out


def cli_run(index: int) -> dict:
    out = WORK / f"batch_cli_{index}"
    stamp = out / "cli.json"
    if stamp.is_file():
        log(f"reuse cli {out.name}")
        return json.loads(stamp.read_text())
    cache = WORK / f"cache_batch_{index}.sqlite"
    shutil.copy2(CACHE, cache)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    require_free()
    cmd = [
        sys.executable, "-m", "acts", "run",
        "--strategy", "reference",
        "--pin", "-Z {entry_count}",
        "--verify", "audit",
        "--prep", "hmmpress -f {reference}",
        "--input", str(QUERIES),
        "--reference", str(PFAM),
        "--cache", str(cache),
        "-o", str(out),
        "--",
        "hmmscan", "--cut_ga", "--noali", "--cpu", CPU,
        "--tblout", "{output:tblout}",
        "--domtblout", "{output:domtblout}",
        "-o", "/dev/null",
        "{reference}", "{input}",
    ]
    load_before = loadavg()
    log(f"cli {out.name} load={load_before}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=PIPE, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    for folder in ("calls", "calls_pinned", "calls_infer", "calls_slack"):
        path = out / folder
        if path.is_dir():
            shutil.rmtree(path)
    if proc.returncode not in (0, 1):
        raise SystemExit(f"cli crashed ({proc.returncode}): {(proc.stderr or proc.stdout)[-1500:]}")
    decision = parse_decision(out / "decision.txt")
    tbl = body_lines((out / "tables" / "tblout").read_text()) if (out / "tables" / "tblout").is_file() else []
    dom = body_lines((out / "tables" / "domtblout").read_text()) if (out / "tables" / "domtblout").is_file() else []
    payload = {
        "returncode": proc.returncode,
        "wall_s": wall,
        "load_before": load_before,
        "load_after": loadavg(),
        "decision": decision.get("decision"),
        "why": decision.get("why"),
        "n_batches": decision.get("n_batches"),
        "phases": decision.get("phases") or {},
        "tbl_byte_equal": tbl == body_lines(STOCK_TBL.read_text()),
        "dom_byte_equal": dom == body_lines(STOCK_DOM.read_text()),
        "stderr_tail": (proc.stderr or "")[-400:],
    }
    stamp.write_text(json.dumps(payload) + "\n")
    log(f"cli {out.name} {payload['decision']} {wall:.1f}s byte={payload['tbl_byte_equal'] and payload['dom_byte_equal']}")
    return payload


def main() -> None:
    require_free()
    for path in (QUERIES, PFAM, STOCK_TBL, STOCK_DOM, CACHE):
        if not path.is_file():
            raise SystemExit(f"missing {path}")
    log("index models")
    model_spans = index_models(PFAM)
    log(f"models {len(model_spans)}")
    order, fasta_spans = index_fasta(QUERIES)
    cand = candidates(STOCK_TBL)
    missing = sorted({name for names in cand.values() for name in names} - set(model_spans))
    if missing:
        raise SystemExit(f"stop: {len(missing)} hit names are not model NAMEs, e.g. {missing[:3]}")
    oracle = batched_scan(order, cand, model_spans, fasta_spans, WORK / "batch_oracle", pin=True)
    if not (oracle["tbl"]["byte_equal"] and oracle["dom"]["byte_equal"]):
        raise SystemExit("stop: oracle batched replay is not byte-identical")
    models = sorted({name for names in cand.values() for name in names})
    k = max(1, int(round(0.05 * len(models))))
    dropped = set(random.Random(DROP_SEED).sample(models, k))
    reduced = {key: names - dropped for key, names in cand.items()}
    injected = batched_scan(order, reduced, model_spans, fasta_spans, WORK / "batch_inject", pin=True)
    if injected["tbl"]["byte_equal"] and injected["dom"]["byte_equal"]:
        raise SystemExit("stop: injected drop did not change the body")
    unpinned = batched_scan(order, cand, model_spans, fasta_spans, WORK / "batch_unpinned", pin=False)
    if unpinned["tbl"]["byte_equal"] or unpinned["dom"]["byte_equal"]:
        raise SystemExit("stop: unpinned replay matched stock on a table")
    runs = []
    for index in (1, 2, 3):
        run = cli_run(index)
        if run["decision"] != "SHIP" or not (run["tbl_byte_equal"] and run["dom_byte_equal"]):
            raise SystemExit(f"stop: cli {index} {run['decision']} byte tbl={run['tbl_byte_equal']} dom={run['dom_byte_equal']}")
        runs.append(run)
    walls = [run["wall_s"] for run in runs]
    mid = sorted(range(3), key=lambda i: walls[i])[1]
    report = {
        "test": "costpass-batch-pilot",
        "proteome": "GCF_013315695.1",
        "proteome_role": "pilot",
        "git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PIPE, check=True, capture_output=True, text=True
        ).stdout.strip(),
        "note": "HEAD at write time may not include this script if it is still uncommitted.",
        "oracle": oracle,
        "injected": {
            "dropped": k,
            "seed": DROP_SEED,
            "differs": not (injected["tbl"]["byte_equal"] and injected["dom"]["byte_equal"]),
            "tbl_classes": injected["tbl"]["classes"],
            "dom_classes": injected["dom"]["classes"],
            "wall_s": injected["wall_s"],
            "n_batches": injected["n_batches"],
        },
        "unpinned": {
            "tbl_byte_equal": unpinned["tbl"]["byte_equal"],
            "dom_byte_equal": unpinned["dom"]["byte_equal"],
            "tbl_classes": unpinned["tbl"]["classes"],
            "dom_classes": unpinned["dom"]["classes"],
            "wall_s": unpinned["wall_s"],
        },
        "cli_runs": runs,
        "median_wall_s": statistics.median(walls),
        "representative_run": mid + 1,
        "representative_phases": runs[mid]["phases"],
    }
    dest = PIPE / "results/exact_replay/costpass_batch_pilot.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    log(f"wrote {dest} median={report['median_wall_s']:.1f}")


if __name__ == "__main__":
    main()
