"""Stock hmmscan timing for genomes the savings runs left imputed.

The command matches ``scripts/run_hmmer_savings.py`` stock argv: HMMER
3.4, ``--cpu``, ``--cut_ga``, ``--noali``, and ``--tblout``. A finished
measurement is not overwritten. This mode is post-hoc and is not
``paper_uses``.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import resource
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from acts.fasta import parse_fasta, write_fasta
from acts.provenance import provenance
from acts.savings_analysis import StockTask

KIND = "hmmscan_stock_completion"
TASK_KIND = "hmmscan_stock_tasks"


def stock_argv(
    binary: str, hmm: Path, fasta: Path, tblout: Path, cpu: int
) -> list[str]:
    return [
        binary,
        "--cpu",
        str(cpu),
        "--cut_ga",
        "--noali",
        "--tblout",
        str(tblout),
        str(hmm),
        str(fasta),
    ]


def task_manifest(tasks: list[StockTask]) -> dict[str, Any]:
    return {
        "kind": TASK_KIND,
        "n_tasks": len(tasks),
        "tasks": [
            {
                "array_index": index,
                "collection": task.collection,
                "position": task.position,
                "accession": task.accession,
                "input_path": task.input_path,
            }
            for index, task in enumerate(tasks)
        ],
    }


def load_manifest(path: Path) -> list[StockTask]:
    raw = json.loads(path.read_text())
    if raw.get("kind") != TASK_KIND:
        raise ValueError(f"{path}: not an hmmscan stock-task manifest")
    tasks = [
        StockTask(
            collection=str(row["collection"]),
            position=int(row["position"]),
            accession=str(row["accession"]),
            input_path=str(row["input_path"]),
        )
        for row in raw.get("tasks") or []
    ]
    if [row["array_index"] for row in raw["tasks"]] != list(range(len(tasks))):
        raise ValueError(f"{path}: array indexes are not 0..n-1")
    return tasks


def result_path(out_dir: Path, task: StockTask) -> Path:
    return out_dir / f"{task.collection}_{task.position:02d}.json"


def _load_fasta(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as stream:
            return stream.read()
    return path.read_text()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _children_cpu_s() -> float:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return float(usage.ru_utime) + float(usage.ru_stime)


def _finished(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError:
        return False
    return (
        raw.get("kind") == KIND
        and raw.get("returncode") == 0
        and float(raw.get("stock_wall_s") or 0) > 0
    )


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def ensure_pressed(hmm: Path, hmmpress: str) -> None:
    pressed = Path(str(hmm) + ".h3m")
    if pressed.is_file() and pressed.stat().st_mtime >= hmm.stat().st_mtime:
        return
    proc = subprocess.run(
        [hmmpress, "-f", str(hmm)], check=False, capture_output=True, text=True
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "")[-800:]
        raise RuntimeError(f"hmmpress failed: {detail}")


def measure_stock(
    task: StockTask,
    *,
    data_root: Path,
    hmm: Path,
    hmmscan: str,
    hmmpress: str,
    out_dir: Path,
    work: Path,
    cpu: int,
) -> Path:
    destination = result_path(out_dir, task)
    if _finished(destination):
        return destination
    source = data_root / task.input_path
    if not source.is_file():
        raise FileNotFoundError(source)
    work.mkdir(parents=True, exist_ok=True)
    fasta = work / f"{task.collection}_{task.position:02d}.faa"
    write_fasta(fasta, parse_fasta(_load_fasta(source)))
    tblout = work / f"{task.collection}_{task.position:02d}.tbl"
    ensure_pressed(hmm, hmmpress)
    argv = stock_argv(hmmscan, hmm, fasta, tblout, cpu)
    version = subprocess.run(
        [hmmscan, "-h"], check=False, capture_output=True, text=True
    )
    cpu_before = _children_cpu_s()
    started = time.perf_counter()
    proc = subprocess.run(argv, check=False, capture_output=True, text=True)
    wall_s = time.perf_counter() - started
    payload = {
        "kind": KIND,
        "collection": task.collection,
        "position": task.position,
        "accession": task.accession,
        "input_path": task.input_path,
        "argv": argv,
        "returncode": proc.returncode,
        "stock_wall_s": wall_s,
        "stock_cpu_s": _children_cpu_s() - cpu_before,
        "tblout_bytes": tblout.stat().st_size if tblout.is_file() else 0,
        "hmmer": " | ".join((version.stdout or version.stderr).splitlines()[:3]),
        "pfam_sha256": _sha256(hmm),
        "cpu": cpu,
        "host": os.uname().nodename,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
        "stderr_tail": (proc.stderr or "")[-400:],
        "provenance": provenance(versions={"hmmer": hmmscan, "pfam": str(hmm)}),
    }
    if proc.returncode != 0:
        _write(destination, payload)
        detail = (proc.stderr or proc.stdout or "")[-800:]
        raise RuntimeError(f"hmmscan failed ({proc.returncode}): {detail}")
    if not tblout.is_file() or tblout.stat().st_size == 0:
        raise RuntimeError(f"hmmscan wrote no table: {tblout}")
    out_dir.mkdir(parents=True, exist_ok=True)
    kept = out_dir / tblout.name
    shutil.copy2(tblout, kept)
    payload["tblout"] = str(kept)
    _write(destination, payload)
    return destination
