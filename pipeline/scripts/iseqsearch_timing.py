#!/usr/bin/env python3
"""Time stock DIAMOND, iSeqSearch, and TARE's DIAMOND refusal path.

The system is TARE. This driver calls ``python3 -m acts``; it does not
modify that package and it does not reimplement the iSeqSearch merger.

Protocol: pipeline/docs/ISEQSEARCH_TIMING_PROTOCOL.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from acts.provenance import provenance  # noqa: E402
from acts.reference_formats import parse_reference, read_records, write_entries  # noqa: E402
from exact_replay_diamond import (  # noqa: E402
    body_lines,
    changed_entries,
    classify_bodies,
    correlation,
    write_queries,
)

Q300_SEED = 20261017
PILOT_SEED = 20261251
Q300_N = 300
PILOT_N = 50
PROTEOME_N = 5117
Q300_NAME_SHA = "b7ed150e41d88cb6eccea223fd6c2bb52c2b6a2478092ec443f8595148d915b5"
PILOT_NAME_SHA = "6d9cb4d8937d5b395b316175f16f996357b912f83e5625745db9f160467ad633"
Q300_MD5 = "a703200e3967517b57f8f7469bb1bd8c"
Q300_BYTES = 114470
DELTA_N = 10239
L_OLD = 208482574
ORDER = (
    ("stock", "TARE", "iSeqSearch"),
    ("TARE", "iSeqSearch", "stock"),
    ("iSeqSearch", "stock", "TARE"),
)
EXPECTED = {
    "old": (93457057, "5245b19456d9a063b13c46602269bc5f"),
    "new": (93801562, "bc9d398533e6df582b563c6c03093bd0"),
    "queries": (1074926, "b170d133266427c46d87d99284e1fda3"),
    "iseq_main": (2477, "2c0762059f0229add06bf351edb2f979"),
    "diamond_linux": (28553136, "7de14b7f9f4c440ddfb5142ad96b1d8b"),
}
OUTFMT = (
    "qseqid sseqid pident length mismatch gapopen "
    "qstart qend sstart send evalue bitscore"
).split()
PAYLOAD: dict = {}
OUT_PATH: Path | None = None


def log(message: str) -> None:
    print(message, flush=True)


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_names(names: list[str]) -> str:
    return hashlib.sha256("\n".join(names).encode()).hexdigest()


def file_id(path: Path) -> dict:
    return {"path": str(path), "bytes": path.stat().st_size, "md5": md5_file(path)}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def persist() -> None:
    if OUT_PATH is not None:
        write_json(OUT_PATH, PAYLOAD)


def on_term(signum: int, _frame) -> None:
    PAYLOAD["partial"] = True
    PAYLOAD["verdict"] = "INCONCLUSIVE"
    PAYLOAD["why"] = f"signal {signum}"
    PAYLOAD["stopped"] = True
    persist()
    raise SystemExit(143)


def require_file(path: Path, expected: tuple[int, str], label: str) -> dict:
    if not path.is_file():
        raise SystemExit(f"STOP_INPUTS missing {label}: {path}")
    found = file_id(path)
    if found["bytes"] != expected[0] or found["md5"] != expected[1]:
        raise SystemExit(
            f"STOP_INPUTS {label} bytes={found['bytes']} md5={found['md5']} "
            f"expected bytes={expected[0]} md5={expected[1]}"
        )
    return found


def fstype(path: Path) -> str:
    proc = subprocess.run(
        ["findmnt", "-n", "-o", "FSTYPE", "-T", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "").strip()


def cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def run_proc(cmd: list[str], *, cwd: Path | None = None, timeout: float = 7200) -> dict:
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    wall = time.perf_counter() - started
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "wall_s": wall,
        "stdout": stdout if len(stdout) <= 20000 else "",
        "stderr": stderr if len(stderr) <= 20000 else "",
        "stdout_tail": stdout[-1500:],
        "stderr_tail": stderr[-1500:],
    }


def blast_cmd(diamond: str, db: Path, query: Path, out: Path, threads: str) -> list[str]:
    return [
        diamond,
        "blastp",
        "--db",
        str(db),
        "--query",
        str(query),
        "--out",
        str(out),
        "--min-score",
        "40",
        "-k",
        "0",
        "--motif-masking",
        "0",
        "-b",
        "2.0",
        "--comp-based-stats",
        "1",
        "--threads",
        threads,
        "--outfmt",
        "6",
        *OUTFMT,
    ]


def makedb(diamond: str, fasta: Path, threads: str) -> dict:
    dmnd = Path(str(fasta) + ".dmnd")
    if dmnd.is_file():
        dmnd.unlink()
    return run_proc(
        [diamond, "makedb", "--in", str(fasta), "--db", str(fasta), "--threads", threads]
    )


def dbinfo_letters(diamond: str, fasta: Path) -> tuple[int, dict]:
    proc = run_proc([diamond, "dbinfo", "--db", str(fasta)], timeout=180)
    if proc["returncode"] != 0:
        raise SystemExit(f"STOP dbinfo failed: {proc['stderr_tail']}")
    text = (proc.get("stdout") or "") + "\n" + (proc.get("stderr") or "")
    for line in text.splitlines():
        if "Letters" not in line:
            continue
        token = line.split()[-1]
        if token.isdigit():
            return int(token), proc
    raise SystemExit(f"STOP dbinfo has no Letters count: {text[-1000:]}")


def s1_placeholders(diamond: str, threads: str) -> list[str]:
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
        "40",
        "-k",
        "0",
        "--motif-masking",
        "0",
        "-b",
        "2.0",
        "--comp-based-stats",
        "1",
        "--threads",
        threads,
        "--outfmt",
        "6",
        *OUTFMT,
    ]


def draw_queries(proteome: Path, mode: str, dest: Path) -> dict:
    records = read_records(proteome)
    if len(records) != PROTEOME_N:
        raise SystemExit(f"STOP_INPUTS proteome has {len(records)} records, expected {PROTEOME_N}")
    measured_idx = sorted(random.Random(Q300_SEED).sample(range(len(records)), Q300_N))
    measured_names = [records[i].name for i in measured_idx]
    if sha256_names(measured_names) != Q300_NAME_SHA:
        raise SystemExit("STOP_INPUTS measured query name hash differs from the dx_i draw")
    if mode == "measured":
        chosen = [records[i] for i in measured_idx]
        write_queries(chosen, dest)
        found = file_id(dest)
        if found["bytes"] != Q300_BYTES or found["md5"] != Q300_MD5:
            raise SystemExit(
                f"STOP_INPUTS regenerated q300 bytes={found['bytes']} md5={found['md5']}"
            )
        return {
            "query_n": Q300_N,
            "seed": Q300_SEED,
            "name_sha256": Q300_NAME_SHA,
            "path": str(dest),
            **found,
        }
    complement = [i for i in range(len(records)) if i not in set(measured_idx)]
    pilot_idx = sorted(random.Random(PILOT_SEED).sample(complement, PILOT_N))
    if set(pilot_idx) & set(measured_idx):
        raise SystemExit("STOP_INPUTS pilot sample intersects the measured 300")
    pilot_names = [records[i].name for i in pilot_idx]
    digest = sha256_names(pilot_names)
    if digest != PILOT_NAME_SHA:
        raise SystemExit(f"STOP_INPUTS pilot name hash {digest}")
    chosen = [records[i] for i in pilot_idx]
    write_queries(chosen, dest)
    found = file_id(dest)
    return {
        "query_n": PILOT_N,
        "seed": PILOT_SEED,
        "name_sha256": digest,
        "disjoint_from_q300": True,
        "path": str(dest),
        **found,
    }


def parse_decision(path: Path) -> dict:
    if not path.is_file():
        return {"decision": "", "why": "decision.txt missing", "text": ""}
    text = path.read_text()
    decision = ""
    why = ""
    for line in text.splitlines():
        if line.startswith("decision:"):
            decision = line.split(":", 1)[1].strip()
        elif line.startswith("why:"):
            why = line.split(":", 1)[1].strip()
    return {"decision": decision, "why": why, "text": text[-4000:]}


def tare_cmd(
    diamond: str,
    threads: str,
    queries: Path,
    reference: Path,
    cache: Path,
    out_dir: Path,
) -> list[str]:
    prep = f"{diamond} makedb --in {{reference}} --db {{reference}} --threads {threads}"
    return [
        sys.executable,
        "-m",
        "acts",
        "run",
        "--strategy",
        "reference",
        "--input",
        str(queries),
        "--reference",
        str(reference),
        "--prep",
        prep,
        "--pin",
        "--verify",
        "full",
        "--audit-p",
        "0",
        "--cache",
        str(cache),
        "-o",
        str(out_dir),
        "--",
        *s1_placeholders(diamond, threads),
    ]


def body_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text()


def classify_pair(stock_text: str, other_text: str) -> dict:
    compared = correlation(stock_text, other_text)
    keep = (
        "stock_rows",
        "other_rows",
        "shared_rows",
        "shared_byte_identical",
        "shared_byte_fraction",
        "same_hsp_different_value",
        "different_hsp",
        "row_missing",
        "row_extra",
        "only_stock",
        "only_other",
        "bodies_equal",
        "line_order_only",
        "evalue_pearson",
        "evalue_kendall_tau",
        "n_correlation",
        "n_duplicate_pairs_skipped",
    )
    return {key: compared[key] for key in keep}


def arm_stock(diamond: str, db: Path, queries: Path, out: Path, threads: str) -> dict:
    proc = run_proc(blast_cmd(diamond, db, queries, out, threads))
    text = body_file(out)
    return {
        "arm": "stock",
        "ran": proc["returncode"] == 0 and bool(text),
        "wall_s": proc["wall_s"],
        "returncode": proc["returncode"],
        "rows": len(body_lines(text)),
        "output": str(out),
        "stderr_tail": proc["stderr_tail"],
    }


def arm_iseq(
    diamond: str,
    threads: str,
    delta_fa: Path,
    queries: Path,
    old_m8: Path,
    l_old: int,
    work: Path,
    tag: str,
    iseq: Path,
) -> dict:
    started = time.perf_counter()
    built = makedb(diamond, delta_fa, threads)
    makedb_s = built["wall_s"]
    if built["returncode"] != 0:
        return {
            "arm": "iSeqSearch",
            "ran": False,
            "wall_s": time.perf_counter() - started,
            "makedb_s": makedb_s,
            "why": built["stderr_tail"] or built["stdout_tail"],
        }
    try:
        letters, info = dbinfo_letters(diamond, delta_fa)
    except SystemExit as exc:
        return {
            "arm": "iSeqSearch",
            "ran": False,
            "wall_s": time.perf_counter() - started,
            "makedb_s": makedb_s,
            "why": str(exc),
        }
    dbinfo_s = info["wall_s"]
    delta_m8 = work / f"{tag}_delta.m8"
    searched = run_proc(blast_cmd(diamond, delta_fa, queries, delta_m8, threads))
    search_s = searched["wall_s"]
    merged = work / f"{tag}_merged.m8"
    merge_cmd = [
        sys.executable,
        str(iseq / "source" / "main.py"),
        "--default",
        str(old_m8),
        str(delta_m8),
        str(merged),
        str(l_old),
        str(letters),
    ]
    merged_proc = run_proc(merge_cmd, cwd=iseq / "source")
    wall = time.perf_counter() - started
    ran = merged_proc["returncode"] == 0 and merged.is_file()
    row = {
        "arm": "iSeqSearch",
        "ran": ran,
        "wall_s": wall,
        "makedb_s": makedb_s,
        "dbinfo_s": dbinfo_s,
        "search_s": search_s,
        "merge_s": merged_proc["wall_s"],
        "l_old": l_old,
        "l_delta": letters,
        "l_sum": l_old + letters,
        "search_returncode": searched["returncode"],
        "merge_returncode": merged_proc["returncode"],
        "output": str(merged) if merged.is_file() else "",
        "rows": len(body_lines(body_file(merged))) if merged.is_file() else 0,
        "commit": "7e862bf3afa52b65b3cca4255de66ab4cb764fe3",
    }
    if not ran:
        row["why"] = (merged_proc["stderr_tail"] or merged_proc["stdout_tail"] or searched["stderr_tail"])[-1000:]
    return row


def arm_tare(
    diamond: str,
    threads: str,
    queries: Path,
    reference: Path,
    snapshot: Path,
    work: Path,
    tag: str,
    stock_text: str,
) -> dict:
    cache = work / f"{tag}.sqlite"
    shutil.copy(snapshot, cache)
    out_dir = work / tag
    if out_dir.exists():
        shutil.rmtree(out_dir)
    cmd = tare_cmd(diamond, threads, queries, reference, cache, out_dir)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["OMP_NUM_THREADS"] = threads
    started = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
    wall = time.perf_counter() - started
    decision = parse_decision(out_dir / "decision.txt")
    body_path = out_dir / "tables" / "out"
    text = body_file(body_path)
    returned = bool(text) and body_lines(text) == body_lines(stock_text)
    refused = decision["decision"] == "REFUSE_PIN" or decision["decision"].startswith("REFUSE")
    return {
        "arm": "TARE",
        "ran": bool(decision["decision"]),
        "wall_s": wall,
        "returncode": proc.returncode,
        "decision": decision["decision"],
        "why": decision["why"],
        "refused": refused,
        "returned_stock": returned,
        "body_written": body_path.is_file() and bool(text),
        "body_rows": len(body_lines(text)),
        "stdout_tail": (proc.stdout or "")[-1500:],
        "stderr_tail": (proc.stderr or "")[-1500:],
        "decision_text": decision["text"],
    }


def summarize(arms: list[dict], name: str) -> dict:
    walls = [row["wall_s"] for row in arms if row.get("arm") == name and row.get("ran") and "wall_s" in row]
    if not walls:
        return {"n": 0, "walls_s": [], "mean_s": None, "median_s": None}
    ordered = sorted(walls)
    mid = ordered[len(ordered) // 2]
    median = mid if len(ordered) % 2 else (ordered[len(ordered) // 2 - 1] + mid) / 2
    mean = sum(walls) / len(walls)
    cv = None
    if mean and len(walls) > 1:
        var = sum((wall - mean) ** 2 for wall in walls) / (len(walls) - 1)
        cv = (var ** 0.5) / mean
    return {
        "n": len(walls),
        "walls_s": walls,
        "mean_s": mean,
        "median_s": median,
        "cv": cv,
    }


def package_version(name: str) -> str:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return "missing"


def reverify_saved(stock: Path, other: Path, dest: Path) -> int:
    compared = classify_pair(stock.read_text(), other.read_text())
    bad_lines = body_lines(other.read_text())
    bad = classify_bodies(stock.read_text(), "\n".join(bad_lines[:-1]) + "\n")
    good = classify_bodies(stock.read_text(), stock.read_text())
    payload = {
        "system": "TARE",
        "test": "iseqsearch-reverify-saved",
        "protocol": "pipeline/docs/ISEQSEARCH_TIMING_PROTOCOL.md",
        "laptop_wall_is_speed_evidence": False,
        "host": platform.node(),
        "git_head": os.environ.get("ACTS_GIT_HASH", ""),
        "stock": file_id(stock),
        "other": file_id(other),
        "classification": compared,
        "known_good_bodies_equal": good["bodies_equal"] and good["shared_byte_identical"] == good["shared_rows"],
        "known_bad_bodies_equal": bad["bodies_equal"],
        "known_bad_row_missing": bad["row_missing"],
        "matches_dx_i_integers": (
            compared["shared_rows"] == 31377
            and compared["shared_byte_identical"] == 407
            and compared["same_hsp_different_value"] == 30968
            and compared["different_hsp"] == 2
            and compared["row_extra"] == 133
            and compared["row_missing"] == 0
            and compared["bodies_equal"] is False
        ),
    }
    try:
        payload["provenance"] = provenance()
    except Exception as exc:
        payload["provenance_error"] = str(exc)
    write_json(dest, payload)
    log(json.dumps({k: payload[k] for k in ("matches_dx_i_integers", "known_good_bodies_equal", "known_bad_row_missing")}))
    return 0 if payload["matches_dx_i_integers"] and payload["known_good_bodies_equal"] and bad["row_missing"] >= 1 and not bad["bodies_equal"] else 1


def run_mode(mode: str) -> int:
    global OUT_PATH
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("STOP: pilot and measured runs execute only under sbatch")
    diamond = os.environ["TARE_DIAMOND"]
    old_fa = Path(os.environ["TARE_OLD_FASTA"])
    new_fa = Path(os.environ["TARE_NEW_FASTA"])
    proteome = Path(os.environ["TARE_QUERY_FAA"])
    iseq = Path(os.environ["TARE_ISEQ"])
    scratch = Path(os.environ["TARE_SCRATCH"])
    threads = os.environ["TARE_THREADS"]
    out = Path(os.environ["TARE_OUT"])
    OUT_PATH = out
    scratch.mkdir(parents=True, exist_ok=True)
    kind = fstype(scratch)
    if not kind or kind == "tmpfs":
        raise SystemExit(f"STOP_SCRATCH fstype {kind!r}")
    free = shutil.disk_usage(scratch).free
    if free < 30 * (1024**3):
        raise SystemExit(f"STOP_SCRATCH free bytes {free}")

    repeats = 1 if mode == "pilot" else 3
    signal.signal(signal.SIGTERM, on_term)
    identities = {
        "old": require_file(old_fa, EXPECTED["old"], "2026_01"),
        "new": require_file(new_fa, EXPECTED["new"], "2026_03"),
        "queries": require_file(proteome, EXPECTED["queries"], "GCF_002853805.1"),
        "iseq_main": require_file(iseq / "source" / "main.py", EXPECTED["iseq_main"], "iSeqSearch main.py"),
    }
    diamond_id = file_id(Path(diamond))
    version = run_proc([diamond, "version"], timeout=60)
    version_text = (version["stdout_tail"] + version["stderr_tail"]).strip()
    if version["returncode"] != 0 or "2.2.5" not in version_text:
        raise SystemExit(f"STOP diamond version is not 2.2.5: {version_text}")
    if mode == "measured" and (
        diamond_id["bytes"] != EXPECTED["diamond_linux"][0]
        or diamond_id["md5"] != EXPECTED["diamond_linux"][1]
    ):
        raise SystemExit(
            f"STOP_INPUTS CARC diamond bytes={diamond_id['bytes']} md5={diamond_id['md5']}"
        )

    PAYLOAD.clear()
    PAYLOAD.update(
        {
            "system": "TARE",
            "test": f"iseqsearch-timing-{mode}",
            "protocol": "pipeline/docs/ISEQSEARCH_TIMING_PROTOCOL.md",
            "mode": mode,
            "partial": True,
            "verdict": "INCONCLUSIVE",
            "why": "running",
            "laptop_wall_is_speed_evidence": False,
            "speed_claim": False,
            "repeats_requested": repeats,
            "threads": threads,
            "job_id": os.environ.get("SLURM_JOB_ID"),
            "host": platform.node(),
            "cpu_model": cpu_model(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "biopython": package_version("biopython"),
            "tqdm": package_version("tqdm"),
            "scratch": str(scratch),
            "scratch_fstype": kind,
            "scratch_free_bytes_start": free,
            "slurm_cpus": os.environ.get("SLURM_CPUS_PER_TASK"),
            "slurm_partition": os.environ.get("SLURM_JOB_PARTITION", ""),
            "exclusive_requested": os.environ.get("TARE_EXCLUSIVE", "") == "1",
            "constraint": os.environ.get("SLURM_JOB_CONSTRAINTS", ""),
            "inputs": identities,
            "diamond": diamond_id,
            "diamond_version": version_text,
            "iseq_commit": "7e862bf3afa52b65b3cca4255de66ab4cb764fe3",
            "frozen_code_commit": os.environ.get("ACTS_GIT_HASH", ""),
            "s1_argv": s1_placeholders(diamond, threads),
            "arms": [],
        }
    )
    try:
        PAYLOAD["provenance"] = provenance(versions={"diamond": version_text})
    except Exception as exc:
        PAYLOAD["provenance_error"] = str(exc)
    persist()

    work = scratch / mode
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    log(f"queries mode={mode}")
    query_info = draw_queries(proteome, mode, work / "queries.faa")
    queries = work / "queries.faa"
    PAYLOAD["queries"] = query_info
    persist()

    log("parsing releases")
    prep_started = time.perf_counter()
    # Databases are built beside scratch copies. The shared FASTAs are not rewritten.
    local_old = work / "uniprot_sprot_2026_01.fasta.gz"
    local_new = work / "uniprot_sprot_2026_03.fasta.gz"
    shutil.copyfile(old_fa, local_old)
    shutil.copyfile(new_fa, local_new)
    old_fa = local_old
    new_fa = local_new
    old_entries = parse_reference(old_fa)
    new_entries = parse_reference(new_fa)
    changed = changed_entries(old_entries, new_entries)
    delta_fa = work / "delta.faa"
    write_entries(changed, delta_fa)
    diff_s = time.perf_counter() - prep_started
    if len(changed) != DELTA_N:
        PAYLOAD["verdict"] = "STOP_INPUTS"
        PAYLOAD["why"] = f"delta entries {len(changed)} != {DELTA_N}"
        PAYLOAD["partial"] = False
        persist()
        return 2
    log("makedb full releases")
    old_build = makedb(diamond, old_fa, threads)
    new_build = makedb(diamond, new_fa, threads)
    if old_build["returncode"] != 0 or new_build["returncode"] != 0:
        PAYLOAD["verdict"] = "INCONCLUSIVE"
        PAYLOAD["why"] = "full makedb failed"
        PAYLOAD["prep_error"] = {
            "old": old_build["stderr_tail"],
            "new": new_build["stderr_tail"],
        }
        persist()
        return 2
    l_old, _info = dbinfo_letters(diamond, old_fa)
    if l_old != L_OLD:
        PAYLOAD["verdict"] = "STOP_INPUTS"
        PAYLOAD["why"] = f"l_old {l_old} != {L_OLD}"
        PAYLOAD["partial"] = False
        persist()
        return 2
    PAYLOAD["prep"] = {
        "diff_wall_s": diff_s,
        "delta_entries": len(changed),
        "delta": file_id(delta_fa),
        "old_makedb_s": old_build["wall_s"],
        "new_makedb_s": new_build["wall_s"],
        "l_old": l_old,
        "old_entries": len(old_entries),
        "new_entries": len(new_entries),
    }
    persist()

    log("warm 2026_01 search")
    warm = arm_stock(diamond, old_fa, queries, work / "warm_2026_01.m8", threads)
    warm["timed"] = False
    PAYLOAD["warm_old"] = warm
    persist()
    if not warm["ran"]:
        PAYLOAD["why"] = "warm 2026_01 search failed"
        persist()
        return 2

    log("stock vs stock")
    stock_a = arm_stock(diamond, new_fa, queries, work / "stock_a.m8", threads)
    stock_b = arm_stock(diamond, new_fa, queries, work / "stock_b.m8", threads)
    text_a = body_file(work / "stock_a.m8")
    text_b = body_file(work / "stock_b.m8")
    identical = body_lines(text_a) == body_lines(text_b) and bool(text_a)
    classes = classify_bodies(text_a, text_b)
    good = classify_bodies(text_a, text_a)
    PAYLOAD["stock_vs_stock"] = {
        "identical": identical,
        "a_rows": stock_a["rows"],
        "b_rows": stock_b["rows"],
        "a_wall_s": stock_a["wall_s"],
        "b_wall_s": stock_b["wall_s"],
        "classes": {
            key: classes[key]
            for key in (
                "bodies_equal",
                "same_hsp_different_value",
                "different_hsp",
                "row_missing",
                "row_extra",
                "line_order_only",
                "shared_rows",
            )
        },
        "known_good": bool(good["bodies_equal"] and good["shared_byte_identical"] == good["shared_rows"]),
    }
    PAYLOAD["prep"]["stock_vs_stock_wall_s"] = stock_a["wall_s"] + stock_b["wall_s"]
    persist()
    floor = 100 if mode == "pilot" else 1000
    if stock_a["rows"] < floor or query_info["query_n"] != (PILOT_N if mode == "pilot" else Q300_N):
        PAYLOAD["verdict"] = "INCONCLUSIVE"
        PAYLOAD["why"] = f"power floor stock_rows={stock_a['rows']} query_n={query_info['query_n']}"
        PAYLOAD["partial"] = False
        persist()
        return 0
    if not identical or not PAYLOAD["stock_vs_stock"]["known_good"]:
        PAYLOAD["verdict"] = "INCONCLUSIVE"
        PAYLOAD["why"] = "stock-vs-stock bodies differ or known-good failed"
        PAYLOAD["partial"] = False
        persist()
        return 0

    log("cold TARE")
    cold_cache = work / "cold.sqlite"
    cold_dir = work / "tare_cold"
    cold_cmd = tare_cmd(diamond, threads, queries, new_fa, cold_cache, cold_dir)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["OMP_NUM_THREADS"] = threads
    cold_started = time.perf_counter()
    cold_proc = subprocess.run(cold_cmd, check=False, capture_output=True, text=True, env=env)
    cold_wall = time.perf_counter() - cold_started
    cold_decision = parse_decision(cold_dir / "decision.txt")
    snapshot = work / "contract.sqlite"
    if cold_cache.is_file():
        shutil.copy(cold_cache, snapshot)
    PAYLOAD["tare_cold"] = {
        "wall_s": cold_wall,
        "returncode": cold_proc.returncode,
        "decision": cold_decision["decision"],
        "why": cold_decision["why"],
        "contract_stored": snapshot.is_file(),
        "stdout_tail": (cold_proc.stdout or "")[-1500:],
        "stderr_tail": (cold_proc.stderr or "")[-1500:],
        "in_alternating_mean": False,
    }
    persist()
    if not snapshot.is_file() or not cold_decision["decision"]:
        PAYLOAD["why"] = "cold TARE did not store a contract"
        persist()
        return 2

    log("alternating")
    alternating_started = time.perf_counter()
    arms: list[dict] = []
    rotation = ORDER if repeats == 3 else (ORDER[0],)
    for repeat, triple in enumerate(rotation, start=1):
        for name in triple:
            tag = f"r{repeat}_{name}"
            log(f"arm {tag}")
            if name == "stock":
                row = arm_stock(diamond, new_fa, queries, work / f"{tag}.m8", threads)
            elif name == "iSeqSearch":
                row = arm_iseq(
                    diamond,
                    threads,
                    delta_fa,
                    queries,
                    work / "warm_2026_01.m8",
                    l_old,
                    work,
                    tag,
                    iseq,
                )
            else:
                row = arm_tare(diamond, threads, queries, new_fa, snapshot, work, tag, text_a)
            row["repeat"] = repeat
            row["timed"] = True
            arms.append(row)
            PAYLOAD["arms"] = arms
            persist()
            log(f"done {tag} ran={row.get('ran')} wall={row.get('wall_s')}")

    iseq_rows = [row for row in arms if row["arm"] == "iSeqSearch" and row.get("ran") and row.get("output")]
    classifications = []
    known_bad_ok = False
    negative_ok = False
    if iseq_rows:
        other_text = body_file(Path(iseq_rows[-1]["output"]))
        classifications.append({"which": iseq_rows[-1]["repeat"], **classify_pair(text_a, other_text)})
        dropped_lines = body_lines(other_text)
        if len(dropped_lines) < 2:
            known_bad_ok = False
        else:
            dropped = "\n".join(dropped_lines[:-1]) + "\n"
            bad = classify_bodies(text_a, dropped)
            known_bad_ok = (not bad["bodies_equal"]) and bad["row_missing"] >= 1
            PAYLOAD["known_bad"] = {
                "bodies_equal": bad["bodies_equal"],
                "row_missing": bad["row_missing"],
                "passed": known_bad_ok,
            }
        negative_ok = classifications[-1]["bodies_equal"] is False and classifications[-1]["other_rows"] > 0
    tare_rows = [row for row in arms if row["arm"] == "TARE"]
    refusal_ok = bool(tare_rows) and all(row.get("refused") for row in tare_rows)
    all_ran = len(arms) == repeats * 3 and all(row.get("ran") for row in arms)
    PAYLOAD["classification"] = classifications
    PAYLOAD["summary"] = {
        "stock": summarize(arms, "stock"),
        "iSeqSearch": summarize(arms, "iSeqSearch"),
        "TARE": summarize(arms, "TARE"),
    }
    stock_mean = PAYLOAD["summary"]["stock"]["mean_s"]
    iseq_mean = PAYLOAD["summary"]["iSeqSearch"]["mean_s"]
    tare_mean = PAYLOAD["summary"]["TARE"]["mean_s"]
    PAYLOAD["ratios_of_means"] = {
        "stock_over_iseq": (stock_mean / iseq_mean) if stock_mean and iseq_mean else None,
        "stock_over_tare": (stock_mean / tare_mean) if stock_mean and tare_mean else None,
    }
    PAYLOAD["controls"] = {
        "stock_vs_stock": identical,
        "known_good": True,
        "known_bad": known_bad_ok,
        "iseq_not_byte_identical": negative_ok,
        "tare_refused": refusal_ok,
        "power": stock_a["rows"] >= floor,
        "tare_returned_stock": [row.get("returned_stock") for row in tare_rows],
    }
    if not all_ran:
        PAYLOAD["verdict"] = "INCONCLUSIVE"
        PAYLOAD["why"] = "an arm did not finish"
    elif not (known_bad_ok and negative_ok and refusal_ok):
        PAYLOAD["verdict"] = "FAIL_CONTROL"
        PAYLOAD["why"] = "a locked control failed"
    else:
        PAYLOAD["verdict"] = "COMPLETE"
        PAYLOAD["why"] = "arms finished and controls passed"
    PAYLOAD["partial"] = False
    search_s = 0.0
    pass_s = 0.0
    for row in arms:
        if not row.get("ran"):
            continue
        pass_s += float(row["wall_s"])
        if row["arm"] == "stock":
            search_s += float(row["wall_s"])
        elif row["arm"] == "iSeqSearch":
            search_s += float(row.get("search_s") or 0.0)
    once_s = alternating_started - prep_started
    PAYLOAD["timing_split"] = {
        "once_s": once_s,
        "pass_s": pass_s,
        "search_s": search_s,
        "in_alternating_mean": False,
    }
    if mode == "pilot" and pass_s:
        scaled_pass = pass_s - search_s + (300 / 50) * search_s
        PAYLOAD["measured_limit_s"] = 1.5 * (once_s + 3 * scaled_pass)
    persist()
    log(f"verdict {PAYLOAD['verdict']}")
    return 0


def check_imports() -> int:
    import acts  # noqa: F401
    from acts.reference_run import ReferenceIncremental  # noqa: F401

    log("imports ok")
    log(f"biopython {package_version('biopython')} tqdm {package_version('tqdm')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TARE iSeqSearch timing")
    parser.add_argument(
        "command",
        choices=("check", "reverify-saved", "pilot", "measured"),
    )
    parser.add_argument("--stock", type=Path)
    parser.add_argument("--other", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.command == "check":
        return check_imports()
    if args.command == "reverify-saved":
        if not args.stock or not args.other or not args.out:
            raise SystemExit("reverify-saved needs --stock --other --out")
        return reverify_saved(args.stock, args.other, args.out)
    return run_mode(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
