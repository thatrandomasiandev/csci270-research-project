#!/usr/bin/env python3
"""Part A baseline. Shipped exact mode, no replay-design change.

38.1 cache fill once, then three 38.2 runs restored from that cache.
Stock is three independent scans. Walls are indicative. The proteome
GCF_013315695.1 is pilot data after this run.
"""
from __future__ import annotations

import ast
import gzip
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
DATA = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data")
WORK = Path("/Users/joshuaterranova/tmp/costpass_work")
HMMER = Path("/opt/homebrew/bin")
CPU = "4"
PROTEOME = "GCF_013315695.1"
QUERY_GZ = DATA / "recurrence/A" / f"{PROTEOME}_protein.faa.gz"
PFAM_382_GZ = DATA / "hmmer/Pfam-A.hmm.gz"
PFAM_381_GZ = DATA / "hmmer/pfam38.1/Pfam-A.hmm.gz"
MIN_FREE = 8 * 1024**3


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def loadavg() -> list[float]:
    return [round(v, 2) for v in os.getloadavg()]


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


def gunzip_to(src: Path, dest: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 0:
        log(f"reuse {dest.name}")
        return
    require_free()
    log(f"decompress {src.name}")
    tmp = dest.with_suffix(dest.suffix + ".partial")
    with gzip.open(src, "rb") as inp, open(tmp, "wb") as out:
        shutil.copyfileobj(inp, out, length=1 << 20)
    tmp.replace(dest)


def press(hmm: Path) -> None:
    sidecar = Path(str(hmm) + ".h3m")
    if sidecar.is_file():
        log(f"reuse press {hmm.name}")
        return
    require_free()
    log(f"hmmpress {hmm.name}")
    proc = subprocess.run(
        [str(HMMER / "hmmpress"), "-f", str(hmm)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"hmmpress failed: {(proc.stderr or proc.stdout)[-800:]}")


def body(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines(keepends=True) if line.strip() and not line.startswith("#")]


def parse_decision(path: Path) -> dict:
    out: dict = {"raw": path.read_text() if path.is_file() else ""}
    phases = {}
    for line in out["raw"].splitlines():
        if line.startswith("decision: "):
            out["decision"] = line.split(": ", 1)[1].strip()
        elif line.startswith("why:"):
            out["why"] = line.split(":", 1)[1].strip()
        elif line.startswith("phases: "):
            phases = ast.literal_eval(line[len("phases: ") :])
        elif line.startswith("replay_records: "):
            out["replay_records"] = int(line.split(": ", 1)[1])
        elif line.startswith("replay_entries: "):
            out["replay_entries"] = int(line.split(": ", 1)[1])
        elif line.startswith("candidate_pairs: "):
            out["candidate_pairs"] = int(line.split(": ", 1)[1])
        elif line.startswith("n_fresh: "):
            out["n_fresh"] = int(line.split(": ", 1)[1])
        elif line.startswith("n_stable: "):
            out["n_stable"] = int(line.split(": ", 1)[1])
        elif line.startswith("audit_checked: "):
            out["audit_checked"] = int(line.split(": ", 1)[1])
        elif line.startswith("ic2: "):
            out["ic2"] = line.split(": ", 1)[1].strip()
    out["phases"] = phases
    return out


def scan_stock(db: Path, queries: Path, tag: Path) -> dict:
    stamp = Path(str(tag) + ".json")
    if stamp.is_file() and Path(str(tag) + ".tbl").is_file():
        log(f"reuse stock {tag.name}")
        return json.loads(stamp.read_text())
    require_free()
    cmd = [
        str(HMMER / "hmmscan"),
        "--cut_ga",
        "--noali",
        "--cpu",
        CPU,
        "--tblout",
        str(tag) + ".tbl",
        "--domtblout",
        str(tag) + ".dom",
        "-o",
        os.devnull,
        str(db),
        str(queries),
    ]
    load_before = loadavg()
    log(f"stock {tag.name} load={load_before}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        raise SystemExit(f"hmmscan failed ({proc.returncode}): {(proc.stderr or proc.stdout)[-800:]}")
    payload = {"wall_s": wall, "load_before": load_before, "load_after": loadavg()}
    stamp.write_text(json.dumps(payload) + "\n")
    log(f"stock {tag.name} {wall:.1f}s")
    return payload


def cli(reference: Path, queries: Path, cache: Path, out: Path) -> dict:
    stamp = out / "cli.json"
    if stamp.is_file() and (out / "decision.txt").is_file():
        log(f"reuse cli {out.name}")
        return json.loads(stamp.read_text())
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    require_free()
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
    payload = {
        "returncode": proc.returncode,
        "wall_s": wall,
        "load_before": load_before,
        "load_after": loadavg(),
        "decision": decision.get("decision"),
        "why": decision.get("why"),
        "phases": decision.get("phases") or {},
        "replay_records": decision.get("replay_records"),
        "replay_entries": decision.get("replay_entries"),
        "candidate_pairs": decision.get("candidate_pairs"),
        "n_fresh": decision.get("n_fresh"),
        "n_stable": decision.get("n_stable"),
        "audit_checked": decision.get("audit_checked"),
        "ic2": decision.get("ic2"),
        "stdout_tail": (proc.stdout or "")[-600:],
        "stderr_tail": (proc.stderr or "")[-400:],
    }
    stamp.write_text(json.dumps(payload) + "\n")
    log(f"cli {out.name} {payload['decision']} {wall:.1f}s")
    return payload


def phase_view(phases: dict) -> dict:
    ic2 = {
        key: value
        for key, value in phases.items()
        if key.startswith("ic2_") and key.endswith("_s") and not key.endswith(("_build_s", "_scan_s"))
    }
    keys = (
        "diff_s",
        "discovery_s",
        "discovery_build_s",
        "discovery_scan_s",
        "replay_s",
        "replay_build_s",
        "replay_scan_s",
        "pin_check_s",
        "render_s",
        "verify_s",
        "verify_build_s",
        "verify_scan_s",
        "parse_s",
        "total_s",
        "subref_build_s",
        "prep_s",
        "tool_s",
    )
    view = {key: phases.get(key, 0.0) for key in keys}
    view["ic2_pads_s"] = ic2
    view["ic2_s"] = sum(ic2.values())
    return view


def median(values: list[float]) -> float:
    return float(statistics.median(values))


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PIPE, check=True, capture_output=True, text=True
    ).stdout.strip()


def hmm_version() -> str:
    text = subprocess.run([str(HMMER / "hmmscan"), "-h"], check=True, capture_output=True, text=True).stdout
    return text.splitlines()[1].strip()


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    for path in (QUERY_GZ, PFAM_382_GZ, PFAM_381_GZ):
        if not path.is_file():
            raise SystemExit(f"missing {path}")
    require_free()
    queries = WORK / "GCF_013315695.1.faa"
    pfam382 = WORK / "pfam38.2.hmm"
    pfam381 = WORK / "pfam38.1.hmm"
    gunzip_to(QUERY_GZ, queries)
    gunzip_to(PFAM_382_GZ, pfam382)
    gunzip_to(PFAM_381_GZ, pfam381)
    press(pfam382)
    press(pfam381)

    stock_runs = []
    for i in (1, 2, 3):
        stock_runs.append(scan_stock(pfam382, queries, WORK / f"stock_{i}"))
    bodies = [body(WORK / "stock_1.tbl"), body(WORK / "stock_1.dom")]
    stock_same = True
    for i in (2, 3):
        if body(WORK / f"stock_{i}.tbl") != bodies[0] or body(WORK / f"stock_{i}.dom") != bodies[1]:
            stock_same = False
    if not stock_same:
        raise SystemExit("stop: stock-vs-stock bodies differ")
    log("stock bodies identical")

    cache_fill = WORK / "cache_38.1.sqlite"
    if not (WORK / "fill_38.1" / "cli.json").is_file():
        cache_fill.unlink(missing_ok=True)
    fill = cli(pfam381, queries, cache_fill, WORK / "fill_38.1")
    if not cache_fill.is_file():
        raise SystemExit("stop: 38.1 fill did not write a cache")

    runs = []
    for i in (1, 2, 3):
        run_cache = WORK / f"cache_replay_{i}.sqlite"
        if not (WORK / f"replay_{i}" / "cli.json").is_file():
            shutil.copy2(cache_fill, run_cache)
        run = cli(pfam382, queries, run_cache, WORK / f"replay_{i}")
        tbl = WORK / f"replay_{i}" / "tables" / "tblout"
        dom = WORK / f"replay_{i}" / "tables" / "domtblout"
        run["byte_equal_tbl"] = tbl.is_file() and body(tbl) == bodies[0]
        run["byte_equal_dom"] = dom.is_file() and body(dom) == bodies[1]
        run["breakdown"] = phase_view(run.get("phases") or {})
        runs.append(run)
        log(
            f"replay {i} byte tbl={run['byte_equal_tbl']} dom={run['byte_equal_dom']} "
            f"total={run['breakdown'].get('total_s')}"
        )

    walls = [run["wall_s"] for run in runs]
    order = sorted(range(len(runs)), key=lambda i: walls[i])
    mid = order[len(order) // 2]
    phase_keys = [
        "diff_s",
        "discovery_s",
        "discovery_scan_s",
        "discovery_build_s",
        "replay_s",
        "replay_scan_s",
        "replay_build_s",
        "render_s",
        "verify_s",
        "parse_s",
        "total_s",
        "ic2_s",
    ]
    med_phases = {}
    for key in phase_keys:
        med_phases[key] = median([run["breakdown"].get(key, 0.0) for run in runs])
    pad_names = sorted({name for run in runs for name in run["breakdown"]["ic2_pads_s"]})
    med_phases["ic2_pads_s"] = {
        name: median([run["breakdown"]["ic2_pads_s"].get(name, 0.0) for run in runs]) for name in pad_names
    }
    stock_med = median([run["wall_s"] for run in stock_runs])
    acts_med = median(walls)
    report = {
        "test": "costpass-baseline",
        "design_change": False,
        "protocol": "shipped CLI exact mode, before per-record replay",
        "proteome": PROTEOME,
        "proteome_role": "pilot data after this measurement",
        "git_head": git_head(),
        "host": platform.node(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "hmmscan": hmm_version(),
        "cpu": 4,
        "verify": "audit",
        "pin": "-Z {entry_count}",
        "walls_indicative": True,
        "n_repeats": 3,
        "input_md5": {
            "Pfam-A.hmm.gz": md5_file(PFAM_382_GZ),
            "pfam38.1/Pfam-A.hmm.gz": md5_file(PFAM_381_GZ),
            f"{PROTEOME}_protein.faa.gz": md5_file(QUERY_GZ),
        },
        "stock": {
            "walls_s": [run["wall_s"] for run in stock_runs],
            "load_before": [run["load_before"] for run in stock_runs],
            "load_after": [run["load_after"] for run in stock_runs],
            "median_s": stock_med,
            "bodies_identical": True,
            "tblout_lines": len(bodies[0]),
            "domtblout_lines": len(bodies[1]),
        },
        "fill_38.1": {
            "wall_s": fill["wall_s"],
            "load_before": fill["load_before"],
            "load_after": fill["load_after"],
            "decision": fill["decision"],
            "why": fill["why"],
            "breakdown": phase_view(fill.get("phases") or {}),
            "note": "Pin check runs here and is stored on the contract. The 38.2 runs reuse it.",
        },
        "replay_38.2": {
            "runs": [
                {
                    "wall_s": run["wall_s"],
                    "load_before": run["load_before"],
                    "load_after": run["load_after"],
                    "decision": run["decision"],
                    "why": run["why"],
                    "ic2": run["ic2"],
                    "replay_records": run["replay_records"],
                    "replay_entries": run["replay_entries"],
                    "candidate_pairs": run["candidate_pairs"],
                    "n_fresh": run["n_fresh"],
                    "n_stable": run["n_stable"],
                    "audit_checked": run["audit_checked"],
                    "byte_equal_tbl": run["byte_equal_tbl"],
                    "byte_equal_dom": run["byte_equal_dom"],
                    "breakdown": run["breakdown"],
                }
                for run in runs
            ],
            "median_wall_s": acts_med,
            "median_phases": med_phases,
            "representative_run": mid + 1,
            "representative_breakdown": runs[mid]["breakdown"],
            "byte_equal": all(run["byte_equal_tbl"] and run["byte_equal_dom"] for run in runs),
        },
        "speedup_vs_stock_median": (stock_med / acts_med) if acts_med else None,
        "free_bytes_end": free_bytes(),
    }
    dest = PIPE / "results/exact_replay/costpass_baseline.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    log(f"wrote {dest} speedup={report['speedup_vs_stock_median']}")
    if not report["replay_38.2"]["byte_equal"]:
        raise SystemExit("stop: a 38.2 replay body differs from stock")
    if any(run["decision"] != "SHIP" for run in runs):
        raise SystemExit("stop: a 38.2 run did not SHIP")


if __name__ == "__main__":
    main()
