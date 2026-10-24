#!/usr/bin/env python3
"""CARC Semgrep measured / smoke runner (pre-reg 2026-10-24).

Modes:
  --mode smoke     one release step A→B, r=1; must SHIP stock-identical except time
  --mode measured  fill A; steps B,C with r=3 alternating stock/TARE; controls; score

Writes JSON to --out. Crash handler writes partial payload on SIGTERM/SIGINT.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import shutil
import signal
import statistics
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

PIPE = Path(os.environ.get("ACTS_PIPELINE_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(PIPE))

from acts.table_json import equal_except_volatile  # noqa: E402

SEMGREP_FLAGS = [
    "--json",
    "--no-rewrite-rule-ids",
    "--metrics=off",
    "--disable-version-check",
    "--timeout",
    "0",
    "--timeout-threshold",
    "0",
    "--max-memory",
    "0",
    "-j",
    "32",
]
VOLATILE = ("time",)
POWER_FLOOR = 500

PAYLOAD: dict | None = None
OUT_PATH: Path | None = None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_out(argv: list[str]) -> str:
    try:
        return subprocess.check_output(argv, text=True, stderr=subprocess.STDOUT).rstrip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"ERR: {exc}"


def host_snap() -> dict:
    lscpu = cmd_out(["lscpu"])
    model = ""
    for ln in lscpu.splitlines():
        if ln.lower().startswith("model name"):
            model = ln.split(":", 1)[-1].strip()
            break
    return {
        "iso_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": cmd_out(["hostname"]),
        "uptime": cmd_out(["uptime"]),
        "cpu_model": model,
        "nproc": cmd_out(["nproc"]),
        "lscpu": lscpu,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_nodelist": os.environ.get("SLURM_NODELIST"),
    }


def write_payload() -> None:
    if PAYLOAD is None or OUT_PATH is None:
        return
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(OUT_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(PAYLOAD, indent=2) + "\n")
    tmp.replace(OUT_PATH)


def on_signal(signum: int, _frame: object) -> None:
    if PAYLOAD is not None:
        PAYLOAD["status"] = "PARTIAL"
        PAYLOAD["signal"] = signal.Signals(signum).name
        PAYLOAD["partial_at"] = datetime.now(timezone.utc).isoformat()
        write_payload()
    raise SystemExit(128 + signum)


def wall_run(argv: list[str], *, env: dict | None = None) -> tuple[int, float, str, str]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        argv,
        text=True,
        capture_output=True,
        env=env,
    )
    wall = time.perf_counter() - t0
    return proc.returncode, wall, proc.stdout, proc.stderr


def load_chain(assets: Path) -> tuple[list[Path], dict]:
    meta = json.loads((assets / "release_chain.json").read_text())
    paths = []
    for rel in meta["releases"]:
        name = Path(rel["path"]).name
        p = assets / "rules" / name
        if not p.is_file():
            p = Path(rel["path"])
        if not p.is_file():
            raise FileNotFoundError(name)
        paths.append(p)
    return paths, meta


def stock_scan(
    semgrep: Path,
    rules: Path,
    records: Path,
    out_json: Path,
    *,
    env: dict,
    j_flags: list[str],
) -> dict:
    files = [ln.strip() for ln in records.read_text().splitlines() if ln.strip()]
    argv = [str(semgrep), "--config", str(rules), *j_flags, "-o", str(out_json), *files]
    rc, wall, stdout, stderr = wall_run(argv, env=env)
    n_findings = None
    n_errors = None
    if out_json.is_file():
        try:
            data = json.loads(out_json.read_text())
            n_findings = len(data.get("results") or [])
            n_errors = len(data.get("errors") or [])
        except json.JSONDecodeError:
            pass
    return {
        "rc": rc,
        "wall_s": wall,
        "n_findings": n_findings,
        "n_errors": n_errors,
        "out_sha256": sha256_file(out_json) if out_json.is_file() else None,
        "argv": argv[:8] + [f"...({len(files)} inputs)"],
        "stderr_tail": (stderr or "")[-2000:],
    }


def tare_run(
    *,
    python: str,
    semgrep: Path,
    rules: Path,
    records: Path,
    cache: Path,
    out_dir: Path,
    env: dict,
    j_flags: list[str],
) -> dict:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    flags = [
        "--config",
        "{reference}",
        *j_flags,
        "-o",
        "{output}",
        "{inputs}",
    ]
    argv = [
        python,
        "-m",
        "acts",
        "run",
        "--strategy",
        "reference",
        "--reference-format",
        "yaml-list",
        "--output-format",
        "json-records",
        "--json-rows",
        "results",
        "--volatile-json-field",
        "time",
        "--pin",
        "--verify",
        "full",
        "--input",
        str(records),
        "--reference",
        str(rules),
        "--cache",
        str(cache),
        "-o",
        str(out_dir),
        "--",
        str(semgrep),
        *flags,
    ]
    run_env = dict(env)
    run_env["PYTHONPATH"] = str(PIPE) + (
        os.pathsep + run_env["PYTHONPATH"] if run_env.get("PYTHONPATH") else ""
    )
    rc, wall, stdout, stderr = wall_run(argv, env=run_env)
    decision = None
    why = None
    dec = out_dir / "decision.txt"
    if dec.is_file():
        for ln in dec.read_text().splitlines():
            if ln.startswith("decision:"):
                decision = ln.split(":", 1)[1].strip()
            elif ln.startswith("why:"):
                why = ln.split(":", 1)[1].strip()
    table = out_dir / "tables" / "out"
    return {
        "rc": rc,
        "wall_s": wall,
        "decision": decision,
        "why": why,
        "out_path": str(table) if table.is_file() else None,
        "out_sha256": sha256_file(table) if table.is_file() else None,
        "stdout_tail": (stdout or "")[-1500:],
        "stderr_tail": (stderr or "")[-2000:],
    }


def compare_except_time(a: Path, b: Path) -> dict:
    ta = a.read_text()
    tb = b.read_text()
    ok = equal_except_volatile(ta, tb, VOLATILE)
    diff_keys: list[str] = []
    diff_class = None
    try:
        da = json.loads(ta)
        db = json.loads(tb)
        for k in sorted(set(da) | set(db)):
            if k in VOLATILE:
                continue
            if da.get(k) != db.get(k):
                diff_keys.append(k)
        if not ok:
            if "results" in diff_keys:
                ra = da.get("results") or []
                rb = db.get("results") or []
                if len(ra) != len(rb):
                    diff_class = "count_mismatch"
                else:
                    diff_class = "value_or_row"
            elif "errors" in diff_keys:
                diff_class = "errors_mismatch"
            else:
                diff_class = "envelope_field"
    except json.JSONDecodeError:
        diff_class = "json_parse"
    return {
        "equal_except_time": ok,
        "diff_keys": diff_keys,
        "diff_class": diff_class,
    }


def save_cache(cache: Path, dest: Path) -> None:
    if dest.exists():
        dest.unlink()
    shutil.copy2(cache, dest)


def restore_cache(src: Path, cache: Path) -> None:
    if cache.exists():
        cache.unlink()
    shutil.copy2(src, cache)


def inject_drop_hook(work: Path, semgrep: Path) -> Path:
    """Wrap semgrep: on second invocation with --config, drop one finding from JSON."""
    hook = work / "semgrep_drop_hook.sh"
    hook.write_text(
        f"""#!/bin/bash
set -euo pipefail
REAL="{semgrep}"
STATE="{work}/drop_hook_state"
mkdir -p "$(dirname "$STATE")"
# Count invocations that look like a scan (have -o)
if printf '%s\\n' "$@" | grep -q -- '-o'; then
  n=0
  if [[ -f "$STATE" ]]; then n=$(cat "$STATE"); fi
  n=$((n+1))
  echo "$n" > "$STATE"
  out=""
  prev=""
  for a in "$@"; do
    if [[ "$prev" == "-o" ]]; then out="$a"; fi
    prev="$a"
  done
  "$REAL" "$@"
  rc=$?
  if [[ "$n" -ge 2 && -n "$out" && -f "$out" ]]; then
    python3 - "$out" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
if d.get("results"):
    d["results"] = d["results"][1:]
    open(p, "w").write(json.dumps(d))
PY
  fi
  exit $rc
else
  exec "$REAL" "$@"
fi
"""
    )
    hook.chmod(0o755)
    return hook


def median(xs: list[float]) -> float | None:
    if not xs:
        return None
    return float(statistics.median(xs))


def cv(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    m = statistics.mean(xs)
    if m == 0:
        return None
    return float(statistics.pstdev(xs) / m)


def run_errors_dependence(
    *,
    semgrep: Path,
    rules: Path,
    records: Path,
    work: Path,
    env: dict,
    j_flags: list[str],
) -> dict:
    """10 half-rule subsets; rate where errors differ from full."""
    text = rules.read_text()
    # Split on top-level list items roughly via parse
    from acts.reference_yaml import parse_yaml_list_text, write_yaml_list

    entries = parse_yaml_list_text(text)
    full_out = work / "errors_dep" / "full.json"
    full_out.parent.mkdir(parents=True, exist_ok=True)
    full = stock_scan(semgrep, rules, records, full_out, env=env, j_flags=j_flags)
    full_errs = json.loads(full_out.read_text()).get("errors") if full_out.is_file() else None
    rng_seed = 20261353
    import random

    rng = random.Random(rng_seed)
    diffs = 0
    subset_rows = []
    for i in range(10):
        half = sorted(rng.sample(entries, max(1, len(entries) // 2)), key=lambda e: e.primary)
        sub_yaml = work / "errors_dep" / f"subset_{i:02d}.yaml"
        write_yaml_list(half, sub_yaml)
        # rewrite header? write_yaml_list uses document_header from entries
        sub_out = work / "errors_dep" / f"subset_{i:02d}.json"
        row = stock_scan(semgrep, sub_yaml, records, sub_out, env=env, j_flags=j_flags)
        sub_errs = json.loads(sub_out.read_text()).get("errors") if sub_out.is_file() else None
        differ = sub_errs != full_errs
        if differ:
            diffs += 1
        subset_rows.append({"i": i, "differ": differ, "n_findings": row.get("n_findings")})
    rate = diffs / 10.0
    return {
        "seed": rng_seed,
        "rate": rate,
        "full_n_errors": len(full_errs or []),
        "n_differ": diffs,
        "subsets": subset_rows,
        "pass": rate == 0.0,
    }


def main() -> int:
    global PAYLOAD, OUT_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("smoke", "measured"), required=True)
    ap.add_argument("--assets", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--semgrep", type=Path, required=True)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--skip-errors-dep", action="store_true")
    ap.add_argument("--skip-negative", action="store_true")
    args = ap.parse_args()

    OUT_PATH = args.out
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    assets = args.assets
    work = args.work
    work.mkdir(parents=True, exist_ok=True)
    # Rebuild records.txt from local files/ so Mac absolute paths are not required.
    files_dir = assets / "corpus" / "files"
    records = work / "records.txt"
    file_paths = sorted(files_dir.glob("*.py"))
    if len(file_paths) < 1000:
        raise SystemExit(f"corpus files missing under {files_dir}: {len(file_paths)}")
    records.write_text("\n".join(str(p.resolve()) for p in file_paths) + "\n")
    rules_paths, chain_meta = load_chain(assets)
    assert len(rules_paths) == 3
    A, B, C = rules_paths

    env = os.environ.copy()
    env["SEMGREP_SEND_METRICS"] = "off"
    env["SEMGREP_ENABLE_VERSION_CHECK"] = "0"
    cache_home = work / "xdg_cache"
    cache_home.mkdir(exist_ok=True)
    env["XDG_CACHE_HOME"] = str(cache_home)

    j_flags = list(SEMGREP_FLAGS)
    # Smoke may set SEMGREP_J for shared-node cpus-per-task.
    if os.environ.get("SEMGREP_J"):
        j_val = os.environ["SEMGREP_J"]
        rebuilt: list[str] = []
        i = 0
        while i < len(j_flags):
            if j_flags[i] == "-j" and i + 1 < len(j_flags):
                rebuilt.extend(["-j", j_val])
                i += 2
            else:
                rebuilt.append(j_flags[i])
                i += 1
        j_flags = rebuilt

    frozen = (assets / "FROZEN_COMMIT").read_text().strip() if (assets / "FROZEN_COMMIT").is_file() else None
    git_head = cmd_out(["git", "-C", str(PIPE.parent), "rev-parse", "HEAD"])

    PAYLOAD = {
        "protocol": "semgrep_measured",
        "pre_reg": "pipeline/docs/SEMGREP_PILOT.md#carc-measured-pre-registration-locked-2026-10-24",
        "mode": args.mode,
        "status": "RUNNING",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head,
        "frozen_commit": frozen,
        "seeds": {
            "corpus": 20261351,
            "releases": 20261352,
            "errors_dep": 20261353,
        },
        "semgrep": {
            "path": str(args.semgrep),
            "version": cmd_out([str(args.semgrep), "--version"]),
            "sha256": sha256_file(args.semgrep),
            "flags": j_flags,
        },
        "host": host_snap(),
        "chain": chain_meta.get("selection"),
        "releases_sha256": [sha256_file(p) for p in rules_paths],
        "corpus_meta": json.loads((assets / "corpus" / "meta.json").read_text())
        if (assets / "corpus" / "meta.json").is_file()
        else None,
        "runs": [],
        "controls": {},
        "scores": {},
    }
    write_payload()

    r = 1 if args.mode == "smoke" else 3
    steps = [(A, B, "A_to_B")] if args.mode == "smoke" else [(A, B, "A_to_B"), (B, C, "B_to_C")]

    # Power + stock-vs-stock on newest (C for measured, B for smoke)
    newest = B if args.mode == "smoke" else C
    stock1 = work / "stock_identity_1.json"
    stock2 = work / "stock_identity_2.json"
    s1 = stock_scan(args.semgrep, newest, records, stock1, env=env, j_flags=j_flags)
    s2 = stock_scan(args.semgrep, newest, records, stock2, env=env, j_flags=j_flags)
    ident = compare_except_time(stock1, stock2)
    power_n = s1.get("n_findings") or 0
    PAYLOAD["controls"]["stock_vs_stock"] = {
        "pass": ident["equal_except_time"],
        "compare": ident,
        "run1": s1,
        "run2": s2,
    }
    PAYLOAD["power"] = {
        "n_findings_newest": power_n,
        "floor": POWER_FLOOR,
        "met": power_n >= POWER_FLOOR,
    }
    write_payload()
    if not ident["equal_except_time"]:
        PAYLOAD["status"] = "FAIL"
        PAYLOAD["fail_reason"] = "stock_vs_stock"
        write_payload()
        return 2
    if power_n < POWER_FLOOR:
        PAYLOAD["status"] = "INCONCLUSIVE"
        PAYLOAD["fail_reason"] = "power_floor"
        write_payload()
        return 3

    if args.mode == "measured" and not args.skip_errors_dep:
        PAYLOAD["controls"]["errors_dependence"] = run_errors_dependence(
            semgrep=args.semgrep,
            rules=newest,
            records=records,
            work=work,
            env=env,
            j_flags=j_flags,
        )
        write_payload()
        if not PAYLOAD["controls"]["errors_dependence"]["pass"]:
            PAYLOAD["status"] = "FAIL"
            PAYLOAD["fail_reason"] = "errors_dependence"
            write_payload()
            return 2

    # Negative control (measured only, or smoke if requested)
    if args.mode == "measured" and not args.skip_negative:
        neg_dir = work / "negative"
        neg_dir.mkdir(exist_ok=True)
        hook = inject_drop_hook(neg_dir, args.semgrep)
        neg_cache = neg_dir / "cache.sqlite"
        if neg_cache.exists():
            neg_cache.unlink()
        fill = tare_run(
            python=args.python,
            semgrep=hook,
            rules=A,
            records=records,
            cache=neg_cache,
            out_dir=neg_dir / "fill",
            env=env,
            j_flags=j_flags,
        )
        # Reset hook counter for update path — use fresh state file after fill
        # Actually hook counts all -o invocations across fill+update; drop on 2nd+.
        # For fill-only many calls; better: only wrap update.
        # Re-do: fill with real semgrep, update with hook.
        neg_cache2 = neg_dir / "cache2.sqlite"
        if neg_cache2.exists():
            neg_cache2.unlink()
        fill2 = tare_run(
            python=args.python,
            semgrep=args.semgrep,
            rules=A,
            records=records,
            cache=neg_cache2,
            out_dir=neg_dir / "fill2",
            env=env,
            j_flags=j_flags,
        )
        # fresh hook state
        state = neg_dir / "drop_hook_state"
        if state.exists():
            state.unlink()
        upd = tare_run(
            python=args.python,
            semgrep=hook,
            rules=B,
            records=records,
            cache=neg_cache2,
            out_dir=neg_dir / "update",
            env=env,
            j_flags=j_flags,
        )
        refused = (upd.get("decision") or "").startswith("REFUSE") or upd.get("decision") not in {
            "SHIP",
            "FALLBACK",
        }
        # Prefer explicit REFUSE
        refused = (upd.get("decision") or "") not in {"SHIP", "FALLBACK"}
        PAYLOAD["controls"]["negative_drop"] = {
            "pass": refused,
            "fill": fill2,
            "update": upd,
            "unused_hook_fill": fill,
        }
        write_payload()
        if not refused:
            PAYLOAD["status"] = "FAIL"
            PAYLOAD["fail_reason"] = "negative_control_shipped"
            write_payload()
            return 2

    # Timed chain
    cache = work / "main_cache.sqlite"
    if cache.exists():
        cache.unlink()
    fill_dir = work / "fill_A"
    fill = tare_run(
        python=args.python,
        semgrep=args.semgrep,
        rules=A,
        records=records,
        cache=cache,
        out_dir=fill_dir,
        env=env,
        j_flags=j_flags,
    )
    PAYLOAD["fill_A"] = fill
    write_payload()
    if fill.get("decision") not in {"SHIP", "FALLBACK"}:
        PAYLOAD["status"] = "FAIL"
        PAYLOAD["fail_reason"] = "fill_A"
        write_payload()
        return 2

    snap_after_A = work / "cache_after_A.sqlite"
    save_cache(cache, snap_after_A)

    step_scores = []
    all_ship = True
    for prev_rules, step_rules, label in steps:
        # snapshot before this step
        if label == "A_to_B":
            snap = snap_after_A
        else:
            snap = work / "cache_after_B.sqlite"
        stock_walls: list[float] = []
        tare_walls: list[float] = []
        step_runs = []
        for rep in range(r):
            # stock
            stock_out = work / f"stock_{label}_r{rep}.json"
            st = stock_scan(
                args.semgrep, step_rules, records, stock_out, env=env, j_flags=j_flags
            )
            stock_walls.append(st["wall_s"])
            # tare: restore + update
            restore_cache(snap, cache)
            td = work / f"tare_{label}_r{rep}"
            tr = tare_run(
                python=args.python,
                semgrep=args.semgrep,
                rules=step_rules,
                records=records,
                cache=cache,
                out_dir=td,
                env=env,
                j_flags=j_flags,
            )
            tare_walls.append(tr["wall_s"])
            cmp = None
            if tr.get("out_path") and stock_out.is_file():
                cmp = compare_except_time(Path(tr["out_path"]), stock_out)
            ship_ok = tr.get("decision") == "SHIP" and cmp and cmp["equal_except_time"]
            if not ship_ok:
                all_ship = False
            step_runs.append({"rep": rep, "stock": st, "tare": tr, "compare": cmp, "ship_ok": ship_ok})
            PAYLOAD["runs"].append({"step": label, "rep": rep, "stock": st, "tare": tr, "compare": cmp})
            write_payload()
        # After finishing reps, leave cache at post-step for next snap
        restore_cache(snap, cache)
        final = tare_run(
            python=args.python,
            semgrep=args.semgrep,
            rules=step_rules,
            records=records,
            cache=cache,
            out_dir=work / f"advance_{label}",
            env=env,
            j_flags=j_flags,
        )
        if label == "A_to_B":
            save_cache(cache, work / "cache_after_B.sqlite")
        ms = median(stock_walls)
        mt = median(tare_walls)
        s_ratio = (ms / mt) if (ms and mt and mt > 0) else None
        step_scores.append(
            {
                "step": label,
                "r": r,
                "stock_walls": stock_walls,
                "tare_walls": tare_walls,
                "median_stock": ms,
                "median_tare": mt,
                "S": s_ratio,
                "cv_stock": cv(stock_walls),
                "cv_tare": cv(tare_walls),
                "all_ship_ok": all(x["ship_ok"] for x in step_runs),
                "advance": final,
                "runs": step_runs,
            }
        )

    # Payback over chain (measured): fill + sum median tare vs (n_steps+1?)*median stock
    fill_wall = fill.get("wall_s") or 0.0
    tare_sum = sum((sc["median_tare"] or 0.0) for sc in step_scores)
    # stock cost if re-run newest each time: for each step median stock; plus would need A stock too
    stock_sum = sum((sc["median_stock"] or 0.0) for sc in step_scores)
    # naive payback: (stock_sum) / (fill_wall + tare_sum) after the updates in the chain
    payback = {
        "fill_wall_s": fill_wall,
        "sum_median_tare_s": tare_sum,
        "sum_median_stock_s": stock_sum,
        "tare_chain_s": fill_wall + tare_sum,
        "ratio_stock_over_tare_chain": (stock_sum / (fill_wall + tare_sum))
        if (fill_wall + tare_sum) > 0
        else None,
        "note": "Payback uses medians over r; fill counted once; refusals counted in runs",
    }

    PAYLOAD["scores"] = {
        "steps": step_scores,
        "payback": payback,
        "all_ship_stock_identical": all_ship,
    }
    if all_ship and PAYLOAD["controls"].get("stock_vs_stock", {}).get("pass"):
        PAYLOAD["status"] = "SHIP"
        PAYLOAD["verdict"] = "PASS"
    else:
        PAYLOAD["status"] = "FAIL"
        PAYLOAD["verdict"] = "FAIL"
        PAYLOAD["fail_reason"] = PAYLOAD.get("fail_reason") or "update_mismatch_or_refuse"
    PAYLOAD["finished_utc"] = datetime.now(timezone.utc).isoformat()
    write_payload()
    return 0 if PAYLOAD["status"] == "SHIP" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        if PAYLOAD is not None:
            PAYLOAD["status"] = "CRASH"
            PAYLOAD["traceback"] = traceback.format_exc()
            write_payload()
        raise
