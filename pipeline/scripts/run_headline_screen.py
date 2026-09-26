#!/usr/bin/env python3
"""HMMER headline screen (HEADLINE_SCREEN.md + 2026-09-26 erratum).

Stock a+b+w only. No ACTS cache. No speedup claim.
"""

from __future__ import annotations

import gzip
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

ROOT = Path(os.environ.get("ACTS_PIPELINE_ROOT", Path(__file__).resolve().parents[1]))
SEED = 20260926
SIZES = (1, 50, 200, 800)
RUNS = 3
Z_FIXED = 1_000_000
DOMZ_FIXED = 1_000_000
PROBE_K = 8
WORKDIR = Path(os.environ.get("ACTS_HEADLINE_WORK", "/tmp/acts_headline_screen"))
OUT = Path(os.environ.get("ACTS_HEADLINE_OUT", str(ROOT / "results" / "headline_screen.json")))
KPROT_JSON = Path(os.environ.get("ACTS_KPROT_JSON", str(ROOT / "results" / "kprot_overlap.json")))
FAA = Path(os.environ.get("ACTS_FAA", str(ROOT / "data" / "kprot" / "BW25113.faa.gz")))
PFAM = Path(os.environ.get("ACTS_PFAM", str(ROOT / "data" / "hmmer" / "Pfam-A.hmm")))


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


def ceiling_m(a: float, b: float, n: int, m: float, w: float) -> float | None:
    den = a + b * m * n + w
    if den <= 0:
        return None
    return (a + b * n) / den


def saved_m(a: float, b: float, n: int, m: float, w: float) -> float:
    return (a + b * n) - (a + b * m * n + w)


def nproc() -> int:
    for key in ("SLURM_CPUS_PER_TASK", "SLURM_CPUS_ON_NODE"):
        raw = os.environ.get(key)
        if raw:
            try:
                return max(1, int(raw.split("(")[0]))
            except ValueError:
                pass
    return max(1, os.cpu_count() or 1)


def open_text(path: Path):
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt")
    return path.open()


def read_fasta(path: Path) -> list[tuple[str, str]]:
    recs: list[tuple[str, str]] = []
    cur_id = ""
    buf: list[str] = []
    with open_text(path) as fh:
        for line in fh:
            if line.startswith(">"):
                if buf:
                    recs.append((cur_id, "".join(buf)))
                cur_id = line[1:].split()[0]
                buf = [line if line.endswith("\n") else line + "\n"]
            elif buf:
                buf.append(line if line.endswith("\n") else line + "\n")
        if buf:
            recs.append((cur_id, "".join(buf)))
    return recs


def write_fasta(path: Path, records: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(text for _i, text in records))


def tblout_body(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln and not ln.startswith("#")]


def tblout_key(line: str, which: str) -> str:
    fields = line.split()
    if which == "hmmscan":
        return fields[2] if len(fields) > 2 else ""
    return fields[0] if fields else ""


def group_tblout(text: str, which: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for ln in tblout_body(text):
        out.setdefault(tblout_key(ln, which), []).append(ln)
    return out


def run_cmd(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, cwd=cwd, capture_output=True, text=True)


def time_cmd(argv: list[str]) -> dict:
    up = uptime_line()
    cpu0 = children_cpu_s()
    t0 = time.perf_counter()
    proc = run_cmd(argv)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(
            f"cmd failed rc={proc.returncode}: {argv[:8]}\n{(proc.stderr or proc.stdout or '')[-800:]}"
        )
    return {
        "wall_s": wall,
        "cpu_s": children_cpu_s() - cpu0,
        "uptime": up,
        "load": parse_load(up),
        "returncode": proc.returncode,
        "stderr_tail": (proc.stderr or "")[-400:],
    }


def which_hmmer() -> dict[str, str]:
    bindir = os.environ.get("ACTS_HMMER_BIN")
    names = ("hmmscan", "hmmsearch", "hmmpress")
    found: dict[str, str] = {}
    for name in names:
        path = shutil.which(name)
        if bindir:
            candidate = Path(bindir) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                path = str(candidate)
        if not path:
            raise FileNotFoundError(f"{name} not on PATH")
        found[name] = path
    ver = run_cmd([found["hmmsearch"], "-h"])
    first = (ver.stdout or ver.stderr).splitlines()[:3]
    return {**found, "version_head": " | ".join(first)}


def ensure_pressed(hmm: Path, hmmpress: str) -> Path:
    if hmm.suffix == ".gz":
        raise ValueError("Pfam-A.hmm must be gunzipped before hmmpress")
    pressed = hmm.with_suffix(hmm.suffix + ".h3m")
    if pressed.is_file() and pressed.stat().st_mtime >= hmm.stat().st_mtime:
        return hmm
    proc = run_cmd([hmmpress, "-f", str(hmm)])
    if proc.returncode != 0:
        raise RuntimeError(f"hmmpress failed: {(proc.stderr or proc.stdout or '')[-800:]}")
    return hmm


def mode_argv(
    which: str,
    bins: dict[str, str],
    hmm: Path,
    faa: Path,
    tblout: Path,
    cpu: int,
) -> list[str]:
    if which == "hmmscan":
        return [
            bins["hmmscan"],
            "--cpu",
            str(cpu),
            "--cut_ga",
            "--noali",
            "--tblout",
            str(tblout),
            str(hmm),
            str(faa),
        ]
    if which == "hmmsearch":
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
    raise ValueError(which)


def subset_invariance(
    which: str,
    bins: dict[str, str],
    hmm: Path,
    records: list[tuple[str, str]],
    work: Path,
    cpu: int,
) -> dict:
    """Part B (b2) on tblout: each record alone must match its full-probe lines."""
    probe = records[: min(PROBE_K, len(records))]
    work.mkdir(parents=True, exist_ok=True)
    full_fa = work / "probe.faa"
    write_fasta(full_fa, probe)
    full_tbl = work / "probe.tbl"
    argv = mode_argv(which, bins, hmm, full_fa, full_tbl, cpu)
    proc = run_cmd(argv)
    if proc.returncode != 0:
        return {
            "decision": "REFUSE_AMBIGUOUS",
            "reason": f"tool failed on full probe: {(proc.stderr or '')[-400:]}",
            "k": len(probe),
        }
    full_text = full_tbl.read_text() if full_tbl.is_file() else ""
    grouped = group_tblout(full_text, which)
    mismatches = []
    for i, (rid, text) in enumerate(probe):
        one = work / f"solo_{i}.faa"
        one.write_text(text)
        tbl = work / f"solo_{i}.tbl"
        proc = run_cmd(mode_argv(which, bins, hmm, one, tbl, cpu))
        if proc.returncode != 0:
            mismatches.append({"i": i, "id": rid, "error": (proc.stderr or "")[-200:]})
            continue
        got = group_tblout(tbl.read_text() if tbl.is_file() else "", which).get(rid, [])
        exp = grouped.get(rid, [])
        if got != exp:
            mismatches.append(
                {
                    "i": i,
                    "id": rid,
                    "n_full": len(exp),
                    "n_solo": len(got),
                    "full_head": exp[:1],
                    "solo_head": got[:1],
                }
            )
    if mismatches:
        return {
            "decision": "REFUSE_GLOBAL",
            "reason": "output depends on the rest of the file",
            "k": len(probe),
            "n_mismatch": len(mismatches),
            "mismatches": mismatches[:5],
        }
    return {
        "decision": "OK",
        "reason": "subset-invariant",
        "k": len(probe),
        "n_mismatch": 0,
    }


def measure_w(faa: Path, tblout: Path) -> dict:
    """Wrapper + I/O: read the full FASTA, write an empty-but-valid tblout."""
    header = "# ACTS headline-screen empty tblout\n#\n"
    runs = []
    for i in range(RUNS):
        up = uptime_line()
        cpu0 = children_cpu_s()
        t0 = time.perf_counter()
        with open_text(faa) as fh:
            for _chunk in iter(lambda: fh.read(1 << 20), ""):
                pass
        dest = tblout.with_name(f"{tblout.name}.w{i}")
        dest.write_text(header)
        wall = time.perf_counter() - t0
        runs.append(
            {
                "run": i + 1,
                "wall_s": wall,
                "cpu_s": children_cpu_s() - cpu0,
                "uptime": up,
                "load": parse_load(up),
            }
        )
    walls = [r["wall_s"] for r in runs]
    return {
        "runs": runs,
        "w_s": statistics.fmean(walls),
        "stdev_s": statistics.stdev(walls) if len(walls) > 1 else 0.0,
        "note": "cat-equivalent FASTA read + empty tblout header; 3 runs at full N",
    }


def host_info() -> dict:
    def _run(argv: list[str]) -> str:
        proc = run_cmd(argv)
        return (proc.stdout or proc.stderr or "").rstrip()

    lscpu = _run(["lscpu"])
    model = ""
    for ln in lscpu.splitlines():
        if "Model name" in ln:
            model = ln.split(":", 1)[-1].strip()
            break
    return {
        "hostname": _run(["hostname"]),
        "date": datetime.now(timezone.utc).isoformat(),
        "uptime": uptime_line(),
        "nproc": nproc(),
        "cpu_model": model,
        "lscpu": lscpu,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_nodelist": os.environ.get("SLURM_NODELIST"),
    }


def load_m() -> dict:
    raw = json.loads(KPROT_JSON.read_text())
    return {
        "m": float(raw["miss_frac"]),
        "recall_in_new": raw.get("recall_in_new"),
        "n_later": raw.get("n_later"),
        "n_shared": raw.get("n_shared"),
        "source": str(KPROT_JSON),
    }


def screen_mode(
    which: str,
    bins: dict[str, str],
    hmm: Path,
    records: list[tuple[str, str]],
    faa_full: Path,
    work: Path,
    cpu: int,
    m_info: dict,
) -> dict:
    print(f"=== {which} subset-invariance k={PROBE_K} ===", flush=True)
    probe = subset_invariance(which, bins, hmm, records, work / f"{which}_probe", cpu)
    print(f"  {probe['decision']}: {probe['reason']}", flush=True)

    print(f"=== {which} measure w ===", flush=True)
    wrec = measure_w(faa_full, work / f"{which}.tbl")
    print(f"  w={wrec['w_s']:.6f}s", flush=True)

    sizes = [n for n in SIZES if n < len(records)] + [len(records)]
    rng = random.Random(SEED)
    raw = []
    for n in sizes:
        idx = rng.sample(range(len(records)), n)
        subset = [records[i] for i in idx]
        dest = work / f"{which}_n{n}.faa"
        write_fasta(dest, subset)
        runs = []
        for i in range(RUNS):
            tbl = work / f"{which}_n{n}_r{i+1}.tbl"
            rec = time_cmd(mode_argv(which, bins, hmm, dest, tbl, cpu))
            rec["run"] = i + 1
            rec["n_tblout"] = len(tblout_body(tbl.read_text() if tbl.is_file() else ""))
            runs.append(rec)
            print(
                f"  {which} n={n} run={i+1} wall_s={rec['wall_s']:.4f} "
                f"cpu_s={rec['cpu_s']:.4f} load={rec['load']}",
                flush=True,
            )
        walls = [r["wall_s"] for r in runs]
        raw.append(
            {
                "n": n,
                "n_records": n,
                "seed": SEED,
                "subset_indices_head": idx[:10],
                "runs": runs,
                "mean_s": statistics.fmean(walls),
                "stdev_s": statistics.stdev(walls) if len(walls) > 1 else 0.0,
                "mean_cpu_s": statistics.fmean(r["cpu_s"] for r in runs),
            }
        )

    ns = [row["n"] for row in raw]
    ts = [row["mean_s"] for row in raw]
    a, b = fit_ab(ns, ts)
    n = ns[-1]
    m = float(m_info["m"])
    w = float(wrec["w_s"])
    ceil = ceiling_m(a, b, n, m, w)
    saved = saved_m(a, b, n, m, w)
    probe_ok = probe.get("decision") == "OK"
    advances = bool(
        probe_ok
        and a > 0
        and b > 0
        and ceil is not None
        and ceil >= 3.0
        and saved >= 60.0
    )
    reject_reasons = []
    if not probe_ok:
        reject_reasons.append(f"subset-invariance {probe.get('decision')}")
    if not (a > 0 and b > 0):
        reject_reasons.append("linear model failed (need a>0 and b>0)")
    if ceil is None or ceil < 3.0:
        reject_reasons.append(f"ceiling={ceil} < 3")
    if saved < 60.0:
        reject_reasons.append(f"saved={saved:.3f}s < 60s")
    return {
        "mode": which,
        "argv_template": mode_argv(which, bins, Path("Pfam-A.hmm"), Path("INPUT.faa"), Path("OUT.tbl"), cpu),
        "cpu": cpu,
        "Z_FIXED": Z_FIXED if which == "hmmsearch" else "n_models",
        "DOMZ_FIXED": DOMZ_FIXED if which == "hmmsearch" else "n_models",
        "subset_invariance": probe,
        "w": wrec,
        "N": n,
        "a_s": a,
        "b_s_per_record": b,
        "m": m,
        "ceiling": ceil,
        "saved_s": saved,
        "advances": advances,
        "decision": "ADVANCE" if advances else "REJECT",
        "reject_reasons": reject_reasons,
        "advance_rule": "a>0 and b>0 and ceiling(m)>=3 and saved>=60s and subset-invariant",
        "raw": raw,
    }


def resolve_pfam() -> Path:
    candidates = [
        PFAM,
        ROOT / "data" / "hmmer" / "Pfam-A.hmm",
        ROOT / "data" / "hmmer" / "Pfam-A.hmm.gz",
        WORKDIR / "Pfam-A.hmm",
        WORKDIR / "Pfam-A.hmm.gz",
    ]
    env = os.environ.get("ACTS_PFAM")
    if env:
        candidates.insert(0, Path(env))
    for path in candidates:
        if path.is_file():
            if str(path).endswith(".gz"):
                dest = WORKDIR / "Pfam-A.hmm"
                WORKDIR.mkdir(parents=True, exist_ok=True)
                if not dest.is_file() or dest.stat().st_mtime < path.stat().st_mtime:
                    print(f"gunzip {path} -> {dest}", flush=True)
                    with gzip.open(path, "rb") as src, dest.open("wb") as out:
                        shutil.copyfileobj(src, out)
                return dest
            return path
    raise FileNotFoundError("Pfam-A.hmm not found; set ACTS_PFAM")


def pfam_version(hmm: Path) -> str:
    ver = ROOT / "data" / "hmmer" / "Pfam.version.gz"
    if ver.is_file():
        return gzip.open(ver, "rt").read().strip()
    with hmm.open() as fh:
        for i, ln in enumerate(fh):
            if ln.startswith("ACC") or ln.startswith("NAME") or ln.startswith("HMMER"):
                return ln.strip()
            if i > 20:
                break
    return "unknown"


def main() -> int:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    host = host_info()
    print(json.dumps({k: host[k] for k in ("hostname", "nproc", "cpu_model", "uptime")}, indent=2), flush=True)
    bins = which_hmmer()
    hmm = ensure_pressed(resolve_pfam(), bins["hmmpress"])
    records = read_fasta(FAA)
    if not records:
        raise SystemExit(f"no FASTA records in {FAA}")
    m_info = load_m()
    cpu = nproc()
    print(f"N={len(records)} cpu={cpu} m={m_info['m']} pfam={hmm}", flush=True)

    modes = []
    for which in ("hmmscan", "hmmsearch"):
        modes.append(
            screen_mode(which, bins, hmm, records, FAA, WORKDIR / which, cpu, m_info)
        )

    paper = None
    for rec in modes:
        if rec["advances"]:
            paper = rec["mode"]
            if rec["mode"] == "hmmsearch":
                break
    # erratum: if both advance, paper uses (ii) hmmsearch
    if all(r["advances"] for r in modes):
        paper = "hmmsearch"

    payload = {
        "protocol": "pipeline/docs/HEADLINE_SCREEN.md",
        "erratum": "2026-09-26",
        "seed": SEED,
        "host": host,
        "hmmer": bins,
        "pfam": str(hmm),
        "pfam_version": pfam_version(hmm),
        "input": str(FAA),
        "N": len(records),
        "m": m_info,
        "Z_FIXED": Z_FIXED,
        "DOMZ_FIXED": DOMZ_FIXED,
        "modes": modes,
        "paper_uses": paper,
        "paper_rule": "first mode that passes (b2) and the ceiling; if both, hmmsearch (ii)",
        "note": "No ACTS cache. No speedup claim. Timing is stock CLI only.",
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({k: payload[k] for k in ("m", "paper_uses")}, indent=2))
    for rec in modes:
        print(
            f"{rec['mode']}: a={rec['a_s']:.4f} b={rec['b_s_per_record']:.6f} "
            f"w={rec['w']['w_s']:.6f} ceiling={rec['ceiling']} saved={rec['saved_s']:.3f} "
            f"{rec['decision']}",
            flush=True,
        )
    print(f"wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
