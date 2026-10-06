#!/usr/bin/env python3
"""Timed Pfam 38.1 → 38.2 re-annotation. The protocol addendum is the spec.

Arms, per genome, on one node, in this order for each repeat:
  (i)   stock hmmscan on the pressed new release
  (ii)  reference-incremental, warm from the old-release cache
  (iii) gestore baseline (no normalizer inference)

Setup and the genome-1 ref-merge preflight are recorded and are not repeats.
A ref-merge mismatch stops the job. The analysis script, not this one, prints
CONFIRMED or REFUTED.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import resource
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.provenance import provenance  # noqa: E402
from acts.reference_cache import argv_namespace, connect_cache  # noqa: E402
from acts.reference_fit import index_rows, parse_table_text, ref_merge_rows  # noqa: E402
from acts.reference_run import ReferenceIncremental, tables_from_dict  # noqa: E402

ARGV = [
    "hmmscan",
    "--cpu",
    "32",
    "--cut_ga",
    "--noali",
    "--tblout",
    "{output:targets}",
    "--domtblout",
    "{output:domains}",
    "{reference}",
    "{input}",
]
PREP = "hmmpress -f {reference}"
ARMS = ("stock", "acts", "gestore")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    raw = path.read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    return raw.decode().strip()


def n_proteins(path: Path) -> int:
    n = 0
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt") as handle:
        for line in handle:
            if line.startswith(">"):
                n += 1
    return n


def cpu_model() -> str:
    path = Path("/proc/cpuinfo")
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor()


def tool_banner(binary: str) -> str:
    proc = subprocess.run([binary, "-h"], capture_output=True, text=True)
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        if "HMMER" in line:
            return line.lstrip("# ").strip()
    return ""


def dump(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(path)


def decompress(src: Path, dest: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 0:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = src.read_bytes()[:2]
    if raw == b"\x1f\x8b":
        with gzip.open(src, "rb") as inp, dest.open("wb") as out:
            shutil.copyfileobj(inp, out, length=1 << 20)
        return
    if src.resolve() != dest.resolve():
        shutil.copyfile(src, dest)


def genome_faa(directory: Path, accession: str) -> Path:
    for name in (f"{accession}_protein.faa.gz", f"{accession}_protein.faa"):
        path = directory / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"no proteome for {accession} under {directory}")


def snapshot_cache(src: Path, dest: Path) -> None:
    """Copy a closed SQLite cache. Resume restores this onto node-local disk."""
    if not src.is_file():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(src)
    target = sqlite3.connect(dest)
    try:
        with target:
            source.backup(target)
    finally:
        source.close()
        target.close()


def child_cpu() -> float:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return float(usage.ru_utime + usage.ru_stime)


def run_cmd(cmd: list[str]) -> tuple[float, float]:
    cpu0 = child_cpu()
    started = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - started
    cpu = child_cpu() - cpu0
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-800:]
        raise RuntimeError(f"{cmd[0]} failed ({proc.returncode}): {err}")
    return wall, cpu


def press(hmm: Path) -> float:
    if Path(str(hmm) + ".h3m").is_file():
        return 0.0
    wall, _cpu = run_cmd(["hmmpress", "-f", str(hmm)])
    return wall


def stock_scan(hmm: Path, faa: Path, tbl: Path, dom: Path) -> tuple[float, float]:
    tbl.parent.mkdir(parents=True, exist_ok=True)
    return run_cmd(
        [
            "hmmscan",
            "--cpu",
            "32",
            "--cut_ga",
            "--noali",
            "--tblout",
            str(tbl),
            "--domtblout",
            str(dom),
            str(hmm),
            str(faa),
        ]
    )


def acts_scan(
    *,
    reference: Path,
    faa: Path,
    out_dir: Path,
    cache: Path,
    baseline: str | None,
) -> tuple[float, float, object]:
    cpu0 = child_cpu()
    started = time.perf_counter()
    result = ReferenceIncremental(
        argv=ARGV,
        input_path=faa,
        out_dir=out_dir,
        reference=reference,
        prep=PREP,
        baseline=baseline,
        cache_path=cache,
        verify="audit",
        audit_p=0.0,
    ).run()
    wall = time.perf_counter() - started
    return wall, child_cpu() - cpu0, result


def compare(stock_dir: Path, acts_dir: Path, cache: Path, reference: Path) -> dict:
    handle = connect_cache(cache)
    try:
        contract = handle.load_contract(argv_namespace(ARGV, reference, None))
    finally:
        handle.close()
    if not contract or contract.get("decision") != "SHIP":
        return {"ok": False, "why": "fit contract is not SHIP", "tables": []}
    tables = tables_from_dict(contract.get("tables") or [])
    details = []
    for table in tables:
        stock_path = stock_dir / table.name
        acts_path = acts_dir / "tables" / table.name
        if not stock_path.is_file() or not acts_path.is_file():
            return {
                "ok": False,
                "why": f"missing table {table.name}",
                "tables": details,
            }
        try:
            stock_rows = index_rows(
                parse_table_text(table.name, stock_path.read_text()).rows,
                table.record_col,
                table.entry_col,
                table.index_col,
            )
            acts_rows = index_rows(
                parse_table_text(table.name, acts_path.read_text()).rows,
                table.record_col,
                table.entry_col,
                table.index_col,
            )
            ok, why = ref_merge_rows(stock_rows, acts_rows, table.columns)
        except (OSError, UnicodeError, ValueError) as exc:
            return {"ok": False, "why": f"{table.name}: {exc}", "tables": details}
        details.append({"table": table.name, "ok": ok, "why": why, "n_stock": len(stock_rows), "n_acts": len(acts_rows)})
        if not ok:
            return {"ok": False, "why": f"{table.name}: {why}", "tables": details}
    if not details:
        return {"ok": False, "why": "fit contract has no tables", "tables": []}
    return {"ok": True, "why": "", "tables": details}


def host_block(old: Path, new: Path, old_version: Path | None, new_version: Path | None) -> dict:
    base = provenance()
    env_hash = os.environ.get("ACTS_GIT_HASH", "").strip()
    if env_hash:
        base["git"] = env_hash
    base.update(
        {
            "cpu_model": cpu_model(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
            "slurm_nodelist": os.environ.get("SLURM_NODELIST", ""),
            "hmmer": tool_banner("hmmscan"),
            "hmmpress": tool_banner("hmmpress"),
            "pfam_old_sha256": sha256(old),
            "pfam_new_sha256": sha256(new),
            "pfam_old_version": version_text(old_version),
            "pfam_new_version": version_text(new_version),
            "pfam_old_path": str(old),
            "pfam_new_path": str(new),
        }
    )
    return base


def drop_incomplete(payload: dict) -> None:
    """A repeat counts only when stock, acts, gestore, and the match are stored."""
    runs = payload.get("runs") or []
    grouped: dict[tuple[str, int], set[str]] = {}
    matched: set[tuple[str, int]] = set()
    for row in runs:
        if not row.get("timed"):
            continue
        key = (row["accession"], int(row["repeat"]))
        grouped.setdefault(key, set()).add(row["arm"])
        if row.get("arm") == "acts" and row.get("match", {}).get("ok") is True:
            matched.add(key)
    keep_keys = {key for key, arms in grouped.items() if arms == set(ARMS) and key in matched}
    payload["runs"] = [
        row
        for row in runs
        if (not row.get("timed")) or (row["accession"], int(row["repeat"])) in keep_keys
    ]


def done_keys(payload: dict) -> set[tuple[str, int, str]]:
    return {
        (row["accession"], int(row["repeat"]), row["arm"])
        for row in payload.get("runs") or []
        if row.get("timed")
    }


def filled(payload: dict) -> set[str]:
    return {row["accession"] for row in payload.get("setup", {}).get("cache_fill") or []}


def record_run(payload: dict, row: dict, out: Path) -> None:
    payload.setdefault("runs", []).append(row)
    dump(payload, out)
    print(
        f"{row['arm']} {row['accession']} r{row['repeat']} "
        f"wall={row['wall_s']:.1f}s timed={row['timed']}",
        flush=True,
    )


def acts_row(genome: dict, repeat: int, timed: bool, wall: float, cpu: float, result, match: dict | None) -> dict:
    extra = dict(result.extra)
    phases = dict(extra.get("phases") or {})
    return {
        "genome_position": genome["position"],
        "accession": genome["accession"],
        "n_proteins": genome["n_proteins"],
        "repeat": repeat,
        "arm": "acts",
        "timed": timed,
        "wall_s": wall,
        "cpu_s": cpu,
        "decision": result.decision,
        "reason": result.reason,
        "phases": phases,
        "probe_phases": extra.get("probe_phases") or {},
        "n_stable": extra.get("n_stable"),
        "n_fresh": extra.get("n_fresh"),
        "n_partial": extra.get("n_partial"),
        "n_entries": extra.get("n_entries"),
        "length_fresh": extra.get("length_fresh"),
        "length_entries": extra.get("length_entries"),
        "reused_rows": extra.get("reused_rows"),
        "fallback_full_scan": extra.get("fallback_full_scan"),
        "match": match,
        "load": list(os.getloadavg()) if hasattr(os, "getloadavg") else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--churn", type=Path, required=True)
    parser.add_argument("--old", type=Path, required=True, help="old release, gzip or plain")
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--old-version", type=Path)
    parser.add_argument("--new-version", type=Path)
    parser.add_argument("--genomes", type=Path, required=True, help="directory of proteomes")
    parser.add_argument("--work", type=Path, required=True, help="persistent cache and pending tables")
    parser.add_argument("--scratch", type=Path, required=True, help="node-local copies")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    predictions = json.loads(args.predictions.read_text())
    churn = json.loads(args.churn.read_text())
    if churn.get("r1_crosscheck") != "ok":
        raise SystemExit(f"churn file failed the R1 cross-check: {args.churn}")
    if churn["c_length"] != predictions["c_length"]:
        raise SystemExit("predictions c_length does not match the churn file")
    if int(churn["length_changed_and_new"]) != int(predictions["length_changed_and_new"]):
        raise SystemExit("predictions changed length does not match the churn file")
    if int(churn["length_new"]) != int(predictions["length_new"]):
        raise SystemExit("predictions new length does not match the churn file")

    old_sha = sha256(args.old)
    new_sha = sha256(args.new)
    if old_sha != churn["old_sha256"] or new_sha != churn["new_sha256"]:
        raise SystemExit("model-file checksums do not match the churn file")
    if old_sha != predictions["old_sha256"] or new_sha != predictions["new_sha256"]:
        raise SystemExit("model-file checksums do not match the locked predictions")

    for genome in predictions["genomes"]:
        found = n_proteins(genome_faa(args.genomes, genome["accession"]))
        if found != int(genome["n_proteins"]):
            raise SystemExit(
                f"{genome['accession']} has {found} proteins, predictions lock {genome['n_proteins']}"
            )

    if args.out.is_file():
        payload = json.loads(args.out.read_text())
        if not payload.get("stop"):
            drop_incomplete(payload)
    else:
        payload = {
            "protocol": "pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md",
            "addendum": predictions["addendum"],
            "predictions": predictions,
            "whole_invocation_cache": "not run; a new reference is a miss",
            "runs": [],
            "setup": {"cache_fill": []},
            "stop": None,
        }
    payload["provenance"] = host_block(args.old, args.new, args.old_version, args.new_version)
    payload["predictions"] = predictions
    dump(payload, args.out)

    if payload.get("stop"):
        print(f"already stopped: {payload['stop']}", flush=True)
        return 0

    args.scratch.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    old_hmm = args.scratch / "old.hmm"
    new_hmm = args.scratch / "new.hmm"
    print("decompressing releases", flush=True)
    decompress(args.old, old_hmm)
    decompress(args.new, new_hmm)
    setup = payload["setup"]
    if "press_new_s" not in setup:
        print("pressing the new release once (not charged to arm i)", flush=True)
        setup["press_new_s"] = press(new_hmm)
        dump(payload, args.out)
    cache = args.scratch / "reference.sqlite"
    persistent_cache = args.work / "reference.sqlite"
    if not cache.is_file() and persistent_cache.is_file():
        print("restoring cache onto node-local scratch", flush=True)
        snapshot_cache(persistent_cache, cache)

    def save_cache() -> None:
        snapshot_cache(cache, persistent_cache)

    def faa_for(accession: str) -> Path:
        dest = args.scratch / f"{accession}.faa"
        if not dest.is_file():
            src = genome_faa(args.genomes, accession)
            decompress(src, dest)
        return dest

    def remember_fill(genome: dict, reference: Path) -> None:
        if genome["accession"] in filled(payload):
            return
        out_dir = args.scratch / f"fill_{genome['accession']}"
        shutil.rmtree(out_dir, ignore_errors=True)
        print(f"cache fill {genome['accession']} on the old release", flush=True)
        wall, cpu, result = acts_scan(
            reference=reference,
            faa=faa_for(genome["accession"]),
            out_dir=out_dir,
            cache=cache,
            baseline=None,
        )
        shutil.rmtree(out_dir, ignore_errors=True)
        if result.decision != "SHIP":
            payload["stop"] = {
                "kind": "STOP_FIT",
                "why": result.reason,
                "accession": genome["accession"],
            }
            dump(payload, args.out)
            raise SystemExit(payload["stop"]["why"])
        phases = dict(result.extra.get("phases") or {})
        setup.setdefault("cache_fill", []).append(
            {
                "accession": genome["accession"],
                "position": genome["position"],
                "n_proteins": genome["n_proteins"],
                "wall_s": wall,
                "cpu_s": cpu,
                "decision": result.decision,
                "probe_wall_s": phases.get("probe_wall_s", 0.0),
                "phases": phases,
                "timed": False,
            }
        )
        if "probe_wall_s" not in setup and phases.get("probe_wall_s", 0.0) > 0:
            setup["probe_wall_s"] = phases["probe_wall_s"]
            setup["probe_phases"] = result.extra.get("probe_phases") or {}
        save_cache()
        dump(payload, args.out)

    def remember_gestore_probe(genome: dict) -> None:
        if setup.get("gestore_probe"):
            return
        out_dir = args.scratch / "gestore_probe"
        shutil.rmtree(out_dir, ignore_errors=True)
        print("gestore probe once (untimed; refusal is the expected contract)", flush=True)
        wall, cpu, result = acts_scan(
            reference=new_hmm,
            faa=faa_for(genome["accession"]),
            out_dir=out_dir,
            cache=cache,
            baseline="gestore",
        )
        shutil.rmtree(out_dir, ignore_errors=True)
        phases = dict(result.extra.get("phases") or {})
        setup["gestore_probe"] = {
            "accession": genome["accession"],
            "wall_s": wall,
            "cpu_s": cpu,
            "decision": result.decision,
            "reason": result.reason,
            "probe_wall_s": phases.get("probe_wall_s", 0.0),
            "expected_decision": "REFUSE",
            "timed": False,
        }
        save_cache()
        dump(payload, args.out)
        if result.decision != "REFUSE":
            payload["stop"] = {
                "kind": "STOP_GESTORE",
                "why": f"gestore decision was {result.decision}, expected REFUSE",
            }
            dump(payload, args.out)
            raise SystemExit(payload["stop"]["why"])

    genomes = predictions["genomes"]
    first = genomes[0]
    remember_fill(first, old_hmm)
    remember_gestore_probe(first)

    if payload.get("stop"):
        return 0

    if not setup.get("preflight"):
        print("preflight ref-merge on genome 1", flush=True)
        pending = args.work / "preflight"
        shutil.rmtree(pending, ignore_errors=True)
        pending.mkdir(parents=True)
        faa = faa_for(first["accession"])
        wall_s, cpu_s = stock_scan(new_hmm, faa, pending / "targets", pending / "domains")
        acts_dir = args.scratch / "preflight_acts"
        shutil.rmtree(acts_dir, ignore_errors=True)
        wall_a, cpu_a, result = acts_scan(
            reference=new_hmm,
            faa=faa,
            out_dir=acts_dir,
            cache=cache,
            baseline=None,
        )
        match = compare(pending, acts_dir, cache, new_hmm)
        setup["preflight"] = {
            "accession": first["accession"],
            "timed": False,
            "stock_wall_s": wall_s,
            "stock_cpu_s": cpu_s,
            "acts_wall_s": wall_a,
            "acts_cpu_s": cpu_a,
            "acts_decision": result.decision,
            "acts_phases": dict(result.extra.get("phases") or {}),
            "match": match,
        }
        shutil.rmtree(pending, ignore_errors=True)
        shutil.rmtree(acts_dir, ignore_errors=True)
        save_cache()
        dump(payload, args.out)
        if not match["ok"] or result.decision != "SHIP":
            payload["stop"] = {
                "kind": "STOP_MATCH",
                "why": match["why"] or result.reason,
                "where": "preflight",
                "accession": first["accession"],
            }
            dump(payload, args.out)
            print(f"STOP_MATCH {payload['stop']['why']}", flush=True)
            return 0

    finished = done_keys(payload)
    for genome in genomes:
        remember_fill(genome, old_hmm)
        if payload.get("stop"):
            return 0
        faa = faa_for(genome["accession"])
        for repeat in range(1, args.repeats + 1):
            key = (genome["accession"], repeat)
            if all((*key, arm) in finished for arm in ARMS):
                continue
            pending = args.work / "pending" / genome["accession"] / f"r{repeat}"
            shutil.rmtree(pending, ignore_errors=True)
            pending.mkdir(parents=True)
            for arm in ARMS:
                if arm == "stock":
                    wall, cpu = stock_scan(new_hmm, faa, pending / "targets", pending / "domains")
                    row = {
                        "genome_position": genome["position"],
                        "accession": genome["accession"],
                        "n_proteins": genome["n_proteins"],
                        "repeat": repeat,
                        "arm": "stock",
                        "timed": True,
                        "wall_s": wall,
                        "cpu_s": cpu,
                        "decision": "stock",
                        "load": list(os.getloadavg()) if hasattr(os, "getloadavg") else [],
                    }
                elif arm == "acts":
                    acts_dir = args.scratch / f"acts_{genome['accession']}_{repeat}"
                    shutil.rmtree(acts_dir, ignore_errors=True)
                    wall, cpu, result = acts_scan(
                        reference=new_hmm,
                        faa=faa,
                        out_dir=acts_dir,
                        cache=cache,
                        baseline=None,
                    )
                    match = compare(pending, acts_dir, cache, new_hmm)
                    shutil.rmtree(acts_dir, ignore_errors=True)
                    row = acts_row(genome, repeat, True, wall, cpu, result, match)
                    save_cache()
                    if result.decision != "SHIP" or not match["ok"]:
                        record_run(payload, row, args.out)
                        payload["stop"] = {
                            "kind": "STOP_MATCH",
                            "why": match["why"] or result.reason,
                            "where": "timed",
                            "accession": genome["accession"],
                            "repeat": repeat,
                        }
                        dump(payload, args.out)
                        shutil.rmtree(pending, ignore_errors=True)
                        print(f"STOP_MATCH {payload['stop']['why']}", flush=True)
                        return 0
                else:
                    acts_dir = args.scratch / f"gestore_{genome['accession']}_{repeat}"
                    shutil.rmtree(acts_dir, ignore_errors=True)
                    wall, cpu, result = acts_scan(
                        reference=new_hmm,
                        faa=faa,
                        out_dir=acts_dir,
                        cache=cache,
                        baseline="gestore",
                    )
                    shutil.rmtree(acts_dir, ignore_errors=True)
                    save_cache()
                    row = acts_row(genome, repeat, True, wall, cpu, result, None)
                    row["arm"] = "gestore"
                    row["expected_decision"] = "REFUSE"
                record_run(payload, row, args.out)
            shutil.rmtree(pending, ignore_errors=True)
            finished.add((*key, "stock"))
            finished.add((*key, "acts"))
            finished.add((*key, "gestore"))
    payload["complete"] = True
    dump(payload, args.out)
    print("REFERENCE_REANNOT_DONE", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"FATAL {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
