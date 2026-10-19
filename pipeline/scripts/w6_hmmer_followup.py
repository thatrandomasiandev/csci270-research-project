#!/usr/bin/env python3
"""Post-hoc HMMER rerun after the row-occurrence index.

Same argv as the recorded run. Not part of the locked headline and not
part of the locked diverse-genome draw. Pass is SHIP on the fill and on
the update, with the update body byte-identical to stock on Pfam 38.2.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "scripts"))

import diverse_genomes_carc as div  # noqa: E402

MD5_OLD = div.MD5_OLD
MD5_NEW = div.MD5_NEW
Z_OLD = div.Z_OLD
Z_NEW = div.Z_NEW

# Checksums recorded on the runs this follow-up repeats.
TASKS = (
    {
        "accession": "GCF_002078355.1",
        "source": "diverse",
        "cpu": "8",
        "proteome_md5": "197fccdf32ffddecca803d3dcb0566e0",
        "why": "duplicate row key ('WP_196795573.1', 'TPR_17', '2.4e-08')",
    },
    {
        "accession": "GCF_000284335.1",
        "source": "diverse",
        "cpu": "8",
        "proteome_md5": "8992b4a86232d603178bf6e333ee9e15",
        "why": "duplicate row key ('WP_014453168.1', 'DNA_gyraseA_C', '1.6e-12')",
    },
    {
        "accession": "GCF_001017655.1",
        "source": "diverse",
        "cpu": "8",
        "proteome_md5": "afaa3f3860e46d99af5b08f5e2108b81",
        "why": "duplicate row key ('WP_052881759.1', 'Hexapep_2', '1.4e-05')",
    },
    {
        "accession": "GCA_001817145.1",
        "source": "diverse",
        "cpu": "8",
        "proteome_md5": "655f1272b23609e3c1bfeb7ec538dee5",
        "why": "tblout: column 18 is mixed numeric and text",
    },
    {
        "accession": "GCF_000001215.4",
        "source": "diverse",
        "cpu": "8",
        "proteome_md5": "d0a81857fd1aa796ff9236cbd5105ab0",
        "why": "tblout: column 18 is mixed numeric and text",
    },
    {
        "accession": "GCF_015290725.1",
        "source": "headline",
        "cpu": "4",
        "proteome_md5": "c878c7a14801d4587dd930b34d3e5fe7",
        "why": "duplicate row key ('WP_000726974.1', 'Gly-zipper_OmpA', '1.2e-06')",
    },
)

PAYLOAD: dict | None = None


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


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
        write_out(PAYLOAD)
    raise SystemExit(2)


def task_by_accession(accession: str) -> dict:
    for task in TASKS:
        if task["accession"] == accession:
            return task
    raise SystemExit(f"unknown accession {accession}")


def main() -> int:
    global PAYLOAD
    parser = argparse.ArgumentParser(description="TARE W6 HMMER follow-up (one genome)")
    parser.add_argument("--accession", required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--old-hmm", type=Path, required=True)
    parser.add_argument("--new-hmm", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("STOP: this run executes only under sbatch")

    spec = task_by_accession(args.accession)
    div.CPU = spec["cpu"]
    os.environ["ACTS_OUT"] = str(args.out)
    args.scratch.mkdir(parents=True, exist_ok=True)
    version = subprocess.run(["hmmscan", "-h"], check=False, capture_output=True, text=True)
    version_lines = (version.stdout or version.stderr or "").splitlines()[:3]
    payload: dict = {
        "test": "w6-hmmer-followup",
        "system": "TARE",
        "package": "acts",
        "role": "follow-up",
        "not_part_of_locked_draw": True,
        "not_a_speedup_claim": True,
        "prior_refusal": spec["why"],
        "prior_source": spec["source"],
        "accession": spec["accession"],
        "cpu": int(spec["cpu"]),
        "frozen_code_commit": os.environ.get("ACTS_COMMIT", ""),
        "git_head": os.environ.get("ACTS_GIT_HEAD", ""),
        "job_id": os.environ.get("SLURM_ARRAY_JOB_ID") or os.environ.get("SLURM_JOB_ID"),
        "array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version,
        "hmmer_version_lines": version_lines,
        "hmmer_tarball_sha256": os.environ.get("ACTS_HMMER_SHA256", ""),
        "scratch": str(args.scratch),
        "argv_stock": (
            "hmmscan --cut_ga --noali --cpu "
            f"{spec['cpu']} --tblout --domtblout -o /dev/null"
        ),
        "argv_acts": (
            "python3 -m acts run --strategy reference --pin '-Z {entry_count}' "
            "--verify audit --prep 'hmmpress -f {reference}' -- "
            f"hmmscan --cut_ga --noali --cpu {spec['cpu']}"
        ),
    }
    PAYLOAD = payload
    signal.signal(signal.SIGTERM, _on_term)
    free = shutil.disk_usage(args.scratch).free
    payload["scratch_free_bytes_start"] = free
    if free < div.MIN_FREE:
        stop(f"scratch has {free} bytes free, need {div.MIN_FREE}", payload)
    if not any("HMMER 3.4" in line for line in version_lines):
        stop(f"hmmscan is not HMMER 3.4: {version_lines}", payload)
    for path in (args.old_hmm, args.new_hmm, args.queries):
        if not path.is_file():
            stop(f"missing {path}", payload)
    got = div.md5_file(args.queries)
    payload["proteome_md5"] = got
    payload["proteome_bytes"] = args.queries.stat().st_size
    if got != spec["proteome_md5"]:
        stop(f"proteome md5 {got} != recorded {spec['proteome_md5']}", payload)
    payload["input_md5"] = {
        "pfam38.1": div.md5_file(args.old_hmm),
        "pfam38.2": div.md5_file(args.new_hmm),
        "proteome": got,
    }
    if payload["input_md5"]["pfam38.1"] != MD5_OLD or payload["input_md5"]["pfam38.2"] != MD5_NEW:
        stop(f"Pfam md5 {payload['input_md5']}", payload)

    old_db = args.scratch / "Pfam-A.38.1.hmm"
    new_db = args.scratch / "Pfam-A.38.2.hmm"
    div.gunzip_to(args.old_hmm, old_db)
    div.gunzip_to(args.new_hmm, new_db)
    pressed = {"38.1": div.press_models(old_db), "38.2": div.press_models(new_db)}
    payload["pressed_models"] = pressed
    if pressed["38.1"] != Z_OLD or pressed["38.2"] != Z_NEW:
        stop(f"press counts {pressed} != {(Z_OLD, Z_NEW)}", payload)

    work = args.scratch / spec["accession"]
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    stock = div.stock_scan(new_db, args.queries, work / "stock_a.tbl", work / "stock_a.dom")
    payload["stock"] = {"wall_s": stock["wall_s"], "argv": stock["argv"]}
    payload["stock_tbl_lines"] = len(div.read_body(work / "stock_a.tbl"))
    payload["stock_dom_lines"] = len(div.read_body(work / "stock_a.dom"))
    write_out(payload)

    cache = work / "cache.sqlite"
    fill = div.tare_run(old_db, args.queries, cache, work / "fill")
    update = div.tare_run(new_db, args.queries, cache, work / "update")
    tbl = Path(update["tbl"])
    dom = Path(update["dom"])
    compared = None
    if tbl.is_file() and dom.is_file():
        compared = div.compare_pair(tbl, dom, work / "stock_a.tbl", work / "stock_a.dom")
        compared["files_present"] = True
    payload["fill"] = {
        "wall_s": fill["wall_s"],
        "returncode": fill["returncode"],
        "decision": fill["decision"],
        "why": fill["why"],
        "argv": fill["argv"],
    }
    payload["update"] = {
        "wall_s": update["wall_s"],
        "returncode": update["returncode"],
        "decision": update["decision"],
        "why": update["why"],
        "argv": update["argv"],
    }
    payload["compare"] = compared
    fill_ok = fill["decision"] == "SHIP"
    update_ok = update["decision"] == "SHIP"
    body_ok = bool(compared and compared.get("byte_equal"))
    if fill_ok and update_ok and body_ok:
        payload["outcome"] = "SHIP"
        payload["claim_class"] = "pass"
    elif compared is None:
        payload["outcome"] = "FAIL"
        payload["claim_class"] = "INCONCLUSIVE"
    else:
        payload["outcome"] = "NOT_SHIP"
        payload["claim_class"] = "NOT_SHIP"
        payload["difference_classes"] = compared.get("classes", [])
    payload["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_out(payload)
    shutil.rmtree(work, ignore_errors=True)
    log(f"done {spec['accession']} {payload['outcome']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException as exc:
        if PAYLOAD is not None and "outcome" not in PAYLOAD:
            PAYLOAD["crashed"] = f"{type(exc).__name__}: {exc}"[:2000]
            PAYLOAD["outcome"] = "FAIL"
            PAYLOAD["claim_class"] = "INCONCLUSIVE"
            write_out(PAYLOAD)
        raise
