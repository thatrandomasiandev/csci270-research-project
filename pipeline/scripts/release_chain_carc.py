#!/usr/bin/env python3
"""CARC runner for the TARE Pfam release chain.

Pilot seed 20261121, one genome, chain 37.4 → 38.0 → 38.1 → 38.2.
Measured seed 20261122, three genomes, full chain from 37.0, r=3.
``--self-test`` checks the drop judge on synthetic lines and does not scan.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import shutil
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "scripts"))

from acts.audit import residue_cap_binds  # noqa: E402
from acts.exact_certificate import (  # noqa: E402
    SEEDS as PAD_SEEDS,
    judge,
    sample_keys,
)
from acts.fasta import read_fasta  # noqa: E402
from acts.reference_run import IC2_SAMPLE_SEED, IC2_SAMPLE_SIZE  # noqa: E402
from headline_carc_measured import (  # noqa: E402
    DRAWS,
    EXCLUDE_REASONS,
    cache_bytes,
    compare_pair,
    cpu_model,
    fstype,
    host_snap,
    md5_file,
    meminfo,
    read_body,
    restore_cache,
)
from headline_carc_pilot import (  # noqa: E402
    index_fasta,
    index_models,
    unpinned,
    write_span,
)

ORDER = ("37.0", "37.1", "37.2", "37.3", "37.4", "38.0", "38.1", "38.2")
PILOT_CHAIN = ("37.4", "38.0", "38.1", "38.2")
POOL_SHA256 = "40dc92dba7c117e9e9e435f61498fd255a08e6790789d7f861a64aa3a51a456c"
POOL_N = 40
PILOT_GENOME = "GCF_057650775.1"
MEASURED_SHA256 = "3cc3445dbbfd79ea11fa75f306c31e3032bf5b2e4d529b08b1ff7d23667f69e2"
MEASURED_GENOMES = (
    "GCF_025259645.1",
    "GCF_057098645.1",
    "GCF_900196535.2",
)
SEED_PILOT = 20261121
SEED_MEASURED = 20261122
SEED_DROP = 20261123
SEED_DROP_RETRY = 20261124
PRIOR_A = 1.0146410126797523
PRIOR_C = 0.10846594102974193
PRIOR_SOURCE = (
    "EXACT_REPLAY_PROTOCOL.md headline measured addendum; "
    "headline-pilot three paired B runs on one genome"
)
MIN_LINES = 1000
MIN_FREE = 40 * 1024**3
CPU = "4"
CV_LIMIT = 0.05
LINE_FLOOR = MIN_LINES

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
    payload["outcome"] = "STOP"
    payload["scored"] = False
    write_out(payload)
    print(f"STOP: {reason}", file=sys.stderr, flush=True)
    raise SystemExit(code)


def finish(payload: dict, code: int = 0) -> None:
    payload["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_out(payload)
    raise SystemExit(code)


def _on_term(signum: int, _frame: object) -> None:
    if PAYLOAD is not None:
        PAYLOAD["stopped"] = f"signal {signum}"
        PAYLOAD["outcome"] = "STOP"
        PAYLOAD["scored"] = False
        write_out(PAYLOAD)
    raise SystemExit(2)


def drop_count(n: int) -> int:
    """k = max(1, round(0.05 N)). Python round-half-even, then the floor of 1."""
    return max(1, int(round(0.05 * n)))


def load_release_index(path: Path) -> tuple[dict, dict]:
    payload = json.loads(path.read_text())
    if payload.get("complete") is not True or payload.get("control_38_1_38_2_pass") is not True:
        raise RuntimeError(f"{path} is not a complete controlled census")
    info: dict[str, dict] = {}
    fdelta: dict[tuple[str, str], float] = {}
    for pair in payload["pairs"]:
        fdelta[(pair["old_release"], pair["new_release"])] = pair["f_delta"]
        for side, version in (("old", pair["old_release"]), ("new", pair["new_release"])):
            row = {
                "md5": pair[f"{side}_file"]["md5"],
                "bytes": pair[f"{side}_file"]["bytes"],
                "z": pair[f"z_{side}"],
                "n_blocks": pair[f"n_blocks_{side}"],
                "parser_entries": pair[f"parser_entries_{side}"],
                "inconclusive_reasons": list(pair[f"inconclusive_reasons_{side}"]),
                "f_delta_as_new": pair["f_delta"] if side == "new" else None,
            }
            previous = info.get(version)
            if previous is not None and previous["md5"] != row["md5"]:
                raise RuntimeError(f"{version} md5 disagrees inside {path}")
            if previous is None or side == "new":
                info[version] = row
    return info, fdelta


def pool_stems(genomes: Path) -> list[str]:
    stems = sorted(
        path.name[: -len("_protein.faa.gz")]
        for path in genomes.glob("*_protein.faa.gz")
    )
    if len(EXCLUDE_REASONS) != 50 or len(DRAWS) != 10:
        raise RuntimeError(
            f"STOP_DRAW: exclude {len(EXCLUDE_REASONS)} draws {len(DRAWS)}"
        )
    blocked = set(EXCLUDE_REASONS) | set(DRAWS)
    pool = [stem for stem in stems if stem not in blocked]
    digest = hashlib.sha256("\n".join(pool).encode()).hexdigest()
    if len(pool) != POOL_N or digest != POOL_SHA256:
        raise RuntimeError(f"STOP_DRAW: pool {len(pool)} {digest}")
    return pool


def draw_genomes(genomes: Path, mode: str, task: int) -> list[str]:
    pool = pool_stems(genomes)
    pilot = sorted(random.Random(SEED_PILOT).sample(sorted(pool), 1))[0]
    if pilot != PILOT_GENOME:
        raise RuntimeError(f"STOP_DRAW: pilot {pilot}")
    if mode == "pilot":
        return [pilot]
    reduced = [stem for stem in pool if stem != pilot]
    digest = hashlib.sha256("\n".join(sorted(reduced)).encode()).hexdigest()
    if digest != MEASURED_SHA256:
        raise RuntimeError(f"STOP_DRAW: reduced {digest}")
    drawn = sorted(random.Random(SEED_MEASURED).sample(sorted(reduced), 3))
    if drawn != list(MEASURED_GENOMES):
        raise RuntimeError(f"STOP_DRAW: measured {drawn}")
    if task < 0 or task >= len(drawn):
        raise RuntimeError(f"STOP_DRAW: task {task}")
    return [drawn[task]]


def decompress(src: Path, dest: Path) -> float:
    log(f"decompress {src.name}")
    t0 = time.perf_counter()
    tmp = dest.with_suffix(dest.suffix + ".partial")
    with tmp.open("wb") as out:
        proc = subprocess.run(["gzip", "-dc", str(src)], stdout=out, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        die(f"gzip failed ({proc.returncode}): {proc.stderr[-400:]!r}")
    tmp.replace(dest)
    return time.perf_counter() - t0


def press(hmm: Path) -> float:
    log(f"hmmpress {hmm.name}")
    t0 = time.perf_counter()
    proc = subprocess.run(["hmmpress", "-f", str(hmm)], check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"hmmpress failed: {(proc.stderr or proc.stdout)[-400:]}")
    return time.perf_counter() - t0


def count_models(path: Path) -> tuple[int, int]:
    headers = ends = 0
    with path.open("rb") as handle:
        for line in handle:
            if line.startswith(b"HMMER3/"):
                headers += 1
            elif line.startswith(b"//"):
                ends += 1
    return headers, ends


def release_cleanup(hmm: Path) -> None:
    for suffix in ("", ".h3i", ".h3m", ".h3f", ".h3p"):
        path = Path(str(hmm) + suffix) if suffix else hmm
        if path.exists():
            path.unlink()


def stock(db: Path, queries: Path, tag: Path, pin_z: int | None = None) -> dict:
    cmd = ["hmmscan", "--cut_ga", "--noali", "--cpu", CPU]
    if pin_z is not None:
        cmd.extend(["-Z", str(pin_z)])
    cmd.extend([
        "--tblout", str(tag) + ".tbl",
        "--domtblout", str(tag) + ".dom",
        "-o", os.devnull,
        str(db),
        str(queries),
    ])
    before = host_snap()
    log(f"stock {tag.name} pin={pin_z}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        die(f"hmmscan failed ({proc.returncode}): {(proc.stderr or proc.stdout)[-600:]}")
    log(f"stock {tag.name} {wall:.1f}s")
    return {
        "arm": "A" if pin_z is None else "drop",
        "wall_s": wall,
        "argv": cmd,
        "before": before,
        "after": host_snap(),
        "tbl": str(tag) + ".tbl",
        "dom": str(tag) + ".dom",
        "pin_z": pin_z,
    }


def parse_decision(path: Path) -> dict:
    import ast

    out: dict = {}
    phases: dict = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        if line.startswith("phases: "):
            raw = line[len("phases: "):]
            try:
                phases = ast.literal_eval(raw)
            except (SyntaxError, ValueError):
                out["phases_raw"] = raw[:500]
                phases = {}
        elif ": " in line:
            key, value = line.split(": ", 1)
            out[key.strip()] = value.strip()
    out["phases"] = phases
    return out


def tare(reference: Path, queries: Path, cache: Path, out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    cmd = [
        sys.executable, "-m", "acts", "run",
        "--strategy", "reference",
        "--pin", "-Z {entry_count}",
        "--verify", "audit",
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
    before = host_snap()
    log(f"tare {out.name}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=PIPE, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    for folder in ("calls", "calls_pinned", "calls_infer", "calls_slack"):
        path = out / folder
        if path.is_dir():
            shutil.rmtree(path)
    decision = parse_decision(out / "decision.txt")
    log(f"tare {out.name} rc={proc.returncode} {decision.get('decision')} {wall:.1f}s")
    return {
        "arm": "B",
        "wall_s": wall,
        "returncode": proc.returncode,
        "argv": cmd,
        "before": before,
        "after": host_snap(),
        "decision": decision.get("decision"),
        "why": decision.get("why"),
        "n_batches": decision.get("n_batches"),
        "phases": decision.get("phases") or {},
        "stdout_tail": (proc.stdout or "")[-500:],
        "stderr_tail": (proc.stderr or "")[-500:],
        "tbl": str(out / "tables" / "tblout"),
        "dom": str(out / "tables" / "domtblout"),
    }


def snapshot_cache(src: Path, dest: Path) -> int:
    size = cache_bytes(src)
    restore_cache(src, dest)
    return size


def public_row(row: dict) -> dict:
    keep = (
        "arm", "repeat", "wall_s", "argv", "before", "after", "decision", "why",
        "n_batches", "phases", "returncode", "compare", "pin_z", "cache_bytes",
        "stdout_tail", "stderr_tail", "tbl", "dom", "outcome", "reason",
    )
    return {key: row[key] for key in keep if key in row}


def die(message: str) -> None:
    """Harness failure: partial JSON, exit 2. A scored FAIL does not come through here."""
    print(f"STOP: {message}", file=sys.stderr, flush=True)
    if PAYLOAD is not None and "outcome" not in PAYLOAD:
        PAYLOAD["stopped"] = message
        PAYLOAD["outcome"] = "STOP"
        PAYLOAD["scored"] = False
        write_out(PAYLOAD)
    raise SystemExit(2)


def line_floor(compared: dict) -> str | None:
    for kind in ("tbl", "dom"):
        stock_n = compared[kind]["lines_stock"]
        replay_n = compared[kind]["lines_replay"]
        if stock_n < LINE_FLOOR or replay_n < LINE_FLOOR:
            return f"{kind} lines stock={stock_n} replay={replay_n} floor={LINE_FLOOR}"
    return None


def bodies_equal(paths: list[tuple[str, str]]) -> bool:
    first = (read_body(Path(paths[0][0])), read_body(Path(paths[0][1])))
    return all(
        (read_body(Path(tbl)), read_body(Path(dom))) == first
        for tbl, dom in paths[1:]
    )


def prepare_release(gz: Path, scratch: Path, version: str, expect: dict) -> dict:
    digest = md5_file(gz)
    if digest != expect["md5"] or gz.stat().st_size != expect["bytes"]:
        die(
            f"md5 mismatch {version}: {digest} {gz.stat().st_size} != {expect['md5']} {expect['bytes']}"
        )
    hmm = scratch / f"pfam{version}.hmm"
    decompress_s = decompress(gz, hmm)
    headers, ends = count_models(hmm)
    if headers != expect["n_blocks"] or ends != expect["n_blocks"] or headers != expect["z"]:
        die(
            f"model-count mismatch {version}: headers={headers} ends={ends} census z={expect['z']} blocks={expect['n_blocks']}"
        )
    if expect["parser_entries"] != expect["z"] or expect["inconclusive_reasons"]:
        return {
            "hmm": hmm,
            "inconclusive": True,
            "reasons": expect["inconclusive_reasons"] or ["parser_entries_ne_z"],
            "decompress_s": decompress_s,
            "headers": headers,
            "ends": ends,
            "md5": digest,
            "z": expect["z"],
        }
    press_s = press(hmm)
    return {
        "hmm": hmm,
        "inconclusive": False,
        "reasons": [],
        "decompress_s": decompress_s,
        "hmmpress_s": press_s,
        "headers": headers,
        "ends": ends,
        "md5": digest,
        "z": expect["z"],
        "press_charged": False,
    }


def names_in_file_order(spans: dict[str, tuple[int, int]]) -> list[str]:
    return [name for name, _span in sorted(spans.items(), key=lambda item: item[1][0])]


def random_pad_names(names: list[str], candidates: set[str], seed: int) -> list[str]:
    """Same draw as acts.exact_certificate.pad_indices for one random seed."""
    non_idx = [i for i, name in enumerate(names) if name not in candidates]
    width = min(max(200, len(candidates)), len(non_idx))
    if width == 0:
        return []
    chosen = sorted(random.Random(seed).sample(non_idx, width))
    return [names[i] for i in chosen]


def filter_text(lines: list[str], record_col: int, keep: set[str]) -> str:
    chosen = []
    for line in lines:
        cells = line.split()
        if record_col < len(cells) and cells[record_col] in keep:
            chosen.append(line)
    return "\n".join(chosen) + ("\n" if chosen else "")


def query_lengths(queries: Path) -> list[int]:
    return [len(rec.seq) for rec in read_fasta(queries)]


def negative_control(
    hmm: Path,
    queries: Path,
    stock_tbl: Path,
    stock_dom: Path,
    pin_z: int,
    scratch: Path,
    drop_seed: int,
) -> dict:
    """Inject a 5% candidate drop. The carried cache is not an input."""
    spans = index_models(hmm)
    names = names_in_file_order(spans)
    stock_tbl_body = read_body(stock_tbl)
    stock_dom_body = read_body(stock_dom)
    candidates = sorted({line.split()[0] for line in stock_tbl_body if line.split()})
    missing_names = [name for name in candidates if name not in spans]
    if missing_names:
        die(f"drop targets missing from the HMM: {missing_names[:5]}")
    k = drop_count(len(candidates))
    dropped = random.Random(drop_seed).sample(candidates, k)
    dropped_set = set(dropped)
    order, _fasta_spans = index_fasta(queries)
    queries_with_hits = [key for key in order if any(line.split()[2] == key for line in stock_tbl_body)]
    sample = sample_keys(queries_with_hits, IC2_SAMPLE_SIZE, IC2_SAMPLE_SEED)
    sample_set = set(sample)
    exercised = False
    for line in stock_tbl_body:
        cells = line.split()
        if len(cells) > 2 and cells[2] in sample_set and cells[0] in dropped_set:
            exercised = True
            break
    keep = [name for name in names if name not in dropped_set]
    reduced_db = scratch / f"drop_{drop_seed}.hmm"
    write_span(hmm, [spans[name] for name in keep], reduced_db)
    press(reduced_db)
    reduced = stock(reduced_db, queries, scratch / f"drop_{drop_seed}", pin_z=pin_z)
    compared = compare_pair(
        Path(reduced["tbl"]), Path(reduced["dom"]), stock_tbl, stock_dom
    )
    release_cleanup(reduced_db)
    pads = []
    refused = False
    for seed in PAD_SEEDS:
        pad_ids = set(random_pad_names(names, set(candidates), seed))
        tbl_verdict = judge(
            filter_text(stock_tbl_body, 2, sample_set),
            filter_text(read_body(Path(reduced["tbl"])), 2, sample_set),
            set(candidates),
            pad_ids,
            0,
        )
        dom_verdict = judge(
            filter_text(stock_dom_body, 3, sample_set),
            filter_text(read_body(Path(reduced["dom"])), 3, sample_set),
            set(candidates),
            pad_ids,
            0,
        )
        pads.append({
            "seed": seed,
            "n_pad": len(pad_ids),
            "tbl": tbl_verdict,
            "dom": dom_verdict,
        })
        if tbl_verdict["pass"] is False or dom_verdict["pass"] is False:
            refused = True
    lengths = query_lengths(queries)
    cap = residue_cap_binds(lengths)
    return {
        "drop_seed": drop_seed,
        "n_candidates": len(candidates),
        "k": k,
        "dropped_head": dropped[:8],
        "n_sample": len(sample),
        "sample_seed": IC2_SAMPLE_SEED,
        "sample_size_constant": IC2_SAMPLE_SIZE,
        "exercised_on_sample": exercised,
        "body_differs": not compared["byte_equal"],
        "compare": compared,
        "pads": pads,
        "judge_refused": refused,
        "residue_cap_binds": cap,
        "reduced_wall_s": reduced["wall_s"],
        "reduced_argv": reduced["argv"],
        "cache_used": False,
    }


def cv(values: list[float]) -> float:
    if len(values) < 2:
        return float("inf")
    mean = statistics.fmean(values)
    if mean <= 0:
        return float("inf")
    return statistics.stdev(values) / mean


def fit_coefficients(observations: list[dict]) -> dict | None:
    a_vals: list[float] = []
    c_vals: list[float] = []
    ids: list[str] = []
    for obs in observations:
        f_delta = obs["f_delta"]
        paired = obs["T_paired"]
        if f_delta <= 0 or paired <= 0:
            continue
        a_vals.append(obs["discovery_s"] / (f_delta * paired))
        c_vals.append((obs["U"] - obs["discovery_s"]) / paired)
        ids.append(obs["step_id"])
    if not a_vals:
        return None
    return {
        "label": "refit",
        "a": sum(a_vals) / len(a_vals),
        "c": sum(c_vals) / len(c_vals),
        "n": len(a_vals),
        "step_ids": ids,
    }


def predict_speedup(f_delta: float, fit: dict) -> float | None:
    denom = fit["a"] * f_delta + fit["c"]
    if denom <= 0:
        return None
    return 1.0 / denom


def step_observations(genome: str, step: dict) -> list[dict]:
    rows = []
    stocks = [row for row in step["repeats"] if row["arm"] == "A"]
    tares = [row for row in step["repeats"] if row["arm"] == "B"]
    for tare_row, stock_row in zip(tares, stocks):
        phases = tare_row.get("phases") or {}
        if "discovery_s" not in phases:
            continue
        rows.append({
            "step_id": f"{genome}:{step['old_release']}->{step['new_release']}:B{tare_row['repeat']}",
            "genome": genome,
            "old_release": step["old_release"],
            "new_release": step["new_release"],
            "repeat": tare_row["repeat"],
            "f_delta": step["f_delta"],
            "discovery_s": float(phases["discovery_s"]),
            "T_paired": stock_row["wall_s"],
            "U": tare_row["wall_s"],
        })
    return rows


def median_pair(step: dict) -> tuple[float | None, float | None]:
    stocks = [row["wall_s"] for row in step["repeats"] if row["arm"] == "A"]
    tares = [row["wall_s"] for row in step["repeats"] if row["arm"] == "B"]
    if not stocks or not tares:
        return None, None
    return statistics.median(stocks), statistics.median(tares)


def genome_payback(fill_wall: float, fill_stock_median: float, updates: list[dict]) -> dict:
    c_tare = fill_wall
    c_stock = fill_stock_median
    rows = []
    payback_m = None
    for index, step in enumerate(updates, start=1):
        t_med, u_med = median_pair(step)
        if t_med is None or u_med is None:
            break
        c_tare += u_med
        c_stock += t_med
        rows.append({"m": index, "release": step["new_release"], "C_TARE": c_tare, "C_stock": c_stock})
        if payback_m is None and c_tare <= c_stock:
            payback_m = index
    return {"m": payback_m, "cumulative": rows}


def summarize(paths: list[Path], dest: Path) -> None:
    """Cross-genome S_pred from earlier steps only. Run after every genome file exists."""
    genomes = [json.loads(path.read_text()) for path in paths]
    by_release: dict[str, list[dict]] = {}
    for genome in genomes:
        for step in genome.get("steps", []):
            if step.get("kind") != "update":
                continue
            by_release.setdefault(step["new_release"], []).append((genome["proteome"], step))
    order = [version for version in ORDER[1:] if version in by_release]
    earlier: list[dict] = []
    predictions = []
    for version in order:
        fit = fit_coefficients(earlier)
        if version == ORDER[1] or fit is None:
            fit_used = {
                "label": "prior",
                "a": PRIOR_A,
                "c": PRIOR_C,
                "source": PRIOR_SOURCE,
                "step_ids": [],
            }
        else:
            fit_used = fit
        block = []
        for proteome, step in by_release[version]:
            t_med, u_med = median_pair(step)
            s_g = (t_med / u_med) if t_med and u_med else None
            s_pred = predict_speedup(step["f_delta"], fit_used)
            rel = None if s_g in (None, 0) or s_pred is None else abs(s_pred - s_g) / s_g
            block.append({
                "genome": proteome,
                "old_release": step["old_release"],
                "new_release": version,
                "f_delta": step["f_delta"],
                "S_g": s_g,
                "stock_median_s": t_med,
                "tare_median_s": u_med,
                "S_pred": s_pred,
                "relative_error": rel,
                "outcome": step.get("outcome"),
            })
            earlier.extend(step_observations(proteome, step))
        s_values = [row["S_g"] for row in block if row["S_g"]]
        predictions.append({
            "new_release": version,
            "fit": {key: fit_used[key] for key in ("label", "a", "c", "step_ids") if key in fit_used},
            "genomes": block,
            "S_g_median": statistics.median(s_values) if s_values else None,
            "S_g_geomean": math.exp(sum(math.log(v) for v in s_values) / len(s_values)) if s_values else None,
            "S_g_min": min(s_values) if s_values else None,
            "S_g_max": max(s_values) if s_values else None,
        })
    out = {
        "system": "TARE",
        "seed": SEED_MEASURED,
        "definition": "S_pred = 1/(a*f_delta+c); a,c from earlier chain steps only, else the headline-pilot prior",
        "predictions": predictions,
        "payback": [
            {
                "genome": genome["proteome"],
                **genome_payback(
                    genome["fill"]["wall_s"],
                    statistics.median(row["wall_s"] for row in genome["fill_stocks"]),
                    [step for step in genome["steps"] if step.get("kind") == "update"],
                ),
            }
            for genome in genomes
            if genome.get("fill") and genome.get("fill_stocks")
        ],
    }
    dest.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"wrote {dest}")


def score_exact(compared: dict, decision: str | None) -> tuple[str, str | None]:
    floor = line_floor(compared)
    if floor:
        return "INCONCLUSIVE", floor
    if decision is not None and decision != "SHIP":
        return "FAIL", f"decision {decision}"
    if not compared["byte_equal"]:
        classes = {
            "tbl": compared["tbl"]["classes"],
            "dom": compared["dom"]["classes"],
        }
        return "FAIL", f"body differs {classes}"
    return "PASS", None


def self_test() -> None:
    """Synthetic positive and negative judge cases. No release file and no hmmscan."""
    if drop_count(10) != 1:
        raise SystemExit("self-test: k for 10 candidates")
    if drop_count(100) != 5:
        raise SystemExit("self-test: k for 100 candidates")
    stock_line = "ModelA Q1 x"
    plus_line = "ModelB Q1 x"
    kept = judge("ModelA Q1 x\nModelB Q1 x\n", "ModelA Q1 x\nModelB Q1 x\n", {"ModelA", "ModelB"}, set(), 0)
    if kept["pass"] is not True:
        raise SystemExit(f"self-test: identical candidate text did not pass {kept}")
    dropped = judge(
        "ModelA Q1 x\nModelB Q1 x\n",
        "ModelA Q1 x\n",
        {"ModelA", "ModelB"},
        {"Pad1"},
        0,
    )
    if dropped["pass"] is not False:
        raise SystemExit(f"self-test: a dropped candidate passed {dropped}")
    names = [f"M{i}" for i in range(10)]
    pads = random_pad_names(names, {"M0", "M1"}, PAD_SEEDS[0])
    if not pads or any(name in {"M0", "M1"} for name in pads):
        raise SystemExit("self-test: pad drew a candidate")
    again = random_pad_names(names, {"M0", "M1"}, PAD_SEEDS[0])
    if pads != again:
        raise SystemExit("self-test: pad draw is not repeatable")
    print("self-test pass", {"kept": kept["pass"], "dropped": dropped["fail_mode"], "example": stock_line != plus_line})


def open_release(version: str, root: Path) -> Path:
    path = root / version / "Pfam-A.hmm.gz"
    if not path.is_file():
        raise RuntimeError(f"missing {path}")
    return path


def run_chain(mode: str, task: int) -> None:
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("STOP: this run executes only under sbatch")
    scratch = Path(os.environ["ACTS_SCRATCH"])
    genomes = Path(os.environ["ACTS_GENOMES"])
    release_root = Path(os.environ["ACTS_RELEASE_DIR"])
    pairs_path = Path(os.environ["ACTS_PAIRS"])
    scratch.mkdir(parents=True, exist_ok=True)
    kind = fstype(str(scratch))
    free = shutil.disk_usage(scratch).free
    chain = PILOT_CHAIN if mode == "pilot" else ORDER
    payload: dict = {
        "system": "TARE",
        "test": f"release-chain-{mode}",
        "protocol": "pipeline/docs/RELEASE_CHAIN_PROTOCOL.md",
        "seed": SEED_PILOT if mode == "pilot" else SEED_MEASURED,
        "mode": mode,
        "task": task,
        "chain": list(chain),
        "job_id": os.environ.get("SLURM_ARRAY_JOB_ID") or os.environ.get("SLURM_JOB_ID"),
        "array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
        "cpu_model": cpu_model(),
        "host": os.uname().nodename,
        "platform": os.uname().sysname + " " + os.uname().release,
        "python": sys.version.split()[0],
        "git_head": os.environ.get("ACTS_GIT_HEAD", ""),
        "git_dirty": os.environ.get("ACTS_GIT_DIRTY", ""),
        "argv": sys.argv,
        "scratch": str(scratch),
        "scratch_fstype": kind,
        "scratch_free_bytes_start": free,
        "meminfo_start": meminfo(),
        "press_charged_to_arms": False,
        "laptop_wall_is_speed_evidence": False,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "steps": [],
    }
    global PAYLOAD
    PAYLOAD = payload
    info, fdelta = load_release_index(pairs_path)
    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)
    if free < MIN_FREE:
        stop(f"scratch {scratch} has {free} bytes free, need {MIN_FREE}", payload)
    if not genomes.is_dir():
        stop(f"missing {genomes}", payload)
    version = subprocess.run(["hmmscan", "-h"], check=False, capture_output=True, text=True)
    version_line = (version.stdout or version.stderr or "").splitlines()[:3]
    payload["hmmer_version_lines"] = version_line
    payload["hmmer_tarball_sha256"] = os.environ.get("ACTS_HMMER_SHA256", "")
    if not any("HMMER 3.4" in line for line in version_line):
        stop(f"hmmscan is not HMMER 3.4: {version_line}", payload)
    try:
        chosen = draw_genomes(genomes, mode, task)
    except RuntimeError as exc:
        stop(str(exc), payload)
    proteome = chosen[0]
    payload["proteome"] = proteome
    faa_gz = genomes / f"{proteome}_protein.faa.gz"
    queries = scratch / "queries.faa"
    with faa_gz.open("rb") as raw:
        proc = subprocess.run(["gzip", "-dc"], stdin=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        stop(f"proteome gzip failed: {proc.stderr[-200:]!r}", payload)
    queries.write_bytes(proc.stdout)
    payload["input_md5"] = {"proteome": md5_file(faa_gz)}
    payload["release_md5"] = {}
    write_out(payload)

    carried: Path | None = None
    repeats_per_step = 1 if mode == "pilot" else 3
    stocks_at_fill = 2 if mode == "pilot" else 3
    first_update_stock: dict | None = None

    for index, version_name in enumerate(chain):
        expect = info[version_name]
        gz = open_release(version_name, release_root)
        prepared = prepare_release(gz, scratch, version_name, expect)
        payload["release_md5"][version_name] = prepared["md5"]
        payload["input_md5"][version_name] = prepared["md5"]
        if prepared["inconclusive"]:
            payload["steps"].append({
                "release": version_name,
                "outcome": "INCONCLUSIVE",
                "reasons": prepared["reasons"],
                "scored": True,
            })
            payload["outcome"] = "INCONCLUSIVE"
            release_cleanup(prepared["hmm"])
            finish(payload, 0)
        hmm = prepared["hmm"]
        step: dict = {
            "release": version_name,
            "kind": "fill" if index == 0 else "update",
            "press": {key: prepared[key] for key in prepared if key != "hmm"},
            "repeats": [],
        }
        if index > 0:
            step["old_release"] = chain[index - 1]
            step["new_release"] = version_name
            step["f_delta"] = fdelta[(chain[index - 1], version_name)]
        payload["current_step"] = step
        if index == 0:
            stock_rows = []
            for repeat in range(1, stocks_at_fill + 1):
                row = stock(hmm, queries, scratch / f"{version_name}_A{repeat}")
                row["repeat"] = repeat
                stock_rows.append(row)
                step["repeats"].append(public_row(row))
            if not bodies_equal([(row["tbl"], row["dom"]) for row in stock_rows]):
                step["outcome"] = "INCONCLUSIVE"
                step["reason"] = "stock repeats are not byte-identical"
                payload["steps"].append(step)
                payload["outcome"] = "INCONCLUSIVE"
                write_out(payload)
                release_cleanup(hmm)
                finish(payload, 0)
            cache = scratch / "cache_fill.sqlite"
            if cache.exists():
                cache.unlink()
            filled = tare(hmm, queries, cache, scratch / "fill")
            filled["repeat"] = 1
            compared = compare_pair(Path(filled["tbl"]), Path(filled["dom"]), Path(stock_rows[0]["tbl"]), Path(stock_rows[0]["dom"]))
            filled["compare"] = compared
            filled["cache_bytes"] = cache_bytes(cache) if cache.exists() else None
            outcome, reason = score_exact(compared, filled["decision"])
            step["fill"] = public_row(filled)
            step["outcome"] = outcome
            step["reason"] = reason
            payload["fill"] = step["fill"]
            payload["fill_stocks"] = [public_row(row) for row in stock_rows]
            payload["steps"].append(step)
            write_out(payload)
            if outcome != "PASS":
                payload["outcome"] = outcome
                release_cleanup(hmm)
                finish(payload, 0)
            carried = scratch / "cache_carried.sqlite"
            snapshot_cache(cache, carried)
            release_cleanup(hmm)
            continue

        assert carried is not None
        incoming = carried
        stock_rows = []
        b_outcomes: list[str] = []
        b1_tables: dict | None = None
        for repeat in range(1, repeats_per_step + 1):
            row = stock(hmm, queries, scratch / f"{version_name}_A{repeat}")
            row["repeat"] = repeat
            stock_rows.append(row)
            step["repeats"].append(public_row(row))
            work = scratch / f"cache_{version_name}_B{repeat}.sqlite"
            restore_cache(incoming, work)
            updated = tare(hmm, queries, work, scratch / f"{version_name}_B{repeat}")
            updated["repeat"] = repeat
            compared = compare_pair(
                Path(updated["tbl"]), Path(updated["dom"]), Path(row["tbl"]), Path(row["dom"])
            )
            updated["compare"] = compared
            updated["cache_bytes"] = cache_bytes(work) if work.exists() else None
            outcome, reason = score_exact(compared, updated["decision"])
            updated["outcome"] = outcome
            updated["reason"] = reason
            b_outcomes.append(outcome)
            step["repeats"].append(public_row(updated))
            if repeat == 1 and outcome == "PASS":
                carried = scratch / f"cache_after_{version_name}.sqlite"
                snapshot_cache(work, carried)
                b1_tables = {"tbl": updated["tbl"], "dom": updated["dom"]}
            write_out(payload)
        stocks_agree = bodies_equal([(row["tbl"], row["dom"]) for row in stock_rows])
        if not stocks_agree:
            step["outcome"] = "INCONCLUSIVE"
            step["reason"] = "stock repeats are not byte-identical; TARE repeats are not scored"
            step["tare_scored"] = False
            payload["steps"].append(step)
            payload["outcome"] = "INCONCLUSIVE"
            release_cleanup(hmm)
            finish(payload, 0)
        b1_ok = b_outcomes[0] == "PASS"
        if b1_ok and all(item == "PASS" for item in b_outcomes):
            step["outcome"] = "PASS"
        elif not b1_ok:
            step["outcome"] = b_outcomes[0]
            step["reason"] = "B1 failed; later releases are not run"
        else:
            step["outcome"] = "FAIL"
            step["reason"] = "a later repeat failed; B1 still carries the chain"
        if mode == "pilot" and chain[index - 1] == "37.4" and b1_tables is not None:
            first_update_stock = stock_rows[0]
        if version_name == "38.2" and b1_tables is not None:
            payload["chained_38_2_tables"] = b1_tables
            payload["stock_38_2_tables"] = {"tbl": stock_rows[0]["tbl"], "dom": stock_rows[0]["dom"]}
        payload["steps"].append(step)
        write_out(payload)
        keep_hmm = mode == "pilot" and version_name in {"38.1", "38.2"} and b1_ok
        if keep_hmm:
            payload.setdefault("kept_hmm", {})[version_name] = str(hmm)
        if mode == "pilot" and chain[index - 1] == "37.4" and version_name == "38.0" and b1_ok:
            payload["negative_control"] = run_pilot_negative(
                payload, hmm, queries, first_update_stock, expect["z"], scratch
            )
            write_out(payload)
            if payload["negative_control"]["status"] != "refused":
                payload["measured_blocked"] = payload["negative_control"]["status"]
        if not keep_hmm:
            release_cleanup(hmm)
        if not b1_ok:
            payload["outcome"] = step["outcome"]
            finish(payload, 0)

    if mode == "pilot":
        payload["drift"] = run_drift(payload, scratch, queries, info, release_root)
        write_out(payload)
        neg = payload.get("negative_control", {})
        exact_fail = any(step.get("outcome") == "FAIL" for step in payload["steps"])
        drift_ok = payload["drift"].get("pass") is True
        if exact_fail:
            payload["outcome"] = "FAIL"
        elif any(step.get("outcome") == "INCONCLUSIVE" for step in payload["steps"]) or not drift_ok and payload["drift"].get("status") == "INCONCLUSIVE":
            payload["outcome"] = "INCONCLUSIVE"
        elif not drift_ok:
            payload["outcome"] = "FAIL"
        elif neg.get("status") != "refused":
            payload["outcome"] = "INCONCLUSIVE" if neg.get("status") == "INCONCLUSIVE" else "FAIL"
            payload["measured_blocked"] = neg.get("status")
        else:
            payload["outcome"] = "PASS"
        payload["pilot_pass"] = payload["outcome"] == "PASS"
        payload["scored"] = True
        finish(payload, 0)

    if mode == "measured" and task == 0:
        last = chain[-1]
        last_step = payload["steps"][-1]
        stock_row = next(row for row in last_step["repeats"] if row["arm"] == "A")
        gz = open_release(last, release_root)
        prepared = prepare_release(gz, scratch, last, info[last])
        payload["unpinned"] = unpinned(
            prepared["hmm"],
            queries,
            Path(stock_row["tbl"]),
            Path(stock_row["dom"]),
            scratch / "unpinned",
        )
        payload["unpinned"]["differs"] = not payload["unpinned"]["byte_equal"]
        release_cleanup(prepared["hmm"])
        if not payload["unpinned"]["differs"]:
            payload["exact_label"] = "not EXACT"
            payload["unpinned_note"] = "byte-identical unpinned replay; matches are uninformative"
    outcomes = [step.get("outcome") for step in payload["steps"]]
    if "FAIL" in outcomes:
        payload["outcome"] = "FAIL"
    elif "INCONCLUSIVE" in outcomes:
        payload["outcome"] = "INCONCLUSIVE"
    elif payload.get("exact_label") == "not EXACT":
        payload["outcome"] = "FAIL"
    else:
        payload["outcome"] = "PASS"
    payload["scored"] = True
    walls = {}
    for step in payload["steps"]:
        if step.get("kind") != "update":
            continue
        stocks = [row["wall_s"] for row in step["repeats"] if row["arm"] == "A"]
        tares = [row["wall_s"] for row in step["repeats"] if row["arm"] == "B"]
        step["S_g"] = statistics.median(stocks) / statistics.median(tares) if stocks and tares else None
        step["cv"] = {"A": cv(stocks), "B": cv(tares)}
        step["cv_flag"] = {arm: step["cv"][arm] > CV_LIMIT for arm in ("A", "B")}
        walls[step["new_release"]] = step["S_g"]
    if payload.get("fill"):
        payload["payback"] = genome_payback(
            payload["fill"]["wall_s"],
            statistics.median(row["wall_s"] for row in payload["fill_stocks"]),
            [step for step in payload["steps"] if step.get("kind") == "update"],
        )
    payload["S_g_by_release"] = walls
    finish(payload, 0)


def run_pilot_negative(payload, hmm, queries, stock_row, pin_z, scratch) -> dict:
    if stock_row is None:
        return {"status": "INCONCLUSIVE", "reason": "no stock body for the first update"}
    lengths = query_lengths(queries)
    if residue_cap_binds(lengths):
        return {
            "status": "INCONCLUSIVE",
            "reason": "residue cap binds; the random-pad layer cannot run",
            "residue_cap_binds": True,
        }
    first = negative_control(
        hmm, queries, Path(stock_row["tbl"]), Path(stock_row["dom"]), pin_z, scratch, SEED_DROP
    )
    chosen = first
    tried = [first]
    if (not first["body_differs"]) or (not first["exercised_on_sample"]):
        second = negative_control(
            hmm, queries, Path(stock_row["tbl"]), Path(stock_row["dom"]), pin_z, scratch, SEED_DROP_RETRY
        )
        tried.append(second)
        chosen = second
        if (not second["body_differs"]) or (not second["exercised_on_sample"]):
            return {"status": "INCONCLUSIVE", "reason": "drop was not exercised on two seeds", "tries": tried}
    if not chosen["judge_refused"]:
        return {"status": "control_failed", "reason": "body differs and the judge passed", "tries": tried}
    return {"status": "refused", "tries": tried}


def run_drift(payload: dict, scratch: Path, queries: Path, info: dict, release_root: Path) -> dict:
    if "kept_hmm" not in payload or "38.1" not in payload["kept_hmm"] or "38.2" not in payload["kept_hmm"]:
        return {"pass": False, "status": "INCONCLUSIVE", "reason": "chain did not keep 38.1 and 38.2"}
    hmm_old = Path(payload["kept_hmm"]["38.1"])
    hmm_new = Path(payload["kept_hmm"]["38.2"])
    cache = scratch / "cache_drift_38.1.sqlite"
    if cache.exists():
        cache.unlink()
    fill = tare(hmm_old, queries, cache, scratch / "drift_fill")
    update = tare(hmm_new, queries, cache, scratch / "drift_update")
    stock_paths = payload.get("stock_38_2_tables")
    chained = payload.get("chained_38_2_tables")
    if not stock_paths or not chained:
        return {"pass": False, "status": "INCONCLUSIVE", "reason": "missing chained or stock 38.2 tables"}
    direct_vs_stock = compare_pair(Path(update["tbl"]), Path(update["dom"]), Path(stock_paths["tbl"]), Path(stock_paths["dom"]))
    chained_vs_stock = compare_pair(Path(chained["tbl"]), Path(chained["dom"]), Path(stock_paths["tbl"]), Path(stock_paths["dom"]))
    direct_vs_chained = compare_pair(Path(update["tbl"]), Path(update["dom"]), Path(chained["tbl"]), Path(chained["dom"]))
    three = direct_vs_stock["byte_equal"] and chained_vs_stock["byte_equal"] and direct_vs_chained["byte_equal"]
    status = "pass" if three else "drift_or_exactness_failure"
    if chained_vs_stock["byte_equal"] and not direct_vs_stock["byte_equal"]:
        status = "drift"
    elif direct_vs_stock["byte_equal"] and not chained_vs_stock["byte_equal"]:
        status = "exactness"
    return {
        "pass": three,
        "status": status,
        "fill_decision": fill["decision"],
        "update_decision": update["decision"],
        "direct_vs_stock": direct_vs_stock,
        "chained_vs_stock": chained_vs_stock,
        "direct_vs_chained": direct_vs_chained,
        "fill_wall_s": fill["wall_s"],
        "update_wall_s": update["wall_s"],
    }


def main() -> None:
    if "--self-test" in sys.argv:
        self_test()
        return
    if "--summarize" in sys.argv:
        raw = sys.argv[sys.argv.index("--summarize") + 1:]
        if len(raw) < 2:
            raise SystemExit("usage: --summarize OUT.json GENOME.json ...")
        summarize([Path(item) for item in raw[1:]], Path(raw[0]))
        return
    mode = os.environ.get("ACTS_MODE", "")
    if mode not in {"pilot", "measured"}:
        raise SystemExit("STOP: ACTS_MODE must be pilot or measured")
    task = 0
    if mode == "measured":
        raw = os.environ.get("SLURM_ARRAY_TASK_ID")
        if raw is None or not raw.isdigit():
            raise SystemExit("STOP: measured run requires SLURM_ARRAY_TASK_ID")
        task = int(raw)
    try:
        run_chain(mode, task)
    except SystemExit:
        raise
    except BaseException as exc:
        if PAYLOAD is not None and "outcome" not in PAYLOAD:
            PAYLOAD["crashed"] = f"{type(exc).__name__}: {exc}"[:2000]
            PAYLOAD["outcome"] = "STOP"
            PAYLOAD["scored"] = False
            write_out(PAYLOAD)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
