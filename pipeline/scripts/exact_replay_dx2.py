#!/usr/bin/env python3
"""DX2 pilot, then the pre-registered measured arms.

Names the locked S1 argv. Does not modify acts/. A pilot number is not a result.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import random
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.provenance import provenance  # noqa: E402
from acts.reference_formats import parse_reference, read_records, write_entries  # noqa: E402
from acts.reference_run import body_lines  # noqa: E402

PIPE = ROOT
DIAMOND = PIPE / "builds" / "diamond-2.2.5" / "diamond"
DATA = PIPE / "data" / "swissprot"
NEW_FA = DATA / "uniprot_sprot_2026_03.fasta.gz"
OLD_FA = DATA / "uniprot_sprot_2026_01.fasta.gz"
Q_PILOT = PIPE / "data" / "recurrence" / "A" / "GCF_002090355.1_protein.faa.gz"
Q_E1 = PIPE / "data" / "recurrence" / "A" / "GCF_002853805.1_protein.faa.gz"
Q_MEASURED = Q_E1
PFAM = PIPE / "data" / "hmmer" / "Pfam-A.hmm.gz"
WORK = PIPE / "data" / "reference_diamond_dx2"
OUT_DIR = PIPE / "results" / "reference_diamond"
HMMER_BIN = Path("/opt/homebrew/bin")

# Committed 2026-10-09 checksum table (extracted FASTA, not the linux binary).
EXPECTED_FASTA = {
    "new": (93_801_562, "bc9d398533e6df582b563c6c03093bd0"),
    "old": (93_457_057, "5245b19456d9a063b13c46602269bc5f"),
}
# Mac binary recorded by the D-X run. The linux row is a different file.
EXPECTED_DIAMOND_MAC = (22_031_624, "711d4c7b29e24c3fd6ec6a288ec1d326")
EXPECTED_LETTERS = {"new": 209_017_843, "old": 208_482_574}
D0_ENTRIES = {"new": 575_748, "old": 574_627}

THREADS = "8"
OUTFMT = (
    "qseqid sseqid pident length mismatch gapopen "
    "qstart qend sstart send evalue bitscore"
).split()
INTERVAL = (6, 7, 8, 9)
QUERY_COL = 0
SUBJECT_COL = 1


def log(message: str) -> None:
    print(message, flush=True)


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_id(path: Path) -> dict:
    return {"path": str(path), "bytes": path.stat().st_size, "md5": md5_file(path)}


def assert_not_tmpfs(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    df = subprocess.run(["df", "-h", str(path)], check=False, capture_output=True, text=True)
    if "tmpfs" in df.stdout.lower():
        raise SystemExit("STOP scratch is tmpfs")
    return df.stdout.strip()


def check_fasta(path: Path, expected: tuple[int, str], label: str) -> dict:
    if not path.is_file():
        raise SystemExit(f"STOP_INPUTS missing {label}: {path}")
    found = file_id(path)
    if (found["bytes"], found["md5"]) != expected:
        raise SystemExit(
            f"STOP_INPUTS {label} bytes={found['bytes']} md5={found['md5']} "
            f"expected bytes={expected[0]} md5={expected[1]}"
        )
    return found


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def git_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PIPE.parent, check=False, capture_output=True, text=True
    )
    return (proc.stdout or "").strip()


def s1(db: Path, query: Path, out: Path, *, threads: str = THREADS, extra: list[str] | None = None) -> list[str]:
    cmd = [
        str(DIAMOND), "blastp",
        "--db", str(db),
        "--query", str(query),
        "--out", str(out),
        "--min-score", "40",
        "-k", "0",
        "--motif-masking", "0",
        "-b", "2.0",
        "--comp-based-stats", "1",
        "--threads", threads,
        "--outfmt", "6",
        *OUTFMT,
    ]
    if extra:
        cmd.extend(extra)
    return cmd


def run_cmd(cmd: list[str], timeout: float) -> tuple[str, str, float]:
    started = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    wall = time.perf_counter() - started
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-800:]
        raise RuntimeError(f"exit {proc.returncode}: {' '.join(cmd[:6])} {tail}")
    return proc.stdout or "", proc.stderr or "", wall


def log_field(text: str, prefix: str) -> str | None:
    for line in text.splitlines():
        if prefix in line:
            return line.strip()
    return None


def ensure_dmnd(fasta: Path) -> Path:
    dmnd = Path(str(fasta) + ".dmnd")
    if dmnd.is_file() and dmnd.stat().st_size > 0:
        return dmnd
    log(f"makedb {fasta.name}")
    run_cmd(
        [str(DIAMOND), "makedb", "--in", str(fasta), "--db", str(fasta), "--threads", THREADS],
        3600,
    )
    if not dmnd.is_file():
        raise RuntimeError(f"makedb wrote no database for {fasta}")
    return dmnd


def blast(db: Path, query: Path, out: Path, *, threads: str = THREADS, extra: list[str] | None = None) -> dict:
    if out.is_file() and out.stat().st_size >= 0 and out.with_suffix(out.suffix + ".meta.json").is_file():
        meta = json.loads(out.with_suffix(out.suffix + ".meta.json").read_text())
        meta["reused"] = True
        return meta
    ensure_dmnd(db)
    cmd = s1(db, query, out, threads=threads, extra=extra)
    log(" ".join(cmd[:8]) + " ...")
    stdout, stderr, wall = run_cmd(cmd, 3600)
    text = stdout + "\n" + stderr
    meta = {
        "path": str(out),
        "wall_s": wall,
        "threads": threads,
        "extra": extra or [],
        "rows": len(body_lines(out.read_text())),
        "algorithm": log_field(text, "Algorithm:"),
        "block_size": log_field(text, "Block size ="),
        "reused": False,
    }
    out.with_suffix(out.suffix + ".meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def write_queries(records, indices: list[int], dest: Path) -> None:
    lines = []
    for index in indices:
        rec = records[index]
        desc = f" {rec.description}" if rec.description else ""
        lines.append(f">{rec.name}{desc}\n{rec.sequence}\n")
    dest.write_text("".join(lines))


def classify(stock_text: str, other_text: str) -> dict:
    def index(text: str) -> dict[tuple[str, str], list[str]]:
        grouped: dict[tuple[str, str], list[str]] = {}
        for line in body_lines(text):
            cells = line.split()
            grouped.setdefault((cells[0], cells[1]), []).append(line)
        return grouped

    stock, other = index(stock_text), index(other_text)
    counts: Counter[str] = Counter()
    both = set(stock) & set(other)
    for key in set(stock) - set(other):
        counts["row_missing"] += len(stock[key])
    for key in set(other) - set(stock):
        counts["row_extra"] += len(other[key])
    identical = 0
    for key in both:
        left, right = stock[key], other[key]
        n = min(len(left), len(right))
        for index_i in range(n):
            a, b = left[index_i].split(), right[index_i].split()
            if len(a) > 9 and len(b) > 9 and tuple(a[i] for i in INTERVAL) == tuple(b[i] for i in INTERVAL):
                if a == b:
                    identical += 1
                else:
                    counts["same_hsp_different_value"] += 1
            else:
                counts["different_hsp"] += 1
        if len(left) > n:
            counts["row_missing"] += len(left) - n
        if len(right) > n:
            counts["row_extra"] += len(right) - n
    stock_lines, other_lines = body_lines(stock_text), body_lines(other_text)
    shared = sum(min(len(stock[key]), len(other[key])) for key in both)
    result = {
        "stock_rows": len(stock_lines),
        "other_rows": len(other_lines),
        "shared_rows": shared,
        "shared_byte_identical": identical,
        "same_hsp_different_value": counts["same_hsp_different_value"],
        "different_hsp": counts["different_hsp"],
        "row_missing": counts["row_missing"],
        "row_extra": counts["row_extra"],
        "bodies_equal": stock_lines == other_lines,
    }
    value_free = not any(
        result[name] for name in ("same_hsp_different_value", "different_hsp", "row_missing", "row_extra")
    )
    result["line_order_only"] = (not result["bodies_equal"]) and value_free
    return result


def subjects_of(text: str, subject_col: int = SUBJECT_COL) -> set[str]:
    found = set()
    for line in body_lines(text):
        cells = line.split()
        if subject_col < len(cells):
            found.add(cells[subject_col])
    return found


def ic_judge(
    r_text: str,
    r_plus_text: str,
    pad_ids: set[str],
    replayed_queries: set[str],
    *,
    query_col: int,
    subject_col: int,
) -> dict:
    """Stated certificate: R rows survive in R+, and R+ has no Pad subject for a replayed query."""
    r_lines = body_lines(r_text)
    plus_lines = body_lines(r_plus_text)
    r_counts, plus_counts = Counter(r_lines), Counter(plus_lines)
    missing = []
    for line, count in r_counts.items():
        if plus_counts[line] < count:
            missing.append(line)
    pad_hits = []
    extra_on_candidates = []
    for line in plus_lines:
        cells = line.split()
        if query_col >= len(cells) or subject_col >= len(cells):
            continue
        query, subject = cells[query_col], cells[subject_col]
        if query not in replayed_queries:
            continue
        if subject in pad_ids:
            pad_hits.append(line)
        elif plus_counts[line] > r_counts[line] and line not in extra_on_candidates:
            # Counted once per distinct extra line; multiplicity is in the counters.
            extra_on_candidates.append(line)
    extra_mult = sum(
        plus_counts[line] - r_counts[line]
        for line in plus_counts
        if plus_counts[line] > r_counts[line]
        and line.split()[subject_col] not in pad_ids
    )
    passed = not missing and not pad_hits
    return {
        "pass": passed,
        "r_rows": len(r_lines),
        "r_plus_rows": len(plus_lines),
        "missing_r_rows": len(missing),
        "pad_hit_rows": len(pad_hits),
        "extra_candidate_row_excess": extra_mult,
        "ordered_bodies_equal": r_lines == plus_lines,
        "missing_example": missing[:3],
        "pad_hit_example": pad_hits[:3],
    }


def diamond_ic(
    entries,
    key_to_index: dict[str, int],
    queries: Path,
    replay_queries: set[str],
    candidate_ids: set[str],
    pin_letters: int,
    pad_seed: int,
    tag: Path,
) -> dict:
    unknown = sorted(candidate_ids - set(key_to_index))
    u_idx = [key_to_index[key] for key in candidate_ids if key in key_to_index]
    u_idx.sort()
    non = [i for i in range(len(entries)) if i not in set(u_idx)]
    pad_n = max(200, len(u_idx))
    if pad_n > len(non):
        raise RuntimeError("pad larger than the non-candidate pool")
    pad_idx = sorted(random.Random(pad_seed).sample(non, pad_n))
    pad_ids = {entries[i].primary for i in pad_idx}
    u_fa = tag.parent / f"{tag.name}.U.faa"
    up_fa = tag.parent / f"{tag.name}.UP.faa"
    write_entries([entries[i] for i in u_idx], u_fa)
    merged = sorted(set(u_idx) | set(pad_idx))
    write_entries([entries[i] for i in merged], up_fa)
    pin = ["--dbsize", str(pin_letters)]
    r_meta = blast(u_fa, queries, Path(str(tag) + ".R.m8"), extra=pin)
    p_meta = blast(up_fa, queries, Path(str(tag) + ".Rplus.m8"), extra=pin)
    judge = ic_judge(
        Path(str(tag) + ".R.m8").read_text(),
        Path(str(tag) + ".Rplus.m8").read_text(),
        pad_ids,
        replay_queries,
        query_col=QUERY_COL,
        subject_col=SUBJECT_COL,
    )
    judge.update({
        "candidate_entries": len(u_idx),
        "pad_entries": pad_n,
        "pad_seed": pad_seed,
        "unmatched_subjects": unknown,
        "wall_R_s": r_meta["wall_s"],
        "wall_Rplus_s": p_meta["wall_s"],
        "algorithm_R": r_meta.get("algorithm"),
        "algorithm_Rplus": p_meta.get("algorithm"),
        "block_R": r_meta.get("block_size"),
        "block_Rplus": p_meta.get("block_size"),
    })
    return judge


def iter_hmm_index(path: Path) -> list[tuple[str, int, int]]:
    """(NAME, start_offset, end_offset) in file order. Offsets are bytes of the text file."""
    models = []
    with path.open("rb") as handle:
        start = 0
        name = ""
        while True:
            line = handle.readline()
            if not line:
                break
            if line.startswith(b"NAME "):
                name = line.split(None, 1)[1].strip().decode()
            elif line.startswith(b"//"):
                end = handle.tell()
                models.append((name, start, end))
                start = end
                name = ""
    return models


def write_hmm(src: Path, models: list[tuple[str, int, int]], keep: set[str], dest: Path) -> int:
    n = 0
    with src.open("rb") as handle, dest.open("wb") as out:
        for name, start, end in models:
            if name not in keep:
                continue
            handle.seek(start)
            out.write(handle.read(end - start))
            n += 1
    for ext in (".h3f", ".h3i", ".h3m", ".h3p"):
        sidecar = Path(str(dest) + ext)
        if sidecar.exists():
            sidecar.unlink()
    run_cmd([str(HMMER_BIN / "hmmpress"), "-f", str(dest)], 600)
    return n


def hmmscan(db: Path, query: Path, tag: Path, z: int | None, cpu: int = 4) -> dict:
    meta_path = Path(str(tag) + ".meta.json")
    if meta_path.is_file() and Path(str(tag) + ".tbl").is_file():
        meta = json.loads(meta_path.read_text())
        meta["reused"] = True
        return meta
    cmd = [str(HMMER_BIN / "hmmscan"), "--cut_ga", "--noali", "--cpu", str(cpu)]
    if z is not None:
        cmd.extend(["-Z", str(z)])
    cmd.extend(["--tblout", str(tag) + ".tbl", "--domtblout", str(tag) + ".dom", "-o", "/dev/null", str(db), str(query)])
    log("hmmscan " + tag.name)
    _stdout, _stderr, wall = run_cmd(cmd, 7200)
    meta = {"wall_s": wall, "z": z, "cpu": cpu, "reused": False,
            "tbl_rows": len(body_lines(Path(str(tag) + ".tbl").read_text())),
            "dom_rows": len(body_lines(Path(str(tag) + ".dom").read_text()))}
    meta_path.write_text(json.dumps(meta) + "\n")
    return meta


def hmmer_positive(work: Path) -> dict:
    """E1 argv on a 50-query subset of the E1 draw. Not a DX2 result."""
    work.mkdir(parents=True, exist_ok=True)
    text_hmm = work / "Pfam-A.hmm"
    if not text_hmm.is_file():
        log("decompress Pfam 38.2")
        with gzip.open(PFAM, "rb") as src, text_hmm.open("wb") as dst:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                dst.write(chunk)
    models = iter_hmm_index(text_hmm)
    if len(models) != 30134:
        raise RuntimeError(f"Pfam model count {len(models)} != 30134")
    names = [name for name, _s, _e in models]
    name_set = set(names)
    records = read_records(Q_E1)
    draw = sorted(random.Random(20261012).sample(range(len(records)), 300))[:50]
    qpath = work / "hmmer_q50.faa"
    write_queries(records, draw, qpath)
    pressed = work / "pfam38.2.hmm"
    if not Path(str(pressed) + ".h3m").is_file():
        log("hmmpress full Pfam 38.2")
        run_cmd([str(HMMER_BIN / "hmmpress"), "-f", str(text_hmm)], 3600)
        # hmmpress writes next to the text file. Point the stock db at that.
        pressed = text_hmm
    else:
        pressed = text_hmm if Path(str(text_hmm) + ".h3m").is_file() else pressed
    stock = hmmscan(pressed, qpath, work / "hmmer_S", None)
    hit_names = set()
    replayed = set()
    for line in body_lines((work / "hmmer_S.tbl").read_text()):
        cells = line.split()
        hit_names.add(cells[0])
        replayed.add(cells[2])
    if not hit_names:
        return {"pass": False, "why": "no tblout hits on the 50-query E1 subset", "stock": stock}
    u = [name for name in names if name in hit_names]
    non = [name for name in names if name not in hit_names]
    pad_n = max(200, len(u))
    pad = random.Random(20261023).sample(non, pad_n)
    pad_set = set(pad)
    # File order of the union.
    union = [name for name in names if name in hit_names or name in pad_set]
    n_u = write_hmm(text_hmm, models, set(u), work / "hmmer_U.hmm")
    n_up = write_hmm(text_hmm, models, set(union), work / "hmmer_UP.hmm")
    r = hmmscan(work / "hmmer_U.hmm", qpath, work / "hmmer_R", 30134)
    rp = hmmscan(work / "hmmer_UP.hmm", qpath, work / "hmmer_Rplus", 30134)
    tables = {}
    passed = True
    for ext, qcol in (("tbl", 2), ("dom", 3)):
        judge = ic_judge(
            (work / f"hmmer_R.{ext}").read_text(),
            (work / f"hmmer_Rplus.{ext}").read_text(),
            pad_set,
            replayed,
            query_col=qcol,
            subject_col=0,
        )
        tables[ext] = judge
        passed = passed and judge["pass"]
    return {
        "label": "positive control, not a result",
        "queries": 50,
        "query_source": "first 50 indices of sorted Random(20261012).sample(n, 300) from GCF_002853805.1",
        "models": len(models),
        "z_pin": 30134,
        "candidate_models": n_u,
        "pad_models": n_up - n_u,
        "queries_with_hit": len(replayed),
        "pass": passed,
        "tables": tables,
        "wall_stock_s": stock["wall_s"],
        "wall_R_s": r["wall_s"],
        "wall_Rplus_s": rp["wall_s"],
        "argv": "hmmscan --cut_ga --noali --cpu 4 [-Z 30134] --tblout --domtblout",
    }


def select_pilot_queries(records) -> tuple[list[int], dict]:
    rng = random.Random(20261019)
    pool = rng.sample(range(len(records)), 80)
    return pool, {"draw": "random.Random(20261019).sample(range(n), 80)", "pool_n": 80}


def pilot() -> None:
    work = WORK / "pilot"
    work.mkdir(parents=True, exist_ok=True)
    scratch = assert_not_tmpfs(work)
    log("verify inputs")
    inputs = {
        "new": check_fasta(NEW_FA, EXPECTED_FASTA["new"], "2026_03"),
        "old": check_fasta(OLD_FA, EXPECTED_FASTA["old"], "2026_01"),
        "pilot_queries": file_id(Q_PILOT),
        "e1_queries": file_id(Q_E1),
        "diamond": file_id(DIAMOND),
    }
    if (inputs["diamond"]["bytes"], inputs["diamond"]["md5"]) != EXPECTED_DIAMOND_MAC:
        raise SystemExit(
            f"STOP_INPUTS diamond mac binary md5={inputs['diamond']['md5']} "
            f"expected {EXPECTED_DIAMOND_MAC[1]}"
        )
    version, _err, _wall = run_cmd([str(DIAMOND), "version"], 30)
    if "2.2.5" not in version:
        raise SystemExit(f"STOP diamond version {version!r}")
    letters = {}
    for label, fasta in (("new", NEW_FA), ("old", OLD_FA)):
        ensure_dmnd(fasta)
        stdout, _e, _w = run_cmd([str(DIAMOND), "dbinfo", "--db", str(fasta)], 120)
        # Reuse the committed parser's rule: last integer token on a Letters line.
        found = None
        for line in stdout.splitlines():
            if "Letters" in line and line.split()[-1].isdigit():
                found = int(line.split()[-1])
        if found != EXPECTED_LETTERS[label]:
            raise SystemExit(f"STOP_INPUTS dbinfo letters {label}={found}")
        letters[label] = found

    log("parse references")
    new_entries = parse_reference(NEW_FA)
    old_entries = parse_reference(OLD_FA)
    if len(new_entries) != D0_ENTRIES["new"] or len(old_entries) != D0_ENTRIES["old"]:
        raise SystemExit(f"STOP_INPUTS entry counts {len(old_entries)} {len(new_entries)}")
    if sum(e.length for e in new_entries) != letters["new"]:
        raise SystemExit("STOP_INPUTS FASTA length sum != dbinfo letters")
    key_to_index = {}
    for index, entry in enumerate(new_entries):
        key_to_index.setdefault(entry.primary, index)

    records = read_records(Q_PILOT)
    pool, draw_meta = select_pilot_queries(records)
    # Construction scan. Not a B1 result.
    pool_sorted = sorted(pool)
    q_pool = work / "pool.faa"
    write_queries(records, pool_sorted, q_pool)
    construction = blast(NEW_FA, q_pool, work / "construction.m8")
    hit_ids = set()
    by_query: dict[str, int] = Counter()
    for line in body_lines((work / "construction.m8").read_text()):
        cells = line.split()
        by_query[cells[0]] += 1
        hit_ids.add(cells[0])
    # First 50 of the sample order (not file order) that have a hit.
    chosen_ids = []
    for index in pool:
        if records[index].key in hit_ids:
            chosen_ids.append(records[index].key)
        if len(chosen_ids) == 50:
            break
    if len(chosen_ids) < 50:
        raise SystemExit(f"STOP pilot underpowered: {len(chosen_ids)} queries with a hit in the pool of 80")
    id_to_index = {rec.key: i for i, rec in enumerate(records)}
    chosen = [id_to_index[key] for key in chosen_ids]
    chosen_file_order = sorted(chosen)
    q50 = work / "q50.faa"
    write_queries(records, chosen_file_order, q50)
    replayed = {records[i].key for i in chosen}

    report: dict = {
        "test": "DX2-pilot",
        "label": "PILOT, not a result",
        "git_head_at_start": git_head(),
        "host": platform.node(),
        "platform": platform.platform(),
        "diamond_version": version.strip(),
        "inputs": inputs,
        "letters": letters,
        "threads": int(THREADS),
        "scratch_df": scratch,
        "query_draw": draw_meta,
        "construction": {
            "label": "SAMPLE-CONSTRUCTION",
            "pool_n": 80,
            "queries_with_hit": len(hit_ids),
            "body_rows": construction["rows"],
            "wall_s": construction["wall_s"],
            "algorithm": construction.get("algorithm"),
            "kept": 50,
        },
        "semantics_note": "pipeline/results/reference_diamond/dx2_semantics.md",
    }

    log("B0 determinism")
    b0a = blast(NEW_FA, q50, work / "b0_a.m8")
    # Force a second invocation: the cache keys on the output path.
    b0b = blast(NEW_FA, q50, work / "b0_b.m8")
    b0_1 = blast(NEW_FA, q50, work / "b0_t1.m8", threads="1")
    body_a = (work / "b0_a.m8").read_text()
    same_repeat = body_lines(body_a) == body_lines((work / "b0_b.m8").read_text())
    same_threads = body_lines(body_a) == body_lines((work / "b0_t1.m8").read_text())
    report["b0"] = {
        "repeat_identical": same_repeat,
        "threads_1_vs_8_identical": same_threads,
        "rows": b0a["rows"],
        "algorithm_threads_8": b0a.get("algorithm"),
        "algorithm_threads_1": b0_1.get("algorithm"),
        "block_threads_8": b0a.get("block_size"),
        "wall_a_s": b0a["wall_s"],
        "wall_b_s": b0b["wall_s"],
        "wall_threads_1_s": b0_1["wall_s"],
    }
    if not same_repeat or not same_threads:
        report["stopped"] = "B0"
        write_json(OUT_DIR / "dx2_pilot.json", {**report, "provenance": provenance("dx2-pilot")})
        raise SystemExit("STOP B0 bodies differ")

    log("B1 oracle replay")
    stock_subjects = subjects_of(body_a)
    pin = ["--dbsize", str(letters["new"])]
    u_idx = sorted(key_to_index[key] for key in stock_subjects if key in key_to_index)
    u_fa = work / "b1_U.faa"
    write_entries([new_entries[i] for i in u_idx], u_fa)
    r = blast(u_fa, q50, work / "b1_R.m8", extra=pin)
    rn = blast(u_fa, q50, work / "b1_Rn.m8", extra=None)
    b1_class = classify(body_a, (work / "b1_R.m8").read_text())
    rn_class = classify(body_a, (work / "b1_Rn.m8").read_text())
    report["b1"] = {
        "candidate_entries": len(u_idx),
        "unmatched_subjects": sorted(stock_subjects - set(key_to_index)),
        "replay_rows": r["rows"],
        "stock_rows": b0a["rows"],
        "bodies_equal": b1_class["bodies_equal"],
        "unpinned_differs": not rn_class["bodies_equal"],
        "classification": b1_class,
        "unpinned_classification": rn_class,
        "algorithm_stock": b0a.get("algorithm"),
        "algorithm_replay": r.get("algorithm"),
        "algorithm_unpinned": rn.get("algorithm"),
        "block_replay": r.get("block_size"),
        "wall_R_s": r["wall_s"],
        "wall_Rn_s": rn["wall_s"],
        "pin": f"--dbsize {letters['new']}",
    }

    log("B2 independence certificate")
    ic_true = diamond_ic(
        new_entries, key_to_index, q50, replayed, stock_subjects, letters["new"], 20261023, work / "ic_b1"
    )
    # Negative control: drop 10% of true hit subjects, same certificate.
    rng_drop = random.Random(20261022)
    n_drop = max(1, len(u_idx) // 10)
    dropped = set(rng_drop.sample(u_idx, n_drop))
    kept_ids = {new_entries[i].primary for i in u_idx if i not in dropped}
    ic_wrong = diamond_ic(
        new_entries, key_to_index, q50, replayed, kept_ids, letters["new"], 20261023, work / "ic_wrong"
    )
    dropped_ids = {new_entries[i].primary for i in dropped}
    # How many dropped subjects the pad draw actually contained.
    # diamond_ic does not return the pad id set; recompute the draw.
    non = [i for i in range(len(new_entries)) if new_entries[i].primary not in kept_ids]
    pad_draw = set(random.Random(20261023).sample(non, max(200, len(kept_ids))))
    dropped_in_pad = sum(1 for i in dropped if i in pad_draw)
    report["b2"] = {
        "diamond_true_candidates": ic_true,
        "diamond_wrong_candidates": ic_wrong,
        "negative_dropped_subjects": n_drop,
        "negative_dropped_in_pad": dropped_in_pad,
        "negative_saw_the_case": (not ic_wrong["pass"]),
        "negative_fail_mode": (
            "pad_hit" if ic_wrong["pad_hit_rows"] else
            "row_change" if ic_wrong["missing_r_rows"] else
            "not_seen"
        ),
    }
    log("B2 HMMER positive control")
    report["b2"]["hmmer_positive"] = hmmer_positive(work / "hmmer")

    log("B3 suspects")
    attempts = []
    if b1_class["bodies_equal"]:
        attempts.append({"name": "none", "why": "B1 bodies identical; no suspect run"})
    else:
        stock_algo = b0a.get("algorithm") or ""
        replay_algo = r.get("algorithm") or ""
        # Force the algorithm the stock log named, on the replay only.
        if "Double-indexed" in stock_algo and "Double-indexed" not in replay_algo:
            forced = blast(u_fa, q50, work / "b3_algo.m8", extra=pin + ["--algo", "0"])
            attempts.append({
                "name": "force --algo 0 on replay",
                "algorithm": forced.get("algorithm"),
                "classification": classify(body_a, (work / "b3_algo.m8").read_text()),
            })
        elif stock_algo == replay_algo:
            attempts.append({
                "name": "--algo",
                "why": "stock and replay logged the same algorithm; not a size-switch",
                "algorithm": stock_algo,
            })
        block_note = {
            "name": "-b",
            "stock": b0a.get("block_size"),
            "replay": r.get("block_size"),
            "why": "S1 already sets -b 2.0; both logs recorded",
        }
        attempts.append(block_note)
        ranked = blast(u_fa, q50, work / "b3_norank.m8", extra=pin + ["--no-ranking"])
        attempts.append({
            "name": "--no-ranking on replay only",
            "algorithm": ranked.get("algorithm"),
            "classification": classify(body_a, (work / "b3_norank.m8").read_text()),
            "note": "Stock stays S1. A match would be a declared extra only if the replay then equals unmodified stock.",
        })
    report["b3"] = {"attempts": attempts}

    log("B4 unchanged-entry disagreement")
    old_hashes = {entry.content_hash for entry in old_entries}
    unchanged_ids = {entry.primary for entry in new_entries if entry.content_hash in old_hashes}
    old_stock = blast(OLD_FA, q50, work / "b4_old.m8")
    def pairs(path: Path, allowed: set[str]) -> set[tuple[str, str]]:
        found = set()
        for line in body_lines(path.read_text()):
            cells = line.split()
            if cells[1] in allowed:
                found.add((cells[0], cells[1]))
        return found
    new_pairs = pairs(work / "b0_a.m8", unchanged_ids)
    old_pairs = pairs(work / "b4_old.m8", unchanged_ids)
    report["b4"] = {
        "unchanged_entries_in_new": len(unchanged_ids),
        "pairs_unchanged_subject_new": len(new_pairs),
        "pairs_unchanged_subject_old": len(old_pairs),
        "hit_in_new_not_old": len(new_pairs - old_pairs),
        "hit_in_old_not_new": len(old_pairs - new_pairs),
        "wall_old_s": old_stock["wall_s"],
        "predicts_missed_candidates": len(new_pairs - old_pairs) + len(old_pairs - new_pairs),
    }

    report["b5"] = {
        "wall_stock_s": b0a["wall_s"],
        "wall_R_s": r["wall_s"],
        "wall_Rplus_s": ic_true["wall_Rplus_s"],
        "ic_overhead_Rplus_over_R": (
            ic_true["wall_Rplus_s"] / r["wall_s"] if r["wall_s"] else None
        ),
        "ic_overhead_Rplus_over_stock": (
            ic_true["wall_Rplus_s"] / b0a["wall_s"] if b0a["wall_s"] else None
        ),
    }
    # Declared extras: only a B3 attempt that made the pinned replay match stock.
    extras = []
    for attempt in attempts:
        klass = attempt.get("classification") or {}
        if klass.get("bodies_equal") and attempt.get("name", "").startswith("--"):
            extras.append(attempt["name"])
    report["declared_extras"] = extras
    report["provenance"] = provenance(versions={"diamond": version.strip()})
    write_json(OUT_DIR / "dx2_pilot.json", report)
    log(f"wrote {OUT_DIR / 'dx2_pilot.json'}")


if __name__ == "__main__":
    pilot()
