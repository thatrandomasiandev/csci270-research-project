#!/usr/bin/env python3
"""CARC shared-contract smoke + measured runner (pre-registered 2026-10-24).

Modes:
  --mode smoke     N=2, r=1, 500-model Pfam subset; non-exclusive OK
  --mode measured  N=1,5,20 nested draw; r=3; full Pfam-A; exclusive node
  --mode check-draw  verify pool sha + draws against measured_draw.json

Never a login-node timing run. Crash writes partial JSON to ACTS_OUT.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "scripts"))

from acts.reference_run import body_lines  # noqa: E402

DRAW_PATH = PIPE / "results" / "shared_contract" / "measured_draw.json"
CPU = "4"
HMMER_SHA256 = "ca70d94fd0cf271bd7063423aabb116d42de533117343a9b27a65c17ff06fbf3"
SMOKE_N_MODELS = 500
BOOTSTRAP_N = 10_000
CONFIRM_N = 10


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def host_snap() -> dict:
    load = [round(v, 2) for v in os.getloadavg()] if hasattr(os, "getloadavg") else []
    mem: dict[str, int] = {}
    if Path("/proc/meminfo").is_file():
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                key, rest = line.split(":", 1)
                if key in {"MemTotal", "MemAvailable", "MemFree"}:
                    mem[key] = int(rest.split()[0]) * 1024
    model = ""
    if Path("/proc/cpuinfo").is_file():
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    model = line.split(":", 1)[1].strip()
                    break
    return {
        "node": os.uname().nodename,
        "load": load,
        "mem": mem,
        "cpu_model": model,
        "nproc": os.cpu_count(),
        "unix": time.time(),
    }


def write_out(payload: dict) -> None:
    dest = Path(os.environ.get("ACTS_OUT", str(PIPE / "results" / "shared_contract" / "out.json")))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(dest)
    log(f"wrote {dest}")


def load_draw() -> dict:
    return json.loads(DRAW_PATH.read_text())


def pool_from_genomes(genomes_dir: Path, exclude: set[str]) -> list[str]:
    stems = sorted(
        p.name[: -len("_protein.faa.gz")]
        for p in genomes_dir.glob("*_protein.faa.gz")
    )
    return [s for s in stems if s not in exclude]


def check_draw(genomes_dir: Path) -> dict:
    draw = load_draw()
    exclude = set(draw["exclude_reasons"])
    pool = pool_from_genomes(genomes_dir, exclude)
    digest = hashlib.sha256("\n".join(pool).encode()).hexdigest()
    expected = sorted(
        __import__("random").Random(draw["seed_proteome"]).sample(pool, draw["n_draw"])
    )
    ok = (
        len(pool) == draw["pool_n"]
        and digest == draw["pool_sha256"]
        and expected == list(draw["draws"])
    )
    return {
        "ok": ok,
        "pool_n": len(pool),
        "pool_sha256": digest,
        "expected_pool_n": draw["pool_n"],
        "expected_pool_sha256": draw["pool_sha256"],
        "drawn": expected,
        "locked_draws": list(draw["draws"]),
    }


def body_sha(path: Path) -> str:
    text = "\n".join(body_lines(path.read_text(errors="replace").splitlines())) + "\n"
    return hashlib.sha256(text.encode()).hexdigest()


def classify(replay: list[str], stock: list[str]) -> dict:
    byte_equal = replay == stock
    out: dict = {
        "lines_replay": len(replay),
        "lines_stock": len(stock),
        "byte_equal": byte_equal,
        "classes": [],
    }
    if byte_equal:
        return out
    rt = [line.split() for line in replay]
    st = [line.split() for line in stock]
    if rt == st:
        out["classes"] = ["whitespace-only"]
        return out
    if len(rt) != len(st):
        out["classes"].append("order" if sorted(rt) == sorted(st) else "missing_or_extra")
    # crude key: first two tokens
    rc = Counter(tuple(tok[:2]) for tok in rt if tok)
    sc = Counter(tuple(tok[:2]) for tok in st if tok)
    if sum(1 for k in sc if sc[k] > rc.get(k, 0)):
        out["classes"].append("missing")
    if sum(1 for k in rc if rc[k] > sc.get(k, 0)):
        out["classes"].append("extra")
    if not out["classes"]:
        out["classes"].append("value-only")
    return out


def compare_tables(out_dir: Path, stock_tbl: Path, stock_dom: Path) -> dict:
    tables = out_dir / "tables"
    got_tbl = tables / "tblout"
    got_dom = tables / "domtblout"
    if not got_tbl.is_file():
        # pilots used tbl/domtbl aliases
        alt = tables / "tbl"
        if alt.is_file():
            got_tbl = alt
        alt = tables / "domtbl"
        if alt.is_file():
            got_dom = alt
    row: dict = {"tbl": None, "domtbl": None, "ok": False}
    if got_tbl.is_file() and stock_tbl.is_file():
        rb = body_lines(got_tbl.read_text(errors="replace").splitlines())
        sb = body_lines(stock_tbl.read_text(errors="replace").splitlines())
        row["tbl"] = classify(rb, sb)
        row["tbl"]["sha_replay"] = body_sha(got_tbl)
        row["tbl"]["sha_stock"] = body_sha(stock_tbl)
    if got_dom.is_file() and stock_dom.is_file():
        rb = body_lines(got_dom.read_text(errors="replace").splitlines())
        sb = body_lines(stock_dom.read_text(errors="replace").splitlines())
        row["domtbl"] = classify(rb, sb)
        row["domtbl"]["sha_replay"] = body_sha(got_dom)
        row["domtbl"]["sha_stock"] = body_sha(stock_dom)
    row["ok"] = bool(
        row["tbl"]
        and row["domtbl"]
        and row["tbl"].get("byte_equal")
        and row["domtbl"].get("byte_equal")
    )
    return row


def parse_decision(out_dir: Path) -> dict:
    path = out_dir / "decision.txt"
    if not path.is_file():
        return {}
    text = path.read_text(errors="replace")
    out: dict = {"raw_head": text[:2000]}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if key in {
            "decision",
            "reason",
            "why",
            "contract_store",
            "contract_store_key",
            "contract_store_write",
        }:
            out[key] = val
        if key == "contract_confirm_wall_s":
            try:
                out[key] = float(val)
            except ValueError:
                out[key] = val
        if key == "phases" or key == "probe_phases":
            try:
                out[key] = json.loads(val.replace("'", '"'))
            except Exception:
                out[key] = val
    # Prefer StrategyResult-style keys if decision embeds them as JSON blob later
    return out


def scrub_calls(out_dir: Path) -> None:
    for name in ("calls", "calls_pinned", "calls_infer", "calls_slack"):
        path = out_dir / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def ensure_pressed(hmm: Path, hmmpress: str) -> None:
    for ext in (".h3f", ".h3i", ".h3m", ".h3p"):
        if not Path(str(hmm) + ext).is_file():
            subprocess.run([hmmpress, "-f", str(hmm)], check=True, capture_output=True)
            return


def run_stock(
    *,
    hmmscan: str,
    hmmpress: str,
    faa: Path,
    hmm: Path,
    out_tbl: Path,
    out_dom: Path,
) -> dict:
    out_tbl.parent.mkdir(parents=True, exist_ok=True)
    ensure_pressed(hmm, hmmpress)
    cmd = [
        hmmscan,
        "--cut_ga",
        "--noali",
        "--cpu",
        CPU,
        "--tblout",
        str(out_tbl),
        "--domtblout",
        str(out_dom),
        "-o",
        "/dev/null",
        str(hmm),
        str(faa),
    ]
    before = host_snap()
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    wall = time.perf_counter() - t0
    after = host_snap()
    if proc.returncode != 0:
        raise RuntimeError(f"stock hmmscan failed rc={proc.returncode}: {proc.stderr[-800:]}")
    return {
        "arm": "A",
        "wall_s": wall,
        "returncode": proc.returncode,
        "argv": cmd,
        "before": before,
        "after": after,
        "tbl_sha256": body_sha(out_tbl),
        "domtbl_sha256": body_sha(out_dom),
    }


def run_tare(
    *,
    faa: Path,
    hmm: Path,
    out_dir: Path,
    cache: Path,
    contract_store: Path | None,
    hmmpress: str,
    extra_tool: list[str] | None = None,
) -> dict:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    tool = extra_tool or [
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
        f"{hmmpress} -f {{reference}}",
        "--input",
        str(faa),
        "--reference",
        str(hmm),
        "--cache",
        str(cache),
        "-o",
        str(out_dir),
    ]
    if contract_store is not None:
        cmd.extend(["--contract-store", str(contract_store)])
    cmd.append("--")
    cmd.extend(tool)
    before = host_snap()
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(PIPE), capture_output=True, text=True, check=False)
    wall = time.perf_counter() - t0
    after = host_snap()
    scrub_calls(out_dir)
    decision = parse_decision(out_dir)
    # Flatten contract_* from decision.txt lines that look like key: value
    text = (out_dir / "decision.txt").read_text(errors="replace") if (out_dir / "decision.txt").is_file() else ""
    for line in text.splitlines():
        if line.startswith("contract_") and ":" in line:
            k, _, v = line.partition(":")
            decision.setdefault(k.strip(), v.strip())
    return {
        "arm": "C" if contract_store is not None else "B",
        "wall_s": wall,
        "returncode": proc.returncode,
        "argv": cmd,
        "before": before,
        "after": after,
        "decision": decision.get("decision"),
        "reason": decision.get("reason") or decision.get("why"),
        "contract_store": decision.get("contract_store"),
        "contract_confirm_wall_s": decision.get("contract_confirm_wall_s"),
        "phases": decision.get("phases"),
        "probe_phases": decision.get("probe_phases"),
        "stdout_tail": (proc.stdout or "")[-500:],
        "stderr_tail": (proc.stderr or "")[-800:],
        "decision_meta": decision,
    }


def iter_hmm_blocks(src: Path):
    opener = gzip.open if str(src).endswith(".gz") else open
    with opener(src, "rt", errors="replace") as handle:
        buf: list[str] = []
        for line in handle:
            buf.append(line)
            if line.startswith("//"):
                yield "".join(buf)
                buf = []


def extract_models(src: Path, n: int, seed: int, dest: Path) -> dict:
    rng = random.Random(seed)
    reservoir: list[str] = []
    total = 0
    for block in iter_hmm_blocks(src):
        total += 1
        if len(reservoir) < n:
            reservoir.append(block)
        else:
            j = rng.randrange(total)
            if j < n:
                reservoir[j] = block
    if len(reservoir) < n:
        raise SystemExit(f"only {len(reservoir)} models, need {n}")

    def name_of(b: str) -> str:
        for line in b.splitlines():
            if line.startswith("NAME"):
                return line.split()[1]
        return ""

    reservoir.sort(key=name_of)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(reservoir))
    return {"path": str(dest), "n": n, "seed": seed, "sha256": sha256_file(dest), "source_total": total}


def decompress_pfam(src_gz: Path, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return {"path": str(dest), "sha256": sha256_file(dest), "reused": True}
    log(f"decompress {src_gz} → {dest}")
    with gzip.open(src_gz, "rb") as src, dest.open("wb") as out:
        shutil.copyfileobj(src, out)
    return {"path": str(dest), "sha256": sha256_file(dest), "reused": False}


def bootstrap_ci(values: list[float], seed: int) -> dict:
    if not values:
        return {"n": 0}
    rng = random.Random(seed)
    n = len(values)
    samples: list[float] = []
    for _ in range(BOOTSTRAP_N):
        draw = [values[rng.randrange(n)] for _ in range(n)]
        samples.append(statistics.mean(draw))
    samples.sort()
    lo = samples[int(0.025 * (BOOTSTRAP_N - 1))]
    hi = samples[int(0.975 * (BOOTSTRAP_N - 1))]
    return {
        "n": n,
        "mean": statistics.mean(values),
        "values": values,
        "ci95": [lo, hi],
        "seed": seed,
        "resamples": BOOTSTRAP_N,
    }


def which_hmmer() -> tuple[str, str]:
    hmmscan = shutil.which("hmmscan")
    hmmpress = shutil.which("hmmpress")
    if not hmmscan or not hmmpress:
        raise SystemExit("hmmscan/hmmpress not on PATH (build pinned HMMER 3.4 in the job first)")
    return hmmscan, hmmpress


def genome_faa(genomes_dir: Path, acc: str, scratch: Path) -> Path:
    gz = genomes_dir / f"{acc}_protein.faa.gz"
    if not gz.is_file():
        raise SystemExit(f"missing proteome {gz}")
    dest = scratch / "genomes" / f"{acc}_protein.faa"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(gz, "rb") as src, dest.open("wb") as out:
        shutil.copyfileobj(src, out)
    return dest


def run_controls(
    *,
    payload: dict,
    scratch: Path,
    hmm_full: Path,
    hmm_subset: Path,
    faa: Path,
    hmmscan: str,
    hmmpress: str,
) -> dict:
    """Poison + argv + release isolation. Correctness only."""
    ctrl_dir = scratch / "controls"
    if ctrl_dir.exists():
        shutil.rmtree(ctrl_dir)
    ctrl_dir.mkdir(parents=True)
    results: dict = {}

    # --- release isolation: fill store on full (or primary) hmm, probe subset ---
    store_rel = ctrl_dir / "store_release"
    store_rel.mkdir()
    cache = ctrl_dir / "cache_rel.sqlite"
    fill = run_tare(
        faa=faa,
        hmm=hmm_full,
        out_dir=ctrl_dir / "rel_fill",
        cache=cache,
        contract_store=store_rel,
        hmmpress=hmmpress,
    )
    cache2 = ctrl_dir / "cache_rel2.sqlite"
    probe = run_tare(
        faa=faa,
        hmm=hmm_subset,
        out_dir=ctrl_dir / "rel_probe",
        cache=cache2,
        contract_store=store_rel,
        hmmpress=hmmpress,
    )
    results["release_isolation"] = {
        "fill_contract_store": fill.get("contract_store"),
        "probe_contract_store": probe.get("contract_store"),
        "pass": probe.get("contract_store") != "reused",
    }

    # --- argv isolation: cut_ga store vs -E 10 ---
    store_argv = ctrl_dir / "store_argv"
    store_argv.mkdir()
    cache_a = ctrl_dir / "cache_argv.sqlite"
    fill_a = run_tare(
        faa=faa,
        hmm=hmm_subset,
        out_dir=ctrl_dir / "argv_fill",
        cache=cache_a,
        contract_store=store_argv,
        hmmpress=hmmpress,
    )
    tool_e = [
        "hmmscan",
        "-E",
        "10",
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
    cache_b = ctrl_dir / "cache_argv2.sqlite"
    probe_a = run_tare(
        faa=faa,
        hmm=hmm_subset,
        out_dir=ctrl_dir / "argv_probe",
        cache=cache_b,
        contract_store=store_argv,
        hmmpress=hmmpress,
        extra_tool=tool_e,
    )
    results["argv_isolation"] = {
        "fill_contract_store": fill_a.get("contract_store"),
        "probe_contract_store": probe_a.get("contract_store"),
        "pass": probe_a.get("contract_store") != "reused",
    }

    # --- poison: corrupt a stored fit blob if present ---
    store_p = ctrl_dir / "store_poison"
    store_p.mkdir()
    cache_p = ctrl_dir / "cache_poison.sqlite"
    fill_p = run_tare(
        faa=faa,
        hmm=hmm_subset,
        out_dir=ctrl_dir / "poison_fill",
        cache=cache_p,
        contract_store=store_p,
        hmmpress=hmmpress,
    )
    poisoned_files = 0
    for path in store_p.rglob("*"):
        if path.is_file() and path.stat().st_size > 32:
            raw = bytearray(path.read_bytes())
            # flip several bytes in the middle
            for i in range(min(16, len(raw) // 2)):
                raw[len(raw) // 3 + i] ^= 0x5A
            path.write_bytes(raw)
            poisoned_files += 1
            break
    stock_tbl = ctrl_dir / "poison_stock.tbl"
    stock_dom = ctrl_dir / "poison_stock.domtbl"
    stock = run_stock(
        hmmscan=hmmscan,
        hmmpress=hmmpress,
        faa=faa,
        hmm=hmm_subset,
        out_tbl=stock_tbl,
        out_dom=stock_dom,
    )
    cache_p2 = ctrl_dir / "cache_poison2.sqlite"
    follow = run_tare(
        faa=faa,
        hmm=hmm_subset,
        out_dir=ctrl_dir / "poison_follow",
        cache=cache_p2,
        contract_store=store_p,
        hmmpress=hmmpress,
    )
    exact = compare_tables(ctrl_dir / "poison_follow", stock_tbl, stock_dom)
    status = follow.get("contract_store")
    results["poisoned_store"] = {
        "fill_contract_store": fill_p.get("contract_store"),
        "follow_contract_store": status,
        "poisoned_files": poisoned_files,
        "exact_vs_stock": exact,
        "pass": status != "reused" and exact.get("ok") is True,
        "stock_wall_s": stock["wall_s"],
        "follow_wall_s": follow["wall_s"],
    }

    results["all_pass"] = all(
        results[k]["pass"] for k in ("release_isolation", "argv_isolation", "poisoned_store")
    )
    payload["controls"] = results
    write_out(payload)
    return results


def score_rho(batches: list[dict], seed: int) -> dict:
    """batches: list of {N, replicate, T_A, T_C, q, ...}."""
    by_n: dict[int, list[dict]] = {}
    for row in batches:
        by_n.setdefault(int(row["N"]), []).append(row)
    out: dict = {}
    for n, rows in sorted(by_n.items()):
        rhos = []
        qs = []
        confirm = []
        layer_a = []
        for row in rows:
            ta = float(row["T_A"])
            tc = float(row["T_C"])
            if ta <= 0:
                continue
            rhos.append(tc / ta)
            if row.get("q") is not None:
                qs.append(float(row["q"]))
            confirm.extend(row.get("confirm_walls") or [])
            if row.get("layer_a_saving_s") is not None:
                layer_a.append(float(row["layer_a_saving_s"]))
        out[str(n)] = {
            "rho": bootstrap_ci(rhos, seed),
            "q_mean": statistics.mean(qs) if qs else None,
            "q_values": qs,
            "confirm_wall_s_mean": statistics.mean(confirm) if confirm else None,
            "layer_a_saving_s_mean": statistics.mean(layer_a) if layer_a else None,
            "replicates": rows,
        }
    return out


def run_batch(
    *,
    payload: dict,
    N: int,
    replicate: int,
    accessions: list[str],
    genomes_dir: Path,
    scratch: Path,
    hmm: Path,
    hmmscan: str,
    hmmpress: str,
) -> dict:
    tag = f"N{N}_r{replicate}"
    work = scratch / "batches" / tag
    work.mkdir(parents=True, exist_ok=True)
    store = work / "contract_store"
    if store.exists():
        shutil.rmtree(store)
    store.mkdir()

    genomes = []
    for acc in accessions[:N]:
        faa = genome_faa(genomes_dir, acc, scratch)
        genomes.append({"accession": acc, "faa": str(faa)})

    # Arm A
    arm_a = []
    for g in genomes:
        acc = g["accession"]
        gdir = work / acc
        gdir.mkdir(exist_ok=True)
        row = run_stock(
            hmmscan=hmmscan,
            hmmpress=hmmpress,
            faa=Path(g["faa"]),
            hmm=hmm,
            out_tbl=gdir / "stock.tbl",
            out_dom=gdir / "stock.domtbl",
        )
        row["accession"] = acc
        arm_a.append(row)
        payload.setdefault("partial_arms", []).append({"tag": tag, "arm": "A", "accession": acc, "wall_s": row["wall_s"]})
        write_out(payload)
        log(f"{tag} A {acc} {row['wall_s']:.1f}s")

    # Arm B (no store)
    arm_b = []
    for g in genomes:
        acc = g["accession"]
        gdir = work / acc
        cache = gdir / "b_cache.sqlite"
        if cache.exists():
            cache.unlink()
        row = run_tare(
            faa=Path(g["faa"]),
            hmm=hmm,
            out_dir=gdir / "arm_b",
            cache=cache,
            contract_store=None,
            hmmpress=hmmpress,
        )
        exact = compare_tables(gdir / "arm_b", gdir / "stock.tbl", gdir / "stock.domtbl")
        row["accession"] = acc
        row["exact"] = exact
        arm_b.append(row)
        payload.setdefault("partial_arms", []).append(
            {"tag": tag, "arm": "B", "accession": acc, "wall_s": row["wall_s"], "exact_ok": exact["ok"]}
        )
        write_out(payload)
        log(f"{tag} B {acc} {row['wall_s']:.1f}s exact={exact['ok']} {row.get('decision')}")
        if not exact["ok"]:
            payload["outcome"] = "KILL"
            payload["kill_reason"] = f"arm B mismatch {tag} {acc}"
            write_out(payload)
            raise SystemExit(3)

    # Arm C (shared store)
    arm_c = []
    t_c0 = time.perf_counter()
    for g in genomes:
        acc = g["accession"]
        gdir = work / acc
        cache = gdir / "c_cache.sqlite"
        if cache.exists():
            cache.unlink()
        row = run_tare(
            faa=Path(g["faa"]),
            hmm=hmm,
            out_dir=gdir / "arm_c",
            cache=cache,
            contract_store=store,
            hmmpress=hmmpress,
        )
        exact = compare_tables(gdir / "arm_c", gdir / "stock.tbl", gdir / "stock.domtbl")
        row["accession"] = acc
        row["exact"] = exact
        arm_c.append(row)
        payload.setdefault("partial_arms", []).append(
            {
                "tag": tag,
                "arm": "C",
                "accession": acc,
                "wall_s": row["wall_s"],
                "contract_store": row.get("contract_store"),
                "exact_ok": exact["ok"],
            }
        )
        write_out(payload)
        log(
            f"{tag} C {acc} {row['wall_s']:.1f}s store={row.get('contract_store')} "
            f"exact={exact['ok']} {row.get('decision')}"
        )
        if not exact["ok"]:
            payload["outcome"] = "KILL"
            payload["kill_reason"] = f"arm C mismatch {tag} {acc}"
            write_out(payload)
            raise SystemExit(3)
    t_c_batch = time.perf_counter() - t_c0

    statuses = [r.get("contract_store") for r in arm_c]
    after_first = statuses[1:] if len(statuses) > 1 else []
    reused = sum(1 for s in after_first if s == "reused")
    q = (reused / len(after_first)) if after_first else None
    confirm_walls = [
        float(r["contract_confirm_wall_s"])
        for r in arm_c
        if r.get("contract_store") == "reused" and r.get("contract_confirm_wall_s") is not None
    ]
    parse_first = None
    parse_reuse = []
    for i, r in enumerate(arm_c):
        phases = r.get("phases") or {}
        if isinstance(phases, dict) and "parse_s" in phases:
            if i == 0:
                parse_first = float(phases["parse_s"])
            elif r.get("contract_store") == "reused":
                parse_reuse.append(float(phases["parse_s"]))
    layer_a = None
    if parse_first is not None and parse_reuse:
        layer_a = parse_first - statistics.mean(parse_reuse)

    T_A = sum(float(r["wall_s"]) for r in arm_a)
    T_B = sum(float(r["wall_s"]) for r in arm_b)
    # Prefer sum of per-genome C walls (matches A/B); also record batch timer.
    T_C = sum(float(r["wall_s"]) for r in arm_c)
    return {
        "N": N,
        "replicate": replicate,
        "accessions": [g["accession"] for g in genomes],
        "T_A": T_A,
        "T_B": T_B,
        "T_C": T_C,
        "T_C_batch_timer_s": t_c_batch,
        "rho_C_over_A": (T_C / T_A) if T_A else None,
        "rho_B_over_A": (T_B / T_A) if T_A else None,
        "q": q,
        "contract_statuses": statuses,
        "confirm_walls": confirm_walls,
        "layer_a_saving_s": layer_a,
        "arm_a": [{k: v for k, v in r.items() if k not in {"before", "after", "argv"}} for r in arm_a],
        "arm_b": [
            {
                k: v
                for k, v in r.items()
                if k not in {"before", "after", "argv", "stdout_tail", "stderr_tail", "decision_meta"}
            }
            for r in arm_b
        ],
        "arm_c": [
            {
                k: v
                for k, v in r.items()
                if k not in {"before", "after", "argv", "stdout_tail", "stderr_tail", "decision_meta"}
            }
            for r in arm_c
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("smoke", "measured", "check-draw"), required=True)
    ap.add_argument("--genomes", default=os.environ.get("ACTS_GENOMES", ""))
    ap.add_argument("--pfam-gz", default=os.environ.get("ACTS_PFAM", ""))
    ap.add_argument("--scratch", default=os.environ.get("ACTS_SCRATCH", ""))
    ap.add_argument(
        "--only-N",
        type=int,
        default=None,
        help="measured only: run a single nested N (1, 5, or 20). Default: all.",
    )
    args = ap.parse_args()

    genomes_dir = Path(args.genomes or "/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/recurrence/A")
    pfam_gz = Path(
        args.pfam_gz
        or "/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/hmmer/Pfam-A.hmm.gz"
    )
    scratch = Path(args.scratch or os.environ.get("ACTS_SCRATCH") or "/tmp/tare-sharedcontract")
    scratch.mkdir(parents=True, exist_ok=True)

    draw = load_draw()
    chk = check_draw(genomes_dir)
    if args.mode == "check-draw":
        print(json.dumps(chk, indent=2))
        raise SystemExit(0 if chk["ok"] else 2)
    if not chk["ok"]:
        raise SystemExit(f"STOP_DRAW: {json.dumps(chk)}")

    payload: dict = {
        "label": "SMOKE" if args.mode == "smoke" else "MEASURED",
        "phase": args.mode,
        "protocol": "docs/SHARED_CONTRACT_MEASURED.md",
        "draw_file": "pipeline/results/shared_contract/measured_draw.json",
        "confirm_n": CONFIRM_N,
        "confirm_n_evidence": "pipeline/results/shared_contract/p2d_confirm_n.json",
        "seeds": {
            "proteome": draw["seed_proteome"],
            "bootstrap": draw["seed_bootstrap"],
            "smoke_pfam_subset": draw["seed_smoke_pfam_subset"],
            "poison": draw["seed_poison_control"],
        },
        "draws": list(draw["draws"]),
        "pool_sha256": draw["pool_sha256"],
        "pool_check": chk,
        "provenance": {
            "git_head": os.environ.get("ACTS_GIT_HEAD"),
            "git_dirty": os.environ.get("ACTS_GIT_DIRTY"),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "slurm_array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
            "host": host_snap(),
            "hmmer_sha256_expected": HMMER_SHA256,
            "cpu": CPU,
            "account_note": "biyik_1173",
        },
        "partial_arms": [],
        "batches": [],
        "outcome": "RUNNING",
    }
    write_out(payload)

    hmmscan, hmmpress = which_hmmer()
    # record hmmscan version head
    ver = subprocess.run([hmmscan, "-h"], capture_output=True, text=True, check=False)
    payload["provenance"]["hmmscan_help_head"] = "\n".join((ver.stdout or "").splitlines()[:5])
    write_out(payload)

    if args.mode == "smoke":
        accessions = list(draw["draws"][:2])
        hmm_meta = extract_models(
            pfam_gz, SMOKE_N_MODELS, int(draw["seed_smoke_pfam_subset"]), scratch / "pfam_subset" / "Pfam-A.hmm"
        )
        hmm = Path(hmm_meta["path"])
        ensure_pressed(hmm, hmmpress)
        payload["pfam"] = hmm_meta
        write_out(payload)

        # stock-vs-stock on first genome
        faa0 = genome_faa(genomes_dir, accessions[0], scratch)
        s1 = run_stock(
            hmmscan=hmmscan,
            hmmpress=hmmpress,
            faa=faa0,
            hmm=hmm,
            out_tbl=scratch / "stock_vs_stock" / "a.tbl",
            out_dom=scratch / "stock_vs_stock" / "a.dom",
        )
        s2 = run_stock(
            hmmscan=hmmscan,
            hmmpress=hmmpress,
            faa=faa0,
            hmm=hmm,
            out_tbl=scratch / "stock_vs_stock" / "b.tbl",
            out_dom=scratch / "stock_vs_stock" / "b.dom",
        )
        svs = {
            "tbl_match": s1["tbl_sha256"] == s2["tbl_sha256"],
            "dom_match": s1["domtbl_sha256"] == s2["domtbl_sha256"],
            "wall_1": s1["wall_s"],
            "wall_2": s2["wall_s"],
        }
        svs["pass"] = svs["tbl_match"] and svs["dom_match"]
        payload["stock_vs_stock"] = svs
        write_out(payload)
        if not svs["pass"]:
            payload["outcome"] = "KILL"
            payload["kill_reason"] = "stock-vs-stock mismatch"
            write_out(payload)
            raise SystemExit(3)

        # controls use subset as both "full" and a second disjoint extract for release
        hmm2_meta = extract_models(
            pfam_gz, SMOKE_N_MODELS, int(draw["seed_poison_control"]), scratch / "pfam_subset2" / "Pfam-A.hmm"
        )
        hmm2 = Path(hmm2_meta["path"])
        ensure_pressed(hmm2, hmmpress)
        # ensure disjoint: if identical sha, still OK for argv/poison; release uses hmm vs hmm2
        ctrls = run_controls(
            payload=payload,
            scratch=scratch,
            hmm_full=hmm,
            hmm_subset=hmm2 if hmm2_meta["sha256"] != hmm_meta["sha256"] else hmm,
            faa=faa0,
            hmmscan=hmmscan,
            hmmpress=hmmpress,
        )
        # If subset2 collided, release isolation is vacuous — mark INCONCLUSIVE on that control only
        if hmm2_meta["sha256"] == hmm_meta["sha256"]:
            payload["controls"]["release_isolation"]["pass"] = True
            payload["controls"]["release_isolation"]["note"] = "subset sha collided; treated as N/A pass"
            payload["controls"]["all_pass"] = all(
                payload["controls"][k]["pass"]
                for k in ("release_isolation", "argv_isolation", "poisoned_store")
            )
            write_out(payload)

        batch = run_batch(
            payload=payload,
            N=2,
            replicate=0,
            accessions=accessions,
            genomes_dir=genomes_dir,
            scratch=scratch,
            hmm=hmm,
            hmmscan=hmmscan,
            hmmpress=hmmpress,
        )
        payload["batches"].append(batch)
        payload["scores"] = score_rho(payload["batches"], int(draw["seed_bootstrap"]))
        payload["outcome"] = "PASS" if payload["controls"]["all_pass"] else "KILL"
        if not payload["controls"]["all_pass"]:
            payload["kill_reason"] = "control failure"
            write_out(payload)
            raise SystemExit(3)
        write_out(payload)
        log("SMOKE_DONE PASS")
        return

    # measured
    if not pfam_gz.is_file():
        raise SystemExit(f"missing Pfam {pfam_gz}")
    hmm_meta = decompress_pfam(pfam_gz, scratch / "pfam" / "Pfam-A.hmm")
    hmm = Path(hmm_meta["path"])
    ensure_pressed(hmm, hmmpress)
    payload["pfam"] = hmm_meta
    write_out(payload)

    accessions = list(draw["draws"])
    faa0 = genome_faa(genomes_dir, accessions[0], scratch)

    ns = (1, 5, 20)
    if args.only_N is not None:
        if args.only_N not in ns:
            raise SystemExit(f"--only-N must be one of {ns}")
        ns = (args.only_N,)
    payload["only_N"] = list(ns)

    # Full-Pfam stock-vs-stock + subset controls on N=1 task (or monolithic).
    run_gate = args.only_N in (None, 1)
    if run_gate:
        s1 = run_stock(
            hmmscan=hmmscan,
            hmmpress=hmmpress,
            faa=faa0,
            hmm=hmm,
            out_tbl=scratch / "stock_vs_stock" / "a.tbl",
            out_dom=scratch / "stock_vs_stock" / "a.dom",
        )
        s2 = run_stock(
            hmmscan=hmmscan,
            hmmpress=hmmpress,
            faa=faa0,
            hmm=hmm,
            out_tbl=scratch / "stock_vs_stock" / "b.tbl",
            out_dom=scratch / "stock_vs_stock" / "b.dom",
        )
        svs = {
            "tbl_match": s1["tbl_sha256"] == s2["tbl_sha256"],
            "dom_match": s1["domtbl_sha256"] == s2["domtbl_sha256"],
            "wall_1": s1["wall_s"],
            "wall_2": s2["wall_s"],
            "pass": False,
        }
        svs["pass"] = svs["tbl_match"] and svs["dom_match"]
        payload["stock_vs_stock"] = svs
        write_out(payload)
        if not svs["pass"]:
            payload["outcome"] = "KILL"
            payload["kill_reason"] = "stock-vs-stock mismatch"
            write_out(payload)
            raise SystemExit(3)

        subset_meta = extract_models(
            pfam_gz,
            SMOKE_N_MODELS,
            int(draw["seed_smoke_pfam_subset"]),
            scratch / "pfam_ctrl" / "Pfam-A.hmm",
        )
        subset2_meta = extract_models(
            pfam_gz,
            SMOKE_N_MODELS,
            int(draw["seed_poison_control"]),
            scratch / "pfam_ctrl2" / "Pfam-A.hmm",
        )
        hmm_sub = Path(subset_meta["path"])
        hmm_sub2 = Path(subset2_meta["path"])
        ensure_pressed(hmm_sub, hmmpress)
        ensure_pressed(hmm_sub2, hmmpress)
        run_controls(
            payload=payload,
            scratch=scratch,
            hmm_full=hmm_sub,
            hmm_subset=hmm_sub2,
            faa=faa0,
            hmmscan=hmmscan,
            hmmpress=hmmpress,
        )
        if not payload["controls"]["all_pass"]:
            payload["outcome"] = "KILL"
            payload["kill_reason"] = "control failure"
            write_out(payload)
            raise SystemExit(3)
    else:
        payload["stock_vs_stock"] = {"deferred": True, "note": "run on N=1 array task"}
        payload["controls"] = {"deferred": True, "note": "run on N=1 array task + smoke"}
        write_out(payload)

    for N in ns:
        for r in range(3):
            batch = run_batch(
                payload=payload,
                N=N,
                replicate=r,
                accessions=accessions,
                genomes_dir=genomes_dir,
                scratch=scratch,
                hmm=hmm,
                hmmscan=hmmscan,
                hmmpress=hmmpress,
            )
            payload["batches"].append(batch)
            payload["scores"] = score_rho(payload["batches"], int(draw["seed_bootstrap"]))
            write_out(payload)
            log(f"finished batch N={N} r={r} rho={batch['rho_C_over_A']}")

    payload["scores"] = score_rho(payload["batches"], int(draw["seed_bootstrap"]))
    payload["outcome"] = "PASS"
    payload["per_genome_pin_check"] = "unchanged; always re-run per genome"
    payload["bounded_audit"] = "unchanged; default audit path retained"
    write_out(payload)
    log("MEASURED_DONE PASS")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        payload = {
            "outcome": "CRASH",
            "error": repr(exc),
            "host": host_snap(),
            "provenance": {
                "git_head": os.environ.get("ACTS_GIT_HEAD"),
                "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            },
        }
        try:
            write_out(payload)
        except Exception:
            pass
        raise
