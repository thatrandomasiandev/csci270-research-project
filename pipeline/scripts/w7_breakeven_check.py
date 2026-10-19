#!/usr/bin/env python3
"""Laptop correctness check for TARE's break-even gate.

The check asks whether an update whose changed fraction is above the
threshold runs the stock command and writes that command's output.
It does not time the gate. Any wall clock recorded here is laptop
bookkeeping, not a speed claim.

Semantics this script is built around, reviewed before the pilot run:

- The shipped reference command pins ``-Z {entry_count}`` and runs
  ``hmmscan --cut_ga``. ``--cut_ga`` reports on gathering thresholds stored
  in the model. The pin is still passed because that is the shipped exact
  path. The gate's stock run uses the argv without the pin. The comparison
  stock run uses that same unpinned argv.
- ``hmmscan`` with more than one thread is not a byte-stable oracle here.
  ``--cpu 1`` stays inside the two-thread cap and is what both arms use.
- A full-size call uses the caller's reference file and does not prep it.
  Both subset files are ``hmmpress``-ed before TARE runs.
- The gate's changed fraction is the share of new entries whose content
  hash is absent from the cache. Volatile profile tags are DATE, BM, SM,
  and COM, the same list the parser uses. Accession identity is not the
  fraction.
- A cold cache is a fill. The fill is required to SHIP. The update is the
  gated run.
- ``--audit-p 0`` keeps the decision on the gate. Equality is a separate
  stock comparison, not the audit sample.
- An empty body can match and still prove nothing. The query is the
  proteins a stock search of that subset reports, so the comparison has
  rows. The changed fraction does not depend on which proteins those are.
  Below the threshold, or with no reported row, the measured result is
  INCONCLUSIVE.
- Stock-vs-stock disagreement stops the check. That is a blind comparison,
  not a gate failure.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import random
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from acts.entry_hash import entry_content_hash  # noqa: E402
from acts.fasta import parse_fasta  # noqa: E402
from acts.reference_formats import PROFILE_VOLATILE_TAGS, iter_profile_raw, parse_reference  # noqa: E402
from acts.reference_run import DEFAULT_BREAK_EVEN_F, body_lines  # noqa: E402
from coupling_shim import diff_class  # noqa: E402

PFAM_OLD = Path.home() / "tmp" / "tare_c" / "Pfam37.4" / "Pfam-A.hmm.gz"
PFAM_NEW = Path.home() / "tmp" / "tare_c" / "Pfam38.0" / "Pfam-A.hmm.gz"
SCRATCH = Path.home() / "tmp" / "tare_w7"
INDEX_PATH = SCRATCH / "pfam_37.4_38.0_index.json"
PILOT_GENOME = Path(
    "/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data_confirm/E/GCF_024971875.1_protein.faa.gz"
)
MEASURED_GENOME = Path(
    "/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data_confirm/E/GCF_021554655.1_protein.faa.gz"
)

PILOT_SEED = 20261211
PILOT_QUERY_SEED = 20261213
MEASURED_SEED = 20261212
MEASURED_QUERY_SEED = 20261214
PILOT_N = 30
PILOT_LOW_UNCHANGED = 22
PILOT_LOW_CHANGED = 2
PILOT_QUERY_N = 4
# Locked after the pilot. The measured draw is disjoint from the pilot stems.
MEASURED_N = 40
MEASURED_QUERY_N = 8
MIN_MODELS = 20

RESULT_DIR = ROOT / "results" / "breakeven"
CPU = "1"


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip()


def git_dirty() -> bool:
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(proc.stdout.strip())


def tag_value(text: str, tag: str) -> str | None:
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == tag and len(parts) > 1:
            return parts[1]
    return None


def stem_of(raw: str) -> str:
    token = tag_value(raw, "ACC") or tag_value(raw, "NAME") or ""
    return token.split(".", 1)[0]


def content_hash(raw: str) -> str:
    text = raw if raw.endswith("\n") else raw + "\n"
    return entry_content_hash(text, PROFILE_VOLATILE_TAGS)


def index_release(path: Path) -> dict:
    stems: dict[str, str] = {}
    n_blocks = 0
    for raw in iter_profile_raw(path):
        n_blocks += 1
        stems[stem_of(raw)] = content_hash(raw)
    return {"n_blocks": n_blocks, "n_stems": len(stems), "stems": stems}


def load_index() -> dict:
    if INDEX_PATH.is_file():
        return json.loads(INDEX_PATH.read_text())
    print("indexing Pfam 37.4 and 38.0", flush=True)
    payload = {
        "old": index_release(PFAM_OLD),
        "new": index_release(PFAM_NEW),
        "old_path": str(PFAM_OLD),
        "new_path": str(PFAM_NEW),
        "old_md5": md5_file(PFAM_OLD),
        "new_md5": md5_file(PFAM_NEW),
    }
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(payload))
    return payload


def write_subset(source: Path, stems: list[str], dest: Path) -> None:
    wanted = set(stems)
    found: dict[str, str] = {}
    order: list[str] = []
    for raw in iter_profile_raw(source):
        stem = stem_of(raw)
        if stem not in wanted:
            continue
        if stem not in found:
            order.append(stem)
        text = raw if raw.endswith("\n") else raw + "\n"
        found[stem] = text
    missing = wanted - set(found)
    if missing:
        raise SystemExit(f"{source.name} is missing {sorted(missing)[:5]}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(found[stem] for stem in order))


def fraction(old_path: Path, new_path: Path) -> dict:
    old_hashes = {entry.content_hash for entry in parse_reference(old_path)}
    new_entries = parse_reference(new_path)
    fresh = sum(1 for entry in new_entries if entry.content_hash not in old_hashes)
    n_new = len(new_entries)
    return {
        "n_old": len(old_hashes),
        "n_new": n_new,
        "n_fresh": fresh,
        "f_delta": (fresh / n_new) if n_new else None,
    }


def decompress_fasta(genome: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(genome, "rt") as src, dest.open("w") as out:
        shutil.copyfileobj(src, out)


def query_ids_from_tbl(path: Path) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for line in body_lines(path.read_text()):
        cells = line.split()
        if len(cells) < 3 or cells[2] in seen:
            continue
        seen.add(cells[2])
        found.append(cells[2])
    return found


def write_named_query(genome_faa: Path, ids: list[str], dest: Path) -> None:
    by_name = {rec.name: rec for rec in parse_fasta(genome_faa.read_text())}
    missing = [name for name in ids if name not in by_name]
    if missing:
        raise SystemExit(f"query ids missing from {genome_faa.name}: {missing[:3]}")
    lines = []
    for name in ids:
        rec = by_name[name]
        lines.append(f">{rec.name} {rec.description}".rstrip())
        lines.append(rec.seq)
    dest.write_text("\n".join(lines) + "\n")


def choose_hitting_query(
    reference: Path,
    genome: Path,
    genome_faa: Path,
    dest: Path,
    *,
    n: int,
    seed: int,
    exclude: set[str] | None = None,
) -> dict | None:
    """Proteins this subset reports, so equality is not an empty-body identity."""
    scan_dir = dest.parent / f"{dest.stem}_hitscan"
    stock_scan(reference, genome_faa, scan_dir)
    ids = [name for name in query_ids_from_tbl(scan_dir / "tblout") if name not in (exclude or set())]
    if not ids:
        return None
    order = list(ids)
    random.Random(seed).shuffle(order)
    chosen = order[:n]
    write_named_query(genome_faa, chosen, dest)
    return {
        "genome": str(genome),
        "genome_md5": md5_file(genome),
        "n_hit_queries": len(ids),
        "n_query": len(chosen),
        "seed": seed,
        "ids": chosen,
        "query_md5": md5_file(dest),
    }


def press(path: Path) -> None:
    proc = subprocess.run(["hmmpress", "-f", str(path)], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr[-500:] or proc.stdout[-500:])


def stock_scan(reference: Path, query: Path, dest: Path) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    argv = [
        "hmmscan", "--cut_ga", "--noali", "--cpu", CPU,
        "--tblout", str(dest / "tblout"),
        "--domtblout", str(dest / "domtblout"),
        "-o", "/dev/null",
        str(reference), str(query),
    ]
    started = time.perf_counter()
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    wall = time.perf_counter() - started
    if proc.returncode != 0:
        raise SystemExit(f"stock hmmscan failed: {(proc.stderr or proc.stdout)[-500:]}")
    return {"argv": argv, "wall_s": wall, "returncode": proc.returncode}


def tare_run(reference: Path, query: Path, cache: Path, out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    argv = [
        sys.executable, "-m", "acts", "run",
        "--strategy", "reference",
        "--pin", "-Z {entry_count}",
        "--verify", "audit",
        "--audit-p", "0",
        "--prep", "hmmpress -f {reference}",
        "--input", str(query),
        "--reference", str(reference),
        "--cache", str(cache),
        "-o", str(out),
        "--",
        "hmmscan", "--cut_ga", "--noali", "--cpu", CPU,
        "--tblout", "{output:tblout}",
        "--domtblout", "{output:domtblout}",
        "-o", "/dev/null",
        "{reference}", "{input}",
    ]
    started = time.perf_counter()
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
    wall = time.perf_counter() - started
    decision_path = out / "decision.txt"
    decision = {}
    if decision_path.is_file():
        for line in decision_path.read_text().splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            decision[key.strip()] = value.strip()
    return {
        "argv": argv,
        "wall_s": wall,
        "returncode": proc.returncode,
        "decision": decision.get("decision"),
        "why": decision.get("why"),
        "f_delta": decision.get("f_delta"),
        "f_threshold": decision.get("f_threshold"),
        "f_threshold_source": decision.get("f_threshold_source"),
        "stdout_tail": (proc.stdout or "")[-400:],
        "stderr_tail": (proc.stderr or "")[-400:],
    }


def compare_tables(stock: Path, tare: Path) -> dict:
    report = {}
    for name in ("tblout", "domtblout"):
        stock_lines = body_lines((stock / name).read_text())
        got_lines = body_lines((tare / "tables" / name).read_text())
        kind = diff_class(stock_lines, got_lines)
        report[name] = {"class": kind, "n_stock": len(stock_lines), "n_tare": len(got_lines)}
    report["equal"] = all(row["class"] == "identical" for row in report.values() if isinstance(row, dict))
    return report


def comparator_controls() -> dict:
    """Known-good and known-bad for the difference classes, before any search."""
    same = diff_class(["m q 1.0"], ["m q 1.0"])
    value = diff_class(["m q 1.0"], ["m q 2.0"])
    missing = diff_class(["m q 1.0"], [])
    extra = diff_class([], ["m q 1.0"])
    order = diff_class(["m q 1", "n q 1"], ["n q 1", "m q 1"])
    ok = same == "identical" and value == "value-only" and missing == "missing" and extra == "extra" and order == "order"
    return {
        "pass": ok,
        "identical": same,
        "value-only": value,
        "missing": missing,
        "extra": extra,
        "order": order,
    }


def tool_versions() -> dict:
    proc = subprocess.run(["hmmscan", "-h"], capture_output=True, text=True, check=False)
    line = next((item for item in proc.stdout.splitlines() if "HMMER" in item), "")
    binary = shutil.which("hmmscan") or ""
    return {
        "hmmscan": line.strip(),
        "hmmscan_path": binary,
        "hmmscan_md5": md5_file(Path(binary)) if binary else None,
        "python": platform.python_version(),
    }


def host_block() -> dict:
    cpu = ""
    try:
        cpu = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
    except OSError:
        cpu = platform.processor()
    return {"host": socket.gethostname(), "cpu": cpu, "system": platform.platform()}


def classify_pair(stems_new: dict[str, str], stems_old: dict[str, str]) -> tuple[list[str], list[str]]:
    unchanged = []
    changed = []
    for stem, digest in stems_new.items():
        old = stems_old.get(stem)
        if old is None:
            changed.append(stem)
        elif old == digest:
            unchanged.append(stem)
        else:
            changed.append(stem)
    return unchanged, changed


def sample_pair(index: dict, stems: list[str], dest: Path) -> dict:
    old_path = dest / "old.hmm"
    new_path = dest / "new.hmm"
    write_subset(PFAM_OLD, [stem for stem in stems if stem in index["old"]["stems"]], old_path)
    write_subset(PFAM_NEW, stems, new_path)
    # A stem that exists only in the new release is not in the old file.
    # fraction() reads the files the gate will see.
    stats = fraction(old_path, new_path)
    press(old_path)
    press(new_path)
    stats["stems"] = stems
    stats["old_md5"] = md5_file(old_path)
    stats["new_md5"] = md5_file(new_path)
    return stats


def run_pair(dest: Path, query: Path, label: str) -> dict:
    cache = dest / "cache.sqlite"
    if cache.exists():
        cache.unlink()
    fill = tare_run(dest / "old.hmm", query, cache, dest / "fill")
    update = tare_run(dest / "new.hmm", query, cache, dest / "update")
    stock_a = stock_scan(dest / "new.hmm", query, dest / "stock_a")
    stock_b = stock_scan(dest / "new.hmm", query, dest / "stock_b")
    direct = {}
    for name in ("tblout", "domtblout"):
        a = body_lines((dest / "stock_a" / name).read_text())
        b = body_lines((dest / "stock_b" / name).read_text())
        direct[name] = diff_class(a, b)
    stock_equal = all(kind == "identical" for kind in direct.values())
    tare_vs_stock = None
    if (dest / "update" / "tables" / "tblout").is_file():
        tare_vs_stock = compare_tables(dest / "stock_a", dest / "update")
    return {
        "label": label,
        "fill": fill,
        "update": update,
        "stock_vs_stock": direct,
        "stock_vs_stock_equal": stock_equal,
        "tare_vs_stock": tare_vs_stock,
        "stock_wall_s_not_a_speed_claim": [stock_a["wall_s"], stock_b["wall_s"]],
    }


def pilot(index: dict) -> dict:
    controls = comparator_controls()
    if not controls["pass"]:
        raise SystemExit(f"comparator controls failed: {controls}")
    unchanged, changed = classify_pair(index["new"]["stems"], index["old"]["stems"])
    rng = random.Random(PILOT_SEED)
    high_stems = rng.sample(sorted(index["new"]["stems"]), PILOT_N)
    low_pool_u = rng.sample(unchanged, PILOT_LOW_UNCHANGED)
    low_pool_c = rng.sample(changed, PILOT_LOW_CHANGED)
    low_stems = low_pool_u + low_pool_c
    work = SCRATCH / "pilot"
    if work.exists():
        shutil.rmtree(work)
    high_dir = work / "high"
    low_dir = work / "low"
    high = sample_pair(index, high_stems, high_dir)
    low = sample_pair(index, low_stems, low_dir)
    genome_faa = work / "genome.faa"
    decompress_fasta(PILOT_GENOME, genome_faa)
    high_query = choose_hitting_query(
        high_dir / "new.hmm", PILOT_GENOME, genome_faa, work / "high_query.faa",
        n=PILOT_QUERY_N, seed=PILOT_QUERY_SEED,
    )
    low_query = choose_hitting_query(
        low_dir / "new.hmm", PILOT_GENOME, genome_faa, work / "low_query.faa",
        n=PILOT_QUERY_N, seed=PILOT_QUERY_SEED,
    )
    if high_query is None or low_query is None:
        raise SystemExit("pilot subset reported no proteins; the equality check would be empty")
    high_run = run_pair(high_dir, work / "high_query.faa", "high")
    low_run = run_pair(low_dir, work / "low_query.faa", "low")
    high_rows = ((high_run["tare_vs_stock"] or {}).get("tblout") or {}).get("n_stock", 0)
    low_rows = ((low_run["tare_vs_stock"] or {}).get("tblout") or {}).get("n_stock", 0)
    high_ok = (
        high["f_delta"] is not None
        and high["f_delta"] > DEFAULT_BREAK_EVEN_F
        and high_rows >= 1
        and high_run["fill"]["decision"] == "SHIP"
        and high_run["update"]["decision"] == "FALLBACK"
        and str(high_run["update"]["why"] or "").startswith("fallback: f_delta=")
        and "> threshold=" in (high_run["update"]["why"] or "")
        and high_run["stock_vs_stock_equal"]
        and (high_run["tare_vs_stock"] or {}).get("equal") is True
    )
    low_ok = (
        low["f_delta"] is not None
        and low["f_delta"] <= DEFAULT_BREAK_EVEN_F
        and low_rows >= 1
        and low_run["fill"]["decision"] == "SHIP"
        and low_run["update"]["decision"] == "SHIP"
        and "exact replay" in (low_run["update"]["why"] or "")
        and "fallback:" not in (low_run["update"]["why"] or "")
        and low_run["stock_vs_stock_equal"]
        and (low_run["tare_vs_stock"] or {}).get("equal") is True
    )
    payload = {
        "system": "TARE",
        "phase": "pilot",
        "laptop_wall_times_are_a_speed_claim": False,
        "git_head": git_head(),
        "seeds": {"models": PILOT_SEED, "query": PILOT_QUERY_SEED},
        "threshold_default": DEFAULT_BREAK_EVEN_F,
        "host": host_block(),
        "tools": tool_versions(),
        "query": {"high": high_query, "low": low_query},
        "comparator_controls": controls,
        "high": {**high, "run": high_run, "pass": high_ok},
        "low": {**{k: v for k, v in low.items() if k != "stems"}, "n_stems": len(low_stems), "run": low_run, "pass": low_ok},
        "pilot_stems": sorted(set(high_stems) | set(low_stems)),
        "pass": controls["pass"] and high_ok and low_ok,
    }
    # Stems are needed by the measured exclusion and are not huge.
    payload["high_stems"] = high_stems
    payload["low_stems"] = low_stems
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    (RESULT_DIR / "pilot.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"pass": payload["pass"], "high_f": high["f_delta"], "low_f": low["f_delta"],
                      "high_decision": high_run["update"]["decision"],
                      "low_decision": low_run["update"]["decision"],
                      "high_why": high_run["update"]["why"],
                      "low_why": low_run["update"]["why"]}, indent=2))
    return payload


def measured(index: dict) -> dict:
    if git_dirty():
        raise SystemExit("measured run requires a clean worktree so the frozen commit is the code that ran")
    pilot_path = RESULT_DIR / "pilot.json"
    if not pilot_path.is_file():
        raise SystemExit("pilot.json is missing; the measured draw cannot exclude it")
    pilot_payload = json.loads(pilot_path.read_text())
    if not pilot_payload.get("pass"):
        raise SystemExit("pilot did not pass; measured run stays locked")
    excluded = set(pilot_payload["pilot_stems"])
    pool = [stem for stem in index["new"]["stems"] if stem not in excluded]
    rng = random.Random(MEASURED_SEED)
    stems = rng.sample(pool, MEASURED_N)
    work = SCRATCH / "measured"
    if work.exists():
        shutil.rmtree(work)
    pilot_ids = set(pilot_payload["query"]["high"]["ids"]) | set(pilot_payload["query"]["low"]["ids"])
    # The pilot genome and the measured genome are different files. Exclude ids anyway.
    genome_faa = work / "genome.faa"
    decompress_fasta(MEASURED_GENOME, genome_faa)
    stats = sample_pair(index, stems, work)
    query_info = choose_hitting_query(
        work / "new.hmm", MEASURED_GENOME, genome_faa, work / "query.faa",
        n=MEASURED_QUERY_N, seed=MEASURED_QUERY_SEED, exclude=pilot_ids,
    )
    if query_info is None:
        payload = {
            "system": "TARE",
            "phase": "measured",
            "laptop_wall_times_are_a_speed_claim": False,
            "git_head": git_head(),
            "frozen_code_commit": git_head(),
            "outcome": "INCONCLUSIVE",
            "reason": "the measured subset reported no protein, so equality would be an empty body",
            "pair": {key: value for key, value in stats.items() if key != "stems"},
        }
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        (RESULT_DIR / "measured.json").write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps({"outcome": payload["outcome"], "reason": payload["reason"]}, indent=2))
        return payload
    run = run_pair(work, work / "query.faa", "measured")
    f_delta = stats["f_delta"]
    decision = run["update"]["decision"]
    why = run["update"]["why"] or ""
    equal = (run["tare_vs_stock"] or {}).get("equal") is True
    n_stock = ((run["tare_vs_stock"] or {}).get("tblout") or {}).get("n_stock", 0)
    if not run["stock_vs_stock_equal"]:
        outcome = "INCONCLUSIVE"
        reason = "stock-vs-stock was not identical; the comparison is blind"
    elif run["fill"]["decision"] == "FALLBACK":
        outcome = "FAIL"
        reason = "the cold-cache fill took the stock fallback"
    elif stats["n_new"] < MIN_MODELS:
        outcome = "INCONCLUSIVE"
        reason = "fewer than the locked minimum of models"
    elif f_delta is None or f_delta <= DEFAULT_BREAK_EVEN_F:
        outcome = "INCONCLUSIVE"
        reason = "changed fraction is not above the threshold; the gate cannot be observed"
    elif n_stock < 1:
        outcome = "INCONCLUSIVE"
        reason = "stock reported no row on the chosen proteins"
    elif decision == "FALLBACK" and why.startswith("fallback: f_delta=") and "> threshold=" in why and equal:
        outcome = "PASS"
        reason = "gate fell back and both tables match stock"
    else:
        outcome = "FAIL"
        reason = "changed fraction is above the threshold but the gate or the stock match did not hold"
    payload = {
        "system": "TARE",
        "phase": "measured",
        "laptop_wall_times_are_a_speed_claim": False,
        "git_head": git_head(),
        "frozen_code_commit": git_head(),
        "seeds": {"models": MEASURED_SEED, "query": MEASURED_QUERY_SEED},
        "excluded_pilot_stems": len(excluded),
        "threshold_default": DEFAULT_BREAK_EVEN_F,
        "min_models": MIN_MODELS,
        "host": host_block(),
        "tools": tool_versions(),
        "query": query_info,
        "pair": {key: value for key, value in stats.items() if key != "stems"},
        "stems": stems,
        "run": run,
        "outcome": outcome,
        "reason": reason,
    }
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    (RESULT_DIR / "measured.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"outcome": outcome, "reason": reason, "f_delta": f_delta,
                      "decision": decision, "why": why, "equal": equal}, indent=2))
    return payload


def main() -> None:
    try:
        os.nice(10)
    except OSError:
        pass
    os.environ["OMP_NUM_THREADS"] = "1"
    parser = argparse.ArgumentParser(description="TARE break-even gate laptop check")
    parser.add_argument("phase", choices=("pilot", "measured"))
    args = parser.parse_args()
    if not PFAM_OLD.is_file() or not PFAM_NEW.is_file():
        raise SystemExit("Pfam 37.4 or 38.0 is missing under ~/tmp/tare_c")
    index = load_index()
    if args.phase == "pilot":
        pilot(index)
    else:
        measured(index)


if __name__ == "__main__":
    main()
