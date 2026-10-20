#!/usr/bin/env python3
"""Correctness pilot and measured run for the pfscanV3 ship.

The laptop cannot compile this source (Apple clang rejects -msse). Both
phases run on CARC. Wall times in the JSON are diagnostics. They are not
a timing claim.

Round-1 seeds: 20261101 pilot, 20261102 measured, 20261103 drop.
WA2 measured_v2 seeds: 20261272 draw, 20261273 drop, 20261274 timing sample.
"""
from __future__ import annotations

import gzip
import json
import os
import platform
import random
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
REPO = PIPE.parent

PILOT_SEED = 20261101
MEASURED_SEED = 20261102
DROP_SEED = 20261103
N_PILOT = 2
N_MEASURED = 10
DROP_FRACTION = 0.05
EXPECT_MATRIX = {"2026_02": 1434, "2026_03": 1441}

# WA2 measured_v2 (pre-registered in UNRELATED_SHIP_PROTOCOL_V2.md).
MEASURED_V2_SEED = 20261272
DROP_V2_SEED = 20261273
TIMING_V2_SEED = 20261274
N_MEASURED_V2 = 20
PER_GENOME_FLOOR = 1906
POOLED_FLOOR = 38120  # 20 * 1906
PROTOCOL_V2 = PIPE / "docs" / "UNRELATED_SHIP_PROTOCOL_V2.md"
BUILD_SMOKE = "GCF_001513615.1_protein.faa.gz"

GENOMES = Path(os.environ.get(
    "ACTS_GENOMES",
    "/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/recurrence/A",
))
ARCHIVES = Path(os.environ.get(
    "ACTS_ARCHIVES",
    "/project2/biyik_1165/jjt_373/csci270-star/tare-exp-a-archives",
))
WORK = Path(os.environ.get("ACTS_SCRATCH", "/scratch1/jjt_373/tare-exp-a")) / "work"
PFSCAN = Path(os.environ.get(
    "ACTS_PFSCAN",
    "/project2/biyik_1165/jjt_373/csci270-star/tare-exp-a/pfscan/bin/pfscanV3",
))
RESULTS = PIPE / "results" / "unrelated_ship"
TASKS_V2 = RESULTS / "v2_tasks"
PROTOCOL = PIPE / "docs" / "UNRELATED_SHIP_PROTOCOL.md"

LOCKED = [
    "pfscanV3", "--matrix-only", "--nthreads", "1",
    "--output-method", "7", "--fasta", "{reference}", "{input}",
]
DISCLOSURE = (
    "Correctness ran on CARC (AMD EPYC 7542, x86_64) because the laptop "
    "build cannot compile SSE: Apple clang rejects -msse on "
    "arm64-apple-darwin27.0.0. This run is not a timing claim."
)


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def git_head() -> str:
    env = os.environ.get("ACTS_GIT_HASH", "").strip()
    if env:
        return env
    stamp = REPO / "GIT_HASH"
    if stamp.is_file():
        return stamp.read_text().strip()
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, check=False, capture_output=True, text=True,
    )
    return proc.stdout.strip()


def cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


def body_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def classify(reference: list[str], other: list[str]) -> dict:
    """Difference classes against the stock body. Equal lines differ by 0."""
    if reference == other:
        return {"byte_equal": True, "differing_lines": 0, "classes": []}

    def key(line: str) -> tuple:
        fields = line.split()
        if len(fields) < 6:
            return tuple(fields)
        return (fields[0], fields[3], fields[4], fields[5])

    classes: list[str] = []
    if Counter(reference) == Counter(other):
        classes.append("order")
        differing = sum(1 for a, b in zip(reference, other) if a != b)
        differing += abs(len(reference) - len(other))
    else:
        same_keys = Counter(map(key, reference)) == Counter(map(key, other))
        ref_c, oth_c = Counter(reference), Counter(other)
        missing = sum(ref_c[line] - oth_c[line] for line in ref_c if ref_c[line] > oth_c[line])
        extra = sum(oth_c[line] - ref_c[line] for line in oth_c if oth_c[line] > ref_c[line])
        if same_keys:
            classes.append("value-only")
        else:
            ref_keys, oth_keys = Counter(map(key, reference)), Counter(map(key, other))
            if any(ref_keys[k] > oth_keys[k] for k in ref_keys):
                classes.append("missing")
            if any(oth_keys[k] > ref_keys[k] for k in oth_keys):
                classes.append("extra")
            if not classes:
                classes.append("value-only")
        differing = missing + extra
    return {"byte_equal": False, "differing_lines": differing, "classes": classes}


def field_report(lines: list[str]) -> dict:
    widths = Counter(len(line.split()) for line in lines)
    return {
        "n_lines": len(lines),
        "widths": {str(k): v for k, v in sorted(widths.items())},
        "all_ten": set(widths) <= {10} and bool(lines),
    }


def header_report(fasta: Path) -> dict:
    keys: list[str] = []
    with fasta.open() as handle:
        for line in handle:
            if line.startswith(">"):
                keys.append(line[1:].split()[0])
    return {
        "n_records": len(keys),
        "unique": len(keys) == len(set(keys)),
        "n_unique": len(set(keys)),
    }


def version_string() -> str:
    proc = subprocess.run([str(PFSCAN), "--help"], check=False, capture_output=True, text=True)
    text = proc.stdout + proc.stderr
    for line in text.splitlines():
        if "Version " in line:
            return line.strip()
    return text.strip().splitlines()[0] if text.strip() else ""


def matrix_path(release: str) -> Path:
    return WORK / "ref" / f"prosite{release}.matrix"


def prepare_references() -> dict:
    from acts.reference_formats import parse_generalized_profile, write_entries

    dest = WORK / "ref"
    dest.mkdir(parents=True, exist_ok=True)
    report = {}
    for release, archive in (
        ("2026_02", ARCHIVES / "prosite2026_02.tar.bz2"),
        ("2026_03", ARCHIVES / "prosite2026_03.tar.bz2"),
    ):
        out = matrix_path(release)
        stamp = dest / f"{release}.json"
        if out.is_file() and stamp.is_file():
            report[release] = json.loads(stamp.read_text())
            log(f"reuse matrix {release} entries={report[release]['n_matrix']}")
            continue
        import tarfile
        with tarfile.open(archive, "r:bz2") as bundle:
            raw = bundle.extractfile("prosite.dat").read().decode("utf-8")
        entries = parse_generalized_profile(raw)
        matrix = [entry for entry in entries if "MATRIX." in entry.raw.splitlines()[0]]
        write_entries(matrix, out)
        payload = {
            "release": release,
            "archive_bytes": archive.stat().st_size,
            "n_entries_parsed": len(entries),
            "n_matrix": len(matrix),
            "expected_matrix": EXPECT_MATRIX[release],
        }
        if payload["n_matrix"] != payload["expected_matrix"]:
            raise SystemExit(f"{release} matrix count {payload['n_matrix']} != {payload['expected_matrix']}")
        stamp.write_text(json.dumps(payload, indent=2) + "\n")
        report[release] = payload
        log(f"wrote matrix {release} entries={payload['n_matrix']}")
    return report


def decompress(name: str) -> Path:
    dest = WORK / "fasta" / name.replace(".faa.gz", ".faa")
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(GENOMES / name, "rt") as src, dest.open("w") as out:
        out.write(src.read())
    return dest


def pfscan(reference: Path, fasta: Path, stdout_path: Path, threads: str = "1") -> dict:
    meta_path = stdout_path.with_suffix(".json")
    if stdout_path.is_file() and meta_path.is_file():
        meta = json.loads(meta_path.read_text())
        log(f"reuse {stdout_path.name} lines={meta['n_lines']}")
        return meta
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(PFSCAN), "--matrix-only", "--nthreads", threads,
        "--output-method", "7", "--fasta", str(reference), str(fasta),
    ]
    log(" ".join(cmd))
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    stdout_path.write_text(proc.stdout)
    stdout_path.with_suffix(".err").write_text(proc.stderr)
    lines = body_lines(proc.stdout)
    meta = {
        "returncode": proc.returncode,
        "wall_s": wall,
        "n_lines": len(lines),
        "xalip": "xalip" in proc.stderr,
        "stderr_tail": proc.stderr[-800:],
        "threads": threads,
        "timing_claim": False,
    }
    meta_path.write_text(json.dumps(meta) + "\n")
    if proc.returncode != 0:
        raise SystemExit(f"pfscan failed ({proc.returncode}): {proc.stderr[-500:]}")
    log(f"pfscan lines={len(lines)} wall={wall:.1f}s threads={threads}")
    return meta


def tare(reference: Path, fasta: Path, cache: Path, out: Path, verify: str) -> dict:
    decision = out / "decision.txt"
    if decision.is_file():
        log(f"reuse tare {out.name}")
        return read_run(out)
    if out.exists():
        for child in out.iterdir():
            if child.is_file():
                child.unlink()
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "acts", "run",
        "--strategy", "reference",
        "--pin",
        "--verify", verify,
        "--input", str(fasta),
        "--reference", str(reference),
        "--cache", str(cache),
        "-o", str(out),
        "--",
        str(PFSCAN), *LOCKED[1:],
    ]
    log(f"tare {out.name} verify={verify} ref={reference.name}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=PIPE, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    (out / "acts.stdout").write_text(proc.stdout)
    (out / "acts.stderr").write_text(proc.stderr)
    payload = read_run(out)
    payload["returncode"] = proc.returncode
    payload["wall_s"] = wall
    payload["stderr_tail"] = proc.stderr[-800:]
    payload["timing_claim"] = False
    stored = {key: value for key, value in payload.items() if key != "body"}
    (out / "run.json").write_text(json.dumps(stored, indent=2) + "\n")
    log(f"tare {out.name} decision={payload.get('decision')} wall={wall:.1f}s")
    return payload


def read_run(out: Path) -> dict:
    text = (out / "decision.txt").read_text() if (out / "decision.txt").is_file() else ""
    parsed = {"decision": "", "why": "", "decision_text": text}
    for line in text.splitlines():
        if line.startswith("decision:"):
            parsed["decision"] = line.split(":", 1)[1].strip()
        elif line.startswith("why:"):
            parsed["why"] = line.split(":", 1)[1].strip()
    table = out / "tables" / "stdout"
    parsed["body"] = body_lines(table.read_text()) if table.is_file() else []
    parsed["n_lines"] = len(parsed["body"])
    if (out / "run.json").is_file() and "returncode" not in parsed:
        stored = json.loads((out / "run.json").read_text())
        parsed["returncode"] = stored.get("returncode")
        parsed["wall_s"] = stored.get("wall_s")
        parsed["stderr_tail"] = stored.get("stderr_tail", "")
    return parsed


def load_contract(cache: Path) -> dict | None:
    if not cache.is_file():
        return None
    conn = sqlite3.connect(cache)
    try:
        row = conn.execute("SELECT payload FROM contracts LIMIT 1").fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return json.loads(row[0])


def decision_counts(text: str) -> dict:
    wanted = {
        "n_entries", "n_stable", "n_fresh", "n_partial",
        "reused_rows", "ic2", "normalizer",
    }
    found: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in wanted:
            found[key] = value.strip()
    return found


def contract_summary(payload: dict | None) -> dict | None:
    if payload is None:
        return None
    tables = []
    for table in payload.get("tables") or []:
        tables.append({
            "name": table.get("name"),
            "record_col": table.get("record_col"),
            "entry_col": table.get("entry_col"),
            "columns": [
                {
                    "index": col.get("index"),
                    "role": col.get("role"),
                    "member": col.get("member"),
                }
                for col in table.get("columns") or []
            ],
        })
    return {
        "decision": payload.get("decision"),
        "reason": payload.get("reason"),
        "exact_eligible": payload.get("exact_eligible"),
        "primary_key_equal": payload.get("primary_key_equal"),
        "inferred_pin": payload.get("inferred_pin"),
        "tables": tables,
    }


def pool() -> list[str]:
    names = sorted(path.name for path in GENOMES.glob("*.faa.gz"))
    if len(names) != 100:
        raise SystemExit(f"e1scale pool has {len(names)} proteomes, expected 100")
    return names


def draw_pilot(names: list[str]) -> list[str]:
    return random.Random(PILOT_SEED).sample(names, N_PILOT)


def draw_measured(names: list[str], pilot_names: list[str]) -> list[str]:
    rest = [name for name in names if name not in set(pilot_names)]
    return random.Random(MEASURED_SEED).sample(rest, N_MEASURED)


def excluded_for_v2(pilot_names: list[str], measured_names: list[str]) -> set[str]:
    return set(pilot_names) | set(measured_names) | {BUILD_SMOKE}


def draw_measured_v2(names: list[str], excluded: set[str]) -> list[str]:
    rest = [name for name in names if name not in excluded]
    if len(rest) < N_MEASURED_V2:
        raise SystemExit(f"v2 pool has {len(rest)} after exclusions, need {N_MEASURED_V2}")
    return random.Random(MEASURED_V2_SEED).sample(rest, N_MEASURED_V2)


def known_bad_v2(reference: Path, fasta: Path, cache: Path, stock_body: list[str], folder: Path) -> dict:
    """Injected drop under DROP_V2_SEED. Same control shape as round-1."""
    from acts.reference_formats import parse_reference

    stamp = folder / "known_bad_v2.json"
    if stamp.is_file():
        return json.loads(stamp.read_text())
    folder.mkdir(parents=True, exist_ok=True)
    entries = parse_reference(reference)
    by_key = {entry.primary: entry for entry in entries}
    candidates = sorted({line.split()[0] for line in stock_body if line.split()})
    n_drop = max(1, int(round(DROP_FRACTION * len(candidates))))
    dropped = random.Random(DROP_V2_SEED).sample(candidates, n_drop)
    missing_keys = [token for token in dropped if token not in by_key]
    if missing_keys:
        raise SystemExit(f"dropped tokens are not matrix keys: {missing_keys[:5]}")
    hashes = [by_key[token].content_hash for token in dropped]
    dropped_cache = folder / "cache.sqlite"
    src = sqlite3.connect(cache)
    dst = sqlite3.connect(dropped_cache)
    try:
        src.backup(dst)
        marks = ",".join("?" for _ in hashes)
        n_rows = dst.execute(
            f"SELECT COUNT(*) FROM rows WHERE entry_hash IN ({marks})", hashes,
        ).fetchone()[0]
        dst.execute(f"DELETE FROM rows WHERE entry_hash IN ({marks})", hashes)
        dst.commit()
    finally:
        src.close()
        dst.close()
    rerun = tare(reference, fasta, dropped_cache, folder / "rerun", "full")
    refused = rerun.get("decision", "").startswith("REFUSE")
    payload = {
        "seed": DROP_V2_SEED,
        "fraction": DROP_FRACTION,
        "n_candidates": len(candidates),
        "n_dropped": n_drop,
        "dropped": dropped,
        "deleted_rows": n_rows,
        "decision": rerun.get("decision"),
        "why": rerun.get("why"),
        "refused": refused and n_rows > 0,
        "control": "injected 5% candidate-row drop must refuse",
    }
    stamp.write_text(json.dumps(payload, indent=2) + "\n")
    log(f"known-bad-v2 refused={payload['refused']} decision={payload['decision']} deleted_rows={n_rows}")
    return payload


def one_measured_v2_genome(name: str, floor: int) -> dict:
    folder = WORK / "measured_v2" / name.replace(".faa.gz", "")
    folder.mkdir(parents=True, exist_ok=True)
    fasta = decompress(name)
    stock = pfscan(matrix_path("2026_03"), fasta, folder / "stock.out")
    lines = body_lines((folder / "stock.out").read_text())
    if len(lines) < floor:
        return {
            "genome": name,
            "lines": {"stock": len(lines), "tare": None},
            "differing_lines": None,
            "classes": [],
            "decision": "INCONCLUSIVE",
            "checks": {"power": "miss", "floor": floor, "ship": False},
            "xalip": stock["xalip"],
            "work_dir": str(folder),
        }
    cache = folder / "cache.sqlite"
    fill = tare(matrix_path("2026_02"), fasta, cache, folder / "fill", "audit")
    update = tare(matrix_path("2026_03"), fasta, cache, folder / "update", "audit")
    compared = classify(lines, update["body"])
    decision = update.get("decision") or "FAIL"
    if decision.upper() == "UNSAFE":
        decision = "UNSAFE"
    elif decision == "SHIP" and not compared["byte_equal"]:
        decision = "FAIL"
    return {
        "genome": name,
        "lines": {"stock": len(lines), "tare": update["n_lines"]},
        "differing_lines": compared["differing_lines"],
        "classes": compared["classes"],
        "decision": decision,
        "why": update.get("why"),
        "checks": {
            "power": "pass",
            "floor": floor,
            "ship": decision == "SHIP",
            "byte_equal": compared["byte_equal"],
            "xalip": stock["xalip"] or ("xalip" in (update.get("stderr_tail") or "")),
        },
        "contract": contract_summary(load_contract(cache)),
        "release_diff": decision_counts(update.get("decision_text") or ""),
        "work_dir": str(folder),
        "fill": {k: v for k, v in fill.items() if k != "body"},
        "update": {k: v for k, v in update.items() if k != "body"},
    }


def heuristic_note(matrix: Path, fasta: Path, folder: Path) -> dict:
    from acts.reference_formats import parse_reference, write_entries

    stamp = folder / "heuristic.json"
    if stamp.is_file():
        return json.loads(stamp.read_text())
    folder.mkdir(parents=True, exist_ok=True)
    entries = parse_reference(matrix)
    write_entries([entries[0]], folder / "one.matrix")
    recs = []
    buf: list[str] = []
    for line in fasta.read_text().splitlines(keepends=True):
        if line.startswith(">") and buf:
            recs.append("".join(buf))
            buf = [line]
        else:
            buf.append(line)
    if buf:
        recs.append("".join(buf))
    tiny = folder / "eight.faa"
    tiny.write_text("".join(recs[:8]))
    with_h = pfscan(folder / "one.matrix", tiny, folder / "with.out")
    without = folder / "without.out"
    # pfscan() always passes the locked argv, which has no --no-heuristic.
    # This one call is the tool-property note, not the ship.
    cmd = [
        str(PFSCAN), "--matrix-only", "--nthreads", "1", "--no-heuristic",
        "--output-method", "7", "--fasta", str(folder / "one.matrix"), str(tiny),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    without.write_text(proc.stdout)
    without.with_suffix(".err").write_text(proc.stderr)
    payload = {
        "profile": entries[0].primary,
        "n_sequences": min(8, len(recs)),
        "with_heuristic_lines": with_h["n_lines"],
        "without_heuristic_lines": len(body_lines(proc.stdout)),
        "without_returncode": proc.returncode,
        "one_profile_warning": "not meant to be used with a single profile" in (
            with_h.get("stderr_tail", "") + proc.stderr
        ),
        "not_a_kill": True,
    }
    stamp.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def threads_pair(reference: Path, fasta: Path, folder: Path) -> dict:
    a = pfscan(reference, fasta, folder / "t2_a.out", threads="2")
    b = pfscan(reference, fasta, folder / "t2_b.out", threads="2")
    cmp = classify(body_lines((folder / "t2_a.out").read_text()), body_lines((folder / "t2_b.out").read_text()))
    return {
        "threads": 2,
        "a_lines": a["n_lines"],
        "b_lines": b["n_lines"],
        **cmp,
        "not_the_locked_argv": True,
    }


def known_bad(reference: Path, fasta: Path, cache: Path, stock_body: list[str], folder: Path) -> dict:
    from acts.reference_formats import parse_reference

    stamp = folder / "known_bad.json"
    if stamp.is_file():
        return json.loads(stamp.read_text())
    folder.mkdir(parents=True, exist_ok=True)
    entries = parse_reference(reference)
    by_key = {entry.primary: entry for entry in entries}
    candidates = sorted({line.split()[0] for line in stock_body if line.split()})
    n_drop = max(1, int(round(DROP_FRACTION * len(candidates))))
    dropped = random.Random(DROP_SEED).sample(candidates, n_drop)
    missing_keys = [token for token in dropped if token not in by_key]
    if missing_keys:
        raise SystemExit(f"dropped tokens are not matrix keys: {missing_keys[:5]}")
    hashes = [by_key[token].content_hash for token in dropped]
    dropped_cache = folder / "cache.sqlite"
    src = sqlite3.connect(cache)
    dst = sqlite3.connect(dropped_cache)
    try:
        src.backup(dst)
        marks = ",".join("?" for _ in hashes)
        n_rows = dst.execute(
            f"SELECT COUNT(*) FROM rows WHERE entry_hash IN ({marks})", hashes,
        ).fetchone()[0]
        dst.execute(f"DELETE FROM rows WHERE entry_hash IN ({marks})", hashes)
        dst.commit()
    finally:
        src.close()
        dst.close()
    rerun = tare(reference, fasta, dropped_cache, folder / "rerun", "full")
    refused = rerun.get("decision", "").startswith("REFUSE")
    payload = {
        "seed": DROP_SEED,
        "fraction": DROP_FRACTION,
        "n_candidates": len(candidates),
        "n_dropped": n_drop,
        "dropped": dropped,
        "deleted_rows": n_rows,
        "decision": rerun.get("decision"),
        "why": rerun.get("why"),
        "refused": refused and n_rows > 0,
        "control": "injected 5% candidate-row drop must refuse",
    }
    stamp.write_text(json.dumps(payload, indent=2) + "\n")
    log(f"known-bad refused={payload['refused']} decision={payload['decision']} deleted_rows={n_rows}")
    return payload


def one_pilot(name: str, do_extra: bool) -> dict:
    folder = WORK / "pilot" / name.replace(".faa.gz", "")
    folder.mkdir(parents=True, exist_ok=True)
    fasta = decompress(name)
    headers = header_report(fasta)
    stock_a = pfscan(matrix_path("2026_03"), fasta, folder / "stock_a.out")
    stock_b = pfscan(matrix_path("2026_03"), fasta, folder / "stock_b.out")
    lines_a = body_lines((folder / "stock_a.out").read_text())
    lines_b = body_lines((folder / "stock_b.out").read_text())
    determinism = classify(lines_a, lines_b)
    report: dict = {
        "genome": name,
        "headers": headers,
        "fields": field_report(lines_a),
        "stock_a_lines": len(lines_a),
        "stock_b_lines": len(lines_b),
        "stock_vs_stock": determinism,
        "xalip": stock_a["xalip"] or stock_b["xalip"],
    }
    if not determinism["byte_equal"]:
        report["stopped"] = "stock-vs-stock bodies differ at --nthreads 1"
        return report
    if do_extra:
        report["threads_2"] = threads_pair(matrix_path("2026_03"), fasta, folder / "threads2")
        report["heuristic"] = heuristic_note(matrix_path("2026_03"), fasta, folder / "heuristic")
    cache = folder / "cache.sqlite"
    fill = tare(matrix_path("2026_02"), fasta, cache, folder / "fill", "audit")
    update = tare(matrix_path("2026_03"), fasta, cache, folder / "update", "audit")
    compared = classify(lines_b, update["body"])
    report["fill"] = {k: v for k, v in fill.items() if k != "body"}
    report["update"] = {k: v for k, v in update.items() if k != "body"}
    report["update_vs_stock"] = compared
    report["contract"] = contract_summary(load_contract(cache))
    report["decision"] = update.get("decision")
    report["lines"] = {"stock": len(lines_b), "tare": update["n_lines"]}
    report["differing_lines"] = compared["differing_lines"]
    return report


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    log(f"wrote {path}")


def host_block() -> dict:
    return {
        "system": "TARE",
        "package": "acts",
        "tool": "pfscanV3",
        "version_string": version_string(),
        "archive_version_line": 'SET(VERSION "3.2.12")',
        "filename": "pftools3-v3.2.13.zip",
        "locked_command": "pfscanV3 --matrix-only --nthreads 1 --output-method 7 --fasta {reference} {input}",
        "git_head": git_head(),
        "host": platform.node(),
        "platform": platform.platform(),
        "cpu": cpu_model(),
        "disclosure": DISCLOSURE,
        "timing_claim": False,
    }


def run_pilot() -> None:
    if not PFSCAN.is_file():
        raise SystemExit(f"pfscanV3 is not at {PFSCAN}")
    names = pool()
    chosen = draw_pilot(names)
    log(f"pilot draw {chosen}")
    refs = prepare_references()
    genomes = []
    for index, name in enumerate(chosen):
        log(f"pilot genome {name}")
        genomes.append(one_pilot(name, do_extra=(index == 0)))
        if genomes[-1].get("stopped"):
            break
    shipped = [row for row in genomes if row.get("decision") == "SHIP" and row["stock_vs_stock"]["byte_equal"]]
    floor_values = [row["lines"]["stock"] for row in shipped]
    floor = min(floor_values) if floor_values else 0
    bad = None
    source = next((row for row in shipped if row["lines"]["stock"] > 0), None)
    if source is not None:
        folder = WORK / "pilot" / source["genome"].replace(".faa.gz", "")
        fasta = decompress(source["genome"])
        bad = known_bad(
            matrix_path("2026_03"),
            fasta,
            folder / "cache.sqlite",
            body_lines((folder / "stock_b.out").read_text()),
            folder / "known_bad",
        )
    identical = bool(shipped) and all(row["update_vs_stock"]["byte_equal"] for row in shipped)
    refused = bool(bad and bad["refused"])
    if not genomes or any(row.get("stopped") for row in genomes):
        outcome = "FAIL"
    elif not identical or len(shipped) != len(chosen):
        outcome = "FAIL"
    elif floor <= 0:
        outcome = "INCONCLUSIVE"
    elif not refused:
        outcome = "FAIL"
    else:
        outcome = "PASS"
    payload = {
        **host_block(),
        "phase": "pilot",
        "seed": PILOT_SEED,
        "drop_seed": DROP_SEED,
        "pool": "pipeline/data/recurrence/A (e1scale, 100 bacterial proteomes)",
        "genomes_drawn": chosen,
        "references": refs,
        "genomes": genomes,
        "contract": shipped[0]["contract"] if shipped else None,
        "known_bad": bad,
        "power_floor": floor,
        "outcome": outcome,
        "checks": {
            "stock_vs_stock": all(row["stock_vs_stock"]["byte_equal"] for row in genomes),
            "headers_unique": all(row["headers"]["unique"] for row in genomes),
            "fields_all_ten": all(row["fields"]["all_ten"] for row in genomes),
            "update_byte_identical": identical,
            "known_bad_refused": refused,
            "power_floor": floor,
        },
    }
    write_json(RESULTS / "pilot.json", payload)
    if outcome != "PASS":
        raise SystemExit(f"pilot outcome {outcome}")


def run_measured() -> None:
    pilot_path = RESULTS / "pilot.json"
    if not pilot_path.is_file():
        raise SystemExit("pilot json is missing")
    pilot = json.loads(pilot_path.read_text())
    if pilot.get("outcome") != "PASS":
        raise SystemExit(f"pilot outcome is {pilot.get('outcome')}; measured run stays unstarted")
    floor = int(pilot["power_floor"])
    if floor <= 0:
        raise SystemExit("power floor is missing")
    if not PROTOCOL.is_file():
        raise SystemExit("protocol is not committed on this tree")
    protocol = PROTOCOL.read_text()
    needle = f"Power floor: {floor}"
    if needle not in protocol:
        raise SystemExit(f"protocol does not lock {needle}")
    names = pool()
    pilot_names = list(pilot["genomes_drawn"])
    chosen = draw_measured(names, pilot_names)
    if set(chosen) & set(pilot_names):
        raise SystemExit("measured draw overlaps the pilot")
    log(f"measured draw {chosen}")
    prepare_references()
    genomes = []
    for name in chosen:
        log(f"measured genome {name}")
        folder = WORK / "measured" / name.replace(".faa.gz", "")
        folder.mkdir(parents=True, exist_ok=True)
        fasta = decompress(name)
        stock = pfscan(matrix_path("2026_03"), fasta, folder / "stock.out")
        lines = body_lines((folder / "stock.out").read_text())
        if len(lines) < floor:
            genomes.append({
                "genome": name,
                "lines": {"stock": len(lines), "tare": None},
                "differing_lines": None,
                "classes": [],
                "decision": "INCONCLUSIVE",
                "checks": {"power": "miss", "floor": floor, "ship": False},
                "xalip": stock["xalip"],
            })
            continue
        cache = folder / "cache.sqlite"
        fill = tare(matrix_path("2026_02"), fasta, cache, folder / "fill", "audit")
        update = tare(matrix_path("2026_03"), fasta, cache, folder / "update", "audit")
        compared = classify(lines, update["body"])
        decision = update.get("decision") or "FAIL"
        if decision == "SHIP" and not compared["byte_equal"]:
            decision = "FAIL"
        genomes.append({
            "genome": name,
            "lines": {"stock": len(lines), "tare": update["n_lines"]},
            "differing_lines": compared["differing_lines"],
            "classes": compared["classes"],
            "decision": decision,
            "why": update.get("why"),
            "checks": {
                "power": "pass",
                "floor": floor,
                "ship": decision == "SHIP",
                "byte_equal": compared["byte_equal"],
                "xalip": stock["xalip"] or ("xalip" in (update.get("stderr_tail") or "")),
            },
            "contract": contract_summary(load_contract(cache)),
            "release_diff": decision_counts(update.get("decision_text") or ""),
        })
    if any(row["decision"] == "INCONCLUSIVE" for row in genomes):
        outcome = "INCONCLUSIVE"
    elif all(row["decision"] == "SHIP" and row["differing_lines"] == 0 for row in genomes):
        outcome = "PASS"
    else:
        outcome = "FAIL"
    payload = {
        **host_block(),
        "phase": "measured",
        "seed": MEASURED_SEED,
        "pilot_seed": PILOT_SEED,
        "excluded_pilot": pilot_names,
        "power_floor": floor,
        "genomes_drawn": chosen,
        "genomes": genomes,
        "contract": genomes[0].get("contract") if genomes else None,
        "checks": {
            "n": len(genomes),
            "n_ship": sum(1 for row in genomes if row["decision"] == "SHIP"),
            "n_differing": sum((row["differing_lines"] or 0) for row in genomes),
            "power_floor": floor,
        },
        "outcome": outcome,
    }
    write_json(RESULTS / "measured.json", payload)
    if outcome != "PASS":
        raise SystemExit(f"measured outcome {outcome}")


def _v2_draw_locked() -> tuple[list[str], list[str], list[str]]:
    """Return (chosen, pilot_names, measured_r1_names) matching the protocol list."""
    pilot_path = RESULTS / "pilot.json"
    measured_path = RESULTS / "measured.json"
    if not pilot_path.is_file() or not measured_path.is_file():
        raise SystemExit("pilot.json and measured.json are required to lock v2 exclusions")
    pilot = json.loads(pilot_path.read_text())
    measured = json.loads(measured_path.read_text())
    pilot_names = list(pilot["genomes_drawn"])
    measured_names = list(measured["genomes_drawn"])
    excluded = excluded_for_v2(pilot_names, measured_names)
    chosen = draw_measured_v2(pool(), excluded)
    return chosen, pilot_names, measured_names


def run_measured_v2_task() -> None:
    """One array task: one genome from the pre-registered draw."""
    if not PROTOCOL_V2.is_file():
        raise SystemExit("PROTOCOL_V2 is not on this tree")
    protocol = PROTOCOL_V2.read_text()
    if "38120" not in protocol or "Power floors" not in protocol:
        raise SystemExit("PROTOCOL_V2 does not lock pooled floor 38120")
    if "1906" not in protocol:
        raise SystemExit("PROTOCOL_V2 does not lock per-genome floor 1906")
    if "Seed `20261272`" not in protocol:
        raise SystemExit("PROTOCOL_V2 does not lock seed 20261272")
    raw = os.environ.get("SLURM_ARRAY_TASK_ID", "").strip()
    if not raw:
        raise SystemExit("SLURM_ARRAY_TASK_ID is required for measured_v2_task")
    index = int(raw)
    chosen, _, _ = _v2_draw_locked()
    if index < 0 or index >= len(chosen):
        raise SystemExit(f"array index {index} outside 0..{len(chosen) - 1}")
    name = chosen[index]
    # Confirm protocol lists this name at this position (1-indexed in the doc).
    if name not in protocol:
        raise SystemExit(f"{name} is not listed in PROTOCOL_V2")
    if not PFSCAN.is_file():
        raise SystemExit(f"pfscanV3 is not at {PFSCAN}")
    prepare_references()
    log(f"measured_v2 task {index} genome {name}")
    row = one_measured_v2_genome(name, PER_GENOME_FLOOR)
    payload = {
        **host_block(),
        "phase": "measured_v2_task",
        "seed": MEASURED_V2_SEED,
        "array_task_id": index,
        "genome": name,
        "per_genome_floor": PER_GENOME_FLOOR,
        "pooled_floor": POOLED_FLOOR,
        "result": row,
    }
    TASKS_V2.mkdir(parents=True, exist_ok=True)
    dest = TASKS_V2 / f"task_{index:02d}.json"
    write_json(dest, payload)


def run_measured_v2_aggregate() -> None:
    """Pool task JSONs, run known-bad, write measured_v2.json."""
    if not PROTOCOL_V2.is_file():
        raise SystemExit("PROTOCOL_V2 is not on this tree")
    chosen, pilot_names, measured_names = _v2_draw_locked()
    genomes = []
    for index, name in enumerate(chosen):
        path = TASKS_V2 / f"task_{index:02d}.json"
        if not path.is_file():
            raise SystemExit(f"missing task result {path}")
        task = json.loads(path.read_text())
        row = task["result"]
        if row["genome"] != name:
            raise SystemExit(f"task {index} genome {row['genome']} != locked {name}")
        genomes.append(row)

    powered = [row for row in genomes if row["checks"].get("power") == "pass"]
    pooled_lines = sum(row["lines"]["stock"] for row in powered)
    pooled_ok = pooled_lines >= POOLED_FLOOR

    bad = None
    control_genome = next(
        (row for row in genomes if row["decision"] == "SHIP" and row.get("differing_lines") == 0),
        None,
    )
    if control_genome is not None:
        folder = Path(control_genome["work_dir"])
        fasta = decompress(control_genome["genome"])
        bad = known_bad_v2(
            matrix_path("2026_03"),
            fasta,
            folder / "cache.sqlite",
            body_lines((folder / "stock.out").read_text()),
            folder / "known_bad_v2",
        )

    n_ship = sum(1 for row in genomes if row["decision"] == "SHIP")
    n_unsafe = sum(1 for row in genomes if str(row["decision"]).upper() == "UNSAFE")
    n_inconclusive = sum(1 for row in genomes if row["decision"] == "INCONCLUSIVE")
    n_fail = sum(
        1 for row in genomes
        if row["decision"] not in {"SHIP", "INCONCLUSIVE"}
    )
    refused = bool(bad and bad.get("refused"))

    if n_unsafe or n_fail:
        outcome = "FAIL"
    elif n_inconclusive or not pooled_ok:
        outcome = "INCONCLUSIVE"
    elif n_ship == len(chosen) and all(
        row["decision"] == "SHIP" and row["differing_lines"] == 0 for row in genomes
    ) and refused:
        outcome = "PASS"
    elif n_ship == len(chosen) and all(
        row["decision"] == "SHIP" and row["differing_lines"] == 0 for row in genomes
    ) and not refused:
        outcome = "FAIL"
    else:
        outcome = "FAIL"

    # Strip work_dir / fill / update bodies from the committed summary size.
    slim = []
    for row in genomes:
        slim.append({k: v for k, v in row.items() if k not in {"fill", "update"}})

    payload = {
        **host_block(),
        "phase": "measured_v2",
        "seed": MEASURED_V2_SEED,
        "drop_seed": DROP_V2_SEED,
        "pilot_seed": PILOT_SEED,
        "excluded_pilot": pilot_names,
        "excluded_measured_r1": measured_names,
        "excluded_smoke": BUILD_SMOKE,
        "per_genome_floor": PER_GENOME_FLOOR,
        "pooled_floor": POOLED_FLOOR,
        "pooled_stock_lines": pooled_lines,
        "pooled_ok": pooled_ok,
        "genomes_drawn": chosen,
        "genomes": slim,
        "known_bad": bad,
        "contract": next((row.get("contract") for row in slim if row.get("contract")), None),
        "checks": {
            "n": len(genomes),
            "n_ship": n_ship,
            "n_unsafe": n_unsafe,
            "n_inconclusive": n_inconclusive,
            "n_fail": n_fail,
            "n_differing": sum((row["differing_lines"] or 0) for row in genomes),
            "per_genome_floor": PER_GENOME_FLOOR,
            "pooled_floor": POOLED_FLOOR,
            "pooled_stock_lines": pooled_lines,
            "known_bad_refused": refused,
        },
        "outcome": outcome,
    }
    write_json(RESULTS / "measured_v2.json", payload)
    if outcome != "PASS":
        raise SystemExit(f"measured_v2 outcome {outcome}")


def run_timing_v2() -> None:
    """Exclusive paired timing for 5 genomes. Only after measured_v2 PASS."""
    measured_path = RESULTS / "measured_v2.json"
    if not measured_path.is_file():
        raise SystemExit("measured_v2.json missing")
    measured = json.loads(measured_path.read_text())
    if measured.get("outcome") != "PASS":
        raise SystemExit(f"timing_v2 blocked: measured_v2 outcome is {measured.get('outcome')}")
    drawn = list(measured["genomes_drawn"])
    timed = random.Random(TIMING_V2_SEED).sample(drawn, 5)
    prepare_references()
    rows = []
    for name in timed:
        folder = WORK / "timing_v2" / name.replace(".faa.gz", "")
        folder.mkdir(parents=True, exist_ok=True)
        fasta = decompress(name)
        stock_walls = []
        for rep in range(3):
            out = folder / f"stock_r{rep}.out"
            # Force fresh timing: remove prior meta so pfscan re-runs.
            meta = out.with_suffix(".json")
            if out.is_file():
                out.unlink()
            if meta.is_file():
                meta.unlink()
            meta_run = pfscan(matrix_path("2026_03"), fasta, out)
            stock_walls.append(meta_run["wall_s"])
        cache = folder / "cache.sqlite"
        if cache.is_file():
            cache.unlink()
        fill = tare(matrix_path("2026_02"), fasta, cache, folder / "fill", "audit")
        tare_walls = []
        for rep in range(3):
            # Fresh update each rep: clear update dir so tare re-runs.
            update_dir = folder / f"update_r{rep}"
            if update_dir.exists():
                for child in update_dir.iterdir():
                    if child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        import shutil
                        shutil.rmtree(child)
            # Reuse fill cache; copy for each update so cache is warm identically.
            rep_cache = folder / f"cache_r{rep}.sqlite"
            src = sqlite3.connect(cache)
            dst = sqlite3.connect(rep_cache)
            try:
                src.backup(dst)
            finally:
                src.close()
                dst.close()
            update = tare(matrix_path("2026_03"), fasta, rep_cache, update_dir, "audit")
            tare_walls.append(update["wall_s"])
        import statistics
        stock_med = statistics.median(stock_walls)
        tare_med = statistics.median(tare_walls)
        rows.append({
            "genome": name,
            "stock_walls_s": stock_walls,
            "tare_update_walls_s": tare_walls,
            "fill_wall_s": fill.get("wall_s"),
            "stock_median_s": stock_med,
            "tare_median_s": tare_med,
            "speedup": (stock_med / tare_med) if tare_med else None,
        })
    import statistics as stats
    speedups = [row["speedup"] for row in rows if row["speedup"]]
    payload = {
        **host_block(),
        "phase": "timing_v2",
        "seed": TIMING_V2_SEED,
        "measured_v2_seed": MEASURED_V2_SEED,
        "measured_v2_git_head": measured.get("git_head"),
        "r": 3,
        "exclusive": True,
        "timing_claim": True,
        "genomes_timed": timed,
        "genomes": rows,
        "median_speedup": stats.median(speedups) if speedups else None,
        "disclosure": (
            "Exclusive CARC timing of pfscanV3 stock vs TARE update after "
            "measured_v2 PASS. Fill time excluded from the speedup ratio."
        ),
    }
    # Override the host_block timing_claim=False.
    payload["timing_claim"] = True
    write_json(RESULTS / "timing_v2.json", payload)


def main() -> None:
    modes = {
        "pilot", "measured",
        "measured_v2_task", "measured_v2_aggregate", "timing_v2",
    }
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        raise SystemExit(
            "usage: unrelated_ship.py pilot|measured|"
            "measured_v2_task|measured_v2_aggregate|timing_v2"
        )
    os.environ.setdefault("PYTHONPATH", str(PIPE))
    dispatch = {
        "pilot": run_pilot,
        "measured": run_measured,
        "measured_v2_task": run_measured_v2_task,
        "measured_v2_aggregate": run_measured_v2_aggregate,
        "timing_v2": run_timing_v2,
    }
    dispatch[sys.argv[1]]()


if __name__ == "__main__":
    main()
