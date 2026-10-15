#!/usr/bin/env python3
"""CARC pilot for the Pfam 38.1 → 38.2 headline timing.

One proteome, seed 20261035, never reused for the measured ten. Exclusive
node, under sbatch only. Press time is logged and is not part of either
arm. Arms alternate A B A B A B. Each B restores the same 38.1 cache
snapshot. A is stock hmmscan on 38.2. B is the shipped exact-mode CLI.
"""
from __future__ import annotations

import ast
import gzip
import hashlib
import json
import os
import random
import shutil
import sqlite3
import statistics
import subprocess
import time
from collections import Counter
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(PIPE))

from acts.reference_run import (  # noqa: E402
    REPLAY_PRESS_PAIRS,
    REPLAY_STARTUP_PAIRS,
    body_lines,
)
from acts.replay_batch import merge_bodies, plan_batches  # noqa: E402

SEED = 20261035
EXPECTED = "GCF_030717825.1"
DRAW_INDEX = 47
POOL_N = 91
POOL_SHA256 = "2f1ea0794c93f09e13f116597e67c56833e23fbaae2043b89c7a96b2066175cf"
EXCLUDE = (
    "GCF_002853805.1",
    "GCF_002090355.1",
    "GCF_013315695.1",
    "GCF_049201905.1",
    "GCF_059719525.1",
    "GCF_016806025.1",
    "GCF_017165095.1",
    "GCF_001515725.1",
    "GCF_023657995.1",
)
MD5_OLD = "dc814cc181ece09102c09c4e6c19f2fd"
MD5_NEW = "7ab3c4e215d0daaea3004e37c4e24f8a"
Z_OLD = 27481
Z_NEW = 30134
CPU = "4"
CACHE_LIMIT = 5 * 1024**3
MIN_FREE = 40 * 1024**3
CV_LIMIT = 0.05
# Mac phase seconds from the task brief, shape reference only.
MAC_SHAPE_S = {
    "diff": 1.4,
    "discovery": 91.0,
    "replay": 17.0,
    "neighbor": 27.0,
    "random": 8.0,
    "verify": 15.0,
    "parse": 14.0,
}
RANDOM_SEEDS = (20261031, 20261032, 20261033)


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def stop(reason: str, payload: dict, code: int = 2) -> None:
    payload["stopped"] = reason
    payload["pilot_pass"] = False
    write_out(payload)
    print(f"STOP: {reason}", file=sys.stderr, flush=True)
    raise SystemExit(code)


def write_out(payload: dict) -> None:
    dest = Path(os.environ["ACTS_OUT"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(dest)
    log(f"wrote {dest}")


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fstype(path: str) -> str:
    best = ""
    kind = ""
    target = os.path.realpath(path)
    with open("/proc/mounts", encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 3:
                continue
            mount = parts[1].replace("\\040", " ")
            if target == mount or target.startswith(mount.rstrip("/") + "/"):
                if len(mount) >= len(best):
                    best, kind = mount, parts[2]
    return kind


def meminfo() -> dict[str, int]:
    out: dict[str, int] = {}
    if not os.path.exists("/proc/meminfo"):
        return out
    with open("/proc/meminfo", encoding="utf-8") as fh:
        for line in fh:
            key, rest = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable", "MemFree"}:
                out[key] = int(rest.split()[0]) * 1024
    return out


def cpu_model() -> str:
    with open("/proc/cpuinfo", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return ""


def host_snap() -> dict:
    load = [round(v, 2) for v in os.getloadavg()]
    mem = meminfo()
    scratch = os.environ.get("ACTS_SCRATCH", "/tmp")
    return {
        "node": os.uname().nodename,
        "load": load,
        "mem_available_bytes": mem.get("MemAvailable"),
        "mem_free_bytes": mem.get("MemFree"),
        "scratch_free_bytes": shutil.disk_usage(scratch).free,
    }


def draw(genomes: Path) -> str:
    stems = sorted(
        p.name[: -len("_protein.faa.gz")]
        for p in genomes.glob("*_protein.faa.gz")
    )
    pool = [stem for stem in stems if stem not in EXCLUDE]
    digest = hashlib.sha256("\n".join(pool).encode()).hexdigest()
    if len(pool) != POOL_N or digest != POOL_SHA256:
        raise RuntimeError(
            f"STOP_DRAW: pool {len(pool)} {digest} != locked {POOL_N} {POOL_SHA256}"
        )
    index = random.Random(SEED).randrange(len(pool))
    if index != DRAW_INDEX or pool[index] != EXPECTED:
        raise RuntimeError(f"STOP_DRAW: index {index} {pool[index]} != {DRAW_INDEX} {EXPECTED}")
    return pool[index]


def decompress(src: Path, dest: Path) -> float:
    log(f"decompress {src}")
    t0 = time.perf_counter()
    tmp = dest.with_suffix(dest.suffix + ".partial")
    with tmp.open("wb") as out:
        proc = subprocess.run(["gzip", "-dc", str(src)], stdout=out, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"gzip failed ({proc.returncode}): {proc.stderr[-400:]!r}")
    tmp.replace(dest)
    return time.perf_counter() - t0


def press(hmm: Path) -> float:
    log(f"hmmpress {hmm.name}")
    t0 = time.perf_counter()
    proc = subprocess.run(
        ["hmmpress", "-f", str(hmm)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"hmmpress failed: {(proc.stderr or proc.stdout)[-400:]}")
    return time.perf_counter() - t0


def count_models(path: Path) -> tuple[int, int]:
    headers = ends = 0
    with path.open("rb") as fh:
        for line in fh:
            if line.startswith(b"HMMER3/"):
                headers += 1
            elif line.startswith(b"//"):
                ends += 1
    return headers, ends


def stock(db: Path, queries: Path, tag: Path) -> dict:
    cmd = [
        "hmmscan", "--cut_ga", "--noali", "--cpu", CPU,
        "--tblout", str(tag) + ".tbl",
        "--domtblout", str(tag) + ".dom",
        "-o", os.devnull,
        str(db), str(queries),
    ]
    before = host_snap()
    log(f"stock {tag.name} load={before['load']} node={before['node']}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    after = host_snap()
    if proc.returncode != 0:
        raise SystemExit(f"hmmscan failed ({proc.returncode}): {(proc.stderr or proc.stdout)[-600:]}")
    log(f"stock {tag.name} {wall:.1f}s")
    return {
        "arm": "A",
        "wall_s": wall,
        "argv": cmd,
        "before": before,
        "after": after,
        "tbl": str(tag) + ".tbl",
        "dom": str(tag) + ".dom",
    }


def parse_decision(path: Path) -> dict:
    out: dict = {}
    phases: dict = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
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
    out["phases"] = phases
    return out


def cache_bytes(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    total = 0
    for suffix in ("", "-wal", "-shm"):
        side = Path(str(path) + suffix)
        if side.is_file():
            total += side.stat().st_size
    return total


def restore_cache(snapshot: Path, dest: Path) -> None:
    if dest.exists():
        dest.unlink()
    for suffix in ("-wal", "-shm"):
        side = Path(str(dest) + suffix)
        if side.exists():
            side.unlink()
    shutil.copy2(snapshot, dest)


def cli(reference: Path, queries: Path, cache: Path, out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    cmd = [
        sys.executable, "-m", "acts", "run",
        "--strategy", "reference",
        "--pin", "-Z {entry_count}",
        "--verify", "audit",
        "--prep", "hmmpress -f {reference}",
        "--input", str(queries),
        "--reference", str(reference),
        "--cache", str(cache),
        "-o", str(out),
        "--",
        "hmmscan", "--cut_ga", "--noali", "--cpu", CPU,
        "--tblout", "{output:tblout}",
        "--domtblout", "{output:domtblout}",
        "-o", "/dev/null",
        "{reference}", "{input}",
    ]
    before = host_snap()
    log(f"cli {out.name} load={before['load']} node={before['node']}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=PIPE, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    after = host_snap()
    for folder in ("calls", "calls_pinned", "calls_infer", "calls_slack"):
        path = out / folder
        if path.is_dir():
            shutil.rmtree(path)
    decision = parse_decision(out / "decision.txt")
    log(f"cli {out.name} rc={proc.returncode} {decision.get('decision')} {wall:.1f}s")
    return {
        "arm": "B",
        "wall_s": wall,
        "returncode": proc.returncode,
        "argv": cmd,
        "before": before,
        "after": after,
        "decision": decision.get("decision"),
        "why": decision.get("why"),
        "n_batches": decision.get("n_batches"),
        "phases": decision.get("phases") or {},
        "stdout_tail": (proc.stdout or "")[-500:],
        "stderr_tail": (proc.stderr or "")[-500:],
        "tbl": out / "tables" / "tblout",
        "dom": out / "tables" / "domtblout",
    }


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
    if byte_equal or rt == st:
        if not byte_equal:
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


def read_body(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return body_lines(path.read_text())


def compare_pair(replay_tbl: Path, replay_dom: Path, stock_tbl: Path, stock_dom: Path) -> dict:
    tbl = classify(read_body(replay_tbl), read_body(stock_tbl), "tbl")
    dom = classify(read_body(replay_dom), read_body(stock_dom), "dom")
    return {"tbl": tbl, "dom": dom, "byte_equal": tbl["byte_equal"] and dom["byte_equal"]}


def shape_of(phases: dict) -> dict:
    random_s = 0.0
    missing = []
    for seed in RANDOM_SEEDS:
        key = f"ic2_random_{seed}_s"
        if key not in phases:
            missing.append(key)
        else:
            random_s += float(phases[key])
    named = {
        "diff": float(phases.get("diff_s", 0.0)),
        "discovery": float(phases.get("discovery_s", 0.0)),
        "replay": float(phases.get("replay_s", 0.0)),
        "neighbor": float(phases.get("ic2_neighbor_s", 0.0)),
        "random": random_s,
        "verify": float(phases.get("verify_s", 0.0)),
        "parse": float(phases.get("parse_s", 0.0)),
    }
    for key in ("diff_s", "discovery_s", "replay_s", "ic2_neighbor_s", "verify_s", "parse_s"):
        if key not in phases:
            missing.append(key)
    return {"seconds": named, "missing": missing}


def shape_ok(shape: dict, stock_wall: float) -> tuple[bool, str]:
    if shape["missing"]:
        return False, "missing " + ", ".join(shape["missing"])
    seconds = shape["seconds"]
    if any(value <= 0 for value in seconds.values()):
        return False, "a phase is zero"
    if seconds["discovery"] <= max(value for name, value in seconds.items() if name != "discovery"):
        return False, "discovery is not strictly the largest phase"
    if seconds["diff"] >= min(value for name, value in seconds.items() if name != "diff"):
        return False, "diff is not strictly the smallest phase"
    if stock_wall > 0 and seconds["verify"] >= 0.25 * stock_wall:
        return False, "verify is a large fraction of stock"
    return True, "discovery largest, diff smallest, pads present"


def cv(values: list[float]) -> float:
    if len(values) < 2:
        return float("inf")
    mean = statistics.fmean(values)
    if mean <= 0:
        return float("inf")
    return statistics.stdev(values) / mean


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


def unpinned(
    db: Path,
    queries: Path,
    stock_tbl: Path,
    stock_dom: Path,
    dest: Path,
) -> dict:
    """Oracle replay of the stock hit set with -Z omitted. The pin control."""
    log("unpinned control")
    model_spans = index_models(db)
    order, fasta_spans = index_fasta(queries)
    cand: dict[str, set[str]] = {}
    for line in read_body(stock_tbl):
        fields = line.split()
        cand.setdefault(fields[2], set()).add(fields[0])
    keys = [key for key in order if cand.get(key)]
    batches = plan_batches(
        keys, cand, startup_pairs=REPLAY_STARTUP_PAIRS, press_pairs=REPLAY_PRESS_PAIRS
    )
    dest.mkdir(parents=True, exist_ok=True)
    tbl_parts: list[str] = []
    dom_parts: list[str] = []
    before = host_snap()
    t0 = time.perf_counter()
    for index, batch in enumerate(batches):
        work = dest / f"b{index}"
        work.mkdir()
        union = sorted(
            {model for key in batch for model in cand[key]},
            key=lambda name: model_spans[name][0],
        )
        write_span(db, [model_spans[name] for name in union], work / "db.hmm")
        write_span(queries, [fasta_spans[key] for key in batch], work / "q.faa")
        press_proc = subprocess.run(
            ["hmmpress", "-f", str(work / "db.hmm")],
            check=False,
            capture_output=True,
            text=True,
        )
        if press_proc.returncode != 0:
            raise SystemExit(f"unpinned hmmpress failed: {(press_proc.stderr or '')[-400:]}")
        cmd = [
            "hmmscan", "--cut_ga", "--noali", "--cpu", CPU,
            "--tblout", str(work / "tbl"),
            "--domtblout", str(work / "dom"),
            "-o", os.devnull,
            str(work / "db.hmm"),
            str(work / "q.faa"),
        ]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(f"unpinned hmmscan failed: {(proc.stderr or proc.stdout)[-400:]}")
        tbl_parts.append((work / "tbl").read_text())
        dom_parts.append((work / "dom").read_text())
        shutil.rmtree(work)
    wall = time.perf_counter() - t0
    tbl = merge_bodies(tbl_parts, 2, keys)
    dom = merge_bodies(dom_parts, 3, keys)
    (dest / "tblout").write_text(tbl)
    (dest / "domtblout").write_text(dom)
    compared = compare_pair(dest / "tblout", dest / "domtblout", stock_tbl, stock_dom)
    log(
        f"unpinned {wall:.1f}s batches={len(batches)} "
        f"byte_equal={compared['byte_equal']} classes={compared['tbl']['classes']}"
    )
    return {
        "wall_s": wall,
        "n_batches": len(batches),
        "n_records": len(keys),
        "pin": False,
        "before": before,
        "after": host_snap(),
        **compared,
    }


def public_repeat(row: dict) -> dict:
    keep = {
        "arm", "repeat", "wall_s", "before", "after", "decision", "why",
        "n_batches", "phases", "returncode", "compare", "shape", "shape_ok",
        "shape_why",
    }
    return {key: row[key] for key in keep if key in row}


def main() -> None:
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("STOP: this pilot runs only under sbatch")
    scratch = Path(os.environ["ACTS_SCRATCH"])
    genomes = Path(os.environ["ACTS_GENOMES"])
    old_gz = Path(os.environ["ACTS_PFAM_OLD"])
    new_gz = Path(os.environ["ACTS_PFAM_NEW"])
    scratch.mkdir(parents=True, exist_ok=True)
    kind = fstype(str(scratch))
    free = shutil.disk_usage(scratch).free
    mem = meminfo()
    log(f"scratch fstype={kind} free={free} scratch={scratch} mem={mem}")
    payload: dict = {
        "test": "headline-pilot",
        "seed": SEED,
        "expected_proteome": EXPECTED,
        "draw_index": DRAW_INDEX,
        "pool_n": POOL_N,
        "pool_sha256": POOL_SHA256,
        "excluded": list(EXCLUDE),
        "job_id": os.environ.get("SLURM_JOB_ID"),
        "cpu_model": cpu_model(),
        "git_head": os.environ.get("ACTS_GIT_HEAD", ""),
        "git_dirty": os.environ.get("ACTS_GIT_DIRTY", ""),
        "scratch": str(scratch),
        "scratch_fstype": kind,
        "scratch_free_bytes_start": free,
        "meminfo_start": mem,
        "pilot_notes": [
            "Resubmission of failed job 13087966, which stopped on its own guard '/tmp is tmpfs'.",
            "tmpfs scratch is allowed: the job holds the whole node's memory (--mem=0) and needs at least 40 GiB free.",
            "Walltime raised from 4 h to 6 h so a slow node cannot time out the pilot.",
        ],
        "cache_limit_bytes": CACHE_LIMIT,
        "mac_shape_s": MAC_SHAPE_S,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "press_charged_to_arms": False,
        "argv_stock": "hmmscan --cut_ga --noali --cpu 4 --tblout --domtblout",
        "argv_acts": (
            "python3 -m acts run --strategy reference --pin '-Z {entry_count}' "
            "--verify audit --prep 'hmmpress -f {reference}' -- hmmscan --cut_ga --noali --cpu 4"
        ),
    }
    global PAYLOAD
    PAYLOAD = payload
    if free < MIN_FREE:
        stop(f"scratch {scratch} has {free} bytes free, need {MIN_FREE}", payload)
    for path in (genomes, old_gz, new_gz):
        if not path.exists():
            stop(f"missing {path}", payload)
    version = subprocess.run(["hmmscan", "-h"], check=False, capture_output=True, text=True)
    version_line = (version.stdout or version.stderr or "").splitlines()[:3]
    payload["hmmer_version_lines"] = version_line
    payload["hmmer_tarball_sha256"] = os.environ.get("ACTS_HMMER_SHA256", "")
    if not any("HMMER 3.4" in line for line in version_line):
        stop(f"hmmscan is not HMMER 3.4: {version_line}", payload)

    try:
        proteome = draw(genomes)
    except RuntimeError as exc:
        stop(str(exc), payload)
    payload["proteome"] = proteome
    faa_gz = genomes / f"{proteome}_protein.faa.gz"
    payload["input_md5"] = {
        "pfam38.1": md5_file(old_gz),
        "pfam38.2": md5_file(new_gz),
        "proteome": md5_file(faa_gz),
    }
    if payload["input_md5"]["pfam38.1"] != MD5_OLD or payload["input_md5"]["pfam38.2"] != MD5_NEW:
        stop(f"pfam md5 {payload['input_md5']}", payload)

    queries = scratch / "queries.faa"
    log("decompress proteome")
    with gzip.open(faa_gz, "rb") as inp, queries.open("wb") as out:
        shutil.copyfileobj(inp, out, length=1 << 20)
    hmm_old = scratch / "pfam38.1.hmm"
    hmm_new = scratch / "pfam38.2.hmm"
    press_old_decompress = decompress(old_gz, hmm_old)
    press_old = press(hmm_old)
    press_new_decompress = decompress(new_gz, hmm_new)
    press_new = press(hmm_new)
    headers_old, ends_old = count_models(hmm_old)
    headers_new, ends_new = count_models(hmm_new)
    payload["press"] = {
        "38.1": {"decompress_s": press_old_decompress, "hmmpress_s": press_old, "headers": headers_old, "ends": ends_old},
        "38.2": {"decompress_s": press_new_decompress, "hmmpress_s": press_new, "headers": headers_new, "ends": ends_new},
    }
    write_out(payload)
    if (headers_old, ends_old) != (Z_OLD, Z_OLD) or (headers_new, ends_new) != (Z_NEW, Z_NEW):
        stop(f"model counts {payload['press']}", payload)

    stock_old = stock(hmm_old, queries, scratch / "stock_38.1")
    payload["stock_38_1"] = public_repeat({**stock_old, "repeat": 0})
    fill_cache = scratch / "cache_38.1.sqlite"
    fill = cli(hmm_old, queries, fill_cache, scratch / "fill")
    filled = cache_bytes(fill_cache)
    payload["fill"] = {
        **public_repeat({**fill, "repeat": 0}),
        "cache_bytes": filled,
    }
    payload["first_run_overhead"] = (
        fill["wall_s"] / stock_old["wall_s"] if stock_old["wall_s"] else None
    )
    write_out(payload)
    if fill["decision"] != "SHIP":
        stop(f"fill decision {fill['decision']}: {fill.get('why')}", payload)
    if filled > CACHE_LIMIT:
        stop(f"cache {filled} bytes exceeds {CACHE_LIMIT}", payload)

    snapshot = scratch / "cache_38.1.snapshot.sqlite"
    restore_cache(fill_cache, snapshot)
    repeats: list[dict] = []
    stock_bodies: list[tuple[list[str], list[str]]] = []
    for index in range(1, 4):
        arm_a = stock(hmm_new, queries, scratch / f"A{index}")
        arm_a["repeat"] = index
        repeats.append(arm_a)
        stock_bodies.append((read_body(Path(arm_a["tbl"])), read_body(Path(arm_a["dom"]))))
        work_cache = scratch / f"cache_B{index}.sqlite"
        restore_cache(snapshot, work_cache)
        arm_b = cli(hmm_new, queries, work_cache, scratch / f"B{index}")
        arm_b["repeat"] = index
        compared = compare_pair(arm_b["tbl"], arm_b["dom"], Path(arm_a["tbl"]), Path(arm_a["dom"]))
        shaped = shape_of(arm_b["phases"])
        ok, why = shape_ok(shaped, arm_a["wall_s"])
        arm_b["compare"] = compared
        arm_b["shape"] = shaped
        arm_b["shape_ok"] = ok
        arm_b["shape_why"] = why
        repeats.append(arm_b)
        payload["repeats"] = [public_repeat(row) for row in repeats]
        write_out(payload)
        log(f"B{index} byte_equal={compared['byte_equal']} shape={ok} {why}")

    same_stock = all(body == stock_bodies[0] for body in stock_bodies[1:])
    payload["stock_vs_stock_byte_equal"] = same_stock
    control = unpinned(
        hmm_new, queries, Path(repeats[0]["tbl"]), Path(repeats[0]["dom"]), scratch / "unpinned"
    )
    payload["unpinned"] = {
        "wall_s": control["wall_s"],
        "n_batches": control["n_batches"],
        "n_records": control["n_records"],
        "pin": False,
        "before": control["before"],
        "after": control["after"],
        "tbl": control["tbl"],
        "dom": control["dom"],
        "byte_equal": control["byte_equal"],
        "differs": not control["byte_equal"],
    }
    walls_a = [row["wall_s"] for row in repeats if row["arm"] == "A"]
    walls_b = [row["wall_s"] for row in repeats if row["arm"] == "B"]
    payload["cv"] = {"A": cv(walls_a), "B": cv(walls_b), "estimator": "stdev/mean", "n": 3}
    payload["median_wall_s"] = {"A": statistics.median(walls_a), "B": statistics.median(walls_b)}
    reasons: list[str] = []
    if not same_stock:
        reasons.append("stock 38.2 repeats are not byte-identical")
    for row in repeats:
        if row["arm"] != "B":
            continue
        if row.get("decision") != "SHIP" or not row["compare"]["byte_equal"]:
            reasons.append(f"B{row['repeat']} is not byte-identical ({row.get('decision')})")
        if not row["shape_ok"]:
            reasons.append(f"B{row['repeat']} phase shape: {row['shape_why']}")
    if payload["cv"]["A"] >= CV_LIMIT:
        reasons.append(f"CV A {payload['cv']['A']:.4f}")
    if payload["cv"]["B"] >= CV_LIMIT:
        reasons.append(f"CV B {payload['cv']['B']:.4f}")
    if not payload["unpinned"]["differs"]:
        reasons.append("unpinned control is byte-identical")
    payload["fail_reasons"] = reasons
    payload["pilot_pass"] = not reasons
    payload["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_out(payload)
    log(f"pilot_pass={payload['pilot_pass']} reasons={reasons}")
    if reasons:
        raise SystemExit(1)


PAYLOAD: dict | None = None


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:  # record why the pilot ended, then re-raise
        if PAYLOAD is not None and "pilot_pass" not in PAYLOAD:
            PAYLOAD["crashed"] = f"{type(exc).__name__}: {exc}"[:2000]
            PAYLOAD["pilot_pass"] = False
            write_out(PAYLOAD)
        raise
