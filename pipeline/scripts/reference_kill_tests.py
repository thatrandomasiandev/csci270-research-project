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

from acts.entry_hash import entry_content_hash
from acts.fasta import parse_fasta, write_fasta  # noqa: E402
from acts.reference_formats import PROFILE_VOLATILE_TAGS

PROTOCOL = "pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md"
SEED = 20261003
NEW = ROOT / "data" / "hmmer" / "Pfam-A.hmm.gz"            # 38.2
OLD = ROOT / "data" / "hmmer" / "pfam38.1" / "Pfam-A.hmm.gz"
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
    text = "".join(block)
    strict = entry_content_hash(text, PROFILE_VOLATILE_TAGS)
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
    from acts.reference_fit import half_ulp as _half_ulp

    return _half_ulp(printed)


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


DOM_E_COLS = {6: "full_seq_E", 11: "c_Evalue", 12: "i_Evalue"}


def domtbl(hmm: Path, fa: Path, work: Path, tag: str) -> dict[tuple[str, str, str], list[str]]:
    out = work / f"{tag}.domtbl"
    run(["hmmscan", "--cpu", "4", "--cut_ga", "--noali", "--domtblout", str(out), str(hmm), str(fa)])
    rows: dict[tuple[str, str, str], list[str]] = {}
    for line in out.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        tok = line.split()
        rows[(tok[3], tok[0], tok[9])] = tok  # (query, model, domain index)
    return rows


def dom_z(rows: dict) -> dict[str, int]:
    """Targets reported per query in one run (candidate data-dependent normalizer)."""
    per: dict[str, set[str]] = {}
    for (q, t, _d) in rows:
        per.setdefault(q, set()).add(t)
    return {q: len(ts) for q, ts in per.items()}


def r3(work: Path) -> dict:
    """domtblout on the R2p inputs (written by r2p in the same work dir layout)."""
    src = work.parent / "r2p"
    fa = src / "q.faa"
    work.mkdir(parents=True, exist_ok=True)
    full = domtbl(src / "R.hmm", fa, work, "R")
    h1 = domtbl(src / "R1.hmm", fa, work, "R1")
    h2 = domtbl(src / "R2.hmm", fa, work, "R2")
    z = {"R": _nmodels(src / "R.hmm"), "R1": _nmodels(src / "R1.hmm"), "R2": _nmodels(src / "R2.hmm")}
    union = {**h1, **h2}
    dz_full, dz1, dz2 = dom_z(full), dom_z(h1), dom_z(h2)
    set_ok = set(full) == set(union)
    mism = 0
    fits = {name: {"Z": 0, "domZ": 0, "n": 0} for name in DOM_E_COLS.values()}
    for key, tok in full.items():
        sub = union.get(key)
        if sub is None:
            continue
        in1 = key in h1
        zh = z["R1"] if in1 else z["R2"]
        dzh = (dz1 if in1 else dz2).get(key[0], 0)
        for i, (a, b) in enumerate(zip(tok, sub)):
            if i in DOM_E_COLS:
                f = fits[DOM_E_COLS[i]]
                f["n"] += 1
                for label, factor in (("Z", z["R"] / zh), ("domZ", dz_full.get(key[0], 0) / dzh if dzh else float("nan"))):
                    resc = float(b) * factor
                    if abs(resc - float(a)) <= half_ulp(a) + half_ulp(b) * factor:
                        f[label] += 1
            elif a != b:
                mism += 1
    assigned = {}
    for col, f in fits.items():
        ok = [lab for lab in ("Z", "domZ") if f["n"] and f[lab] == f["n"]]
        assigned[col] = ok or ["not reusable"]
    out = {
        "protocol": PROTOCOL, "git": git_head(), "inputs": "R2p (r2p work dir)",
        "domain_lines_full": len(full), "domain_lines_union": len(union),
        "check1_domain_set_equal": set_ok,
        "check2_unnormalized_mismatches": mism,
        "normalizer_fits": fits, "assigned_normalizer": assigned,
        "kill_rule": "check1 false or check2 mismatches > 0",
        "killed": (not set_ok) or mism > 0,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
    }
    (ROOT / "results" / "reference_kill_r3.json").write_text(json.dumps(out, indent=2) + "\n")
    return out


def _nmodels(hmm: Path) -> int:
    return sum(1 for ln in hmm.read_text().splitlines() if ln.startswith("//"))


def _tbl_dom_z(path: Path) -> dict[str, int]:
    per: dict[str, set[str]] = {}
    for line in path.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        tok = line.split()
        per.setdefault(tok[2], set()).add(tok[0])
    return {q: len(t) for q, t in per.items()}


def r3c(work: Path) -> dict:
    """Confirmatory c-Evalue test on fresh data (seed 20261004)."""
    seed = 20261004
    work.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    recs = parse_fasta(gzip.open(ROOT / "data" / "recurrence" / "A" / "GCF_002853805.1_protein.faa.gz", "rt").read())
    fa = write_fasta(work / "q.faa", rng.sample(recs, 300))
    blocks = [b for _, b in iter_models(NEW)]
    names = set((ROOT / "results" / "reference_kill_g1_hit_models.txt").read_text().split())
    name_of = lambda b: next((ln.split()[1] for ln in b if ln.startswith("NAME ")), "")
    hit = [b for b in blocks if name_of(b) in names]
    rest = [b for b in blocks if name_of(b) not in names]
    chosen = hit + random.Random(SEED).sample(rest, 1000)  # same 4,871 models as R2p
    idx = list(range(len(chosen)))
    rng.shuffle(idx)
    halves = {"R1": [chosen[i] for i in idx[: len(chosen) // 2]], "R2": [chosen[i] for i in idx[len(chosen) // 2 :]]}
    hmms = {"R": write_models(chosen, work / "R.hmm"), **{k: write_models(v, work / f"{k}.hmm") for k, v in halves.items()}}
    z = {"R": len(chosen), "R1": len(halves["R1"]), "R2": len(halves["R2"])}
    dz, dom = {}, {}
    for tag, hmm in hmms.items():
        tbl, dtbl = work / f"{tag}.tbl", work / f"{tag}.domtbl"
        run(["hmmscan", "--cpu", "4", "--cut_ga", "--noali", "--tblout", str(tbl), "--domtblout", str(dtbl), str(hmm), str(fa)])
        dz[tag] = _tbl_dom_z(tbl)
        rows = {}
        for line in dtbl.read_text().splitlines():
            if line.startswith("#") or not line.strip():
                continue
            tok = line.split()
            rows[(tok[3], tok[0], tok[9])] = tok
        dom[tag] = rows
    union = {**dom["R1"], **dom["R2"]}
    set_ok = set(dom["R"]) == set(union)
    mism = 0
    fit = {"full_seq_E": 0, "i_Evalue": 0, "c_Evalue": 0}
    n = 0
    for key, tok in dom["R"].items():
        sub = union.get(key)
        if sub is None:
            continue
        half = "R1" if key in dom["R1"] else "R2"
        n += 1
        for i, (a, b) in enumerate(zip(tok, sub)):
            if i in (6, 12):
                f = z["R"] / z[half]
                if abs(float(b) * f - float(a)) <= half_ulp(a) + half_ulp(b) * f:
                    fit["full_seq_E" if i == 6 else "i_Evalue"] += 1
            elif i == 11:
                dzh = dz[half].get(key[0], 0)
                f = dz["R"].get(key[0], 0) / dzh if dzh else float("nan")
                if dzh and abs(float(b) * f - float(a)) <= half_ulp(a) + half_ulp(b) * f:
                    fit["c_Evalue"] += 1
            elif a != b:
                mism += 1
    out = {
        "protocol": PROTOCOL, "git": git_head(), "seed": seed, "models_full": z["R"],
        "domain_lines_full": len(dom["R"]), "domain_lines_union": len(union),
        "check1_domain_set_equal": set_ok, "check2_unnormalized_mismatches": mism,
        "n_lines": n, "consistent": fit,
        "c_Evalue_reusable_tbl_domZ": set_ok and mism == 0 and fit["c_Evalue"] == n,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
    }
    (ROOT / "results" / "reference_kill_r3c.json").write_text(json.dumps(out, indent=2) + "\n")
    return out


if __name__ == "__main__":
    which = sys.argv[1]
    if which == "r1":
        print(json.dumps(r1(), indent=1))
    elif which in ("r2", "r2p", "r2n"):
        res = r2(Path(sys.argv[2]), powered=(which != "r2"), cut_ga=(which != "r2n"))
        print(json.dumps({k: v for k, v in res.items() if k != "examples"}, indent=1))
        print(json.dumps(res["examples"], indent=1))
    elif which == "r3c":
        print(json.dumps(r3c(Path(sys.argv[2])), indent=1))
    elif which == "r3":
        print(json.dumps(r3(Path(sys.argv[2])), indent=1))
    else:
        raise SystemExit("usage: reference_kill_tests.py r1 | r2|r2p|r2n|r3 WORKDIR")
