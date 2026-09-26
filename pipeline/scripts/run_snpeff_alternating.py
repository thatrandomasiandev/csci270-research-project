#!/usr/bin/env python3
"""Pre-registered alternating SnpEff rerun. Does not write the locked fit JSON."""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from oracle_snpeff_ann import added_by_key, apply_added, run_snpeff, snpeff_cmd
from acts.vcf import bodies_equal, body_lines, is_header, read_maybe_gz, variant_key

PRED = ROOT / "results" / "snpeff_timing_fit.json"
S96 = ROOT / "data" / "vep_chr22" / "HG00096.c1.vcf.gz"
S97 = ROOT / "data" / "vep_chr22" / "HG00097.c1.vcf.gz"
FULL = ROOT / "data" / "vep_chr22" / "subsets" / "HG00099.n52638.vcf"
N1 = ROOT / "data" / "vep_chr22" / "subsets" / "HG00099.n1.vcf"
CACHED_COPY = ROOT / "data" / "vep_chr22" / "cached_work" / "HG00099.vcf"
WORKDIR = ROOT / "data" / "vep_chr22" / "alternating_work"
OUT = ROOT / "results" / "snpeff_alternating.json"
DRIFT_PNG = ROOT / "results" / "snpeff_alternating_drift.png"
N_PAIRS = 10
N1_RUNS = 5
SHELL_RUNS = 5
BOOT_N = 10_000
BOOT_SEED = 20260924


def vcf_parts(path: Path) -> tuple[list[str], list[str]]:
    text = read_maybe_gz(path)
    header = [ln for ln in text.splitlines() if is_header(ln)]
    return header, body_lines(text)


def write_vcf(path: Path, header: list[str], body: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(header + body) + "\n")
    return path


def cached_annotate(
    header: list[str],
    body: list[str],
    cache: dict[str, str],
    tmp: Path,
) -> tuple[str, dict]:
    t0 = time.perf_counter()
    misses = [ln for ln in body if variant_key(ln) not in cache]
    hits_n = len(body) - len(misses)
    snpeff_s = 0.0
    if misses:
        tmp.mkdir(parents=True, exist_ok=True)
        miss_vcf = tmp / "miss.vcf"
        write_vcf(miss_vcf, header, misses)
        out, _err, wall = run_snpeff(miss_vcf)
        snpeff_s = wall
        cache.update(added_by_key(out))
    rebuilt = []
    holes = 0
    for ln in body:
        added = cache.get(variant_key(ln))
        if added is None:
            holes += 1
            rebuilt.append(ln)
        else:
            rebuilt.append(apply_added(ln, added))
    wall = time.perf_counter() - t0
    text = "\n".join(header + rebuilt) + "\n"
    stats = {
        "n_records": len(body),
        "n_hits": hits_n,
        "n_misses": len(misses),
        "n_cache_holes": holes,
        "snpeff_miss_s": snpeff_s,
        "wall_s": wall,
    }
    return text, stats


def machine_snapshot(label: str) -> dict:
    def run(argv: list[str]) -> str:
        return subprocess.check_output(argv, text=True).rstrip()

    mem = subprocess.check_output(
        ["sh", "-c", "memory_pressure | tail -1"], text=True
    ).rstrip()
    return {
        "label": label,
        "iso_utc": datetime.now(timezone.utc).isoformat(),
        "iso_local": datetime.now().isoformat(),
        "uptime": run(["uptime"]),
        "pmset_batt": run(["pmset", "-g", "batt"]),
        "pmset_therm": run(["pmset", "-g", "therm"]),
        "memory_pressure_tail": mem,
    }


def bootstrap_median_ci(values: list[float], *, n: int, seed: int) -> tuple[float, float, float]:
    import random

    rng = random.Random(seed)
    k = len(values)
    meds = []
    for _ in range(n):
        sample = [values[rng.randrange(k)] for _ in range(k)]
        meds.append(statistics.median(sample))
    meds.sort()
    lo_i = int(0.025 * (n - 1))
    hi_i = int(0.975 * (n - 1))
    return statistics.median(values), meds[lo_i], meds[hi_i]


def plot_drift(pairs: list[dict], dest: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    xs_s, ys_s, xs_c, ys_c = [], [], [], []
    for p in pairs:
        xs_s.append(p["stock_run_index"])
        ys_s.append(p["stock_s"])
        xs_c.append(p["cached_run_index"])
        ys_c.append(p["cached_s"])
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    ax.plot(xs_s, ys_s, "o-", color="#4A5568", label="stock")
    ax.plot(xs_c, ys_c, "s-", color="#2B6CB0", label="cached")
    ax.set_xlabel("timed-run index (warm-up excluded)")
    ax.set_ylabel("wall (s)")
    ax.set_title("Alternating session: wall vs run index")
    ax.legend()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, dpi=160, bbox_inches="tight")
    plt.close(fig)


def shell_time_java(vcf: Path, log: Path) -> dict:
    cmd = snpeff_cmd(vcf)
    out = WORKDIR / "shell_out.vcf"
    # /usr/bin/time -p prints real/user/sys on stderr.
    t0 = time.perf_counter()
    proc = subprocess.run(
        ["/usr/bin/time", "-p", *cmd],
        check=True,
        stdout=out.open("w"),
        stderr=subprocess.PIPE,
        text=True,
    )
    parent_s = time.perf_counter() - t0
    real = None
    user = None
    sys_s = None
    for ln in proc.stderr.splitlines():
        parts = ln.split()
        if len(parts) == 2 and parts[0] == "real":
            real = float(parts[1])
        elif len(parts) == 2 and parts[0] == "user":
            user = float(parts[1])
        elif len(parts) == 2 and parts[0] == "sys":
            sys_s = float(parts[1])
    log.write_text(proc.stderr)
    return {
        "time_real_s": real,
        "time_user_s": user,
        "time_sys_s": sys_s,
        "python_parent_s": parent_s,
        "stderr": proc.stderr,
    }


def main() -> int:
    for p in (PRED, S96, S97, FULL, N1):
        if not p.is_file():
            print(f"INCOMPLETE: missing {p}", file=sys.stderr)
            return 2
    pred = json.loads(PRED.read_text())
    b = pred["fit"]["b_s_per_record"]
    w = pred["wrapper_cat"]["mean_s"]
    n_full = pred["n_full"]
    miss_n = pred["miss_n"]

    same_bytes = FULL.read_bytes() == CACHED_COPY.read_bytes() if CACHED_COPY.is_file() else None
    header, body = vcf_parts(FULL)
    if len(body) != n_full:
        print(f"INCOMPLETE: full body {len(body)} != locked N {n_full}", file=sys.stderr)
        return 2

    before = machine_snapshot("before")
    print(json.dumps(before, indent=2), flush=True)

    WORKDIR.mkdir(parents=True, exist_ok=True)
    cache: dict[str, str] = {}
    populate = {}
    for name, src in (("HG00096", S96), ("HG00097", S97)):
        h, bdy = vcf_parts(src)
        _t, st = cached_annotate(h, bdy, cache, WORKDIR / f"pop_{name}")
        populate[name] = st
        print(f"populate {name} hits={st['n_hits']} misses={st['n_misses']}", flush=True)
    cache_prev = dict(cache)

    stock_ref, _err, warm_stock_s = run_snpeff(FULL)
    print(f"warmup stock wall_s={warm_stock_s:.4f} (discarded)", flush=True)
    rebuilt, wst = cached_annotate(header, body, dict(cache_prev), WORKDIR / "warmup_cached")
    print(f"warmup cached wall_s={wst['wall_s']:.4f} (discarded)", flush=True)
    if not bodies_equal(rebuilt, stock_ref) or wst["n_cache_holes"]:
        print("MATCH failed on warm-up cached path; not timing.", flush=True)
        OUT.write_text(
            json.dumps({"bodies_equal_warmup": False, "decision": "STOP_MATCH"}, indent=2) + "\n"
        )
        return 1

    pairs: list[dict] = []
    timed_index = 0
    pending_stock: dict | None = None
    pending_cached: dict | None = None

    def flush_pair(pair_i: int) -> bool:
        nonlocal pending_stock, pending_cached
        assert pending_stock is not None and pending_cached is not None
        if not bodies_equal(pending_cached["text"], pending_stock["text"]):
            return False
        if not bodies_equal(pending_cached["text"], stock_ref):
            return False
        r = pending_stock["wall_s"] / pending_cached["wall_s"]
        pairs.append(
            {
                "pair": pair_i,
                "order": "AB" if pair_i % 2 == 1 else "BA",
                "stock_s": pending_stock["wall_s"],
                "cached_s": pending_cached["wall_s"],
                "r": r,
                "stock_iso_local": pending_stock["iso_local"],
                "cached_iso_local": pending_cached["iso_local"],
                "stock_run_index": pending_stock["run_index"],
                "cached_run_index": pending_cached["run_index"],
                "bodies_equal_pair": True,
                "bodies_equal_vs_warmup_stock": True,
            }
        )
        print(
            f"pair {pair_i}: stock={pending_stock['wall_s']:.4f} "
            f"cached={pending_cached['wall_s']:.4f} r={r:.4f}",
            flush=True,
        )
        pending_stock = None
        pending_cached = None
        return True

    for pair_i in range(1, N_PAIRS + 1):
        abba = "AB" if pair_i % 2 == 1 else "BA"
        seq = ["stock", "cached"] if abba == "AB" else ["cached", "stock"]
        for j, kind in enumerate(seq):
            timed_index += 1
            iso = datetime.now().isoformat()
            if kind == "stock":
                text, _e, wall = run_snpeff(FULL)
                if not bodies_equal(text, stock_ref):
                    print("stock body drifted vs warm-up; STOP.", flush=True)
                    OUT.write_text(
                        json.dumps(
                            {"decision": "STOP_MATCH", "why": "stock body drift", "pairs": pairs},
                            indent=2,
                        )
                        + "\n"
                    )
                    return 1
                pending_stock = {
                    "text": text,
                    "wall_s": wall,
                    "iso_local": iso,
                    "run_index": timed_index,
                    "order_in_pair": "A" if j == 0 else "B",
                }
                print(f"  timed #{timed_index} stock wall_s={wall:.4f}", flush=True)
            else:
                text, st = cached_annotate(
                    header, body, dict(cache_prev), WORKDIR / f"pair{pair_i}_cached"
                )
                if st["n_cache_holes"] or not bodies_equal(text, stock_ref):
                    print("MATCH failed on cached path; not timing further.", flush=True)
                    OUT.write_text(
                        json.dumps(
                            {
                                "decision": "STOP_MATCH",
                                "why": "cached bodies_equal failed",
                                "pairs": pairs,
                            },
                            indent=2,
                        )
                        + "\n"
                    )
                    return 1
                pending_cached = {
                    "text": text,
                    "wall_s": st["wall_s"],
                    "iso_local": iso,
                    "run_index": timed_index,
                    "order_in_pair": "A" if j == 0 else "B",
                }
                print(f"  timed #{timed_index} cached wall_s={st['wall_s']:.4f}", flush=True)
        if not flush_pair(pair_i):
            print("MATCH failed on pair; not timing further.", flush=True)
            OUT.write_text(
                json.dumps({"decision": "STOP_MATCH", "why": "pair MATCH", "pairs": pairs}, indent=2)
                + "\n"
            )
            return 1

    ratios = [p["r"] for p in pairs]
    median_r, ci_lo, ci_hi = bootstrap_median_ci(ratios, n=BOOT_N, seed=BOOT_SEED)
    if ci_lo > 1.0:
        decision = "speedup_stands"
    elif ci_lo <= 1.0 <= ci_hi:
        decision = "speedup_not_established"
    else:
        decision = "ci_entirely_below_1"

    n1_times = []
    for i in range(N1_RUNS):
        _o, _e, wall = run_snpeff(N1)
        n1_times.append(wall)
        print(f"a_now n=1 run={i+1} wall_s={wall:.4f}", flush=True)
    a_now = statistics.fmean(n1_times)
    r_from_a = (a_now + b * n_full) / (a_now + b * miss_n + w)

    py_stock = [p["stock_s"] for p in pairs]
    shell_runs = []
    for i in range(SHELL_RUNS):
        rec = shell_time_java(FULL, WORKDIR / f"time_shell_{i}.err")
        shell_runs.append(rec)
        print(f"shell /usr/bin/time run={i+1} real_s={rec['time_real_s']}", flush=True)

    after = machine_snapshot("after")
    print(json.dumps(after, indent=2), flush=True)

    plot_drift(pairs, DRIFT_PNG)

    shell_reals = [r["time_real_s"] for r in shell_runs if r["time_real_s"] is not None]
    payload = {
        "tool": "SnpEff 5.4c GRCh38.86",
        "flags": ["-noStats", "-noLog"],
        "prediction_commit": "701d24b",
        "same_bytes_full_vs_cached_work": same_bytes,
        "input": str(FULL),
        "machine_before": before,
        "machine_after": after,
        "populate": populate,
        "warmup": {
            "stock_s": warm_stock_s,
            "cached_s": wst["wall_s"],
            "bodies_equal": True,
        },
        "pairs": pairs,
        "median_r": median_r,
        "bootstrap": {
            "n": BOOT_N,
            "seed": BOOT_SEED,
            "ci95_lo": ci_lo,
            "ci95_hi": ci_hi,
        },
        "decision": decision,
        "decision_rule": "ci_lo>1 speedup_stands; ci includes 1 speedup_not_established",
        "a_now": {
            "n": 1,
            "runs_s": n1_times,
            "mean_s": a_now,
            "stdev_s": statistics.stdev(n1_times),
        },
        "locked": {
            "b_s_per_record": b,
            "w_s": w,
            "N": n_full,
            "miss_n": miss_n,
        },
        "r_from_a_now": r_from_a,
        "r_from_a_now_minus_median_r": r_from_a - median_r,
        "python_stock_full": {
            "n": len(py_stock),
            "runs_s": py_stock,
            "mean_s": statistics.fmean(py_stock),
            "stdev_s": statistics.stdev(py_stock),
        },
        "shell_usr_bin_time": {
            "n": len(shell_reals),
            "runs_s": shell_reals,
            "mean_s": statistics.fmean(shell_reals) if shell_reals else None,
            "stdev_s": statistics.stdev(shell_reals) if len(shell_reals) > 1 else None,
            "raw": shell_runs,
        },
        "drift_plot": str(DRIFT_PNG),
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
