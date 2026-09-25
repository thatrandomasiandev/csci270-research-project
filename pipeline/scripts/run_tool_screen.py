#!/usr/bin/env python3
"""Stock a+b screen. No cache. Does not edit snpeff_timing_fit.json."""

from __future__ import annotations

import json
import os
import random
import resource
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.vcf import body_lines, is_header, read_maybe_gz

SEED = 20260925
SIZES = (1, 1000, 5000, 20000)
RUNS = 3
WORKDIR = Path("/tmp/acts_tool_screen")
OUT = ROOT / "results" / "tool_screen.json"
S99 = ROOT / "data" / "vep_chr22" / "HG00099.c1.vcf.gz"
SNPEFF_JAR = ROOT / "tools" / "snpEff" / "snpEff.jar"
SNPEFF_DATA = ROOT / "tools" / "snpEff" / "data"
PY_ROOTS = (
    Path("/Users/joshuaterranova/Desktop/Coding Projects"),
    Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS"),
)
PRUNE = {".venv", "venv", "node_modules", "__pycache__", "site-packages", ".git", "dist", "build"}


def children_cpu_s() -> float:
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    return float(ru.ru_utime) + float(ru.ru_stime)


def uptime_line() -> str:
    return subprocess.check_output(["uptime"], text=True).rstrip()


def parse_load(uptime: str) -> list[float] | None:
    key = "load average:" if "load average:" in uptime else "load averages:"
    if key not in uptime:
        return None
    try:
        return [float(x) for x in uptime.split(key, 1)[1].replace(",", " ").split()[:3]]
    except ValueError:
        return None


def fit_ab(ns: list[int], ts: list[float]) -> tuple[float, float]:
    n_bar = statistics.fmean(ns)
    t_bar = statistics.fmean(ts)
    var_n = sum((n - n_bar) ** 2 for n in ns)
    if var_n == 0:
        return t_bar, 0.0
    cov = sum((n - n_bar) * (t - t_bar) for n, t in zip(ns, ts))
    b = cov / var_n
    return t_bar - b * n_bar, b


def ceiling(a: float, b: float, n: int, m: float) -> float | None:
    den = a + b * m * n
    if den <= 0:
        return None
    return (a + b * n) / den


def pause_google_drive() -> dict:
    before = subprocess.check_output(["pgrep", "-lf", "Google Drive"], text=True).rstrip()
    subprocess.run(["osascript", "-e", 'tell application "Google Drive" to quit'], check=False)
    time.sleep(2)
    after = subprocess.run(["pgrep", "-lf", "Google Drive"], capture_output=True, text=True)
    return {
        "before": before,
        "quit_returncode": after.returncode,
        "after": after.stdout.rstrip(),
    }


def list_py_files() -> list[Path]:
    out: list[Path] = []
    for root in PY_ROOTS:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in PRUNE]
            for name in filenames:
                if name.endswith(".py"):
                    out.append(Path(dirpath) / name)
    out.sort()
    return out


def vcf_parts(path: Path) -> tuple[list[str], list[str]]:
    text = read_maybe_gz(path)
    header = [ln for ln in text.splitlines() if is_header(ln)]
    return header, body_lines(text)


def write_vcf(path: Path, header: list[str], body: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(header + body) + "\n")


def time_cmd(argv: list[str], *, cwd: Path | None = None) -> dict:
    up = uptime_line()
    cpu0 = children_cpu_s()
    t0 = time.perf_counter()
    proc = subprocess.run(
        argv,
        check=False,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wall = time.perf_counter() - t0
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"cmd failed rc={proc.returncode}: {argv[:6]}…\n{proc.stderr[-800:]}"
        )
    return {
        "wall_s": wall,
        "cpu_s": children_cpu_s() - cpu0,
        "uptime": up,
        "load": parse_load(up),
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
    }


def measure_sizes(n_full: int, run_n) -> list[dict]:
    sizes = [n for n in SIZES if n < n_full] + [n_full]
    raw = []
    for n in sizes:
        runs = []
        for i in range(RUNS):
            rec = run_n(n)
            rec["run"] = i + 1
            runs.append(rec)
            print(
                f"  n={n} run={i+1} wall_s={rec['wall_s']:.4f} cpu_s={rec['cpu_s']:.4f} "
                f"load={rec['load']}",
                flush=True,
            )
        walls = [r["wall_s"] for r in runs]
        raw.append(
            {
                "n": n,
                "runs": runs,
                "mean_s": statistics.fmean(walls),
                "stdev_s": statistics.stdev(walls) if len(walls) > 1 else 0.0,
                "mean_cpu_s": statistics.fmean(r["cpu_s"] for r in runs),
            }
        )
    return raw


def summarize(name: str, raw: list[dict], extra: dict) -> dict:
    ns = [row["n"] for row in raw]
    ts = [row["mean_s"] for row in raw]
    a, b = fit_ab(ns, ts)
    n = ns[-1]
    c20 = ceiling(a, b, n, 0.2)
    c0 = ceiling(a, b, n, 0.0)
    advances = bool(a > 0 and b > 0 and c20 is not None and c20 >= 3.0)
    out = {
        "tool": name,
        "N": n,
        "a_s": a,
        "b_s_per_record": b,
        "ceiling_m0.2": c20,
        "ceiling_m0": c0,
        "advances": advances,
        "advance_rule": "ceiling(0.2) >= 3.0 and a>0 and b>0",
        "raw": raw,
        **extra,
    }
    return out


def run_snpeff_heavy() -> dict:
    header, body = vcf_parts(S99)
    n_full = len(body)
    rng = random.Random(SEED)
    dest_dir = WORKDIR / "snpeff"
    dest_dir.mkdir(parents=True, exist_ok=True)
    subsets: dict[int, Path] = {}
    for n in [x for x in SIZES if x < n_full] + [n_full]:
        idx = rng.sample(range(n_full), n)
        idx.sort()
        dest = dest_dir / f"HG00099.rand{n}.vcf"
        write_vcf(dest, header, [body[i] for i in idx])
        subsets[n] = dest

    def run_n(n: int) -> dict:
        cwd = dest_dir / f"cwd_{n}_{time.time_ns()}"
        cwd.mkdir(parents=True, exist_ok=True)
        return time_cmd(
            [
                "java",
                "-Xmx4g",
                "-jar",
                str(SNPEFF_JAR),
                "-dataDir",
                str(SNPEFF_DATA),
                "-ud",
                "20000",
                "GRCh38.86",
                str(subsets[n]),
            ],
            cwd=cwd,
        )

    print("SnpEff heavier", flush=True)
    raw = measure_sizes(n_full, run_n)
    return summarize(
        "SnpEff 5.4c GRCh38.86 heavier (stats on, -ud 20000)",
        raw,
        {
            "flags": ["-ud", "20000"],
            "stats": True,
            "input": str(S99),
            "subset_seed": SEED,
        },
    )


def run_ruff() -> dict:
    files = list_py_files()
    n_full = len(files)
    rng = random.Random(SEED)
    order = list(range(n_full))
    rng.shuffle(order)
    dest_root = WORKDIR / "ruff"
    dest_root.mkdir(parents=True, exist_ok=True)

    def farm(n: int) -> Path:
        d = dest_root / f"n{n}"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        for i, src_i in enumerate(order[:n]):
            src = files[src_i]
            dest = d / f"{i:05d}_{src.name}"
            dest.symlink_to(src)
        return d

    farms = {}
    for n in [x for x in SIZES if x < n_full] + [n_full]:
        farms[n] = farm(n)

    def run_n(n: int) -> dict:
        return time_cmd(["ruff", "check", "--no-cache", str(farms[n])])

    print(f"ruff N={n_full}", flush=True)
    raw = measure_sizes(n_full, run_n)
    return summarize(
        "ruff check --no-cache 0.8.4",
        raw,
        {
            "flags": ["check", "--no-cache"],
            "n_files_listed": n_full,
            "roots": [str(p) for p in PY_ROOTS],
            "subset_seed": SEED,
        },
    )


def main() -> int:
    if not S99.is_file() or not SNPEFF_JAR.is_file():
        print("INCOMPLETE: missing SnpEff or HG00099", file=sys.stderr)
        return 2
    WORKDIR.mkdir(parents=True, exist_ok=True)
    drive = pause_google_drive()
    before = {
        "iso_utc": datetime.now(timezone.utc).isoformat(),
        "iso_local": datetime.now().isoformat(),
        "uptime": uptime_line(),
        "load": parse_load(uptime_line()),
        "google_drive": drive,
    }
    print(json.dumps(before, indent=2), flush=True)

    tools = []
    tools.append(
        {
            "tool": "VEP offline chr22",
            "skipped": True,
            "why": "vep not on PATH; no ~/.vep cache; full human cache not downloaded",
            "advances": False,
        }
    )
    tools.append(
        {
            "tool": "SnpSift dbNSFP",
            "skipped": True,
            "why": "dbNSFP TSV not on disk; only make_dbNSFP.sh; not fetched",
            "advances": False,
        }
    )
    tools.append(run_snpeff_heavy())
    tools.append(run_ruff())

    after = {
        "iso_utc": datetime.now(timezone.utc).isoformat(),
        "iso_local": datetime.now().isoformat(),
        "uptime": uptime_line(),
        "load": parse_load(uptime_line()),
    }
    payload = {
        "protocol": "pipeline/docs/TOOL_SCREEN.md",
        "seed": SEED,
        "runs_per_size": RUNS,
        "sizes": list(SIZES),
        "machine_before": before,
        "machine_after": after,
        "tools": tools,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    print(f"wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
