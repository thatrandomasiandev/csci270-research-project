#!/usr/bin/env python3
"""Reference-side incrementality kill tests (docs/REFERENCE_INCREMENTAL_PROTOCOL.md).

  r1  Pfam churn between two releases (strict and body hashes per model)
  r2  hmmscan --cut_ga decomposition over a split model set, plus the E-value
      normalizer E_R = E_half * Z_R / Z_half

Writes results/reference_kill_r1.json and results/reference_kill_r2.json.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.fasta import parse_fasta, write_fasta  # noqa: E402

PROTOCOL = "pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md"
SEED = 20261003
NEW = ROOT / "data" / "hmmer" / "Pfam-A.hmm.gz"            # 38.2
OLD = ROOT / "data" / "hmmer" / "pfam38.1" / "Pfam-A.hmm.gz"
NO_EFFECT = ("DATE", "BM  ", "SM  ", "COM ")               # cannot change hmmscan --tblout
EVALUE_COLS = (4, 7)                                       # full-seq E, best-domain E (0-based)


def git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def iter_models(path: Path):
    """Yield (accession_without_version, block_lines) for each model."""
    block: list[str] = []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            block.append(line)
            if line.startswith("//"):
                acc = next((ln.split()[1] for ln in block if ln.startswith("ACC ")), "")
                yield acc.split(".")[0], block
                block = []


def model_hashes(block: list[str]) -> tuple[str, str]:
    strict = hashlib.sha256(
        "".join(ln for ln in block if not ln.startswith(NO_EFFECT)).encode()
    ).hexdigest()
    in_body = False
    body: list[str] = []
    for ln in block:
        if ln.startswith("GA  "):
            body.append(ln)
        if ln.startswith("HMM "):
            in_body = True
        if in_body:
            body.append(ln)
    return strict, hashlib.sha256("".join(body).encode()).hexdigest()


def r1() -> dict:
    old = {acc: model_hashes(b) for acc, b in iter_models(OLD)}
    new = {acc: model_hashes(b) for acc, b in iter_models(NEW)}
    shared = set(old) & set(new)
    strict_same = sum(1 for a in shared if old[a][0] == new[a][0])
    body_same = sum(1 for a in shared if old[a][1] == new[a][1])
    out = {
        "protocol": PROTOCOL, "git": git_head(),
        "old_release": "Pfam 38.1", "new_release": "Pfam 38.2",
        "z_old": len(old), "z_new": len(new),
        "added": len(set(new) - set(old)), "removed": len(set(old) - set(new)),
        "shared": len(shared),
        "unchanged_strict": strict_same, "unchanged_body": body_same,
        "frac_new_unchanged_strict": strict_same / len(new),
        "frac_new_unchanged_body": body_same / len(new),
        "kill_rule": "frac_new_unchanged_strict < 0.5",
        "killed": strict_same / len(new) < 0.5,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
    }
    (ROOT / "results" / "reference_kill_r1.json").write_text(json.dumps(out, indent=2) + "\n")
    return out


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def write_models(blocks: list[list[str]], path: Path) -> Path:
    path.write_text("".join("".join(b) for b in blocks))
    run(["hmmpress", "-f", str(path)])
    return path


def tblout(
    hmm: Path, fa: Path, work: Path, tag: str, cut_ga: bool = True
) -> dict[tuple[str, str], list[str]]:
    out = work / f"{tag}.tbl"
    thresh = ["--cut_ga"] if cut_ga else []
    run(["hmmscan", "--cpu", "4", *thresh, "--noali", "--tblout", str(out), str(hmm), str(fa)])
    hits: dict[tuple[str, str], list[str]] = {}
    for line in out.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        tok = line.split()
        hits[(tok[2], tok[0])] = tok  # (query, model)
    return hits


def fmt_like(printed: str, value: float) -> str:
    """Re-print `value` with the same significant digits as HMMER printed `printed`."""
    mant = printed.lower().split("e")[0]
    digits = len(mant.replace(".", "").replace("-", "").lstrip("0")) or 1
    return f"{value:.{max(digits - 1, 0)}e}" if "e" in printed.lower() else f"{value:.{len(mant.split('.')[1]) if '.' in mant else 0}f}"


def same_number(a: str, b: str) -> bool:
    try:
        return float(a) == float(b)
    except ValueError:
        return a == b


def half_ulp(printed: str) -> float:
    s = printed.lower()
    mant, _, exp = s.partition("e")
    dec = len(mant.split(".")[1]) if "." in mant else 0
    return 0.5 * 10 ** (-dec) * (10 ** int(exp) if exp else 1)


def r2(work: Path, powered: bool = False, cut_ga: bool = True) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    recs = parse_fasta(gzip.open(ROOT / "data" / "recurrence" / "A" / "GCF_002853805.1_protein.faa.gz", "rt").read())
    fa = write_fasta(work / "q.faa", rng.sample(recs, 300))
    blocks = [b for _, b in iter_models(NEW)]
    if powered:
        names = set((ROOT / "results" / "reference_kill_g1_hit_models.txt").read_text().split())
        name_of = lambda b: next((ln.split()[1] for ln in b if ln.startswith("NAME ")), "")
        hit = [b for b in blocks if name_of(b) in names]
        rest = [b for b in blocks if name_of(b) not in names]
        chosen = hit + rng.sample(rest, 1000)
    else:
        chosen = rng.sample(blocks, 400)
    n_models = len(chosen)
    idx = list(range(n_models))
    rng.shuffle(idx)
    half1 = [chosen[i] for i in idx[: n_models // 2]]
    half2 = [chosen[i] for i in idx[n_models // 2 :]]
    full = tblout(write_models(chosen, work / "R.hmm"), fa, work, "R", cut_ga)
    h1 = tblout(write_models(half1, work / "R1.hmm"), fa, work, "R1", cut_ga)
    h2 = tblout(write_models(half2, work / "R2.hmm"), fa, work, "R2", cut_ga)
    z_full = n_models
    union = {**h1, **h2}
    hitset_ok = set(full) == set(union)
    col_mismatch = 0
    ev_total = ev_byte = ev_consistent = 0
    examples = []
    for key, tok in full.items():
        sub = union.get(key)
        if sub is None:
            continue
        z_half = len(half1) if key in h1 else len(half2)
        for i, (a, b) in enumerate(zip(tok, sub)):
            if i in EVALUE_COLS:
                ev_total += 1
                rescaled = float(b) * z_full / z_half
                reprinted = fmt_like(a, rescaled)
                if same_number(reprinted, a):
                    ev_byte += 1
                if abs(rescaled - float(a)) <= half_ulp(a) + half_ulp(b) * z_full / z_half:
                    ev_consistent += 1
                elif len(examples) < 5:
                    examples.append({"key": key, "col": i, "full": a, "half": b, "rescaled": rescaled})
            elif a != b:
                col_mismatch += 1
                if len(examples) < 5:
                    examples.append({"key": key, "col": i, "full": a, "half": b})
        if len(tok) != len(sub):
            col_mismatch += 1
    out = {
        "protocol": PROTOCOL, "git": git_head(), "seed": SEED,
        "hmmer": run(["hmmscan", "-h"]).splitlines()[1],
        "queries": 300, "models_full": z_full, "models_halves": [len(half1), len(half2)],
        "powered": powered, "cut_ga": cut_ga,
        "hits_only_in_union": len(set(union) - set(full)),
        "hits_only_in_full": len(set(full) - set(union)),
        "hits_full": len(full), "hits_union": len(union),
        "check1_hitset_equal": hitset_ok,
        "check2_unnormalized_mismatches": col_mismatch,
        "evalue_tokens": ev_total,
        "evalue_byte_reproducible": ev_byte,
        "evalue_consistent_within_print": ev_consistent,
        "examples": examples,
        "kill_rule": "check1 false or check2 mismatches > 0",
        "killed": (not hitset_ok) or col_mismatch > 0,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
    }
    name = ("reference_kill_r2p.json" if cut_ga else "reference_kill_r2n.json") if powered else "reference_kill_r2.json"
    (ROOT / "results" / name).write_text(json.dumps(out, indent=2) + "\n")
    return out


if __name__ == "__main__":
    which = sys.argv[1]
    if which == "r1":
        print(json.dumps(r1(), indent=1))
    elif which in ("r2", "r2p", "r2n"):
        res = r2(Path(sys.argv[2]), powered=(which != "r2"), cut_ga=(which != "r2n"))
        print(json.dumps({k: v for k, v in res.items() if k != "examples"}, indent=1))
        print(json.dumps(res["examples"], indent=1))
    else:
        raise SystemExit("usage: reference_kill_tests.py r1 | r2 WORKDIR")
