#!/usr/bin/env python3
"""CARC alternating SnpEff rerun. Does not write the locked fit or Mac JSON."""

from __future__ import annotations

import json
import os
import resource
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("ACTS_PIPELINE_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT))

from acts.snpeff_ann import added_by_key, apply_added, run_snpeff
from acts.vcf import bodies_equal, body_lines, is_header, read_maybe_gz, variant_key

PRED = ROOT / "results" / "snpeff_timing_fit.json"
MAC_JSON = Path(os.environ.get("ACTS_MAC_JSON", ROOT / "results" / "snpeff_alternating.json"))
S96 = ROOT / "data" / "vep_chr22" / "HG00096.c1.vcf.gz"
S97 = ROOT / "data" / "vep_chr22" / "HG00097.c1.vcf.gz"
FULL = ROOT / "data" / "vep_chr22" / "subsets" / "HG00099.n52638.vcf"
N1 = ROOT / "data" / "vep_chr22" / "subsets" / "HG00099.n1.vcf"
WORKDIR = Path(os.environ.get("ACTS_ALT_WORK", ROOT / "data" / "vep_chr22" / "alternating_work_carc"))
OUT = Path(os.environ.get("ACTS_ALT_OUT", ROOT / "results" / "snpeff_alternating_carc.json"))
N_PAIRS = 10
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


def children_cpu_s() -> float:
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    return float(ru.ru_utime) + float(ru.ru_stime)


def run_snpeff_timed(vcf: Path) -> tuple[str, str, float, float]:
    cpu0 = children_cpu_s()
    text, err, wall = run_snpeff(vcf)
    return text, err, wall, children_cpu_s() - cpu0


def cached_annotate(
    header: list[str],
    body: list[str],
    cache: dict[str, str],
    tmp: Path,
) -> tuple[str, dict]:
    t0 = time.perf_counter()
    cpu0 = children_cpu_s()
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
        "cpu_s": children_cpu_s() - cpu0,
    }
    return text, stats


def _cmd(argv: list[str]) -> str:
    try:
        return subprocess.check_output(argv, text=True, stderr=subprocess.STDOUT).rstrip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"ERR: {exc}"


def uptime_line() -> str:
    return _cmd(["uptime"])


def parse_load(uptime: str) -> list[float] | None:
    key = "load average:"
    if key not in uptime:
        key = "load averages:"
    if key not in uptime:
        return None
    tail = uptime.split(key, 1)[1].replace(",", " ")
    try:
        return [float(x) for x in tail.split()[:3]]
    except ValueError:
        return None


def machine_snapshot(label: str) -> dict:
    lscpu = _cmd(["lscpu"])
    model = ""
    for ln in lscpu.splitlines():
        if ln.lower().startswith("model name"):
            model = ln.split(":", 1)[-1].strip()
            break
    return {
        "label": label,
        "iso_utc": datetime.now(timezone.utc).isoformat(),
        "iso_local": datetime.now().isoformat(),
        "hostname": _cmd(["hostname"]),
        "uptime": uptime_line(),
        "load": parse_load(uptime_line()),
        "java_version": _cmd(["java", "-version"]),
        "cpu_model": model,
        "lscpu": lscpu,
        "nproc": _cmd(["nproc"]),
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


def mac_side_by_side(path: Path) -> dict | None:
    if not path.is_file():
        return None
    mac = json.loads(path.read_text())
    before = mac.get("machine_before") or {}
    after = mac.get("machine_after") or {}
    a_now = mac.get("a_now") or {}
    boot = mac.get("bootstrap") or {}
    return {
        "source": str(path),
        "protocol_commit": "ddf0807",
        "median_r": mac.get("median_r"),
        "ci95_lo": boot.get("ci95_lo"),
        "ci95_hi": boot.get("ci95_hi"),
        "decision": mac.get("decision"),
        "a_now_mean_s": a_now.get("mean_s"),
        "a_now_stdev_s": a_now.get("stdev_s"),
        "a_now_runs_s": a_now.get("runs_s"),
        "load_before_uptime": before.get("uptime"),
        "load_after_uptime": after.get("uptime"),
        "precondition_idle": False,
        "withdrawn": ["shell-loop conclusions", "n=1-after-block conclusions"],
    }


def stop(payload: dict, code: int) -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    return code


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

    header, body = vcf_parts(FULL)
    if len(body) != n_full:
        print(f"INCOMPLETE: full body {len(body)} != locked N {n_full}", file=sys.stderr)
        return 2

    before = machine_snapshot("before")
    print(json.dumps({k: before[k] for k in before if k != "lscpu"}, indent=2), flush=True)

    WORKDIR.mkdir(parents=True, exist_ok=True)
    cache: dict[str, str] = {}
    populate = {}
    for name, src in (("HG00096", S96), ("HG00097", S97)):
        h, bdy = vcf_parts(src)
        _t, st = cached_annotate(h, bdy, cache, WORKDIR / f"pop_{name}")
        populate[name] = st
        print(f"populate {name} hits={st['n_hits']} misses={st['n_misses']}", flush=True)
    cache_prev = dict(cache)

    stock_ref, _err, warm_stock_s, warm_stock_cpu = run_snpeff_timed(FULL)
    print(f"warmup stock wall_s={warm_stock_s:.4f} cpu_s={warm_stock_cpu:.4f} (discarded)", flush=True)
    rebuilt, wst = cached_annotate(header, body, dict(cache_prev), WORKDIR / "warmup_cached")
    print(f"warmup cached wall_s={wst['wall_s']:.4f} cpu_s={wst['cpu_s']:.4f} (discarded)", flush=True)
    if not bodies_equal(rebuilt, stock_ref) or wst["n_cache_holes"]:
        print("MATCH failed on warm-up cached path; not timing.", flush=True)
        return stop({"bodies_equal_warmup": False, "decision": "STOP_MATCH"}, 1)

    pairs: list[dict] = []
    n1_runs: list[dict] = []
    timed_index = 0
    pending_stock: dict | None = None
    pending_cached: dict | None = None

    def flush_pair(pair_i: int, uptime_before: str) -> bool:
        nonlocal pending_stock, pending_cached
        assert pending_stock is not None and pending_cached is not None
        if not bodies_equal(pending_cached["text"], pending_stock["text"]):
            return False
        if not bodies_equal(pending_cached["text"], stock_ref):
            return False
        r = pending_stock["wall_s"] / pending_cached["wall_s"]
        r_cpu = pending_stock["cpu_s"] / pending_cached["cpu_s"]
        pairs.append(
            {
                "pair": pair_i,
                "order": "AB" if pair_i % 2 == 1 else "BA",
                "stock_s": pending_stock["wall_s"],
                "cached_s": pending_cached["wall_s"],
                "stock_cpu_s": pending_stock["cpu_s"],
                "cached_cpu_s": pending_cached["cpu_s"],
                "r": r,
                "r_cpu": r_cpu,
                "stock_iso_local": pending_stock["iso_local"],
                "cached_iso_local": pending_cached["iso_local"],
                "stock_run_index": pending_stock["run_index"],
                "cached_run_index": pending_cached["run_index"],
                "uptime_before_pair": uptime_before,
                "load_before_pair": parse_load(uptime_before),
                "bodies_equal_pair": True,
                "bodies_equal_vs_warmup_stock": True,
            }
        )
        print(
            f"pair {pair_i}: stock={pending_stock['wall_s']:.4f} "
            f"cached={pending_cached['wall_s']:.4f} r={r:.4f} r_cpu={r_cpu:.4f} "
            f"uptime={uptime_before}",
            flush=True,
        )
        pending_stock = None
        pending_cached = None
        return True

    for pair_i in range(1, N_PAIRS + 1):
        uptime_before = uptime_line()
        print(f"pair {pair_i} uptime before: {uptime_before}", flush=True)
        abba = "AB" if pair_i % 2 == 1 else "BA"
        seq = ["stock", "cached"] if abba == "AB" else ["cached", "stock"]
        for j, kind in enumerate(seq):
            timed_index += 1
            iso = datetime.now().isoformat()
            if kind == "stock":
                text, _e, wall, cpu = run_snpeff_timed(FULL)
                if not bodies_equal(text, stock_ref):
                    print("stock body drifted vs warm-up; STOP.", flush=True)
                    return stop(
                        {"decision": "STOP_MATCH", "why": "stock body drift", "pairs": pairs},
                        1,
                    )
                pending_stock = {
                    "text": text,
                    "wall_s": wall,
                    "cpu_s": cpu,
                    "iso_local": iso,
                    "run_index": timed_index,
                    "order_in_pair": "A" if j == 0 else "B",
                }
                print(f"  timed #{timed_index} stock wall_s={wall:.4f} cpu_s={cpu:.4f}", flush=True)
            else:
                text, st = cached_annotate(
                    header, body, dict(cache_prev), WORKDIR / f"pair{pair_i}_cached"
                )
                if st["n_cache_holes"] or not bodies_equal(text, stock_ref):
                    print("MATCH failed on cached path; not timing further.", flush=True)
                    return stop(
                        {
                            "decision": "STOP_MATCH",
                            "why": "cached bodies_equal failed",
                            "pairs": pairs,
                        },
                        1,
                    )
                pending_cached = {
                    "text": text,
                    "wall_s": st["wall_s"],
                    "cpu_s": st["cpu_s"],
                    "iso_local": iso,
                    "run_index": timed_index,
                    "order_in_pair": "A" if j == 0 else "B",
                }
                print(
                    f"  timed #{timed_index} cached wall_s={st['wall_s']:.4f} cpu_s={st['cpu_s']:.4f}",
                    flush=True,
                )
        if not flush_pair(pair_i, uptime_before):
            print("MATCH failed on pair; not timing further.", flush=True)
            return stop({"decision": "STOP_MATCH", "why": "pair MATCH", "pairs": pairs}, 1)

        if pair_i % 2 == 0:
            iso = datetime.now().isoformat()
            _o, _e, wall, cpu = run_snpeff_timed(N1)
            rec = {
                "after_pair": pair_i,
                "wall_s": wall,
                "cpu_s": cpu,
                "iso_local": iso,
                "uptime": uptime_line(),
            }
            n1_runs.append(rec)
            print(
                f"a_now n=1 after_pair={pair_i} wall_s={wall:.4f} cpu_s={cpu:.4f}",
                flush=True,
            )

    ratios = [p["r"] for p in pairs]
    median_r, ci_lo, ci_hi = bootstrap_median_ci(ratios, n=BOOT_N, seed=BOOT_SEED)
    cpu_ratios = [p["r_cpu"] for p in pairs]
    median_r_cpu, ci_cpu_lo, ci_cpu_hi = bootstrap_median_ci(
        cpu_ratios, n=BOOT_N, seed=BOOT_SEED
    )
    if ci_lo > 1.0:
        decision = "speedup_stands"
    elif ci_lo <= 1.0 <= ci_hi:
        decision = "speedup_not_established"
    else:
        decision = "ci_entirely_below_1"

    n1_times = [r["wall_s"] for r in n1_runs]
    a_now = statistics.fmean(n1_times)
    r_from_a = (a_now + b * n_full) / (a_now + b * miss_n + w)
    py_stock = [p["stock_s"] for p in pairs]

    after = machine_snapshot("after")
    print(json.dumps({k: after[k] for k in after if k != "lscpu"}, indent=2), flush=True)

    payload = {
        "tool": "SnpEff 5.4c GRCh38.86",
        "flags": ["-noStats", "-noLog"],
        "prediction_commit": "701d24b",
        "protocol_commit_expected": "see VEP_PROTOCOL.md Alternating rerun, CARC",
        "input": str(FULL),
        "machine_before": before,
        "machine_after": after,
        "populate": populate,
        "warmup": {
            "stock_s": warm_stock_s,
            "stock_cpu_s": warm_stock_cpu,
            "cached_s": wst["wall_s"],
            "cached_cpu_s": wst["cpu_s"],
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
        "median_r_cpu": median_r_cpu,
        "bootstrap_cpu": {
            "n": BOOT_N,
            "seed": BOOT_SEED,
            "ci95_lo": ci_cpu_lo,
            "ci95_hi": ci_cpu_hi,
        },
        "decision": decision,
        "decision_rule": "ci_lo>1 speedup_stands; ci includes 1 speedup_not_established",
        "decision_metric": "wall_time_ratio",
        "a_now": {
            "n": 1,
            "schedule": "after even-numbered pairs (2,4,6,8,10)",
            "runs": n1_runs,
            "runs_s": n1_times,
            "mean_s": a_now,
            "stdev_s": statistics.stdev(n1_times) if len(n1_times) > 1 else None,
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
            "stdev_s": statistics.stdev(py_stock) if len(py_stock) > 1 else None,
        },
        "mac_side_by_side": mac_side_by_side(MAC_JSON),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({k: payload[k] for k in payload if k not in ("pairs", "populate", "machine_before", "machine_after")}, indent=2))
    print(f"wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
