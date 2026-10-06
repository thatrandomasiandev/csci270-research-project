#!/usr/bin/env python3
"""HMMER accumulated-savings run (docs/SAVINGS_PROTOCOL.md).

One invocation = one (collection, mode). Stock samples and cached runs
share the node: for each genome k, stock (if sampled) runs immediately
before cached. Writes JSON after every genome.

The contract gate (`acts.infer_fasta.contract_satisfies`) accepts the
locked match type when the contract is whitespace-normalized or the
layout is pinned. A pinned layout is checked as byte equality, which
implies the whitespace relation of the same match type (addendum
2026-10-06). A failed byte check halts with STOP_MATCH. It is not
retried as whitespace.

Before any genome run, `acts.infer_fasta.preflight_stock_outputs`
rebuilds every available full stock body for this argv under the
contract's MATCH. A mismatch halts with STOP_PREFLIGHT. The probe that
infers the contract still runs; the collection does not.
"""

from __future__ import annotations

import gzip
import json
import os
import random
import resource
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("ACTS_PIPELINE_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT))

from acts.cache import RecordCache
from acts.fasta import FastaRec, parse_fasta, write_fasta
from acts.fasta_memo import cached_search, contract_path_for
from acts.infer_fasta import (
    InferError,
    TableContract,
    contract_satisfies,
    infer_table_contract,
    layout_is_pinned,
    preflight_stock_outputs,
    run_table_tool,
)
from acts.table import tables_match

PROTOCOL = "pipeline/docs/SAVINGS_PROTOCOL.md"
AUDIT_SEED = 20260927
AUDIT_P = 0.02
AUDIT_NONEMPTY_FLOOR = 20
PROBE_N = 8
SUBSET_MODE = "singleton"
Z_FIXED = 1_000_000
DOMZ_FIXED = 1_000_000
ERROR_FLAG = 0.10

ORDER = {
    "A": [9, 5, 2, 75, 29, 64, 23, 80, 4, 14, 47, 63, 31, 28, 16, 52, 6, 39, 69, 78, 25, 74, 76, 57, 20, 24, 15, 67, 41, 44],
    "B": [4, 2, 1, 14, 32, 11, 38, 7, 23, 15, 24, 35, 27, 28, 39, 22, 31, 13, 37, 9, 17, 6, 36, 5, 18, 29, 12, 21, 8, 16, 10, 25, 3, 33, 0, 26, 30, 34, 19, 20],
}
STOCK_POS = {"A": {1, 2, 5, 10, 20, 30}, "B": {1, 2, 5, 10, 20, 40}}
EXPECTED_MATCH = {"hmmscan": "order", "hmmsearch": "multiset"}


def nproc() -> int:
    for key in ("SLURM_CPUS_PER_TASK", "SLURM_CPUS_ON_NODE"):
        raw = os.environ.get(key)
        if raw:
            try:
                return max(1, int(raw.split("(")[0]))
            except ValueError:
                pass
    return max(1, os.cpu_count() or 1)


def children_cpu_s() -> float:
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    return float(ru.ru_utime) + float(ru.ru_stime)


def uptime_line() -> str:
    return subprocess.check_output(["uptime"], text=True).rstrip()


def host_info() -> dict:
    def _run(argv: list[str]) -> str:
        proc = subprocess.run(argv, check=False, capture_output=True, text=True)
        return (proc.stdout or proc.stderr or "").rstrip()

    lscpu = _run(["lscpu"])
    model = next((ln.split(":", 1)[-1].strip() for ln in lscpu.splitlines() if "Model name" in ln), "")
    return {
        "hostname": _run(["hostname"]),
        "date": datetime.now(timezone.utc).isoformat(),
        "uptime": uptime_line(),
        "nproc": nproc(),
        "cpu_model": model,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_nodelist": os.environ.get("SLURM_NODELIST"),
    }


def load_faa(path: Path) -> list[FastaRec]:
    if path.suffix == ".gz" or path.name.endswith(".faa.gz"):
        return parse_fasta(gzip.open(path, "rt").read())
    return parse_fasta(path.read_text())


def which_hmmer() -> dict[str, str]:
    bindir = os.environ.get("ACTS_HMMER_BIN")
    found: dict[str, str] = {}
    for name in ("hmmscan", "hmmsearch", "hmmpress"):
        path = shutil.which(name)
        if bindir:
            candidate = Path(bindir) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                path = str(candidate)
        if not path:
            raise FileNotFoundError(f"{name} not on PATH")
        found[name] = path
    ver = subprocess.run([found["hmmsearch"], "-h"], check=False, capture_output=True, text=True)
    found["version_head"] = " | ".join((ver.stdout or ver.stderr).splitlines()[:3])
    return found


def ensure_pressed(hmm: Path, hmmpress: str) -> Path:
    if hmm.suffix == ".gz":
        raise ValueError("Pfam-A.hmm must be gunzipped before hmmpress")
    pressed = Path(str(hmm) + ".h3m")
    if pressed.is_file() and pressed.stat().st_mtime >= hmm.stat().st_mtime:
        return hmm
    proc = subprocess.run([hmmpress, "-f", str(hmm)], check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"hmmpress failed: {(proc.stderr or proc.stdout or '')[-800:]}")
    return hmm


def stage_pfam(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    if src.suffix == ".gz" or src.name.endswith(".hmm.gz"):
        dest = dest_dir / "Pfam-A.hmm"
        if not dest.is_file() or dest.stat().st_mtime < src.stat().st_mtime:
            with gzip.open(src, "rb") as fh_in, dest.open("wb") as fh_out:
                shutil.copyfileobj(fh_in, fh_out)
        return dest
    dest = dest_dir / src.name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest


def screen_fit(mode: str) -> dict:
    screen = json.loads((ROOT / "results" / "headline_screen.json").read_text())
    for row in screen["modes"]:
        if row["mode"] == mode:
            return {
                "a": row["a_s"],
                "b": row["b_s_per_record"],
                "w": row["w"]["w_s"],
                "N_screen": screen["N"],
            }
    raise KeyError(mode)


def predicted_speedup(collection: str, mode: str, k: int) -> float | None:
    path = ROOT / "results" / "hmmer_predicted_speedup.json"
    if not path.is_file():
        return None
    raw = json.loads(path.read_text())
    for row in raw["collections"][collection]["modes"][mode]["per_k"]:
        if row["k"] == k:
            return row["speedup_median"]
    return None


def wrapper_argv(mode: str, binary: str, hmm: Path, cpu: int) -> list[str]:
    emit = str(ROOT / "scripts" / "emit_side_table.py")
    core = [sys.executable, emit, binary, "--cpu", str(cpu), "--noali", "--tblout", "{table}"]
    if mode == "hmmscan":
        return core + ["--cut_ga", str(hmm), "{input}"]
    if mode == "hmmsearch":
        return core + ["-Z", str(Z_FIXED), "--domZ", str(DOMZ_FIXED), str(hmm), "{input}"]
    raise ValueError(mode)


def stock_argv(mode: str, bins: dict[str, str], hmm: Path, faa: Path, tblout: Path, cpu: int) -> list[str]:
    if mode == "hmmscan":
        return [bins["hmmscan"], "--cpu", str(cpu), "--cut_ga", "--noali", "--tblout", str(tblout), str(hmm), str(faa)]
    if mode == "hmmsearch":
        return [
            bins["hmmsearch"],
            "--cpu",
            str(cpu),
            "--noali",
            "-Z",
            str(Z_FIXED),
            "--domZ",
            str(DOMZ_FIXED),
            "--tblout",
            str(tblout),
            str(hmm),
            str(faa),
        ]
    raise ValueError(mode)


def time_cmd(argv: list[str]) -> dict:
    up = uptime_line()
    cpu0 = children_cpu_s()
    t0 = time.perf_counter()
    proc = subprocess.run(argv, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(
            f"cmd failed rc={proc.returncode}: {argv[:8]}\n{(proc.stderr or proc.stdout or '')[-800:]}"
        )
    return {
        "wall_s": wall,
        "cpu_s": children_cpu_s() - cpu0,
        "uptime": up,
        "returncode": proc.returncode,
        "stderr_tail": (proc.stderr or "")[-400:],
    }


def empty_payload(raw: str | None) -> bool:
    if raw is None:
        return False
    try:
        return json.loads(raw).get("rows") == []
    except json.JSONDecodeError:
        return False


def paths_for(collection: str, mode: str) -> dict[str, Path]:
    base = Path(os.environ.get("ACTS_SAVINGS_OUT", str(ROOT / "results" / "savings")))
    stem = f"{collection}_{mode}"
    return {
        "base": base,
        "json": base / f"{stem}.json",
        # Scoped per (collection, mode): one run's gate failure must not halt the
        # others (2026-09-28: hmmsearch STOP_MATCH killed a healthy hmmscan run).
        "stop": base / f"STOP_{stem}.json",
        "tblout_dir": base / "tblout",
        "rebuilt_dir": base / "rebuilt",
        "cache_dir": base / "cache" / stem,
    }


def git_hash() -> str:
    env = (os.environ.get("ACTS_GIT_HASH") or "").strip()
    if env:
        return env
    sidecar = Path(os.environ.get("ACTS_GIT_HASH_FILE", "") or (ROOT / "results" / "savings" / "GIT_HASH"))
    if sidecar.is_file():
        return sidecar.read_text().strip()
    return "unknown"


def stop_decision(where: str) -> str:
    if where in {"stock MATCH", "cached MATCH"}:
        return "STOP_MATCH"
    if where == "audit":
        return "STOP_AUDIT"
    if where == "contract":
        return "STOP_CONTRACT"
    if where == "preflight":
        return "STOP_PREFLIGHT"
    return f"STOP_{where.replace(' ', '_').upper()}"


def upsert_genome(payload: dict, row: dict) -> None:
    pos = row["position"]
    genomes = payload.setdefault("genomes", [])
    for i, existing in enumerate(genomes):
        if existing.get("position") == pos:
            genomes[i] = {**existing, **row}
            return
    genomes.append(row)


def genome_complete(row: dict | None, collection: str) -> bool:
    if not row or row.get("cached_wall_s") is None:
        return False
    if row.get("position") in STOCK_POS[collection]:
        return row.get("stock_wall_s") is not None
    return True


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(path)


def stop_if_flagged(stop_path: Path) -> dict | None:
    if stop_path.is_file():
        return json.loads(stop_path.read_text())
    return None


def write_stop(stop_path: Path, payload: dict) -> None:
    where = str(payload.get("where") or "unknown")
    payload = {**payload, "decision": payload.get("decision") or stop_decision(where)}
    atomic_write(stop_path, payload)


def load_or_init(path: Path, skeleton: dict) -> dict:
    if path.is_file():
        return json.loads(path.read_text())
    return skeleton


def genome_tblout(paths: dict[str, Path], collection: str, mode: str, position: int, kind: str) -> Path:
    folder = paths["tblout_dir"] if kind == "stock" else paths["rebuilt_dir"]
    return folder / f"{collection}_{mode}_{position:02d}_{kind}.tbl"


def do_match(rebuilt: str, stock: str, contract: TableContract) -> bool:
    return tables_match(rebuilt, stock, contract.match, match_ws=contract.match_ws)


def pick_audit(
    recs: list[FastaRec],
    cache: RecordCache,
    hit_keys: set[str],
    rng: random.Random,
) -> list[FastaRec]:
    hits = [rec for rec in recs if rec.key in hit_keys]
    nonempty = [rec for rec in hits if not empty_payload(cache.get(rec.key))]
    chosen: list[FastaRec] = [rec for rec in hits if rng.random() < AUDIT_P]
    have_ne = {rec.key for rec in chosen if not empty_payload(cache.get(rec.key))}
    need = AUDIT_NONEMPTY_FLOOR - len(have_ne)
    if need > 0:
        extra = [rec for rec in nonempty if rec.key not in {r.key for r in chosen}]
        rng.shuffle(extra)
        chosen.extend(extra[:need])
    # unique by key, keep first name
    seen: set[str] = set()
    out: list[FastaRec] = []
    for rec in chosen:
        if rec.key in seen:
            continue
        seen.add(rec.key)
        out.append(rec)
    return out


def summarize(payload: dict, fit: dict, collection: str, mode: str) -> None:
    rows = payload.get("genomes") or []
    if not rows:
        return
    stock_wall = stock_cpu = cached_wall = cached_cpu = 0.0
    flags = []
    for row in rows:
        n_i = row["N_i"]
        pred = fit["a"] + fit["b"] * n_i
        row["stock_predicted_s"] = pred
        measured = row.get("stock_wall_s")
        if measured is None:
            stock_wall += pred
        else:
            stock_wall += measured
            stock_cpu += row.get("stock_cpu_s") or 0.0
            err = abs(measured - pred) / measured if measured else 0.0
            row["stock_pred_rel_error"] = err
            if err > ERROR_FLAG:
                flags.append({"genome": row["position"], "rel_error": err})
        if row.get("cached_wall_s") is not None:
            cached_wall += row["cached_wall_s"]
            cached_cpu += row.get("cached_cpu_s") or 0.0
        k = row["position"] - 1
        if k >= 1:
            row["predicted_speedup_part2"] = predicted_speedup(collection, mode, k)
            if row.get("cached_wall_s") and (measured or pred):
                denom = measured if measured is not None else pred
                row["measured_speedup"] = denom / row["cached_wall_s"]
    payload["cumulative"] = {
        "stock_wall_s": stock_wall,
        "stock_cpu_s": stock_cpu,
        "cached_wall_s": cached_wall or None,
        "cached_cpu_s": cached_cpu or None,
        "stock_wall_h": stock_wall / 3600.0,
        "cached_wall_h": (cached_wall / 3600.0) if cached_wall else None,
        "cum_speedup_wall": (stock_wall / cached_wall) if cached_wall else None,
        "fit_error_flags": flags,
    }
    if collection == "A" and mode == "hmmscan" and cached_wall:
        payload["kill"] = {
            "rule": "cached wall must be < 50% of stock wall at end of A / hmmscan",
            "cached_over_stock": cached_wall / stock_wall,
            "fails": cached_wall >= 0.5 * stock_wall,
        }


def genomes_spec(collection: str) -> list[dict]:
    acc = json.loads((ROOT / "results" / "recurrence_accessions.json").read_text())
    listed = acc["collections"][collection]["genomes"]
    out = []
    for pos, idx in enumerate(ORDER[collection], start=1):
        g = listed[idx]
        out.append(
            {
                "position": pos,
                "index": idx,
                "accession": g["accession"],
                "strain": g.get("strain"),
                "path": g["path"],
                "n_unique_listed": g.get("n_unique"),
            }
        )
    return out


def preflight_stock_files(collection: str, mode: str, paths: dict[str, Path]) -> list[tuple[str, str]]:
    """Full stock tblout already on disk for this argv, including an optional archive.

    ACTS_PREFLIGHT_STOCK is a directory of ``{collection}_{mode}_*_stock.tbl``
    from an earlier run. The current run's tblout directory is included too.
    Reading those files is the preflight; it is not a genome run.
    """
    dirs: list[Path] = []
    extra = (os.environ.get("ACTS_PREFLIGHT_STOCK") or "").strip()
    if extra:
        dirs.append(Path(extra))
    dirs.append(paths["tblout_dir"])
    seen: set[Path] = set()
    found: list[tuple[str, str]] = []
    pattern = f"{collection}_{mode}_*_stock.tbl"
    for folder in dirs:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob(pattern)):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append((path.name, path.read_text()))
    return found


def ensure_contract(argv: list[str], recs: list[FastaRec], cache_path: Path, work: Path) -> TableContract:
    path = contract_path_for(cache_path)
    if path.is_file():
        return TableContract.load(path)
    # Pinned to the pre-registered probe: probe_n=8, singleton subset checks (12 calls),
    # which is what analyze_savings.py prices as P. The library default is now batched.
    contract = infer_table_contract(
        argv, recs, work / "probe", probe_n=PROBE_N, subset_mode=SUBSET_MODE
    )
    contract.save(path)
    return contract


def run_stock_genome(
    *,
    spec: dict,
    recs: list[FastaRec],
    mode: str,
    bins: dict[str, str],
    hmm: Path,
    cpu: int,
    work: Path,
    paths: dict[str, Path],
    collection: str,
    contract: TableContract | None,
) -> dict:
    faa = work / f"stock_{spec['position']:02d}.fa"
    write_fasta(faa, recs)
    tbl = genome_tblout(paths, collection, mode, spec["position"], "stock")
    tbl.parent.mkdir(parents=True, exist_ok=True)
    timed = time_cmd(stock_argv(mode, bins, hmm, faa, tbl, cpu))
    text = tbl.read_text() if tbl.is_file() else ""
    rebuilt = genome_tblout(paths, collection, mode, spec["position"], "cached")
    match = None
    if rebuilt.is_file() and contract is not None:
        match = do_match(rebuilt.read_text(), text, contract)
        if not match:
            write_stop(
                paths["stop"],
                {
                    "stopped": True,
                    "where": "stock MATCH",
                    "collection": collection,
                    "mode": mode,
                    "position": spec["position"],
                    "accession": spec["accession"],
                },
            )
    return {
        **spec,
        "N_i": len(recs),
        "n_unique": len({r.key for r in recs}),
        "stock_wall_s": timed["wall_s"],
        "stock_cpu_s": timed["cpu_s"],
        "stock_uptime": timed["uptime"],
        "match": match,
        "tblout": str(tbl),
    }


def run_cached_genome(
    *,
    spec: dict,
    recs: list[FastaRec],
    mode: str,
    argv: list[str],
    cache: RecordCache,
    contract: TableContract,
    work: Path,
    paths: dict[str, Path],
    collection: str,
    rng: random.Random,
) -> dict:
    cpu0 = children_cpu_s()
    t0 = time.perf_counter()
    rebuilt, stats = cached_search(
        recs, cache, contract, argv, work / f"g{spec['position']:02d}", contract_path=contract_path_for(cache.path)
    )
    wall = time.perf_counter() - t0
    cpu = children_cpu_s() - cpu0
    cache.save()
    dest = genome_tblout(paths, collection, mode, spec["position"], "cached")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(rebuilt)

    pre_hits = stats["n_hits"]
    miss_fa = work / f"g{spec['position']:02d}" / "miss.fa"
    miss_keys = {r.key for r in parse_fasta(miss_fa.read_text())} if miss_fa.is_file() else set()
    hit_recs = [r for r in recs if r.key not in miss_keys]
    empty_hits = sum(1 for r in hit_recs if empty_payload(cache.get(r.key)))
    nonempty_hits = len(hit_recs) - empty_hits

    stock_tbl = genome_tblout(paths, collection, mode, spec["position"], "stock")
    match = None
    audit = None
    sampled = spec["position"] in STOCK_POS[collection]
    if sampled and stock_tbl.is_file():
        match = do_match(rebuilt, stock_tbl.read_text(), contract)
        if not match:
            write_stop(
                paths["stop"],
                {
                    "stopped": True,
                    "where": "cached MATCH",
                    "collection": collection,
                    "mode": mode,
                    "position": spec["position"],
                    "accession": spec["accession"],
                },
            )
    elif not sampled:
        audit_recs = pick_audit(recs, cache, {r.key for r in hit_recs}, rng)
        if audit_recs:
            fa = work / f"audit_{spec['position']:02d}.fa"
            write_fasta(fa, audit_recs)
            stock_text = run_table_tool(argv, fa)
            rebuilt_audit, _ = cached_search(
                audit_recs, cache, contract, argv, work / f"audit_re_{spec['position']:02d}"
            )
            ok = do_match(rebuilt_audit, stock_text, contract)
            audit = {
                "n_hits": pre_hits,
                "n_checked": len(audit_recs),
                "n_nonempty_checked": sum(1 for r in audit_recs if not empty_payload(cache.get(r.key))),
                "ok": ok,
            }
            if not ok:
                write_stop(
                    paths["stop"],
                    {
                        "stopped": True,
                        "where": "audit",
                        "collection": collection,
                        "mode": mode,
                        "position": spec["position"],
                        "accession": spec["accession"],
                    },
                )

    return {
        **spec,
        "N_i": len(recs),
        "n_unique": len({r.key for r in recs}),
        "cached_wall_s": wall,
        "cached_cpu_s": cpu,
        "n_hits": stats["n_hits"],
        "n_misses": stats["n_misses"],
        "n_empty_hits": empty_hits,
        "n_nonempty_hits": nonempty_hits,
        "cache_size_after": stats["cache_size_after"],
        "match": match,
        "audit": audit,
        "rebuilt": str(dest),
    }


def persist(payload: dict, fit: dict, collection: str, mode: str, out_json: Path) -> None:
    summarize(payload, fit, collection, mode)
    atomic_write(out_json, payload)


def halt(payload: dict, fit: dict, collection: str, mode: str, out_json: Path, flagged: dict) -> int:
    payload["stopped"] = flagged
    payload["decision"] = flagged.get("decision") or stop_decision(str(flagged.get("where") or "unknown"))
    persist(payload, fit, collection, mode, out_json)
    print(f"{payload['decision']}: {flagged}", flush=True)
    return 2


def main() -> int:
    collection = os.environ.get("ACTS_SAVINGS_COLLECTION", "")
    mode = os.environ.get("ACTS_SAVINGS_MODE", "")
    if collection not in ORDER or mode not in EXPECTED_MATCH:
        raise SystemExit("set ACTS_SAVINGS_COLLECTION={A,B} MODE={hmmscan,hmmsearch}")

    cpu = nproc()
    fit = screen_fit(mode)
    specs = genomes_spec(collection)
    paths = paths_for(collection, mode)
    paths["base"].mkdir(parents=True, exist_ok=True)
    work = Path(os.environ.get("ACTS_SAVINGS_WORK", f"/tmp/acts_savings_{os.getpid()}"))
    work.mkdir(parents=True, exist_ok=True)
    out_json = paths["json"]

    flagged = stop_if_flagged(paths["stop"])
    if flagged:
        print(f"STOP already set: {flagged}")
        return 2

    bins = which_hmmer()
    pfam_src = Path(os.environ.get("ACTS_PFAM", str(ROOT / "data" / "hmmer" / "Pfam-A.hmm.gz")))
    hmm = ensure_pressed(stage_pfam(pfam_src, work / "hmmer"), bins["hmmpress"])
    argv = wrapper_argv(mode, bins[mode], hmm, cpu)
    commit = git_hash()

    skeleton = {
        "protocol": PROTOCOL,
        "addendum": "2026-09-27 same node",
        "git": commit,
        "collection": collection,
        "mode": mode,
        "path": "paired",
        "paper": "token / whitespace-normalized identity, not byte identity",
        "primary": mode == "hmmsearch",
        "post_hoc": mode == "hmmscan",
        "host": host_info(),
        "hmmer": bins["version_head"],
        "pfam": str(hmm),
        "cpu": cpu,
        "fit": fit,
        "argv_wrapper": argv,
        "genomes": [],
        "stopped": None,
        "decision": None,
    }
    payload = load_or_init(out_json, skeleton)
    payload["host"] = host_info()
    payload["git"] = commit
    payload["addendum"] = "2026-09-27 same node"
    payload["resumed"] = bool(payload.get("genomes"))
    by_pos = {row["position"]: row for row in payload.get("genomes") or []}

    cache_path = paths["cache_dir"] / "cache.jsonl"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = RecordCache(cache_path, argv=argv, kind="fasta")
    contract = None
    rng = random.Random(AUDIT_SEED)

    for spec in specs:
        flagged = stop_if_flagged(paths["stop"])
        if flagged:
            return halt(payload, fit, collection, mode, out_json, flagged)
        existing = by_pos.get(spec["position"])
        if genome_complete(existing, collection):
            continue

        sampled = spec["position"] in STOCK_POS[collection]
        recs = load_faa(ROOT / spec["path"])
        gwork = work / f"g{spec['position']:02d}"
        gwork.mkdir(parents=True, exist_ok=True)
        row = {
            **(existing or spec),
            **spec,
            "N_i": len(recs),
            "n_unique": len({r.key for r in recs}),
        }
        if not sampled and row.get("stock_wall_s") is None:
            row["stock_source"] = "predicted a+b*N_i"

        if contract is None:
            print("inferring table contract (probe_n=8) …", flush=True)
            contract = ensure_contract(argv, recs, cache.path, gwork)
            ok, reason = contract_satisfies(contract, EXPECTED_MATCH[mode])
            if not ok:
                write_stop(
                    paths["stop"],
                    {
                        "stopped": True,
                        "where": "contract",
                        "mode": mode,
                        "match": contract.match,
                        "match_ws": contract.match_ws,
                        "pinned": layout_is_pinned(contract),
                        "expected": EXPECTED_MATCH[mode],
                        "reason": reason,
                    },
                )
                return halt(payload, fit, collection, mode, out_json, json.loads(paths["stop"].read_text()))
            print(f"contract gate: {reason}", flush=True)
            pre = preflight_stock_outputs(contract, preflight_stock_files(collection, mode, paths))
            print(f"preflight: {pre['reason']}", flush=True)
            if not pre["ok"]:
                write_stop(
                    paths["stop"],
                    {
                        "stopped": True,
                        "where": "preflight",
                        "mode": mode,
                        "match": contract.match,
                        "match_ws": contract.match_ws,
                        "pinned": layout_is_pinned(contract),
                        "reason": pre["reason"],
                        "files": pre["files"],
                    },
                )
                return halt(payload, fit, collection, mode, out_json, json.loads(paths["stop"].read_text()))

        if sampled and row.get("stock_wall_s") is None:
            print(f"stock {collection} {mode} genome {spec['position']} {spec['accession']}", flush=True)
            stock_row = run_stock_genome(
                spec=spec,
                recs=recs,
                mode=mode,
                bins=bins,
                hmm=hmm,
                cpu=cpu,
                work=gwork,
                paths=paths,
                collection=collection,
                contract=contract,
            )
            row.update(stock_row)
            upsert_genome(payload, row)
            by_pos[spec["position"]] = row
            persist(payload, fit, collection, mode, out_json)
            if row.get("match") is False:
                return halt(
                    payload,
                    fit,
                    collection,
                    mode,
                    out_json,
                    stop_if_flagged(paths["stop"]) or {"decision": "STOP_MATCH", "where": "stock MATCH"},
                )

        if row.get("cached_wall_s") is None:
            print(f"cached {collection} {mode} genome {spec['position']} {spec['accession']}", flush=True)
            cached_row = run_cached_genome(
                spec=spec,
                recs=recs,
                mode=mode,
                argv=argv,
                cache=cache,
                contract=contract,
                work=gwork,
                paths=paths,
                collection=collection,
                rng=rng,
            )
            row.update(cached_row)
            upsert_genome(payload, row)
            by_pos[spec["position"]] = row
            persist(payload, fit, collection, mode, out_json)
            if row.get("match") is False or (row.get("audit") and not row["audit"]["ok"]):
                return halt(
                    payload,
                    fit,
                    collection,
                    mode,
                    out_json,
                    stop_if_flagged(paths["stop"])
                    or {
                        "decision": "STOP_MATCH" if row.get("match") is False else "STOP_AUDIT",
                        "where": "cached MATCH" if row.get("match") is False else "audit",
                    },
                )

    payload["finished_utc"] = datetime.now(timezone.utc).isoformat()
    persist(payload, fit, collection, mode, out_json)
    print(f"wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
