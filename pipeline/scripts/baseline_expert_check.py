#!/usr/bin/env python3
"""Laptop checks for the expert scripts. Walls are not speed evidence.

    python3 scripts/baseline_expert_check.py batchtest
    python3 scripts/baseline_expert_check.py pilot
    python3 scripts/baseline_expert_check.py measured
    python3 scripts/baseline_expert_check.py diamond
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import platform
import random
import signal
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from acts.reference_formats import read_records  # noqa: E402
from acts.replay_batch import plan_batches  # noqa: E402
import baseline_rescale as rescale  # noqa: E402

DATA = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data")
SCRATCH = Path.home() / "tmp" / "tare_d"
HMM = Path("/opt/homebrew/bin")
DIAMOND = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/builds/diamond-2.2.5/diamond")
OLD_FA = DATA / "swissprot" / "uniprot_sprot_2026_01.fasta.gz"
NEW_FA = DATA / "swissprot" / "uniprot_sprot_2026_03.fasta.gz"
SCRIPT = Path(__file__).resolve().parent / "expert_update_hmmscan.sh"
DIAMOND_SCRIPT = Path(__file__).resolve().parent / "expert_update_diamond.sh"
OUT_DIR = ROOT / "results" / "baselines_exact"
RSS_LIMIT = 3 * 1024 ** 3
COSTPASS = ["GCF_016806025.1", "GCF_017165095.1"]
DX3_SEED = 20261029
DX3_N = 2000
DX3_GENOME = DATA / "recurrence" / "A" / "GCF_001515725.1_protein.faa.gz"
DX3_RECORDS = 4407
PINNED_LETTERS = 209017843
INTERVAL = (6, 7, 8, 9)


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def git_head() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT.parent, check=True, capture_output=True, text=True)
    return proc.stdout.strip()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def line_count(path: Path) -> int:
    with path.open() as handle:
        return sum(1 for _ in handle)


def group_rss(pgid: int) -> int:
    proc = subprocess.run(["ps", "-o", "rss=", "-g", str(pgid)], capture_output=True, text=True, check=False)
    total = 0
    for line in proc.stdout.splitlines():
        text = line.strip()
        if text.isdigit():
            total += int(text)
    return total * 1024


def run_watched(cmd: list[str], log_path: Path, env: dict[str, str]) -> dict:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timed = ["/usr/bin/time", "-l", "nice", "-n", "10", *cmd]
    with log_path.open("w") as handle:
        proc = subprocess.Popen(
            timed,
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        peak = 0
        killed = False
        while proc.poll() is None:
            rss = group_rss(proc.pid)
            peak = max(peak, rss)
            if rss > RSS_LIMIT:
                os.killpg(proc.pid, signal.SIGKILL)
                killed = True
                proc.wait(timeout=30)
                break
            time.sleep(0.25)
        code = proc.returncode if proc.returncode is not None else proc.wait()
    text = log_path.read_text(errors="replace")
    resident = None
    for line in text.splitlines():
        if "maximum resident set size" in line:
            token = line.split()[0]
            if token.isdigit():
                resident = int(token)
    peak = max(peak, resident or 0)
    return {
        "argv": cmd,
        "returncode": code,
        "killed_over_rss": killed,
        "peak_rss_bytes": peak,
        "log": str(log_path),
    }


def base_env(work: Path, **extra: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "CPU": "2",
        "WORK": str(work),
        "HMMSCAN": str(HMM / "hmmscan"),
        "HMMFETCH": str(HMM / "hmmfetch"),
        "HMMPRESS": str(HMM / "hmmpress"),
        "DIAMOND": str(DIAMOND),
        "LC_ALL": "C",
    })
    env.update(extra)
    return env


def provenance() -> dict:
    version = subprocess.run([str(HMM / "hmmscan"), "-h"], capture_output=True, text=True).stdout.splitlines()
    return {
        "git_head": git_head(),
        "host": platform.node(),
        "python": platform.python_version(),
        "hmmscan": version[1] if len(version) > 1 else "",
        "cpu": 2,
        "walls_are_evidence": False,
        "script_lines": {
            "expert_update_hmmscan.sh": line_count(SCRIPT),
            "expert_batch.awk": line_count(SCRIPT.parent / "expert_batch.awk"),
            "expert_update_diamond.sh": line_count(DIAMOND_SCRIPT),
        },
    }


def relabel(stats: dict) -> dict:
    copied = dict(stats)
    copied["expert_lines"] = copied["rescaler_lines"]
    return copied


def batchtest() -> None:
    rng = random.Random(0)
    cases = []
    cases.append((["only"], {"only": {"a"}}))
    records = [f"q{i:03d}" for i in range(40)]
    cand = {rec: {f"c{rng.randrange(12):03d}" for _ in range(rng.randrange(1, 5))} for rec in records}
    cases.append((records, cand))
    records = [f"p{i}" for i in range(17)]
    names = ["PhnJ", "Peptidase_S6", "DAGK_prokar", "MFS_1", "AAA"]
    cand = {rec: {names[rng.randrange(len(names))] for _ in range(rng.randrange(1, 4))} for rec in records}
    cases.append((records, cand))
    for record_order, candidates in cases:
        lines = []
        for index, key in enumerate(record_order):
            if not candidates.get(key):
                continue
            lines.append(f"{index}\t{key}\t{','.join(sorted(candidates[key]))}")
        proc = subprocess.run(
            [str(SCRIPT), "--plan"],
            input="\n".join(lines) + "\n",
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise SystemExit(f"plan failed\n{proc.stderr}")
        got: dict[str, list[str]] = defaultdict(list)
        order = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            batch, query = line.split("\t")
            if batch not in got:
                order.append(batch)
            got[batch].append(query)
        expected = plan_batches(record_order, candidates, startup_pairs=2000, press_pairs=84)
        found = [got[batch] for batch in order]
        if found != expected:
            raise SystemExit(f"BATCH_MISMATCH expected={expected[:3]} got={found[:3]} n={len(expected)} vs {len(found)}")
    empty = subprocess.run([str(SCRIPT), "--plan"], input="", text=True, capture_output=True, check=True)
    if empty.stdout.strip():
        raise SystemExit("empty plan was not empty")
    log("batchtest pass")


def score_expert(stock_tbl: Path, stock_dom: Path, old_tbl: Path, queries: Path, work: Path, out_prefix: Path, *, omit_z: bool) -> dict:
    env = base_env(work, **({"EXPERT_OMIT_Z": "1"} if omit_z else {}))
    if work.exists():
        subprocess.run(["rm", "-rf", str(work)], check=True)
    started = time.perf_counter()
    watched = run_watched(
        [str(SCRIPT), str(SCRATCH / "hmm" / "pfam38.1.hmm"), str(SCRATCH / "hmm" / "pfam38.2.hmm"), str(old_tbl), str(queries), str(out_prefix)],
        work.parent / (work.name + ".log"),
        env,
    )
    watched["wall_s"] = time.perf_counter() - started
    if watched["killed_over_rss"] or watched["peak_rss_bytes"] > RSS_LIMIT:
        raise SystemExit(f"STOP_RSS {watched}")
    if watched["returncode"] != 0:
        raise SystemExit(f"expert script failed {watched}")
    tbl = relabel(rescale.compare_bodies(rescale.body_lines(stock_tbl), rescale.body_lines(Path(str(out_prefix) + ".tbl")), "tbl"))
    dom = relabel(rescale.compare_bodies(rescale.body_lines(stock_dom), rescale.body_lines(Path(str(out_prefix) + ".dom")), "dom"))
    return {"run": watched, "tbl": tbl, "dom": dom, "bodies_equal": tbl["bodies_equal"] and dom["bodies_equal"]}


def pilot() -> None:
    queries = SCRATCH / "pilot" / "queries.faa"
    old_tbl = SCRATCH / "pilot" / "S381.tbl"
    stock_tbl = SCRATCH / "pilot" / "S382_a.tbl"
    stock_dom = SCRATCH / "pilot" / "S382_a.dom"
    old_dom = SCRATCH / "pilot" / "S381.dom"
    for path in (queries, old_tbl, old_dom, stock_tbl, stock_dom):
        if not path.is_file():
            raise SystemExit(f"STOP D1 pilot output missing: {path}")
    positive = score_expert(stock_tbl, stock_dom, old_tbl, queries, SCRATCH / "expert_pilot" / "work", SCRATCH / "expert_pilot" / "out", omit_z=False)
    negative = score_expert(stock_tbl, stock_dom, old_tbl, queries, SCRATCH / "expert_pilot_neg" / "work", SCRATCH / "expert_pilot_neg" / "out", omit_z=True)
    if negative["bodies_equal"]:
        raise SystemExit("NEGATIVE_CONTROL_FAIL expert omit-Z matched stock")
    report = {
        "mode": "pilot",
        "pilot": True,
        "seed": rescale.PILOT_SEED,
        "proteome": rescale.PILOT_PROTEOME,
        **provenance(),
        "positive_bodies_equal": positive["bodies_equal"],
        "negative_control_differs": not negative["bodies_equal"],
        "positive": positive,
        "negative_tbl_byte_identical": negative["tbl"]["byte_identical"],
        "negative_dom_byte_identical": negative["dom"]["byte_identical"],
        "label": "PILOT_EXACT" if positive["bodies_equal"] else "PILOT_DIFF",
    }
    # The run payload includes a log path and is large enough; drop nothing the
    # protocol asked for. Peak RSS is the control that the cap held.
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / "expert_pilot.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    log(f"{report['label']} wrote {dest}")


def measured() -> None:
    rows = []
    for index, stem in enumerate(COSTPASS):
        work = SCRATCH / "measured" / stem
        queries = work / "queries.faa"
        old_tbl = work / "S381.tbl"
        if index == 0:
            stock_tbl, stock_dom = work / "S382_a.tbl", work / "S382_a.dom"
        else:
            stock_tbl, stock_dom = work / "S382.tbl", work / "S382.dom"
        for path in (queries, old_tbl, stock_tbl, stock_dom):
            if not path.is_file():
                raise SystemExit(f"STOP D1 stock missing: {path}")
        row = score_expert(
            stock_tbl, stock_dom, old_tbl, queries,
            SCRATCH / "expert_measured" / stem / "work",
            SCRATCH / "expert_measured" / stem / "out",
            omit_z=False,
        )
        row["proteome"] = stem
        rows.append(row)
        log(f"{stem} bodies_equal={row['bodies_equal']}")
    exact = all(row["bodies_equal"] for row in rows)
    report = {
        "mode": "measured",
        "pilot": False,
        "proteomes_named": COSTPASS,
        **provenance(),
        "label": "EXACT" if exact else "DIFF",
        "proteomes": rows,
    }
    dest = OUT_DIR / "expert_laptop.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    log(f"{report['label']} wrote {dest}")


def write_queries(records, indices: list[int], dest: Path) -> None:
    lines = []
    for index in indices:
        rec = records[index]
        desc = f" {rec.description}" if rec.description else ""
        lines.append(f">{rec.name}{desc}\n{rec.sequence}\n")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(lines))


def diamond_blast(db: Path, query: Path, out: Path, letters: int, log_path: Path) -> dict:
    cmd = [
        str(DIAMOND), "blastp", "--db", str(db), "--query", str(query), "--out", str(out),
        "--min-score", "40", "-k", "0", "--motif-masking", "0", "-b", "2.0",
        "--comp-based-stats", "1", "--threads", "2", "--dbsize", str(letters),
        "--outfmt", "6", "qseqid", "sseqid", "pident", "length", "mismatch", "gapopen",
        "qstart", "qend", "sstart", "send", "evalue", "bitscore",
    ]
    watched = run_watched(cmd, log_path, os.environ.copy())
    watched["wall_s_is_evidence"] = False
    return watched


def classify_m8(stock: list[str], other: list[str]) -> dict:
    stock_by: dict[tuple[str, str], list[str]] = defaultdict(list)
    other_by: dict[tuple[str, str], list[str]] = defaultdict(list)
    for line in stock:
        cells = line.split()
        stock_by[(cells[0], cells[1])].append(line)
    for line in other:
        cells = line.split()
        other_by[(cells[0], cells[1])].append(line)
    missing = extra = value_only = different_row = identical = 0
    examples: dict[str, list[str]] = {"missing": [], "extra": [], "value-only": [], "different-row": []}
    for key in set(stock_by) | set(other_by):
        left = stock_by.get(key, [])
        right = other_by.get(key, [])
        if len(left) > len(right):
            missing += len(left) - len(right)
            examples["missing"].extend(left[len(right):])
        elif len(right) > len(left):
            extra += len(right) - len(left)
            examples["extra"].extend(right[len(left):])
        for a_line, b_line in zip(left, right):
            a, b = a_line.split(), b_line.split()
            if a_line == b_line:
                identical += 1
                continue
            same_interval = len(a) > 9 and len(b) > 9 and tuple(a[i] for i in INTERVAL) == tuple(b[i] for i in INTERVAL)
            if same_interval:
                value_only += 1
                if len(examples["value-only"]) < 20:
                    examples["value-only"].append(a_line + " || " + b_line)
            else:
                different_row += 1
                if len(examples["different-row"]) < 20:
                    examples["different-row"].append(a_line + " || " + b_line)
    classes = []
    for name, count in (
        ("value-only", value_only), ("different-row", different_row),
        ("missing", missing), ("extra", extra),
    ):
        if count:
            classes.append(name)
    if identical == len(stock) == len(other) and stock != other:
        classes.append("order")
    for key in examples:
        examples[key] = examples[key][:20]
    return {
        "stock_lines": len(stock),
        "expert_lines": len(other),
        "byte_identical": identical,
        "value_only": value_only,
        "different_row": different_row,
        "missing": missing,
        "extra": extra,
        "difference_classes": classes,
        "examples": examples,
        "bodies_equal": stock == other,
        "script_noticed": False,
    }


def diamond() -> None:
    if not DIAMOND.is_file():
        raise SystemExit(f"STOP diamond missing {DIAMOND}")
    info = subprocess.run([str(DIAMOND), "dbinfo", "--db", str(NEW_FA)], capture_output=True, text=True, check=False)
    if info.returncode != 0:
        raise SystemExit(f"STOP dbinfo {(info.stderr or info.stdout)[-400:]}")
    letters = None
    for line in info.stdout.splitlines():
        if "Letters" in line and line.split()[-1].isdigit():
            letters = int(line.split()[-1])
    if letters != PINNED_LETTERS:
        raise SystemExit(f"STOP dbinfo letters {letters}")
    records = read_records(DX3_GENOME)
    if len(records) != DX3_RECORDS:
        raise SystemExit(f"STOP {DX3_GENOME.name} has {len(records)} records")
    draw = sorted(random.Random(DX3_SEED).sample(range(len(records)), DX3_N))
    work = SCRATCH / "diamond"
    work.mkdir(parents=True, exist_ok=True)
    queries = work / "q.faa"
    if not queries.is_file():
        write_queries(records, draw, queries)
    runs = []
    for tag, db in (("stock_a", NEW_FA), ("stock_b", NEW_FA), ("old", OLD_FA)):
        out = work / f"{tag}.m8"
        log(f"diamond {tag}")
        watched = diamond_blast(db, queries, out, letters, work / f"{tag}.log")
        runs.append({"tag": tag, **watched})
        if watched["killed_over_rss"] or watched["peak_rss_bytes"] > RSS_LIMIT:
            _write_diamond("STOP_RSS", runs, None, letters, draw)
            raise SystemExit("STOP_RSS diamond")
        if watched["returncode"] != 0:
            raise SystemExit(f"STOP diamond {tag} exit {watched['returncode']}")
    stock_a = rescale.body_lines(work / "stock_a.m8")
    stock_b = rescale.body_lines(work / "stock_b.m8")
    if stock_a != stock_b:
        _write_diamond("INCONCLUSIVE", runs, {"why": "stock-vs-stock mismatch"}, letters, draw)
        raise SystemExit("INCONCLUSIVE stock-vs-stock")
    log("expert diamond")
    env = base_env(work / "expert_work")
    watched = run_watched(
        [str(DIAMOND_SCRIPT), str(OLD_FA), str(NEW_FA), str(work / "old.m8"), str(queries), str(work / "expert.m8")],
        work / "expert.log",
        env,
    )
    runs.append({"tag": "expert", **watched})
    if watched["killed_over_rss"] or watched["peak_rss_bytes"] > RSS_LIMIT:
        _write_diamond("STOP_RSS", runs, None, letters, draw)
        raise SystemExit("STOP_RSS expert diamond")
    if watched["returncode"] != 0:
        raise SystemExit(f"STOP expert diamond exit {watched['returncode']}")
    classified = classify_m8(stock_a, rescale.body_lines(work / "expert.m8"))
    label = "SILENT_DIFF" if not classified["bodies_equal"] else "EXACT"
    _write_diamond(label, runs, classified, letters, draw)
    log(f"{label} missing={classified['missing']} extra={classified['extra']}")


def _write_diamond(label: str, runs: list[dict], classified: dict | None, letters: int, draw: list[int]) -> None:
    version = subprocess.run([str(DIAMOND), "version"], capture_output=True, text=True)
    report = {
        "mode": "diamond",
        "pilot": False,
        "seed": DX3_SEED,
        "seed_note": "Published dx3 draw, not a seed from block 20261131-20261139.",
        "queries": DX3_N,
        "records_available": DX3_RECORDS,
        "genome": DX3_GENOME.name,
        "draw_head": draw[:8],
        "dbinfo_letters": letters,
        "diamond_md5": md5_file(DIAMOND),
        "diamond_version": (version.stdout or version.stderr).strip(),
        **provenance(),
        "script_exit_expected": 0,
        "script_noticed": False,
        "label": label,
        "runs": runs,
        "classification": classified,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / "expert_diamond.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    log(f"wrote {dest}")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "batchtest"
    if mode == "batchtest":
        batchtest()
    elif mode == "pilot":
        pilot()
    elif mode == "measured":
        measured()
    elif mode == "diamond":
        diamond()
    else:
        raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
