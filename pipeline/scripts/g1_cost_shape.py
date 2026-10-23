"""G1 cost-shape probe for the non-biology domains (NONBIO_DOMAIN_PLAN.md, phase G1).

Question: how does a tool's wall time T(f) scale when it runs with a random fraction f of its
reference entries (signatures or rules) on a fixed corpus? Fit T(f) = c + a*f and project the
replay speedup S = T(1) / T(f_delta) for a release's changed fraction f_delta. If a (the
entry-proportional share) is small, TARE cannot win and its break-even gate should decline.

This is a laptop shape probe, not speed evidence (AGENTS.md test design standard): it decides
whether the server experiment is worth running. Seed 20261321. At most 2 threads, nice 10.

Run: nice -n 10 python3 pipeline/scripts/g1_cost_shape.py --root ~/tmp/tare_g1 --out pipeline/results/nonbio/g1_laptop.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

SEED = 20261321
FRACTIONS = [0.01, 0.10, 0.25, 0.50, 1.00]
REPEATS = 3

# ClamAV files that carry signatures (subsampled). Control files stay whole: allow lists,
# ignore lists, file-type magic, certificate trust and config. .info is dropped: in a loose
# directory it would describe files that no longer match.
CLAM_SUBSAMPLE = {".hdb", ".hsb", ".mdb", ".msb", ".ndb", ".ldb", ".cdb", ".idb", ".pdb", ".wdb",
                  ".hdu", ".hsu", ".mdu", ".msu", ".ndu", ".ldu"}
CLAM_KEEP = {".fp", ".sfp", ".ign", ".ign2", ".ftm", ".crb", ".cfg"}


def sh(cmd: list[str], env: dict | None = None) -> tuple[float, int, str]:
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return time.perf_counter() - t0, proc.returncode, (proc.stdout + proc.stderr)[-400:]


def corpus_manifest(files: list[Path]) -> dict:
    h = hashlib.sha256()
    total = 0
    for p in files:
        h.update(str(p).encode())
        total += p.stat().st_size
    return {"n_files": len(files), "bytes": total, "path_list_sha256": h.hexdigest()}


def clam_subsets(root: Path, rng: random.Random) -> dict[float, Path]:
    src = root / "clam" / "unpacked"
    out = {}
    for f in FRACTIONS:
        d = root / "clam" / f"subset_{f:.2f}"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        for p in sorted(src.iterdir()):
            if p.suffix in CLAM_KEEP:
                shutil.copy2(p, d / p.name)
            elif p.suffix in CLAM_SUBSAMPLE:
                lines = p.read_text(errors="surrogateescape").splitlines(keepends=True)
                keep = lines if f >= 1.0 else [ln for ln in lines if rng.random() < f]
                if keep:
                    (d / p.name).write_text("".join(keep), errors="surrogateescape")
        out[f] = d
    return out


def semgrep_subsets(root: Path, rng: random.Random) -> tuple[dict[float, Path], int]:
    rules = sorted((root / "rules" / "python").rglob("*.yaml"))
    rules = [r for r in rules if "/test" not in str(r)]
    out = {}
    for f in FRACTIONS:
        d = root / "semgrep" / f"rules_{f:.2f}"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        k = max(1, round(f * len(rules)))
        for i, r in enumerate(sorted(rng.sample(rules, k))):
            shutil.copy2(r, d / f"{i:04d}_{r.name}")
        out[f] = d
    return out, len(rules)


def fit(points: dict[float, list[float]]) -> dict:
    xs = [f for f, ws in points.items() for _ in ws]
    ys = [w for ws in points.values() for w in ws]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    a = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    c = my - a * mx
    t1 = statistics.median(points[1.0])
    proj = {str(fd): t1 / (c + a * fd) for fd in (0.01, 0.05, 0.134)}
    return {"a_s": a, "c_s": c, "a_share": a / (a + c), "median_wall_s": {str(k): statistics.median(v) for k, v in points.items()},
            "projected_S_at_changed_fraction": proj}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = Path(args.root).expanduser()
    rng = random.Random(SEED)

    # ClamAV corpus: a fixed, benign set of binaries and libraries already on disk.
    clam_files = sorted(p for p in Path("/opt/homebrew/Cellar").rglob("*")
                        if p.is_file() and not p.is_symlink() and p.stat().st_size > 4096)[:4000]
    clam_list = root / "clam" / "corpus.txt"
    clam_list.write_text("\n".join(map(str, clam_files)) + "\n")
    tiny = root / "clam" / "tiny.txt"
    tiny.write_text("x\n")

    # Semgrep corpus: Python files already on disk (Semgrep's own installed dependencies).
    sg_files = sorted((root / "venv" / "lib").rglob("*.py"))[:3000]
    sg_target = root / "semgrep" / "target"
    if sg_target.exists():
        shutil.rmtree(sg_target)
    sg_target.mkdir(parents=True)
    for i, p in enumerate(sg_files):
        shutil.copy2(p, sg_target / f"{i:05d}_{p.name}")

    clam_dirs = clam_subsets(root, rng)
    sg_dirs, n_rules = semgrep_subsets(root, rng)

    env = dict(os.environ, XDG_CACHE_HOME=str(root / "cache"), SEMGREP_SEND_METRICS="off",
               SEMGREP_ENABLE_VERSION_CHECK="0")
    semgrep = str(root / "venv" / "bin" / "semgrep")

    res = {"seed": SEED, "fractions": FRACTIONS, "repeats": REPEATS, "host": platform.node(),
           "machine": platform.machine(), "laptop_wall_is_speed_evidence": False,
           "clamav": {"version": subprocess.run(["clamscan", "--version"], capture_output=True, text=True).stdout.strip(),
                      "corpus": corpus_manifest(clam_files), "argv": "clamscan --allmatch -i --no-summary -d DIR -f corpus.txt",
                      "walls": {}, "load_only": {}, "rc": {}},
           "semgrep": {"version": "1.182.1", "n_rule_files": n_rules, "corpus": corpus_manifest(sg_files),
                       "argv": "semgrep scan --config DIR --json -j 2 --metrics=off --disable-version-check --no-git-ignore --timeout 30 TARGET",
                       "walls": {}, "rc": {}}}
    order = [(r, f) for r in range(REPEATS) for f in (FRACTIONS if r % 2 == 0 else FRACTIONS[::-1])]
    for r, f in order:
        d = clam_dirs[f]
        w, rc, tail = sh(["clamscan", "--allmatch", "-i", "--no-summary", "-d", str(d), str(tiny)])
        res["clamav"]["load_only"].setdefault(str(f), []).append(w)
        w, rc, tail = sh(["clamscan", "--allmatch", "-i", "--no-summary", "-d", str(d), "-f", str(clam_list)])
        res["clamav"]["walls"].setdefault(str(f), []).append(w)
        res["clamav"]["rc"].setdefault(str(f), []).append(rc)
        w, rc, tail = sh([semgrep, "scan", "--config", str(sg_dirs[f]), "--json", "-j", "2", "--metrics=off",
                          "--disable-version-check", "--no-git-ignore", "--timeout", "30", "-q",
                          "-o", str(root / "semgrep" / f"out_{f:.2f}_{r}.json"), str(sg_target)], env=env)
        res["semgrep"]["walls"].setdefault(str(f), []).append(w)
        res["semgrep"]["rc"].setdefault(str(f), []).append(rc)
        print(f"rep {r} f={f:.2f} clam={res['clamav']['walls'][str(f)][-1]:.1f}s "
              f"semgrep={w:.1f}s rc={rc}", flush=True)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(res, indent=2) + "\n")
    for tool in ("clamav", "semgrep"):
        res[tool]["fit"] = fit({float(k): v for k, v in res[tool]["walls"].items()})
    res["clamav"]["load_fit"] = fit({float(k): v for k, v in res["clamav"]["load_only"].items()})
    Path(args.out).write_text(json.dumps(res, indent=2) + "\n")
    print(json.dumps({t: res[t]["fit"] for t in ("clamav", "semgrep")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
