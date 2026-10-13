#!/usr/bin/env python3
"""Pilot for --cut_ga exactness at the Q1000 sample. Not a measured result.

Design is E1/E2 from docs/EXACT_REPLAY_PROTOCOL.md. The Q1000 draw (seed
20261013) is pilot data and is not reused for the measured run.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
DATA = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data")
WORK = Path("/Users/joshuaterranova/tmp/e1scale_work")
HMMER = Path("/opt/homebrew/bin")
CPU = "4"
Z_NEW = 30134
Q_FASTA = DATA / "recurrence/A/GCF_002853805.1_protein.faa.gz"
PFAM_382_GZ = DATA / "hmmer/Pfam-A.hmm.gz"
PFAM_381_GZ = DATA / "hmmer/pfam38.1/Pfam-A.hmm.gz"
PFAM_382 = WORK / "pfam38.2.hmm"
PFAM_381 = WORK / "pfam38.1.hmm"
Q1000_SHA = "ffaa279d4ceb09c9bc89641996f023b46f83f375c3933a0ce1db651c64f2eb7c"
Q300_SHA = "3a6e66691257ebdc2aea15c5682fab45afcb19d851c0b4d287381d9d651a7659"
MIN_FREE = 3 * 1024**3


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def free_bytes() -> int:
    return shutil.disk_usage(WORK).free


def require_free() -> None:
    free = free_bytes()
    if free < MIN_FREE:
        raise SystemExit(f"stop: {free} bytes free under {WORK}, need {MIN_FREE}")


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_fasta(path: Path) -> list[str]:
    recs: list[str] = []
    opener = gzip.open if str(path).endswith(".gz") else open
    buf: list[str] = []
    with opener(path, "rt") as fh:
        for line in fh:
            if line.startswith(">") and buf:
                recs.append("".join(buf))
                buf = [line]
            else:
                buf.append(line)
        if buf:
            recs.append("".join(buf))
    return recs


def write_sample(recs: list[str], dest: Path, seed: int, k: int, expect: str) -> dict:
    rng = random.Random(seed)
    idxs = rng.sample(range(len(recs)), k)
    idxs.sort()
    dest.write_text("".join(recs[i] for i in idxs))
    digest = hashlib.sha256(",".join(map(str, idxs)).encode()).hexdigest()
    if digest != expect:
        raise SystemExit(f"sample sha {digest} != {expect} (seed {seed} k {k})")
    return {
        "seed": seed,
        "k": k,
        "n_records": len(recs),
        "sample_sha256": digest,
        "index_first": idxs[0],
        "index_last": idxs[-1],
    }


def body(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines(keepends=True) if not line.startswith("#")]


def scan(db: Path, queries: Path, tag: Path, z: int | None = None) -> float:
    ok = Path(str(tag) + ".ok")
    if ok.is_file() and Path(str(tag) + ".tbl").is_file() and Path(str(tag) + ".dom").is_file():
        meta = json.loads(ok.read_text())
        log(f"reuse {tag.name} wall={meta['wall_s']:.1f}s")
        return float(meta["wall_s"])
    require_free()
    cmd = [str(HMMER / "hmmscan"), "--cut_ga", "--noali", "--cpu", CPU]
    if z is not None:
        cmd += ["-Z", str(z)]
    cmd += [
        "--tblout", str(tag) + ".tbl",
        "--domtblout", str(tag) + ".dom",
        "-o", os.devnull,
        str(db),
        str(queries),
    ]
    log(" ".join(cmd))
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-800:]
        raise SystemExit(f"hmmscan failed ({proc.returncode}): {err}")
    ok.write_text(json.dumps({"wall_s": wall, "argv": cmd}) + "\n")
    log(f"done {tag.name} {wall:.1f}s")
    return wall


def row_key(tokens: list[str], kind: str) -> tuple:
    if kind == "tbl":
        return (tokens[0], tokens[2])
    return (tokens[0], tokens[3], tokens[15], tokens[16], tokens[17], tokens[18])


def classify(replay: list[str], stock: list[str], kind: str) -> dict:
    n = max(len(replay), len(stock))
    differing = sum(
        1
        for i in range(n)
        if (replay[i] if i < len(replay) else None) != (stock[i] if i < len(stock) else None)
    )
    rt = [line.split() for line in replay]
    st = [line.split() for line in stock]
    byte_equal = replay == stock
    token_equal = rt == st
    out: dict = {
        "lines_replay": len(replay),
        "lines_stock": len(stock),
        "byte_equal": byte_equal,
        "token_equal": token_equal,
        "differing_positions": differing,
        "differs_on_every_line": bool(n) and len(replay) == len(stock) and differing == n,
        "classes": [],
    }
    if byte_equal:
        return out
    if token_equal:
        out["classes"] = ["whitespace-only"]
        return out
    rk = [row_key(toks, kind) for toks in rt]
    sk = [row_key(toks, kind) for toks in st]
    rc, sc = Counter(rk), Counter(sk)
    missing = [list(key) for key in sc if sc[key] > rc[key]]
    extra = [list(key) for key in rc if rc[key] > sc[key]]
    classes: list[str] = []
    if missing:
        classes.append("missing")
    if extra:
        classes.append("extra")
    if not missing and not extra and rk != sk:
        classes.append("order")
    buckets: dict[tuple, list[list[str]]] = {}
    for toks in rt:
        buckets.setdefault(row_key(toks, kind), []).append(toks)
    value = False
    for toks in st:
        key = row_key(toks, kind)
        group = buckets.get(key)
        if not group:
            continue
        if group.pop(0) != toks:
            value = True
    if value:
        classes.append("value-only")
    out["classes"] = classes
    out["missing_keys"] = len(missing)
    out["extra_keys"] = len(extra)
    out["missing_key_examples"] = missing[:8]
    out["extra_key_examples"] = extra[:8]
    if replay and stock:
        out["first_replay"] = replay[0][:240]
        out["first_stock"] = stock[0][:240]
    return out


def classify_pair(replay_tag: Path, stock_tag: Path) -> dict:
    return {
        "tbl": classify(body(Path(str(replay_tag) + ".tbl")), body(Path(str(stock_tag) + ".tbl")), "tbl"),
        "dom": classify(body(Path(str(replay_tag) + ".dom")), body(Path(str(stock_tag) + ".dom")), "dom"),
    }


def both_byte(report: dict) -> bool:
    return bool(report["tbl"]["byte_equal"] and report["dom"]["byte_equal"])


def run_driver(queries: Path, stock_new: Path, stock_old: Path, work: Path, dest: Path) -> dict:
    if dest.is_file():
        log(f"reuse driver {dest.name}")
        return json.loads(dest.read_text())
    work.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(PIPE / "scripts/exact_replay_hmmscan.py"),
        "--work", str(work),
        "--queries", str(queries),
        "--new-gz", str(PFAM_382_GZ),
        "--stock-new", str(stock_new),
        "--old-gz", str(PFAM_381_GZ),
        "--stock-old", str(stock_old),
        "--cpu", CPU,
        "--out", str(dest),
    ]
    log("driver " + queries.name)
    proc = subprocess.run(cmd, check=False, cwd=PIPE, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"driver failed ({proc.returncode}): {(proc.stderr or proc.stdout)[-1200:]}")
    return json.loads(dest.read_text())


def stream_models(src: Path, keep: set[str], dest: Path) -> int:
    n = 0
    buf: list[str] = []
    name = ""
    with open(dest, "w") as out, open(src) as fh:
        for line in fh:
            buf.append(line)
            if line.startswith("NAME "):
                name = line.split(None, 1)[1].strip()
            elif line.startswith("//"):
                if name in keep:
                    out.write("".join(buf))
                    n += 1
                buf, name = [], ""
    for ext in (".h3f", ".h3i", ".h3m", ".h3p"):
        side = Path(str(dest) + ext)
        if side.exists():
            side.unlink()
    subprocess.run([str(HMMER / "hmmpress"), "-f", str(dest)], check=True, capture_output=True)
    return n


def hits(tbl: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in body(tbl):
        fields = line.split()
        out.setdefault(fields[2], []).append(fields[0])
    return out


def subset_fasta(src: Path, keep: set[str], dest: Path) -> int:
    n = 0
    on = False
    rows: list[str] = []
    for line in src.read_text().splitlines(keepends=True):
        if line.startswith(">"):
            on = line[1:].split()[0] in keep
            n += on
        if on:
            rows.append(line)
    dest.write_text("".join(rows))
    return n


def inject(stock_tbl: Path, queries: Path, dest_dir: Path) -> dict:
    """Drop 5% of oracle candidate models and rerun the pinned replay."""
    stamp = dest_dir / "inject.json"
    if stamp.is_file():
        log("reuse inject")
        return json.loads(stamp.read_text())
    dest_dir.mkdir(parents=True, exist_ok=True)
    found = hits(stock_tbl)
    models = sorted({name for names in found.values() for name in names})
    k = max(1, int(round(0.05 * len(models))))
    rng = random.Random(20261013)
    dropped = sorted(rng.sample(models, k))
    kept = set(models) - set(dropped)
    n_models = stream_models(PFAM_382, kept, dest_dir / "db.hmm")
    n_queries = subset_fasta(queries, set(found), dest_dir / "q.faa")
    wall = scan(dest_dir / "db.hmm", dest_dir / "q.faa", dest_dir / "R", Z_NEW)
    report = classify_pair(dest_dir / "R", stock_tbl.with_suffix(""))
    payload = {
        "candidate_models": len(models),
        "dropped": k,
        "dropped_names": dropped,
        "replay_models": n_models,
        "replay_queries": n_queries,
        "wall_s": wall,
        "vs_stock": report,
        "differs": not both_byte(report),
        "missing_reported": "missing" in report["tbl"]["classes"] or "missing" in report["dom"]["classes"],
    }
    stamp.write_text(json.dumps(payload, indent=2) + "\n")
    dest_dir.joinpath("db.hmm").unlink(missing_ok=True)
    return payload


def run_cli(reference: Path, queries: Path, cache: Path, out: Path, verify: str) -> dict:
    stamp = out / "cli_stamp.json"
    if stamp.is_file():
        log(f"reuse cli {out.name}")
        return json.loads(stamp.read_text())
    out.mkdir(parents=True, exist_ok=True)
    require_free()
    cmd = [
        sys.executable, "-m", "acts", "run",
        "--strategy", "reference",
        "--pin", "-Z {entry_count}",
        "--verify", verify,
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
    log(f"cli {reference.name} verify={verify}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=PIPE, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    calls = out / "calls"
    if calls.is_dir():
        shutil.rmtree(calls)
    if proc.returncode not in (0, 1):
        raise SystemExit(f"cli crashed ({proc.returncode}): {(proc.stderr or proc.stdout)[-1500:]}")
    decision = (out / "decision.txt").read_text() if (out / "decision.txt").is_file() else ""
    payload = {
        "returncode": proc.returncode,
        "wall_s": wall,
        "verify": verify,
        "decision_text": decision,
        "stdout_tail": proc.stdout[-1500:],
        "stderr_tail": proc.stderr[-800:],
    }
    stamp.write_text(json.dumps(payload, indent=2) + "\n")
    log(f"cli {out.name} rc={proc.returncode} {wall:.1f}s")
    return payload


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PIPE, check=True, capture_output=True, text=True
    ).stdout.strip()


def hmm_version() -> str:
    text = subprocess.run([str(HMMER / "hmmscan"), "-h"], check=True, capture_output=True, text=True).stdout
    return text.splitlines()[1]


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    for path in (PFAM_382, PFAM_381, Q_FASTA, PFAM_382_GZ, PFAM_381_GZ):
        if not path.is_file():
            raise SystemExit(f"missing input {path}")
    require_free()
    log("reading proteome")
    recs = read_fasta(Q_FASTA)
    q1000 = write_sample(recs, WORK / "q1000.faa", 20261013, 1000, Q1000_SHA)
    q300 = write_sample(recs, WORK / "q300.faa", 20261012, 300, Q300_SHA)
    log(f"samples ok q1000={q1000['index_first']}..{q1000['index_last']} q300 n={q300['k']}")

    t_a = scan(PFAM_382, WORK / "q1000.faa", WORK / "q1000_S382_a")
    t_b = scan(PFAM_382, WORK / "q1000.faa", WORK / "q1000_S382_b")
    determinism = classify_pair(WORK / "q1000_S382_a", WORK / "q1000_S382_b")
    if not both_byte(determinism):
        dest = PIPE / "results/exact_replay/e1scale_pilot.json"
        dest.write_text(json.dumps({"pilot": True, "stopped": "stock-vs-stock", "determinism": determinism}, indent=2) + "\n")
        raise SystemExit("stock-vs-stock failed; no arm ran")
    log("stock-vs-stock byte-identical")

    t_old = scan(PFAM_381, WORK / "q1000.faa", WORK / "q1000_S381")
    driver = run_driver(
        WORK / "q1000.faa",
        WORK / "q1000_S382_a",
        WORK / "q1000_S381",
        WORK / "q1000_driver",
        WORK / "q1000_driver.json",
    )
    e1 = classify_pair(WORK / "q1000_driver" / "e1_R", WORK / "q1000_S382_a")
    rn = classify_pair(WORK / "q1000_driver" / "e1_Rn", WORK / "q1000_S382_a")
    e2 = classify_pair(WORK / "q1000_driver" / "e2_R", WORK / "q1000_S382_a")
    log(f"Q1000 E1 byte={both_byte(e1)} Rn every={rn['tbl']['differs_on_every_line']} E2 byte={both_byte(e2)}")

    injected = inject(WORK / "q1000_S382_a.tbl", WORK / "q1000.faa", WORK / "q1000_inject")
    log(f"inject differs={injected['differs']} missing={injected['missing_reported']} classes tbl={injected['vs_stock']['tbl']['classes']}")

    t300_new = scan(PFAM_382, WORK / "q300.faa", WORK / "q300_S382")
    t300_old = scan(PFAM_381, WORK / "q300.faa", WORK / "q300_S381")
    driver300 = run_driver(
        WORK / "q300.faa",
        WORK / "q300_S382",
        WORK / "q300_S381",
        WORK / "q300_driver",
        WORK / "q300_driver.json",
    )
    e1_300 = classify_pair(WORK / "q300_driver" / "e1_R", WORK / "q300_S382")
    e2_300 = classify_pair(WORK / "q300_driver" / "e2_R", WORK / "q300_S382")
    rn_300 = classify_pair(WORK / "q300_driver" / "e1_Rn", WORK / "q300_S382")
    log(f"Q300 E1 byte={both_byte(e1_300)} E2 byte={both_byte(e2_300)}")

    cache = WORK / "cli_cache.sqlite"
    cli_old = run_cli(PFAM_381, WORK / "q1000.faa", cache, WORK / "cli_381", "audit")
    cli_new = run_cli(PFAM_382, WORK / "q1000.faa", cache, WORK / "cli_382", "full")
    tbl_out = WORK / "cli_382" / "tables" / "tblout"
    dom_out = WORK / "cli_382" / "tables" / "domtblout"
    if tbl_out.is_file() and dom_out.is_file():
        cli_cmp = {
            "tbl": classify(body(tbl_out), body(WORK / "q1000_S382_a.tbl"), "tbl"),
            "dom": classify(body(dom_out), body(WORK / "q1000_S382_a.dom"), "dom"),
        }
        cli_byte = both_byte(cli_cmp)
    else:
        cli_cmp = {"error": "cli did not write tables"}
        cli_byte = False
    log(f"CLI byte={cli_byte}")

    for folder in (WORK / "q1000_driver", WORK / "q300_driver"):
        for path in folder.glob("*.hmm"):
            path.unlink(missing_ok=True)
            for ext in (".h3f", ".h3i", ".h3m", ".h3p"):
                Path(str(path) + ext).unlink(missing_ok=True)

    report = {
        "pilot": True,
        "protocol": "docs/EXACT_REPLAY_PROTOCOL.md",
        "semantics": "results/exact_replay/e1scale_semantics.md",
        "git_head": git_head(),
        "host": platform.node(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "hmmscan": hmm_version(),
        "cpu": 4,
        "walls_indicative": True,
        "input_md5": {
            "Pfam-A.hmm.gz": md5_file(PFAM_382_GZ),
            "pfam38.1/Pfam-A.hmm.gz": md5_file(PFAM_381_GZ),
            "GCF_002853805.1_protein.faa.gz": md5_file(Q_FASTA),
        },
        "pressed_models": {"38.2": 30134, "38.1": 27481},
        "Q1000": q1000,
        "Q300": q300,
        "determinism": {"walls_s": {"run_1": t_a, "run_2": t_b}, "vs": determinism, "pass": True},
        "E1": {"driver": driver.get("E1"), "vs_stock": e1, "byte_equal": both_byte(e1)},
        "Rn": {"vs_stock": rn, "differs_on_every_line": rn["tbl"]["differs_on_every_line"] and rn["dom"]["differs_on_every_line"]},
        "E2_driver": {"driver": driver.get("E2"), "vs_stock": e2, "byte_equal": both_byte(e2)},
        "injected": injected,
        "known_good_300": {
            "walls_s": {"38.2": t300_new, "38.1": t300_old},
            "E1_byte_equal": both_byte(e1_300),
            "E2_byte_equal": both_byte(e2_300),
            "Rn_differs_on_every_line": rn_300["tbl"]["differs_on_every_line"] and rn_300["dom"]["differs_on_every_line"],
            "E1": e1_300,
            "E2": e2_300,
            "driver_E1": driver300.get("E1"),
            "driver_E2": driver300.get("E2"),
        },
        "cli": {
            "fill_38.1": {k: cli_old[k] for k in ("returncode", "wall_s", "verify", "decision_text")},
            "replay_38.2": {k: cli_new[k] for k in ("returncode", "wall_s", "verify", "decision_text")},
            "vs_independent_stock": cli_cmp,
            "byte_equal": cli_byte,
        },
        "free_bytes_end": free_bytes(),
    }
    dest = PIPE / "results/exact_replay/e1scale_pilot.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    log(f"wrote {dest}")


if __name__ == "__main__":
    main()
