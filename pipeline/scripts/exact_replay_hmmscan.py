#!/usr/bin/env python3
"""E1/E2 of docs/EXACT_REPLAY_PROTOCOL.md: pinned-normalizer replay for hmmscan.

Experiment driver, not the shipped path. Body = lines not starting with '#'.
"""
from __future__ import annotations

import argparse, gzip, hashlib, json, os, platform, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acts.entry_hash import entry_content_hash  # noqa: E402
from acts.reference_formats import PROFILE_VOLATILE_TAGS  # noqa: E402


def strict_entry_hash(block: str) -> str:
    return entry_content_hash(block, PROFILE_VOLATILE_TAGS)

HMMER = os.environ.get("HMMER_BIN", "")


def tool(name: str) -> str:
    return str(Path(HMMER) / name) if HMMER else name


def iter_models(path: Path):
    """Yield (name, acc, block_text) in file order from a (gzipped) HMMER3 text file."""
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt") as fh:
        buf: list[str] = []
        name = acc = ""
        for line in fh:
            buf.append(line)
            if line.startswith("NAME "):
                name = line.split(None, 1)[1].strip()
            elif line.startswith("ACC "):
                acc = line.split(None, 1)[1].strip()
            elif line.startswith("//"):
                yield name, acc, "".join(buf)
                buf, name, acc = [], "", ""


def body(path: Path) -> list[str]:
    return [l for l in path.read_text().splitlines(keepends=True) if not l.startswith("#")]


def hits(tbl: Path) -> dict[str, list[str]]:
    """query -> target names (tblout: col0 target, col2 query)."""
    out: dict[str, list[str]] = {}
    for line in body(tbl):
        f = line.split()
        out.setdefault(f[2], []).append(f[0])
    return out


def write_db(models, keep: set[str], dest: Path) -> int:
    n = 0
    with open(dest, "w") as fh:
        for name, _acc, block in models:
            if name in keep:
                fh.write(block); n += 1
    for ext in (".h3f", ".h3i", ".h3m", ".h3p"):
        p = Path(str(dest) + ext)
        if p.exists():
            p.unlink()
    subprocess.run([tool("hmmpress"), "-f", str(dest)], check=True, capture_output=True)
    return n


def subset_fasta(src: Path, keep: set[str], dest: Path) -> int:
    n, on, out = 0, False, []
    for line in src.read_text().splitlines(keepends=True):
        if line.startswith(">"):
            on = line[1:].split()[0] in keep
            n += on
        if on:
            out.append(line)
    dest.write_text("".join(out))
    return n


def scan(db: Path, q: Path, tag: Path, cpu: int, z: int | None) -> float:
    cmd = [tool("hmmscan"), "--cut_ga", "--noali", "--cpu", str(cpu)]
    if z is not None:
        cmd += ["-Z", str(z)]
    cmd += ["--tblout", f"{tag}.tbl", "--domtblout", f"{tag}.dom", "-o", os.devnull, str(db), str(q)]
    t = time.perf_counter()
    subprocess.run(cmd, check=True)
    return time.perf_counter() - t


def compare(a: str, b: str) -> dict:
    res = {}
    for ext in ("tbl", "dom"):
        x, y = body(Path(f"{a}.{ext}")), body(Path(f"{b}.{ext}"))
        diff = sum(1 for i in range(max(len(x), len(y))) if (x[i] if i < len(x) else None) != (y[i] if i < len(y) else None))
        res[ext] = {"lines_a": len(x), "lines_b": len(y), "equal": x == y, "differing_positions": diff}
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--queries", type=Path, required=True)
    ap.add_argument("--new-gz", type=Path, required=True)
    ap.add_argument("--stock-new", required=True, help="tag of stock run on new release (S)")
    ap.add_argument("--old-gz", type=Path)
    ap.add_argument("--stock-old", help="tag of stock run on old release (S1); enables E2")
    ap.add_argument("--cpu", type=int, default=4)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    w = a.work
    new_models = list(iter_models(a.new_gz))
    z_new = len(new_models)
    report: dict = {"protocol": "docs/EXACT_REPLAY_PROTOCOL.md", "z_new": z_new,
                    "host": platform.node(), "machine": platform.machine(),
                    "hmmscan": subprocess.run([tool("hmmscan"), "-h"], capture_output=True, text=True).stdout.splitlines()[1]}
    S = hits(Path(f"{a.stock_new}.tbl"))

    # E1: oracle candidates = S's hits.
    keep = {t for ts in S.values() for t in ts}
    nq = subset_fasta(a.queries, set(S), w / "e1_q.faa")
    nm = write_db(new_models, keep, w / "e1_db.hmm")
    t_r = scan(w / "e1_db.hmm", w / "e1_q.faa", w / "e1_R", a.cpu, z_new)
    t_rn = scan(w / "e1_db.hmm", w / "e1_q.faa", w / "e1_Rn", a.cpu, None)
    c1, c2 = compare(f"{w}/e1_R", a.stock_new), compare(f"{w}/e1_Rn", a.stock_new)
    report["E1"] = {"queries_replayed": nq, "models_replayed": nm, "wall_R_s": t_r, "wall_Rn_s": t_rn,
                    "check1_R_vs_S": c1, "check2_Rn_vs_S": c2,
                    "check1_pass": all(v["equal"] for v in c1.values()),
                    "check2_pass": not all(v["equal"] for v in c2.values())}
    report["E1"]["killed"] = not report["E1"]["check1_pass"]

    if a.stock_old and a.old_gz:
        t0 = time.perf_counter()
        old_hash = {name: strict_entry_hash(block) for name, _acc, block in iter_models(a.old_gz)}
        changed = {name for name, _acc, block in new_models if old_hash.get(name) != strict_entry_hash(block)}
        t_diff = time.perf_counter() - t0
        S1 = hits(Path(f"{a.stock_old}.tbl"))
        new_names = {m[0] for m in new_models}
        cached = {q: [t for t in ts if t in new_names and t not in changed] for q, ts in S1.items()}
        t0 = time.perf_counter()
        n_changed = write_db(new_models, changed, w / "e2_disc.hmm")
        t_build_disc = time.perf_counter() - t0
        t_disc = scan(w / "e2_disc.hmm", a.queries, w / "e2_D", a.cpu, z_new)
        D = hits(w / "e2_D.tbl")
        cand: dict[str, set[str]] = {}
        for src in (cached, D):
            for q, ts in src.items():
                cand.setdefault(q, set()).update(ts)
        cand = {q: ts for q, ts in cand.items() if ts}
        union = set().union(*cand.values()) if cand else set()
        t0 = time.perf_counter()
        nq2 = subset_fasta(a.queries, set(cand), w / "e2_q.faa")
        nm2 = write_db(new_models, union, w / "e2_db.hmm")
        t_build_rep = time.perf_counter() - t0
        t_rep = scan(w / "e2_db.hmm", w / "e2_q.faa", w / "e2_R", a.cpu, z_new)
        c = compare(f"{w}/e2_R", a.stock_new)
        report["E2"] = {"changed_or_new_models": n_changed, "candidate_queries": nq2, "replay_models": nm2,
                        "candidate_pairs": sum(len(v) for v in cand.values()),
                        "wall_s": {"diff": t_diff, "build_discovery_db": t_build_disc, "discovery_scan": t_disc,
                                   "build_replay_db": t_build_rep, "replay_scan": t_rep},
                        "check_vs_S": c, "pass": all(v["equal"] for v in c.values())}
        report["E2"]["killed"] = not report["E2"]["pass"]
    a.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
