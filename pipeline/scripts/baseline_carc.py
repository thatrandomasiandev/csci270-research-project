#!/usr/bin/env python3
"""CARC timing for stock, TARE, and the expert script.

Refuses to run unless ACTS_CARC=1 and SLURM_JOB_ID are set. Laptop
self-check: ``python3 scripts/baseline_carc.py selftest``.
"""
from __future__ import annotations

import gzip
import json
import math
import os
import platform
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve().parent / "expert_update_hmmscan.sh"
BOOT_SEED = 20261139
BOOT_N = 10000
PAPER_RATIO = 3.4 / 4.6
EXCLUDE = {
    "GCF_002853805.1_protein.faa.gz",
    "GCF_002090355.1_protein.faa.gz",
    "GCF_013315695.1_protein.faa.gz",
    "GCF_049201905.1_protein.faa.gz",
    "GCF_059719525.1_protein.faa.gz",
    "GCF_016806025.1_protein.faa.gz",
    "GCF_017165095.1_protein.faa.gz",
    "GCF_001515725.1_protein.faa.gz",
    "GCF_001513615.1_protein.faa.gz",
    "GCF_024585005.1_protein.faa.gz",
}
PILOT_GENOMES = ["GCF_041235215.1_protein.faa.gz"]
MEASURED_GENOMES = [
    "GCF_002302335.1_protein.faa.gz",
    "GCF_016904475.1_protein.faa.gz",
    "GCF_025259645.1_protein.faa.gz",
    "GCF_030347155.1_protein.faa.gz",
    "GCF_977065495.1_protein.faa.gz",
]
ARMS = ("stock", "tare", "expert")


def median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        raise ValueError("empty")
    k = (len(sorted_values) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return float(sorted_values[int(k)])
    return sorted_values[lo] * (hi - k) + sorted_values[hi] * (k - lo)


def summarize(values: list[float], seed: int = BOOT_SEED) -> dict:
    if any(v <= 0 for v in values):
        raise SystemExit(f"STOP non-positive wall {values}")
    logs = [math.log(v) for v in values]
    rng = random.Random(seed)
    boots = []
    n = len(values)
    for _ in range(BOOT_N):
        draw = [values[rng.randrange(n)] for _ in range(n)]
        boots.append(median(draw))
    boots.sort()
    return {
        "n": n,
        "values": values,
        "median": median(values),
        "geometric_mean": math.exp(sum(logs) / len(logs)),
        "min": min(values),
        "max": max(values),
        "bootstrap_n": BOOT_N,
        "bootstrap_seed": seed,
        "percentile": "linear",
        "ci95": [percentile(boots, 0.025), percentile(boots, 0.975)],
    }


def order_for(genome: int, replicate: int) -> list[str]:
    shift = (genome + replicate) % 3
    return list(ARMS[shift:] + ARMS[:shift])


def selftest() -> None:
    assert order_for(0, 0) == ["stock", "tare", "expert"]
    assert order_for(0, 1) == ["tare", "expert", "stock"]
    assert order_for(1, 0) == ["tare", "expert", "stock"]
    assert order_for(4, 2) == ["stock", "tare", "expert"]
    assert order_for(2, 0) == ["expert", "stock", "tare"]
    assert median([10.0, 30.0, 20.0]) == 20.0
    one = summarize([1.0, 4.0])
    two = summarize([1.0, 4.0])
    assert one == two
    assert abs(one["geometric_mean"] - 2.0) < 1e-12
    print("baseline_carc selftest pass")


def require_draw(genomes: Path) -> None:
    pool = sorted(p.name for p in genomes.glob("*.faa.gz") if p.name not in EXCLUDE)
    # EXCLUDE already drops the laptop pilot proteome. The remaining pool is
    # the CARC pool only if the directory matches the laptop listing.
    pilot = random.Random(20261131).sample(pool, 1)
    measured = sorted(random.Random(20261132).sample(pool, 5))
    if pilot != PILOT_GENOMES or measured != MEASURED_GENOMES:
        raise SystemExit(
            "STOP genome draw disagrees with the locked names "
            f"pilot={pilot} measured={measured}"
        )


def gunzip_queries(src: Path, dest: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 0:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(src, "rt") as inp, dest.open("w") as out:
        shutil.copyfileobj(inp, out)


def timed(cmd: list[str], cwd: Path, env: dict[str, str], *, allow_exit_1: bool = False) -> dict:
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    wall = time.perf_counter() - started
    ok = proc.returncode == 0 or (allow_exit_1 and proc.returncode == 1)
    if not ok:
        raise SystemExit(f"STOP command exit {proc.returncode}: {' '.join(cmd[:8])}")
    return {"argv": cmd, "returncode": proc.returncode, "wall_s": wall}


def materialize_hmm(src: Path, dest: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 0 and Path(str(dest) + ".h3m").is_file():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.is_file() or dest.stat().st_size == 0:
        with gzip.open(src, "rt") as inp, dest.open("w") as out:
            shutil.copyfileobj(inp, out)
    subprocess.run(["hmmpress", "-f", str(dest)], check=True)


def tare_cmd(reference: Path, queries: Path, cache: Path, out: Path, cpu: str) -> list[str]:
    return [
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
        "hmmscan", "--cut_ga", "--noali", "--cpu", cpu,
        "--tblout", "{output:tblout}",
        "--domtblout", "{output:domtblout}",
        "-o", "/dev/null",
        "{reference}", "{input}",
    ]


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
        return
    if os.environ.get("ACTS_CARC") != "1" or not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("refusing: set ACTS_CARC=1 inside a Slurm allocation")
    stage = os.environ.get("ACTS_STAGE", "measured")
    if stage not in ("pilot", "measured"):
        raise SystemExit(f"STOP stage {stage}")
    genomes = Path(os.environ["ACTS_GENOMES"])
    require_draw(genomes)
    names = PILOT_GENOMES if stage == "pilot" else MEASURED_GENOMES
    reps = 1 if stage == "pilot" else 3
    scratch = Path(os.environ["ACTS_SCRATCH"])
    out_path = Path(os.environ["ACTS_OUT"])
    cpu = os.environ.get("SLURM_CPUS_PER_TASK", "32")
    old_gz = Path(os.environ["ACTS_PFAM_OLD"])
    new_gz = Path(os.environ["ACTS_PFAM_NEW"])
    old_txt = scratch / "pfam38.1.hmm"
    new_txt = scratch / "pfam38.2.hmm"
    print("pressing full databases outside the timers", flush=True)
    materialize_hmm(old_gz, old_txt)
    materialize_hmm(new_gz, new_txt)
    env = os.environ.copy()
    env["CPU"] = cpu
    env["HMMSCAN"] = "hmmscan"
    env["HMMFETCH"] = "hmmfetch"
    env["HMMPRESS"] = "hmmpress"
    report: dict = {
        "stage": stage,
        "pilot": stage == "pilot",
        "walls_are_evidence": stage == "measured",
        "protocol": "docs/BASELINES_EXACT_PROTOCOL.md",
        "git_head": os.environ.get("ACTS_GIT_HEAD") or "",
        "slurm_job_id": os.environ["SLURM_JOB_ID"],
        "host": platform.node(),
        "cpu": int(cpu),
        "reps": reps,
        "hmmer_sha256": os.environ.get("ACTS_HMMER_SHA256"),
        "timing_boundary": (
            "Full-database decompress and hmmpress are outside every timer. "
            "The 38.1 cache fill and the 38.1 stock table the expert script reads "
            "are outside the timers. Each timed TARE command is the published CLI, "
            "including its own prep hmmpress. Stock times hmmscan only. "
            "The expert timer is the shell script only."
        ),
        "paper_derived": {
            "check_audit_fraction_of_stock": 0.076,
            "script_speedup": 4.6,
            "tare_speedup": 3.4,
            "ratio_tare_over_script": PAPER_RATIO,
            "note": "Laptop derivation from costpass_measured.json proteome 0. Not a CARC measurement.",
        },
        "proteomes": [],
    }
    for g, name in enumerate(names):
        gdir = scratch / "g" / name
        queries = gdir / "queries.faa"
        gunzip_queries(genomes / name, queries)
        cache_fill = gdir / "cache_38.1.sqlite"
        if not cache_fill.is_file():
            print(f"untimed cache fill {name}", flush=True)
            timed(tare_cmd(old_txt, queries, cache_fill, gdir / "fill", cpu), ROOT, env, allow_exit_1=True)
        old_tbl = gdir / "S381.tbl"
        if not old_tbl.is_file():
            print(f"untimed 38.1 stock {name}", flush=True)
            timed(
                [
                    "hmmscan", "--cut_ga", "--noali", "--cpu", cpu,
                    "--tblout", str(old_tbl), "--domtblout", str(gdir / "S381.dom"),
                    "-o", "/dev/null", str(old_txt), str(queries),
                ],
                ROOT, env,
            )
        runs = []
        for i in range(reps):
            sequence = order_for(g, i)
            for arm in sequence:
                slot = gdir / f"r{i}" / arm
                slot.mkdir(parents=True, exist_ok=True)
                print(f"time g={g} r={i} {arm} {name}", flush=True)
                if arm == "stock":
                    result = timed(
                        [
                            "hmmscan", "--cut_ga", "--noali", "--cpu", cpu,
                            "--tblout", str(slot / "out.tbl"),
                            "--domtblout", str(slot / "out.dom"),
                            "-o", "/dev/null", str(new_txt), str(queries),
                        ],
                        ROOT, env,
                    )
                elif arm == "tare":
                    cache = slot / "cache.sqlite"
                    shutil.copy2(cache_fill, cache)
                    result = timed(tare_cmd(new_txt, queries, cache, slot / "out", cpu), ROOT, env, allow_exit_1=True)
                else:
                    work = slot / "work"
                    run_env = env.copy()
                    run_env["WORK"] = str(work)
                    result = timed(
                        [
                            str(SCRIPT), str(old_txt), str(new_txt), str(old_tbl),
                            str(queries), str(slot / "expert"),
                        ],
                        ROOT, run_env,
                    )
                result["arm"] = arm
                result["replicate"] = i
                result["order"] = sequence
                runs.append(result)
                report["proteomes"] = report["proteomes"]  # keep the file current
                write_report(out_path, report | {"proteomes_partial": report["proteomes"] + [{"genome": name, "runs": runs}]})
        walls = {
            arm: [row["wall_s"] for row in runs if row["arm"] == arm]
            for arm in ARMS
        }
        sg_tare = median(walls["stock"]) / median(walls["tare"])
        sg_expert = median(walls["stock"]) / median(walls["expert"])
        report["proteomes"].append({
            "genome": name,
            "runs": runs,
            "median_wall_s": {arm: median(walls[arm]) for arm in ARMS},
            "S_g": {"tare": sg_tare, "expert": sg_expert},
            "R_g": sg_tare / sg_expert,
        })
        write_report(out_path, report)
    if stage == "measured":
        sg_tare_v = [row["S_g"]["tare"] for row in report["proteomes"]]
        sg_expert_v = [row["S_g"]["expert"] for row in report["proteomes"]]
        ratio_v = [row["R_g"] for row in report["proteomes"]]
        report["summary"] = {
            "S_g_tare": summarize(sg_tare_v),
            "S_g_expert": summarize(sg_expert_v),
            "R_g": summarize(ratio_v),
        }
        write_report(out_path, report)
    print(f"wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
