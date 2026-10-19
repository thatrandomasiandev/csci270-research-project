#!/usr/bin/env python3
"""W12a CARC timing: stock, TARE, and the expert script.

Refuses a measured or pilot scan unless ACTS_CARC=1 and SLURM_JOB_ID are
set. Login-node checks, with no HMMER scan::

    python3 scripts/baselines_exact_w12a.py selftest
    ACTS_GENOMES=... python3 scripts/baselines_exact_w12a.py drawcheck

The locked draw is the 2026-10-19 addendum in docs/BASELINES_EXACT_PROTOCOL.md.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import random
import re
import signal
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from baseline_carc import (  # noqa: E402
    gunzip_queries,
    materialize_hmm,
    median,
    order_for,
    summarize,
    tare_cmd,
)
from headline_carc_measured import (  # noqa: E402
    DRAWS,
    EXCLUDE_REASONS,
    cache_bytes,
    classify,
    parse_decision,
    read_body,
    restore_cache,
    row_key,
)

PILOT_SEED = 20261241
MEASURED_SEED = 20261242
BOOT_SEED = 20261249
BOOT_N = 10000
MIN_BODY_LINES = 1000
DIR_SHA256 = "bf703062fb6adad0cbfd3335a7dfb7279bacff18a20a48e0aa95b2cb5ae5034d"
POOL_SHA256 = "199fc50c099f1e09ce443d8f03335a5a037bae22205933c3177be3476b60ca04"
START_COMMIT = "1c65571538afcc139af560156147e4276905f9b4"
ASSEMBLY = re.compile(r"GC[AF]_\d+\.\d+")
SUFFIX = "_protein.faa.gz"

W8_NAMED = {
    "GCF_057650775.1": "RELEASE_CHAIN_PROTOCOL.md pilot, seed 20261121",
    "GCF_025259645.1": "RELEASE_CHAIN_PROTOCOL.md measured, seed 20261122",
    "GCF_057098645.1": "RELEASE_CHAIN_PROTOCOL.md measured, seed 20261122",
    "GCF_900196535.2": "RELEASE_CHAIN_PROTOCOL.md measured, seed 20261122",
}
D2_EXTRA = {
    "GCF_024585005.1": "D1 rescaler pilot, seed 20261133",
    "GCF_977065495.1": "D2b locked measured genome, seed 20261132",
}
EXPECTED_POOL = (
    "GCF_001900595.1",
    "GCF_002357915.1",
    "GCF_002953435.1",
    "GCF_003018555.1",
    "GCF_003018855.1",
    "GCF_010365405.1",
    "GCF_014295275.1",
    "GCF_017900975.1",
    "GCF_018415995.1",
    "GCF_019375055.2",
    "GCF_019969525.1",
    "GCF_020034635.1",
    "GCF_023370135.1",
    "GCF_024918035.1",
    "GCF_025782825.1",
    "GCF_036498065.1",
    "GCF_037231045.1",
    "GCF_037920625.1",
    "GCF_040271735.2",
    "GCF_040571355.1",
    "GCF_045348745.1",
    "GCF_045689345.1",
    "GCF_048404355.1",
    "GCF_048571365.1",
    "GCF_049354865.1",
    "GCF_052938795.1",
    "GCF_054902895.1",
    "GCF_055398225.1",
    "GCF_055807995.1",
    "GCF_056784295.1",
    "GCF_057812745.1",
    "GCF_057813415.1",
    "GCF_058106345.1",
    "GCF_904866455.1",
)
PILOT_STEMS = ("GCF_003018855.1",)
MEASURED_STEMS = (
    "GCF_018415995.1",
    "GCF_019969525.1",
    "GCF_037231045.1",
    "GCF_040271735.2",
    "GCF_055807995.1",
)
# Committed W8 rule on the headline pool, seed 20261222, not a committed draw.
W8_SIM_N3 = ("GCF_010365405.1", "GCF_023370135.1", "GCF_056784295.1")
W8_SIM_N5 = (
    "GCF_010365405.1",
    "GCF_023370135.1",
    "GCF_024585005.1",
    "GCF_056784295.1",
    "GCF_057650775.1",
)
W8_SIM_PILOT = ("GCF_003018555.1",)
W8_SIM_AFTER_PILOT = (
    "GCF_014295275.1",
    "GCF_024585005.1",
    "GCF_057098645.1",
)

REPORT: dict = {}
_FLUSHING = False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_lines(lines: list[str]) -> str:
    payload = ("\n".join(lines) + ("\n" if lines else "")).encode()
    return hashlib.sha256(payload).hexdigest()


def faa_name(stem: str) -> str:
    return stem + SUFFIX


def pool_sha(stems: list[str]) -> str:
    return hashlib.sha256("\n".join(stems).encode()).hexdigest()


def directory_stems(genomes: Path) -> list[str]:
    stems = sorted(path.name[: -len(SUFFIX)] for path in genomes.glob("*" + SUFFIX))
    if not stems:
        raise SystemExit(f"STOP no proteomes in {genomes}")
    return stems


def blocked_accessions() -> set[str]:
    if len(EXCLUDE_REASONS) != 50 or len(DRAWS) != 10:
        raise SystemExit(
            f"STOP headline exclusion {len(EXCLUDE_REASONS)} draws {len(DRAWS)}"
        )
    diverse_path = ROOT / "results" / "diverse_genomes" / "draw.json"
    if not diverse_path.is_file():
        raise SystemExit(f"STOP missing {diverse_path}")
    diverse = set(ASSEMBLY.findall(diverse_path.read_text()))
    if len(diverse) < 50:
        raise SystemExit(f"STOP diverse accession parse ({len(diverse)})")
    return set(EXCLUDE_REASONS) | set(DRAWS) | diverse | set(W8_NAMED) | set(D2_EXTRA)


def draw_names(pool: list[str]) -> tuple[list[str], list[str]]:
    if list(pool) != list(EXPECTED_POOL):
        raise SystemExit("STOP pool disagrees with the locked 34-stem pool")
    if pool_sha(pool) != POOL_SHA256:
        raise SystemExit("STOP pool sha256 disagrees with the lock")
    pilot = sorted(random.Random(PILOT_SEED).sample(list(pool), 1))
    rest = [stem for stem in pool if stem not in pilot]
    measured = sorted(random.Random(MEASURED_SEED).sample(rest, 5))
    if pilot != list(PILOT_STEMS) or measured != list(MEASURED_STEMS):
        raise SystemExit(f"STOP draw pilot={pilot} measured={measured}")
    return pilot, measured


def w8_simulations(stems: list[str]) -> dict:
    """What seed 20261222 would draw on the committed W8 pool rule.

    Not an exclusion. The committed W8 document still names seeds
    20261121 and 20261122. Overlap with our locked names stops the run.
    """
    w8_pool = [stem for stem in stems if stem not in EXCLUDE_REASONS and stem not in DRAWS]
    sim3 = tuple(sorted(random.Random(20261222).sample(w8_pool, 3)))
    sim5 = tuple(sorted(random.Random(20261222).sample(list(w8_pool), 5)))
    pilot = tuple(sorted(random.Random(20261221).sample(list(w8_pool), 1)))
    reduced = [stem for stem in w8_pool if stem not in pilot]
    after = tuple(sorted(random.Random(20261222).sample(reduced, 3)))
    if sim3 != W8_SIM_N3 or sim5 != W8_SIM_N5 or pilot != W8_SIM_PILOT or after != W8_SIM_AFTER_PILOT:
        raise SystemExit("STOP W8 seed-20261222 simulation disagrees with the lock")
    ours = set(PILOT_STEMS) | set(MEASURED_STEMS)
    overlap = sorted(ours & (set(sim3) | set(sim5) | set(pilot) | set(after)))
    if overlap:
        raise SystemExit(f"STOP locked genomes overlap a W8 20261222 simulation: {overlap}")
    return {
        "note": (
            "W8 seed 20261222 is not committed. These are the committed pool "
            "rule at that seed. They are not removed from our pool."
        ),
        "n3": list(sim3),
        "n5": list(sim5),
        "pilot_seed_20261221": list(pilot),
        "n3_after_that_pilot": list(after),
        "overlap_with_w12a": overlap,
    }


def verify_directory(genomes: Path) -> dict:
    stems = directory_stems(genomes)
    digest = pool_sha(stems)
    if digest != DIR_SHA256:
        raise SystemExit(f"STOP directory sha256 {digest} != {DIR_SHA256}")
    blocked = blocked_accessions()
    pool = [stem for stem in stems if stem not in blocked]
    pilot, measured = draw_names(pool)
    sims = w8_simulations(stems)
    return {
        "directory_sha256": digest,
        "pool_sha256": pool_sha(pool),
        "pool_n": len(pool),
        "pilot": pilot,
        "measured": measured,
        "w8_seed_20261222_not_committed": sims,
    }


def cv(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    if mean == 0:
        return None
    var = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(var) / mean


def flush() -> None:
    global _FLUSHING
    if _FLUSHING:
        return
    _FLUSHING = True
    try:
        text = json.dumps(REPORT, indent=2) + "\n"
        paths: list[Path] = []
        if os.environ.get("ACTS_OUT"):
            paths.append(Path(os.environ["ACTS_OUT"]))
        if os.environ.get("ACTS_SCRATCH"):
            paths.append(Path(os.environ["ACTS_SCRATCH"]) / "server_partial.json")
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(text)
            temporary.replace(path)
    finally:
        _FLUSHING = False


def on_signal(signum: int, _frame) -> None:
    REPORT["status"] = "partial"
    REPORT["signal"] = signum
    REPORT["walls_are_evidence"] = False
    flush()
    raise SystemExit(128 + signum)


def timed(cmd: list[str], cwd: Path, env: dict[str, str], *, allow_exit_1: bool = False) -> dict:
    started = time.perf_counter()
    proc = subprocess_run(cmd, cwd, env)
    wall = time.perf_counter() - started
    ok = proc.returncode == 0 or (allow_exit_1 and proc.returncode == 1)
    row = {
        "argv": cmd,
        "returncode": proc.returncode,
        "wall_s": wall,
        "stdout_tail": (proc.stdout or "")[-500:],
        "stderr_tail": (proc.stderr or "")[-500:],
    }
    if not ok:
        raise SystemExit(f"STOP command exit {proc.returncode}: {' '.join(cmd[:8])}")
    return row


def subprocess_run(cmd: list[str], cwd: Path, env: dict[str, str]):
    import subprocess

    return subprocess.run(cmd, cwd=cwd, env=env, check=False, capture_output=True, text=True)


def example_keys(replay: list[str], stock: list[str], kind: str, limit: int = 3) -> dict:
    replay_counts = Counter(row_key(line.split(), kind) for line in replay)
    stock_counts = Counter(row_key(line.split(), kind) for line in stock)
    missing = [list(key) for key in stock_counts if stock_counts[key] > replay_counts[key]][:limit]
    extra = [list(key) for key in replay_counts if replay_counts[key] > stock_counts[key]][:limit]
    return {"missing": missing, "extra": extra}


def table_report(path: Path, reference: list[str] | None, kind: str) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        return {"present": False, "byte_identical": False, "classes": ["missing-file"], "lines": 0}
    lines = read_body(path)
    payload: dict = {
        "present": True,
        "path": str(path),
        "lines": len(lines),
        "body_sha256": sha256_lines(lines),
    }
    if reference is None:
        return payload
    info = classify(lines, reference, kind)
    classes = list(info["classes"])
    if info.get("missing_keys") and info.get("extra_keys") and "different-row" not in classes:
        classes.append("different-row")
    payload.update(
        {
            "byte_identical": bool(info["byte_equal"]),
            "token_equal": bool(info["token_equal"]),
            "classes": classes,
            "missing_keys": info.get("missing_keys", 0),
            "extra_keys": info.get("extra_keys", 0),
            "lines_stock": info["lines_stock"],
        }
    )
    if not info["byte_equal"]:
        payload["examples"] = example_keys(lines, reference, kind)
    return payload


def output_paths(slot: Path, arm: str) -> dict[str, Path]:
    if arm == "stock":
        return {"tbl": slot / "out.tbl", "dom": slot / "out.dom"}
    if arm == "tare":
        return {"tbl": slot / "out" / "tables" / "tblout", "dom": slot / "out" / "tables" / "domtblout"}
    return {"tbl": slot / "expert.tbl", "dom": slot / "expert.dom"}


def attach_identity(run: dict, slot: Path, reference: dict[str, list[str]]) -> None:
    paths = output_paths(slot, run["arm"])
    run["tables"] = {
        kind: table_report(paths[kind], reference[kind], kind) for kind in ("tbl", "dom")
    }
    if run["arm"] == "tare":
        decision = parse_decision(slot / "out" / "decision.txt")
        run["decision"] = decision.get("decision")
        run["why"] = decision.get("why")
        phases = decision.get("phases") or {}
        run["phase_names"] = sorted(phases)


def arm_byte_identical(runs: list[dict], arm: str) -> bool:
    rows = [run for run in runs if run["arm"] == arm and "tables" in run]
    if len(rows) != 3:
        return False
    return all(
        run["tables"][kind].get("byte_identical") is True for run in rows for kind in ("tbl", "dom")
    )


def selftest() -> None:
    assert order_for(0, 0) == ["stock", "tare", "expert"]
    assert order_for(0, 1) == ["tare", "expert", "stock"]
    assert order_for(1, 0) == ["tare", "expert", "stock"]
    assert order_for(4, 2) == ["stock", "tare", "expert"]
    pilot, measured = draw_names(list(EXPECTED_POOL))
    assert pilot == list(PILOT_STEMS)
    assert measured == list(MEASURED_STEMS)
    assert set(pilot).isdisjoint(measured)
    one = summarize([1.0, 4.0, 2.0], seed=BOOT_SEED)
    two = summarize([1.0, 4.0, 2.0], seed=BOOT_SEED)
    assert one == two
    assert one["bootstrap_seed"] == BOOT_SEED
    same = ["PF00001.1 - Q1"]
    assert classify(same, same, "tbl")["byte_equal"] is True
    diff = classify(["PF00002.1 - Q1"], same, "tbl")
    assert "missing" in diff["classes"] and "extra" in diff["classes"]
    assert pool_sha(list(EXPECTED_POOL)) == POOL_SHA256
    print("baselines_exact_w12a selftest pass")


def drawcheck() -> None:
    genomes = Path(os.environ["ACTS_GENOMES"])
    info = verify_directory(genomes)
    print(json.dumps(info, indent=2))
    print("baselines_exact_w12a drawcheck pass")


def cpu_model() -> str:
    path = Path("/proc/cpuinfo")
    if not path.is_file():
        return platform.processor()
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()
    return platform.processor()


def execute() -> None:
    stage = os.environ.get("ACTS_STAGE", "pilot")
    if stage not in ("pilot", "measured"):
        raise SystemExit(f"STOP stage {stage}")
    genomes = Path(os.environ["ACTS_GENOMES"])
    scratch = Path(os.environ["ACTS_SCRATCH"])
    cpu = os.environ.get("SLURM_CPUS_PER_TASK", "")
    if cpu != "32":
        raise SystemExit(f"STOP SLURM_CPUS_PER_TASK={cpu!r}; the lock is 32")
    draw = verify_directory(genomes)
    names = [faa_name(stem) for stem in (draw["pilot"] if stage == "pilot" else draw["measured"])]
    for name in names:
        if not (genomes / name).is_file():
            raise SystemExit(f"STOP missing {genomes / name}")
    script = Path(__file__).resolve().parent / "expert_update_hmmscan.sh"
    old_gz = Path(os.environ["ACTS_PFAM_OLD"])
    new_gz = Path(os.environ["ACTS_PFAM_NEW"])
    REPORT.update(
        {
            "status": "running",
            "stage": stage,
            "pilot": stage == "pilot",
            "walls_are_evidence": False,
            "locked_claim": False,
            "protocol": "docs/BASELINES_EXACT_PROTOCOL.md#2026-10-19-w12a",
            "system_name": "TARE",
            "package": "acts",
            "worktree_start": START_COMMIT,
            "git_head": os.environ.get("ACTS_GIT_HEAD") or "",
            "driver_sha256": sha256_file(Path(__file__).resolve()),
            "expert_script_lines": len(script.read_text().splitlines()),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "host": platform.node(),
            "cpu_model": cpu_model(),
            "cpu": int(cpu),
            "nproc": os.cpu_count(),
            "python": sys.version.split()[0],
            "reps": 3,
            "seeds": {
                "pilot_draw": PILOT_SEED,
                "measured_draw": MEASURED_SEED,
                "bootstrap": BOOT_SEED,
            },
            "min_body_lines": MIN_BODY_LINES,
            "draw": draw,
            "exclusions": {
                "headline_exclude_n": len(EXCLUDE_REASONS),
                "headline_draw_n": len(DRAWS),
                "w8_named": W8_NAMED,
                "d2_extra": D2_EXTRA,
            },
            "hmmer_sha256": os.environ.get("ACTS_HMMER_SHA256"),
            "hmmer_tarball": os.environ.get("ACTS_HMMER_TARBALL"),
            "pfam_old": str(old_gz),
            "pfam_new": str(new_gz),
            "timing_boundary": (
                "HMMER build, full-database decompress, full-database hmmpress, "
                "the 38.1 cache fill, and the 38.1 stock table are outside S. "
                "Each timed TARE command is the published CLI, including its prep "
                "hmmpress. Stock times hmmscan only. The expert timer is the shell "
                "script, including its own hmmfetch index, discovery scan, and "
                "per-batch hmmpress. EXPERT_OMIT_Z is untimed and pilot-only."
            ),
            "paper_derived_not_a_measurement": {
                "script_speedup_estimate": 4.6,
                "tare_speedup_estimate": 3.4,
                "ratio_tare_over_script": 3.4 / 4.6,
                "note": "Laptop derivation this run replaces. Not used to compute S.",
            },
            "proteomes": [],
        }
    )
    flush()
    print("hashing Pfam archives", flush=True)
    REPORT["pfam_old_sha256"] = sha256_file(old_gz)
    REPORT["pfam_new_sha256"] = sha256_file(new_gz)
    flush()
    old_txt = scratch / "pfam38.1.hmm"
    new_txt = scratch / "pfam38.2.hmm"
    print("pressing full databases outside the timers", flush=True)
    started = time.perf_counter()
    materialize_hmm(old_gz, old_txt)
    materialize_hmm(new_gz, new_txt)
    REPORT["full_database_press_wall_s"] = time.perf_counter() - started
    version = subprocess_run(["hmmscan", "-h"], ROOT, os.environ.copy())
    REPORT["hmmscan_version_line"] = (version.stdout or "").splitlines()[:2]
    flush()
    env = os.environ.copy()
    env["CPU"] = cpu
    env["HMMSCAN"] = "hmmscan"
    env["HMMFETCH"] = "hmmfetch"
    env["HMMPRESS"] = "hmmpress"
    for genome_index, name in enumerate(names):
        score_genome(
            genome_index,
            name,
            genomes,
            scratch,
            cpu,
            env,
            old_txt,
            new_txt,
            script,
            stage,
        )
    finish(stage)


def score_genome(
    genome_index: int,
    name: str,
    genomes: Path,
    scratch: Path,
    cpu: str,
    env: dict[str, str],
    old_txt: Path,
    new_txt: Path,
    script: Path,
    stage: str,
) -> None:
    gdir = scratch / "g" / name
    queries = gdir / "queries.faa"
    print(f"gunzip {name}", flush=True)
    gunzip_queries(genomes / name, queries)
    cache_fill = gdir / "cache_38.1.sqlite"
    untimed: dict = {}
    if not cache_fill.is_file():
        print(f"untimed cache fill {name}", flush=True)
        untimed["cache_fill"] = timed(
            tare_cmd(old_txt, queries, cache_fill, gdir / "fill", cpu),
            ROOT,
            env,
            allow_exit_1=True,
        )
        untimed["cache_fill"]["decision"] = parse_decision(gdir / "fill" / "decision.txt").get("decision")
    if cache_fill.is_file():
        untimed["cache_bytes"] = cache_bytes(cache_fill)
    old_tbl = gdir / "S381.tbl"
    if not old_tbl.is_file():
        print(f"untimed 38.1 stock {name}", flush=True)
        untimed["stock_38_1"] = timed(
            [
                "hmmscan", "--cut_ga", "--noali", "--cpu", cpu,
                "--tblout", str(old_tbl), "--domtblout", str(gdir / "S381.dom"),
                "-o", "/dev/null", str(old_txt), str(queries),
            ],
            ROOT,
            env,
        )
    runs: list[dict] = []
    power_ok = True
    stopped_early = False
    for replicate in range(3):
        sequence = order_for(genome_index, replicate)
        for arm in sequence:
            slot = gdir / f"r{replicate}" / arm
            slot.mkdir(parents=True, exist_ok=True)
            print(f"time g={genome_index} r={replicate} {arm} {name}", flush=True)
            if arm == "stock":
                result = timed(
                    [
                        "hmmscan", "--cut_ga", "--noali", "--cpu", cpu,
                        "--tblout", str(slot / "out.tbl"),
                        "--domtblout", str(slot / "out.dom"),
                        "-o", "/dev/null", str(new_txt), str(queries),
                    ],
                    ROOT,
                    env,
                )
            elif arm == "tare":
                if not cache_fill.is_file():
                    result = {
                        "argv": [],
                        "returncode": None,
                        "wall_s": None,
                        "skipped": "cache fill did not write a database",
                    }
                else:
                    restore_cache(cache_fill, slot / "cache.sqlite")
                    result = timed(
                        tare_cmd(new_txt, queries, slot / "cache.sqlite", slot / "out", cpu),
                        ROOT,
                        env,
                        allow_exit_1=True,
                    )
            else:
                work = slot / "work"
                run_env = env.copy()
                run_env["WORK"] = str(work)
                result = timed(
                    ["sh", str(script), str(old_txt), str(new_txt), str(old_tbl), str(queries), str(slot / "expert")],
                    ROOT,
                    run_env,
                )
            result["arm"] = arm
            result["replicate"] = replicate
            result["order"] = sequence
            runs.append(result)
            REPORT["proteome_inflight"] = {"genome": name, "runs": runs, "untimed": untimed}
            flush()
            if arm == "stock" and not stopped_early:
                tbl_lines = read_body(slot / "out.tbl") if (slot / "out.tbl").is_file() else []
                dom_lines = read_body(slot / "out.dom") if (slot / "out.dom").is_file() else []
                if len(tbl_lines) < MIN_BODY_LINES or len(dom_lines) < MIN_BODY_LINES:
                    power_ok = False
                    stopped_early = True
                    print(
                        f"INCONCLUSIVE power tbl={len(tbl_lines)} dom={len(dom_lines)} {name}",
                        flush=True,
                    )
                    break
        if stopped_early:
            break
    reference_slot = None
    reference: dict[str, list[str]] | None = None
    for run in runs:
        if run["arm"] == "stock" and run.get("returncode") == 0:
            reference_slot = gdir / f"r{run['replicate']}" / "stock"
            reference = {
                "tbl": read_body(reference_slot / "out.tbl"),
                "dom": read_body(reference_slot / "out.dom"),
            }
            break
    if reference is not None:
        for run in runs:
            if run.get("skipped") or run.get("returncode") is None:
                run["tables"] = {
                    "tbl": {"present": False, "byte_identical": False, "classes": ["missing-file"]},
                    "dom": {"present": False, "byte_identical": False, "classes": ["missing-file"]},
                }
                continue
            attach_identity(run, gdir / f"r{run['replicate']}" / run["arm"], reference)
    stock_runs = [run for run in runs if run["arm"] == "stock" and "tables" in run]
    stock_match = (
        len(stock_runs) == 3
        and all(run["tables"]["tbl"].get("byte_identical") for run in stock_runs)
        and all(run["tables"]["dom"].get("byte_identical") for run in stock_runs)
    )
    walls = {
        arm: [run["wall_s"] for run in runs if run["arm"] == arm and isinstance(run.get("wall_s"), float)]
        for arm in ("stock", "tare", "expert")
    }
    tare_runs = [run for run in runs if run["arm"] == "tare"]
    tare_ship = len(tare_runs) == 3 and all(run.get("decision") == "SHIP" for run in tare_runs)
    complete = all(len(walls[arm]) == 3 for arm in walls) and not stopped_early
    speed_scored = bool(
        complete
        and stock_match
        and power_ok
        and tare_ship
        and all(value > 0 for arm in walls for value in walls[arm])
    )
    genome = {
        "genome": name,
        "stem": name[: -len(SUFFIX)],
        "untimed": untimed,
        "runs": runs,
        "power_ok": power_ok,
        "stopped_for_power": stopped_early,
        "stock_vs_stock_byte_identical": stock_match,
        "tare_ship": tare_ship,
        "tare_byte_identical": arm_byte_identical(runs, "tare") if reference is not None else False,
        "expert_byte_identical": arm_byte_identical(runs, "expert") if reference is not None else False,
        "arms_complete": complete,
        "speed_scored": speed_scored,
        "reference_body_lines": {
            "tbl": len(reference["tbl"]) if reference else 0,
            "dom": len(reference["dom"]) if reference else 0,
        },
    }
    if speed_scored:
        genome["median_wall_s"] = {arm: median(walls[arm]) for arm in walls}
        genome["cv"] = {arm: cv(walls[arm]) for arm in walls}
        genome["cv_above_0_05"] = {
            arm: genome["cv"][arm] is not None and genome["cv"][arm] > 0.05 for arm in walls
        }
        genome["S_g"] = {
            "tare": genome["median_wall_s"]["stock"] / genome["median_wall_s"]["tare"],
            "expert": genome["median_wall_s"]["stock"] / genome["median_wall_s"]["expert"],
        }
        genome["R_g"] = genome["S_g"]["tare"] / genome["S_g"]["expert"]
    if stage == "pilot" and reference is not None and power_ok and not stopped_early:
        genome["negative_control"] = omit_z_control(
            gdir, script, old_txt, new_txt, old_tbl, queries, env, reference
        )
    REPORT["proteomes"].append(genome)
    REPORT.pop("proteome_inflight", None)
    flush()


def omit_z_control(
    gdir: Path,
    script: Path,
    old_txt: Path,
    new_txt: Path,
    old_tbl: Path,
    queries: Path,
    env: dict[str, str],
    reference: dict[str, list[str]],
) -> dict:
    slot = gdir / "neg_omit_z"
    slot.mkdir(parents=True, exist_ok=True)
    run_env = env.copy()
    run_env["WORK"] = str(slot / "work")
    run_env["EXPERT_OMIT_Z"] = "1"
    print("untimed negative control EXPERT_OMIT_Z=1", flush=True)
    result = timed(
        ["sh", str(script), str(old_txt), str(new_txt), str(old_tbl), str(queries), str(slot / "expert")],
        ROOT,
        run_env,
    )
    tables = {
        "tbl": table_report(slot / "expert.tbl", reference["tbl"], "tbl"),
        "dom": table_report(slot / "expert.dom", reference["dom"], "dom"),
    }
    present = bool(tables["tbl"].get("present") and tables["dom"].get("present"))
    differs = present and not (
        tables["tbl"].get("byte_identical") and tables["dom"].get("byte_identical")
    )
    result.update(
        {
            "timed": False,
            "walls_are_evidence": False,
            "tables": tables,
            "differs_from_stock": differs,
            "classes": {kind: tables[kind].get("classes", []) for kind in ("tbl", "dom")},
        }
    )
    return result


def finish(stage: str) -> None:
    proteomes = REPORT["proteomes"]
    REPORT["byte_identity"] = {
        genome["stem"]: {
            "stock_vs_stock": genome.get("stock_vs_stock_byte_identical"),
            "tare": genome.get("tare_byte_identical"),
            "expert": genome.get("expert_byte_identical"),
            "tare_ship": genome.get("tare_ship"),
        }
        for genome in proteomes
        if genome.get("stem")
    }
    if stage == "pilot":
        genome = proteomes[0] if proteomes else {}
        control = genome.get("negative_control") or {}
        if not genome.get("power_ok") or not genome.get("stock_vs_stock_byte_identical"):
            status = "inconclusive"
        elif not control.get("differs_from_stock"):
            status = "control_fail"
        elif not genome.get("arms_complete"):
            status = "inconclusive"
        else:
            status = "pilot_pass"
        REPORT["status"] = status
        REPORT["walls_are_evidence"] = False
        REPORT["locked_claim"] = False
        flush()
        print(f"pilot status {status}", flush=True)
        return
    scored = [genome for genome in proteomes if genome.get("speed_scored")]
    REPORT["genomes_speed_scored"] = len(scored)
    if len(scored) == 5 and len(proteomes) == 5:
        REPORT["status"] = "measured"
        REPORT["locked_claim"] = True
        REPORT["walls_are_evidence"] = True
    else:
        REPORT["status"] = "inconclusive"
        REPORT["locked_claim"] = False
        REPORT["walls_are_evidence"] = False
    if scored:
        REPORT["summary"] = {
            "S_g_tare": summarize([genome["S_g"]["tare"] for genome in scored], seed=BOOT_SEED),
            "S_g_expert": summarize([genome["S_g"]["expert"] for genome in scored], seed=BOOT_SEED),
            "R_g": summarize([genome["R_g"] for genome in scored], seed=BOOT_SEED),
            "bootstrap_note": (
                "Each summary draws its own Random(20261249) stream. "
                "n=10000, linear percentile, indexes via baseline_carc.summarize."
            ),
            "n_scored": len(scored),
            "scored_genomes": [genome["stem"] for genome in scored],
        }
        if len(scored) != 5:
            REPORT["summary"]["not_the_locked_five"] = True
    flush()
    print(f"measured status {REPORT['status']}", flush=True)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "drawcheck":
        drawcheck()
        return
    if os.environ.get("ACTS_CARC") != "1" or not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("refusing: set ACTS_CARC=1 inside a Slurm allocation")
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    try:
        execute()
    except SystemExit as exc:
        if REPORT.get("status") == "running":
            REPORT["status"] = "partial"
            REPORT["error"] = str(exc)
            REPORT["walls_are_evidence"] = False
            flush()
        raise
    except Exception as exc:
        REPORT["status"] = "partial"
        REPORT["error"] = repr(exc)
        REPORT["traceback"] = traceback.format_exc()
        REPORT["walls_are_evidence"] = False
        flush()
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
