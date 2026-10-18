#!/usr/bin/env python3
"""Laptop pilot for DIAMOND database-order dependence, and the option sweep.

The semantics review is pipeline/results/diamond_order/g_semantics.md.
A pilot number is not a measured result. The measured arm is specified in
pipeline/docs/DIAMOND_ORDER_PROTOCOL.md and is not started here.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.provenance import provenance  # noqa: E402
from acts.reference_formats import read_records  # noqa: E402
from acts.reference_run import body_lines  # noqa: E402
from scripts.exact_replay_dx2 import OUTFMT, classify  # noqa: E402

SHARED = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS")
DIAMOND = SHARED / "pipeline/builds/diamond-2.2.5/diamond"
SWISSPROT = SHARED / "pipeline/data/swissprot/uniprot_sprot_2026_03.fasta.gz"
GENOME = SHARED / "pipeline/data/recurrence/A/GCF_001650275.1_protein.faa.gz"
DX2 = SHARED / "pipeline/data/reference_diamond_dx2/measured"
U_FASTA = DX2 / "e1_U.faa"
KNOWN_QUERY = DX2 / "e1_q.faa"

SCRATCH = Path.home() / "tmp/tare_g"
OUT_DIR = ROOT / "results/diamond_order"
EXPECTED_DMND_LETTERS = 209_017_843
EXPECTED_ENTRIES = 575_748
EXPECTED_FASTA = (93_801_562, "bc9d398533e6df582b563c6c03093bd0")
EXPECTED_DIAMOND = (22_031_624, "711d4c7b29e24c3fd6ec6a288ec1d326")
MIN_ROWS = 1000
THREADS = "2"
RSS_LIMIT_KB = 4 * 1024 * 1024
DBSIZE = "209017843"
PILOT_SEED = 20261161
PILOT_N = 300
SHUFFLE_SEEDS = (20261163, 20261164, 20261165, 20261166, 20261167)
SHAPES = ("111101110111", "111011010010111")
SAMPLE_CAP = 8

LOST_KEYS = (
    ("WP_000107384.1", "sp|Q00407|VHUA_METVO"),
    ("WP_000137873.1", "sp|Q31S42|RPAA_SYNE7"),
    ("WP_000256438.1", "sp|Q0WWW9|XYLL3_ARATH"),
    ("WP_000493792.1", "sp|Q39QB5|NUOI2_GEOMG"),
    ("WP_001026276.1", "sp|A9BCC5|CH10_PROM4"),
    ("WP_001026276.1", "sp|Q5GST6|CH10_WOLTR"),
)

# One change each. Values replace an earlier flag of the same name.
SWEEP = (
    ("faster", ["--faster"]),
    ("fast", ["--fast"]),
    ("mid-sensitive", ["--mid-sensitive"]),
    ("sensitive", ["--sensitive"]),
    ("more-sensitive", ["--more-sensitive"]),
    ("very-sensitive", ["--very-sensitive"]),
    ("ultra-sensitive", ["--ultra-sensitive"]),
    ("shapes-6x10", ["--shapes-6x10"]),
    ("shapes-30x10", ["--shapes-30x10"]),
    ("masking-none", ["--masking", "none"]),
    ("masking-seg", ["--masking", "seg"]),
    ("masking-seg-all", ["--masking", "seg-all"]),
    ("masking-tantan", ["--masking", "tantan"]),
    ("motif-masking-1", ["--motif-masking", "1"]),
    ("ext-banded-fast", ["--ext", "banded-fast"]),
    ("ext-banded-slow", ["--ext", "banded-slow"]),
    ("ext-full", ["--ext", "full"]),
    ("ext-global", ["--ext", "global"]),
    ("ext-none", ["--ext", "none"]),
    ("algo-0", ["--algo", "0"]),
    ("algo-1", ["--algo", "1"]),
    ("algo-ctg", ["--algo", "ctg"]),
    ("shapes-1", ["--shapes", "1"]),
    ("seed-cut-0.9", ["--seed-cut", "0.9"]),
    ("freq-masking", ["--freq-masking"]),
    ("freq-sd-10", ["--freq-masking", "--freq-sd", "10"]),
    ("id2-0", ["--id2", "0"]),
    ("id2-1", ["--id2", "1"]),
    ("approx-id-50", ["--approx-id", "50"]),
    ("hamming-dist-boundary-check", ["--hamming-dist-boundary-check"]),
    ("linsearch", ["--linsearch"]),
    ("soft-masking-tantan", ["--soft-masking", "tantan"]),
    ("soft-masking-seg", ["--soft-masking", "seg"]),
    ("id-30", ["--id", "30"]),
    ("query-cover-20", ["--query-cover", "20"]),
    ("min-len-ratio-0.9", ["--min-len-ratio", "0.9"]),
)


class RunFailed(RuntimeError):
    pass


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


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def disk_free_bytes(path: Path) -> int:
    stats = os.statvfs(path)
    return stats.f_bavail * stats.f_frsize


def df_text(path: Path) -> str:
    proc = subprocess.run(["df", "-h", str(path)], check=False, capture_output=True, text=True)
    return (proc.stdout or proc.stderr).strip()


def rss_kb(pid: int) -> int:
    proc = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(pid)],
        check=False,
        capture_output=True,
        text=True,
    )
    text = (proc.stdout or "").strip()
    if not text:
        return 0
    total = 0
    for part in text.split():
        try:
            total += int(part)
        except ValueError:
            continue
    return total


def run_limited(cmd: list[str], timeout: float) -> dict:
    """Run one DIAMOND command at the laptop cap. Kill it above 4 GiB RSS."""
    started = time.perf_counter()
    proc = subprocess.Popen(
        cmd,
        cwd=SCRATCH,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    peak = 0
    killed = ""
    try:
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=2)
                break
            except subprocess.TimeoutExpired:
                peak = max(peak, rss_kb(proc.pid))
                if peak > RSS_LIMIT_KB:
                    killed = "rss"
                    os.killpg(proc.pid, signal.SIGKILL)
                if time.perf_counter() - started > timeout:
                    killed = killed or "timeout"
                    os.killpg(proc.pid, signal.SIGKILL)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=30)
    wall = time.perf_counter() - started
    text = (stdout or "") + "\n" + (stderr or "")
    if killed:
        raise RunFailed(f"{killed} after {wall:.1f}s peak_rss_kb={peak} tail={text[-400:]}")
    if proc.returncode != 0:
        raise RunFailed(f"exit {proc.returncode} peak_rss_kb={peak} tail={text[-600:]}")
    return {
        "wall_s": wall,
        "peak_rss_kb": peak,
        "stdout": stdout or "",
        "stderr": stderr or "",
    }


def log_lines(text: str, needles: tuple[str, ...]) -> list[str]:
    found = []
    for line in text.splitlines():
        if any(needle in line for needle in needles):
            found.append(line.strip())
    return found


def load_swissprot(path: Path) -> tuple[list[str], list[str], list[int]]:
    raws: list[str] = []
    keys: list[str] = []
    lengths: list[int] = []
    with gzip.open(path, "rt") as handle:
        header = ""
        body: list[str] = []
        length = 0

        def flush() -> None:
            nonlocal header, body, length
            if not header:
                return
            raw = header + "".join(body)
            if not raw.endswith("\n"):
                raw += "\n"
            raws.append(raw)
            keys.append(header[1:].split()[0])
            lengths.append(length)
            header = ""
            body = []
            length = 0

        for line in handle:
            if line.startswith(">"):
                flush()
                header = line
            else:
                body.append(line)
                length += sum(1 for char in line if not char.isspace())
        flush()
    return raws, keys, lengths


def write_fasta(raws: list[str], order: list[int], dest: Path) -> None:
    with dest.open("w") as handle:
        for index in order:
            handle.write(raws[index])


def shuffled_order(n: int, seed: int) -> list[int]:
    order = list(range(n))
    random.Random(seed).shuffle(order)
    return order


def base_argv(db: Path, query: Path, out: Path, extra: list[str], *, dbsize: bool) -> list[str]:
    cmd = [
        "nice",
        "-n",
        "10",
        str(DIAMOND),
        "blastp",
        "--db",
        str(db),
        "--query",
        str(query),
        "--out",
        str(out),
        "--min-score",
        "40",
        "-k",
        "0",
        "--motif-masking",
        "0",
        "-b",
        "2.0",
        "--comp-based-stats",
        "1",
        "--threads",
        THREADS,
        "--tmpdir",
        str(SCRATCH),
        "--outfmt",
        "6",
        *OUTFMT,
    ]
    if dbsize:
        cmd.extend(["--dbsize", DBSIZE])
    return merge_flags(cmd, extra)


def merge_flags(cmd: list[str], extra: list[str]) -> list[str]:
    out = list(cmd)
    index = 0
    while index < len(extra):
        flag = extra[index]
        value = None
        if index + 1 < len(extra) and not extra[index + 1].startswith("-"):
            value = extra[index + 1]
            index += 2
        else:
            index += 1
        if flag in out:
            at = out.index(flag)
            if value is not None:
                if at + 1 < len(out) and not str(out[at + 1]).startswith("-"):
                    out[at + 1] = value
                else:
                    out.insert(at + 1, value)
        elif value is None:
            out.append(flag)
        else:
            out.extend([flag, value])
    return out


def makedb(fasta: Path, db: Path) -> dict:
    cmd = [
        "nice",
        "-n",
        "10",
        str(DIAMOND),
        "makedb",
        "--in",
        str(fasta),
        "--db",
        str(db),
        "--threads",
        THREADS,
        "--tmpdir",
        str(SCRATCH),
    ]
    meta = run_limited(cmd, 1800)
    dmnd = Path(str(db) + ".dmnd")
    if not dmnd.is_file() or dmnd.stat().st_size == 0:
        raise RunFailed(f"makedb wrote no database at {dmnd}")
    meta["argv"] = cmd
    meta["dmnd"] = file_id(dmnd)
    meta["stdout"] = ""
    meta["stderr_tail"] = meta.pop("stderr")[-500:]
    return meta


def search(db: Path, query: Path, out: Path, extra: list[str], *, dbsize: bool) -> dict:
    if out.exists():
        out.unlink()
    cmd = base_argv(db, query, out, extra, dbsize=dbsize)
    meta = run_limited(cmd, 1800)
    if not out.is_file():
        raise RunFailed("blastp wrote no output")
    text = out.read_text()
    log_text = meta["stdout"] + "\n" + meta["stderr"]
    return {
        "argv": cmd,
        "wall_s": meta["wall_s"],
        "peak_rss_kb": meta["peak_rss_kb"],
        "rows": len(body_lines(text)),
        "md5": hashlib.md5(text.encode()).hexdigest(),
        "log": log_lines(log_text, ("Algorithm:", "Block size", "Length sorting", "Min length ratio")),
        "text": text,
    }


def content_of(klass: dict) -> dict:
    value_changed = klass["same_hsp_different_value"] + klass["different_hsp"]
    classes = []
    if klass["same_hsp_different_value"]:
        classes.append("value-only")
    if klass["different_hsp"]:
        classes.append("different row")
    if klass["row_missing"]:
        classes.append("missing")
    if klass["row_extra"]:
        classes.append("extra")
    if klass["line_order_only"]:
        classes.append("order")
    return {
        "missing": klass["row_missing"],
        "extra": klass["row_extra"],
        "value_changed": value_changed,
        "same_hsp_different_value": klass["same_hsp_different_value"],
        "different_hsp": klass["different_hsp"],
        "line_order_only": klass["line_order_only"],
        "bodies_equal": klass["bodies_equal"],
        "stock_rows": klass["stock_rows"],
        "other_rows": klass["other_rows"],
        "shared_byte_identical": klass["shared_byte_identical"],
        "difference_classes": classes,
        "content_changed": bool(klass["row_missing"] or klass["row_extra"] or value_changed),
    }


def grouped(text: str) -> dict[tuple[str, str], list[str]]:
    rows: dict[tuple[str, str], list[str]] = {}
    for line in body_lines(text):
        cells = line.split()
        rows.setdefault((cells[0], cells[1]), []).append(line)
    return rows


def affected_queries(stock_text: str, other_text: str) -> list[str]:
    left, right = grouped(stock_text), grouped(other_text)
    queries = set()
    for key in set(left) | set(right):
        if left.get(key) != right.get(key):
            queries.add(key[0])
    return sorted(queries)


def changed_keys(stock_text: str, other_text: str) -> list[tuple[str, str, str]]:
    left, right = grouped(stock_text), grouped(other_text)
    found = []
    for key in sorted(set(left) | set(right)):
        if left.get(key) == right.get(key):
            continue
        if key not in right:
            kind = "missing"
        elif key not in left:
            kind = "extra"
        else:
            kind = "value-changed"
        found.append((key[0], key[1], kind))
    return found


def keys_present(text: str, keys: tuple[tuple[str, str], ...]) -> list[list[str]]:
    have = set(grouped(text))
    return [[query, subject] for query, subject in keys if (query, subject) in have]


def id_offset(dmnd: Path, accession: str) -> int | None:
    needle = accession.encode()
    position = 0
    tail = b""
    with dmnd.open("rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                return None
            data = tail + chunk
            found = data.find(needle)
            if found >= 0:
                return position - len(tail) + found
            position += len(chunk)
            tail = data[-(len(needle) - 1) :] if len(needle) > 1 else b""


def sequence_of(raw: str) -> str:
    lines = raw.splitlines()
    return "".join(line.strip() for line in lines[1:])


# DIAMOND's default shapes match the murphy10 alphabet
# (src/stats/stats.cpp:48, "A KR EDNQ C G H ILVM FYW P ST").
_MURPHY = {}
for _group in ("A", "KR", "EDNQ", "C", "G", "H", "ILVM", "FYW", "P", "ST"):
    for _char in _group:
        _MURPHY[_char] = _group[0]


def _reduce(seq: str) -> str:
    return "".join(_MURPHY.get(char, "X") for char in seq)


def shape_hits(query: str, subject: str, shape: str) -> list[dict]:
    """Murphy10 matches whose seed start would read past the entry.

    A seed at subject index ``spos`` reads ``[spos-16, spos+32)``. That window
    leaves the entry when ``spos < 16`` or ``spos + 32 > len(subject)``. Only
    those subject starts are scanned. Positions are on the unreduced sequence.
    """
    query, subject = _reduce(query), _reduce(subject)
    width = len(shape)
    if len(query) < width or len(subject) < width:
        return []
    starts = set(range(min(16, len(subject) - width + 1)))
    for spos in range(max(0, len(subject) - 32), len(subject) - width + 1):
        starts.add(spos)
    hits = []
    for spos in sorted(starts):
        for qpos in range(len(query) - width + 1):
            if _shape_match(query, subject, shape, qpos, spos):
                hits.append(
                    {
                        "shape": shape,
                        "qpos": qpos,
                        "spos": spos,
                        "reads_before_entry": spos < 16,
                        "reads_after_entry": spos + 32 > len(subject),
                    }
                )
                break
        if len(hits) >= 6:
            break
    return hits


def _shape_match(query: str, subject: str, shape: str, qpos: int, spos: int) -> bool:
    for offset, bit in enumerate(shape):
        if bit == "1" and query[qpos + offset] != subject[spos + offset]:
            return False
    return True


def alignment_fields(line: str) -> dict:
    cells = line.split()
    return {
        "line": line,
        "qstart": int(cells[6]),
        "qend": int(cells[7]),
        "sstart": int(cells[8]),
        "send": int(cells[9]),
        "bitscore": cells[11],
    }


def near_boundary(fields: dict, length: int) -> dict:
    # BLAST coordinates are 1-based and inclusive.
    start_distance = fields["sstart"] - 1
    end_distance = length - fields["send"]
    return {
        "subject_length": length,
        "residues_before_alignment": start_distance,
        "residues_after_alignment": end_distance,
        "alignment_starts_within_16": start_distance < 16,
        "alignment_ends_within_32": end_distance < 32,
    }


def neighbor_context(
    order: list[int],
    position: int,
    raws: list[str],
    keys: list[str],
) -> dict:
    pred = None if position == 0 else position - 1
    succ = None if position + 1 == len(order) else position + 1

    def tail(index: int | None, n: int, head: bool) -> str | None:
        if index is None:
            return None
        seq = sequence_of(raws[order[index]])
        return seq[:n] if head else seq[-n:]

    return {
        "predecessor": None if pred is None else keys[order[pred]],
        "successor": None if succ is None else keys[order[succ]],
        "predecessor_last_16": tail(pred, 16, head=False),
        "successor_first_32": tail(succ, 32, head=True),
        "predecessor_is_perimeter": pred is None,
        "successor_is_perimeter": succ is None,
    }


def comparator_control() -> dict:
    sample = "q\ts\t100\t10\t0\t0\t1\t10\t1\t10\t1e-5\t20\n"
    other = sample + "q\tt\t100\t10\t0\t0\t1\t10\t1\t10\t1e-5\t20\n"
    same = classify(sample, sample)
    missing = classify(other, sample)
    ok = (
        not content_of(same)["content_changed"]
        and same["bodies_equal"]
        and missing["row_missing"] == 1
        and missing["row_extra"] == 0
    )
    if not ok:
        raise SystemExit("STOP comparator self-check failed")
    return {
        "identical_content_changed": content_of(same)["content_changed"],
        "deleted_line_row_missing": missing["row_missing"],
        "pass": True,
    }


def require_inputs() -> dict:
    if not DIAMOND.is_file():
        raise SystemExit(f"STOP missing diamond {DIAMOND}")
    diamond = file_id(DIAMOND)
    if (diamond["bytes"], diamond["md5"]) != EXPECTED_DIAMOND:
        raise SystemExit(f"STOP diamond md5 {diamond['md5']}")
    if not SWISSPROT.is_file():
        raise SystemExit(f"STOP missing {SWISSPROT}")
    gz_id = file_id(SWISSPROT)
    if (gz_id["bytes"], gz_id["md5"]) != EXPECTED_FASTA:
        raise SystemExit(f"STOP swissprot gzip md5 {gz_id['md5']} bytes {gz_id['bytes']}")
    free = disk_free_bytes(Path.home())
    log(df_text(Path.home()))
    if free < 8 * (1 << 30):
        raise SystemExit(f"STOP disk free {free} bytes")
    return {"diamond": diamond, "swissprot_gz": gz_id, "disk_free_bytes": free, "df": df_text(Path.home())}


def cleanup(path: Path) -> None:
    if path.is_file():
        path.unlink()


def g1_pilot(stamp: dict) -> Path:
    work = SCRATCH / "g1"
    work.mkdir(parents=True, exist_ok=True)
    log("loading Swiss-Prot")
    raws, keys, lengths = load_swissprot(SWISSPROT)
    letters = sum(lengths)
    if len(keys) != EXPECTED_ENTRIES or letters != EXPECTED_DMND_LETTERS:
        raise SystemExit(f"STOP swissprot entries={len(keys)} letters={letters}")
    key_to_index = {key: index for index, key in enumerate(keys)}
    if len(key_to_index) != len(keys):
        raise SystemExit("STOP duplicate Swiss-Prot ids")

    orig_fa = work / "original.faa"
    log("writing original FASTA")
    write_fasta(raws, list(range(len(keys))), orig_fa)
    fasta_id = file_id(orig_fa)
    if fasta_id["bytes"] < 200_000_000:
        raise SystemExit(f"STOP extracted fasta is unexpectedly small: {fasta_id['bytes']}")

    log("writing shuffled FASTA files")
    for seed in SHUFFLE_SEEDS:
        write_fasta(raws, shuffled_order(len(keys), seed), work / f"shuffle_{seed}.faa")
    del raws

    log("makedb original, twice")
    build_a = makedb(orig_fa, work / "original_a")
    build_b = makedb(orig_fa, work / "original_b")
    build_same = build_a["dmnd"]["md5"] == build_b["dmnd"]["md5"]
    cleanup(Path(str(work / "original_b") + ".dmnd"))
    cleanup(orig_fa)
    db = work / "original_a"
    first_offset = id_offset(Path(str(db) + ".dmnd"), keys[0])

    records = read_records(GENOME)
    if len(records) < PILOT_N + 2000:
        raise SystemExit(f"STOP genome has {len(records)} proteins")
    draw = sorted(random.Random(PILOT_SEED).sample(range(len(records)), PILOT_N))
    query = work / "q300.faa"
    query.write_text("".join(f">{records[i].name}\n{records[i].sequence}\n" for i in draw))
    query_ids = [records[i].name for i in draw]
    query_seqs = {records[i].name: records[i].sequence for i in draw}
    n_records = len(records)
    del records

    log("search original twice")
    first = search(db, query, work / "original_1.m8", [], dbsize=False)
    second = search(db, query, work / "original_2.m8", [], dbsize=False)
    search_same = first["text"] == second["text"]
    stock_text = first["text"]
    stock_rows = first["rows"]

    shuffles = []
    pending: list[dict] = []
    for seed in SHUFFLE_SEEDS:
        log(f"shuffle {seed}")
        order = shuffled_order(len(keys), seed)
        fasta = work / f"shuffle_{seed}.faa"
        built = makedb(fasta, work / f"shuffle_{seed}")
        cleanup(fasta)
        found = search(work / f"shuffle_{seed}", query, work / f"shuffle_{seed}.m8", [], dbsize=False)
        klass = classify(stock_text, found["text"])
        summary = content_of(klass)
        queries = affected_queries(stock_text, found["text"])
        changes = changed_keys(stock_text, found["text"])
        boundary_hits = 0
        for query_id, subject, kind in changes:
            fields = _row_fields(stock_text, found["text"], query_id, subject, kind)
            if subject not in key_to_index:
                continue
            mark = near_boundary(fields, lengths[key_to_index[subject]])
            if mark["alignment_starts_within_16"] or mark["alignment_ends_within_32"]:
                boundary_hits += 1
            if len(pending) < SAMPLE_CAP:
                pending.append(
                    _pending_sample(seed, query_id, subject, kind, fields, mark, order, key_to_index, keys)
                )
        shuffles.append(
            {
                "seed": seed,
                "dmnd": built["dmnd"],
                "first_id": keys[order[0]],
                "first_id_offset": id_offset(Path(str(work / f"shuffle_{seed}") + ".dmnd"), keys[order[0]]),
                "makedb_wall_s": built["wall_s"],
                "search_wall_s": found["wall_s"],
                "peak_rss_kb": found["peak_rss_kb"],
                "log": found["log"],
                "rows": found["rows"],
                "output_md5": found["md5"],
                "comparison": summary,
                "affected_queries": queries,
                "affected_query_count": len(queries),
                "changed_row_count": len(changes),
                "changed_rows_alignment_near_boundary": boundary_hits,
            }
        )
        cleanup(work / f"shuffle_{seed}.m8")
        cleanup(Path(str(work / f"shuffle_{seed}") + ".dmnd"))

    sample_rows = hydrate_samples(pending, query_seqs)
    md5s = [row["dmnd"]["md5"] for row in shuffles]
    distinct = len(set(md5s) | {build_a["dmnd"]["md5"]}) == len(md5s) + 1
    if not search_same or not comparator_control()["pass"]:
        outcome = "CONTROLS_FAILED"
    elif stock_rows < MIN_ROWS or not build_same or not distinct:
        outcome = "INCONCLUSIVE"
    else:
        outcome = "PILOT"
    report = {
        "label": "PILOT",
        "not_a_result": True,
        "outcome": outcome,
        "semantics": "pipeline/results/diamond_order/g_semantics.md",
        "minimum_stock_rows": MIN_ROWS,
        "code_commit": stamp["git"],
        "starting_commit": "507c45fcd2eb3c3e7850791cb2daf5e84400ffab",
        "deviations": [
            "threads 2, dx3 used 8",
            "--tmpdir set to the scratch directory",
            "nice -n 10",
            "RSS killed above 4 GiB",
            "the gzip checksum was applied to the extracted FASTA on the first launch; that launch stopped before any search and was corrected",
        ],
        "inputs": stamp,
        "swissprot": {
            "entries": len(keys),
            "letters": letters,
            "extracted_fasta": fasta_id,
        },
        "genome": {"path": str(GENOME), **file_id(GENOME), "records": n_records},
        "query": {
            "seed": PILOT_SEED,
            "n": PILOT_N,
            "ids": query_ids,
            "fasta_md5": md5_file(query),
        },
        "controls": {
            "comparator": comparator_control(),
            "original_build_md5_equal": build_same,
            "original_build_md5": build_a["dmnd"]["md5"],
            "second_build_md5": build_b["dmnd"]["md5"],
            "original_search_byte_identical": search_same,
            "shuffle_dmnd_all_distinct": distinct,
            "original_first_id": keys[0],
            "original_first_id_offset": first_offset,
        },
        "original_search": {
            "rows": stock_rows,
            "md5": first["md5"],
            "wall_s": first["wall_s"],
            "repeat_wall_s": second["wall_s"],
            "peak_rss_kb": max(first["peak_rss_kb"], second["peak_rss_kb"]),
            "log": first["log"],
            "argv": first["argv"],
            "makedb_argv": build_a["argv"],
            "makedb_wall_s": build_a["wall_s"],
        },
        "shuffles": shuffles,
        "boundary_sample": sample_rows,
        "boundary_sample_note": (
            "Seed coordinates are murphy10 matches of the two default shapes "
            "(src/stats/stats.cpp, src/search/setup.cpp). Only seed starts that "
            "would read outside the entry are scanned, and at most 6 hits are "
            "kept. Alignment proximity uses subject start within 16 residues or "
            "subject end within 32 and is counted for every changed row."
        ),
        "provenance": provenance(versions={"diamond": "2.2.5"}),
    }
    # Drop the bulky texts before writing. They were never stored on report.
    dest = OUT_DIR / "g1_pilot.json"
    write_json(dest, report)
    cleanup(orig_fa)
    cleanup(query)
    cleanup(work / "original_1.m8")
    cleanup(work / "original_2.m8")
    cleanup(Path(str(db) + ".dmnd"))
    log(f"wrote {dest} outcome={outcome} rows={stock_rows}")
    return dest


def _row_fields(stock_text: str, other_text: str, query_id: str, subject: str, kind: str) -> dict:
    source = other_text if kind == "extra" else stock_text
    for line in body_lines(source):
        cells = line.split()
        if cells[0] == query_id and cells[1] == subject:
            return alignment_fields(line)
    raise RuntimeError(f"missing line for {query_id} {subject}")


def _ends(order: list[int], position: int, keys: list[str]) -> dict:
    pred = None if position == 0 else keys[order[position - 1]]
    succ = None if position + 1 == len(order) else keys[order[position + 1]]
    return {
        "predecessor": pred,
        "successor": succ,
        "predecessor_is_perimeter": pred is None,
        "successor_is_perimeter": succ is None,
    }


def _pending_sample(
    seed: int,
    query_id: str,
    subject: str,
    kind: str,
    fields: dict,
    mark: dict,
    order: list[int],
    key_to_index: dict[str, int],
    keys: list[str],
) -> dict:
    original_pos = key_to_index[subject]
    shuffle_pos = order.index(original_pos)
    original = {
        "predecessor": None if original_pos == 0 else keys[original_pos - 1],
        "successor": None if original_pos + 1 == len(keys) else keys[original_pos + 1],
        "predecessor_is_perimeter": original_pos == 0,
        "successor_is_perimeter": original_pos + 1 == len(keys),
    }
    return {
        "shuffle_seed": seed,
        "query": query_id,
        "subject": subject,
        "kind": kind,
        "alignment": fields,
        "boundary": mark,
        "original_neighbors": original,
        "shuffled_neighbors": _ends(order, shuffle_pos, keys),
    }


def _edge(seq: str | None, n: int, head: bool) -> str | None:
    if seq is None:
        return None
    return seq[:n] if head else seq[-n:]


def hydrate_samples(pending: list[dict], query_seqs: dict[str, str]) -> list[dict]:
    needed = set()
    for row in pending:
        needed.add(row["subject"])
        for side in ("original_neighbors", "shuffled_neighbors"):
            needed.add(row[side]["predecessor"])
            needed.add(row[side]["successor"])
    needed.discard(None)
    seqs: dict[str, str] = {}
    if needed:
        with gzip.open(SWISSPROT, "rt") as handle:
            header = ""
            chunks: list[str] = []

            def take() -> None:
                if header:
                    key = header[1:].split()[0]
                    if key in needed:
                        seqs[key] = "".join(chunks)
                chunks.clear()

            for line in handle:
                if line.startswith(">"):
                    take()
                    header = line
                    if len(seqs) == len(needed):
                        break
                elif header[1:].split()[0] in needed:
                    chunks.append(line.strip())
            else:
                take()
    rows = []
    for row in pending:
        subject = seqs.get(row["subject"], "")
        seeds = []
        for shape in SHAPES:
            seeds.extend(shape_hits(query_seqs.get(row["query"], ""), subject, shape))
        crossing = [hit for hit in seeds if hit["reads_before_entry"] or hit["reads_after_entry"]]
        neighbors = {}
        for side in ("original_neighbors", "shuffled_neighbors"):
            block = dict(row[side])
            block["predecessor_last_16"] = _edge(seqs.get(block["predecessor"]), 16, head=False)
            block["successor_first_32"] = _edge(seqs.get(block["successor"]), 32, head=True)
            neighbors[side] = block
        left, right = neighbors["original_neighbors"], neighbors["shuffled_neighbors"]
        rows.append(
            {
                **row,
                "original_neighbors": left,
                "shuffled_neighbors": right,
                "neighbor_context_differs": (
                    left["predecessor_last_16"] != right["predecessor_last_16"]
                    or left["successor_first_32"] != right["successor_first_32"]
                ),
                "raw_shape_hits_capped": seeds,
                "raw_shape_hit_crosses_boundary": bool(crossing),
            }
        )
    return rows


def g2_sweep(stamp: dict) -> Path:
    work = SCRATCH / "g2"
    work.mkdir(parents=True, exist_ok=True)
    log("g2 makedb full and subset")
    raws, keys, _lengths = load_swissprot(SWISSPROT)
    full_fa = work / "full.faa"
    write_fasta(raws, list(range(len(keys))), full_fa)
    del raws
    full_build = makedb(full_fa, work / "full")
    cleanup(full_fa)
    subset_fa = work / "U.faa"
    subset_fa.write_bytes(U_FASTA.read_bytes())
    subset_build = makedb(subset_fa, work / "U")
    cleanup(subset_fa)
    full_db = work / "full"
    subset_db = work / "U"

    log("g2 determinism")
    full_1 = search(full_db, KNOWN_QUERY, work / "full_1.m8", [], dbsize=False)
    full_2 = search(full_db, KNOWN_QUERY, work / "full_2.m8", [], dbsize=False)
    sub_1 = search(subset_db, KNOWN_QUERY, work / "U_1.m8", [], dbsize=True)
    sub_2 = search(subset_db, KNOWN_QUERY, work / "U_2.m8", [], dbsize=True)
    full_same = full_1["text"] == full_2["text"]
    sub_same = sub_1["text"] == sub_2["text"]
    present = keys_present(full_1["text"], LOST_KEYS)
    absent = keys_present(sub_1["text"], LOST_KEYS)
    known_bad = len(present) == 6 and len(absent) == 0

    log("g2 id2 and ignore-warnings controls")
    id2 = search(subset_db, KNOWN_QUERY, work / "U_id2.m8", ["--id2", "1"], dbsize=True)
    id2_back = keys_present(id2["text"], LOST_KEYS)
    ignored = search(subset_db, KNOWN_QUERY, work / "U_ignore.m8", ["--ignore-warnings"], dbsize=True)
    ignore_same = ignored["text"] == sub_1["text"]
    checker_blind = len(id2_back) != 6

    arms = []
    for name, extra in SWEEP:
        log(f"g2 {name}")
        arm = _one_option(name, extra, full_db, subset_db, work, full_1["text"], sub_1["text"])
        arms.append(arm)

    if not full_same or not sub_same:
        outcome = "CONTROLS_FAILED"
    elif checker_blind:
        outcome = "INCONCLUSIVE"
    else:
        outcome = "PILOT"
    checked = [arm["name"] for arm in arms if arm["checked"]]
    returned = [
        {"name": arm["name"], "returned": arm["lost_lines_returned"]}
        for arm in arms
        if arm["checked"] and arm["lost_lines_returned"]
    ]
    matched = [
        arm["name"]
        for arm in arms
        if arm["checked"] and not arm["subset_vs_full"]["content_changed"]
    ]
    report = {
        "label": "PILOT",
        "not_a_result": True,
        "outcome": outcome,
        "semantics": "pipeline/results/diamond_order/g_semantics.md",
        "code_commit": stamp["git"],
        "starting_commit": "507c45fcd2eb3c3e7850791cb2daf5e84400ffab",
        "known_bad_keys": [list(key) for key in LOST_KEYS],
        "deviations": [
            "threads 2, dx3 used 8",
            "--tmpdir set to the scratch directory",
            "nice -n 10",
        ],
        "inputs": stamp,
        "databases": {"full": full_build["dmnd"], "subset": subset_build["dmnd"]},
        "query": {**file_id(KNOWN_QUERY)},
        "controls": {
            "full_search_byte_identical": full_same,
            "subset_search_byte_identical": sub_same,
            "known_bad_six_present_in_full": len(present) == 6,
            "known_bad_six_absent_from_subset": len(absent) == 0,
            "known_bad_reproduced": known_bad,
            "full_vs_subset": content_of(classify(full_1["text"], sub_1["text"])),
            "id2_1_returned_keys": id2_back,
            "id2_1_checker_sees_all_six": len(id2_back) == 6,
            "ignore_warnings_byte_identical_to_default_subset": ignore_same,
            "ignore_warnings_still_missing": keys_present(ignored["text"], LOST_KEYS) == [],
            "checker_blind": checker_blind,
        },
        "default_full": {
            "rows": full_1["rows"],
            "md5": full_1["md5"],
            "wall_s": full_1["wall_s"],
            "peak_rss_kb": full_1["peak_rss_kb"],
            "log": full_1["log"],
            "argv": full_1["argv"],
        },
        "default_subset": {
            "rows": sub_1["rows"],
            "md5": sub_1["md5"],
            "wall_s": sub_1["wall_s"],
            "peak_rss_kb": sub_1["peak_rss_kb"],
            "log": sub_1["log"],
            "argv": sub_1["argv"],
        },
        "not_checked": [
            "--ignore-warnings (negative control only)",
            "--comp-based-stats (dx3_rootcause.json, not re-run)",
            "--no-ranking (dx3_rootcause.json, not re-run)",
            "--dbsize (dx3_rootcause.json, not re-run; the subset arm still pins it)",
            "--swipe (not run; exhaustive alignment can exceed 4 GiB)",
            "--evalue --matrix --gapopen --gapextend --top --max-hsps --range-culling --global-ranking",
            "--iterate (the sensitivity modes are separate arms)",
        ],
        "checked_options": checked,
        "options_that_returned_any_lost_line": returned,
        "options_where_subset_matches_full": matched,
        "arms": arms,
        "provenance": provenance(versions={"diamond": "2.2.5"}),
    }
    dest = OUT_DIR / "g2_options.json"
    write_json(dest, report)
    for path in work.glob("*"):
        if path.is_file():
            path.unlink()
    log(f"wrote {dest} outcome={outcome} checked={len(checked)}")
    return dest


def _one_option(
    name: str,
    extra: list[str],
    full_db: Path,
    subset_db: Path,
    work: Path,
    full_default: str,
    subset_default: str,
) -> dict:
    try:
        full = search(full_db, KNOWN_QUERY, work / f"full_{name}.m8", extra, dbsize=False)
        subset = search(subset_db, KNOWN_QUERY, work / f"U_{name}.m8", extra, dbsize=True)
    except RunFailed as exc:
        cleanup(work / f"full_{name}.m8")
        cleanup(work / f"U_{name}.m8")
        return {
            "name": name,
            "extra": extra,
            "checked": False,
            "error": str(exc)[-500:],
            "lost_lines_returned": 0,
            "returned_keys": [],
            "still_missing_keys": [list(key) for key in LOST_KEYS],
            "subset_vs_full": None,
            "subset_vs_default_subset": None,
            "full_vs_default_full": None,
        }
    returned = keys_present(subset["text"], LOST_KEYS)
    still = [[q, s] for q, s in LOST_KEYS if [q, s] not in returned]
    arm = {
        "name": name,
        "extra": extra,
        "checked": True,
        "error": None,
        "lost_lines_returned": len(returned),
        "returned_keys": returned,
        "still_missing_keys": still,
        "full_has_lost_keys": keys_present(full["text"], LOST_KEYS),
        "subset_vs_full": content_of(classify(full["text"], subset["text"])),
        "subset_vs_default_subset": content_of(classify(subset_default, subset["text"])),
        "full_vs_default_full": content_of(classify(full_default, full["text"])),
        "full_rows": full["rows"],
        "subset_rows": subset["rows"],
        "full_md5": full["md5"],
        "subset_md5": subset["md5"],
        "full_wall_s": full["wall_s"],
        "subset_wall_s": subset["wall_s"],
        "peak_rss_kb": max(full["peak_rss_kb"], subset["peak_rss_kb"]),
        "full_log": full["log"],
        "subset_argv": subset["argv"],
        "full_argv": full["argv"],
    }
    cleanup(work / f"full_{name}.m8")
    cleanup(work / f"U_{name}.m8")
    return arm


def main() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    if "tmpfs" in df_text(SCRATCH).lower():
        raise SystemExit("STOP scratch is tmpfs")
    comparator_control()
    stamp = require_inputs()
    version = run_limited([str(DIAMOND), "version"], 30)
    stamp["diamond_version"] = (version["stdout"] or version["stderr"]).strip()
    stamp["provenance_at_start"] = provenance(versions={"diamond": stamp["diamond_version"]})
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in {"g1", "all"}:
        g1_pilot(stamp)
    if which in {"g2", "all"}:
        g2_sweep(stamp)


if __name__ == "__main__":
    main()
