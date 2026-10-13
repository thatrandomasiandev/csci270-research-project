#!/usr/bin/env python3
"""Test D-X. Names the locked argv. Calls acts/ for the pin. No new normalizer."""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from acts.infer_knobs import (  # noqa: E402
    apply_extra_argv,
    capture_help_argv,
    infer_knobs,
    parse_help_options,
)
from acts.provenance import provenance  # noqa: E402
from acts.reference_formats import parse_reference, read_records, write_entries  # noqa: E402
from acts.reference_run import pin_tokens, pin_values  # noqa: E402

from run_reference_diamond import dbinfo_letters, pearson, s1_argv  # noqa: E402

PIPE = ROOT
DATA = PIPE / "data" / "swissprot"
WORK = PIPE / "data" / "reference_diamond_dx"
OUT = PIPE / "results" / "reference_diamond" / "dx.json"
D2 = PIPE / "results" / "reference_diamond" / "reference_diamond_d2.json"
DIAMOND = PIPE / "builds" / "diamond-2.2.5" / "diamond"
ISEQ = PIPE / "builds" / "Incremental-Protein-Search"
PY = PIPE / "builds" / "diamond-dx-venv" / "bin" / "python"
Q_MAIN = PIPE / "data" / "recurrence" / "A" / "GCF_002853805.1_protein.faa.gz"
Q_HELD = PIPE / "data" / "recurrence" / "A" / "GCF_002090355.1_protein.faa.gz"

NEW_FA = DATA / "uniprot_sprot_2026_03.fasta.gz"
OLD_FA = DATA / "uniprot_sprot_2026_01.fasta.gz"
EXPECTED = {
    "new": (93801562, "bc9d398533e6df582b563c6c03093bd0"),
    "old": (93457057, "5245b19456d9a063b13c46602269bc5f"),
    "queries": (1074926, "b170d133266427c46d87d99284e1fda3"),
    "iseq_main": (2477, "2c0762059f0229add06bf351edb2f979"),
}
EXPECTED_PIN = "--dbsize {total_entry_length}"
DECOY_TOKENS = {"--threads", "-p", "--block-size", "-b", "--index-chunks", "-c"}
INTERVAL = (6, 7, 8, 9)
EVALUE_COL = 10
GIB = 1024**3
STOCK_RSS = 18 * GIB
PROBE_RSS = 8 * GIB


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


def assert_not_tmpfs(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    df = subprocess.run(["df", "-h", str(path)], check=False, capture_output=True, text=True)
    mount = subprocess.run(["mount"], check=False, capture_output=True, text=True)
    text = f"{df.stdout}\n{mount.stdout}".lower()
    if "tmpfs" in df.stdout.lower() or "ramdisk" in text:
        raise SystemExit("STOP scratch is tmpfs or a RAM disk")
    return df.stdout.strip()


def check_identity(path: Path, expected: tuple[int, str], label: str) -> dict:
    if not path.is_file():
        raise SystemExit(f"STOP_INPUTS missing {label}: {path}")
    found = file_id(path)
    if found["bytes"] != expected[0] or found["md5"] != expected[1]:
        raise SystemExit(
            f"STOP_INPUTS {label} bytes={found['bytes']} md5={found['md5']} "
            f"expected bytes={expected[0]} md5={expected[1]}"
        )
    return found


def rss_bytes(pid: int) -> int:
    proc = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(pid)],
        check=False,
        capture_output=True,
        text=True,
    )
    token = proc.stdout.strip().split()
    if not token:
        return 0
    try:
        return int(token[0]) * 1024
    except ValueError:
        return 0


def run_cmd(cmd: list[str], timeout: float, rss_cap: int) -> tuple[str, str, float]:
    started = time.perf_counter()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    while proc.poll() is None:
        if time.perf_counter() - started > timeout:
            proc.kill()
            proc.wait(timeout=10)
            raise RuntimeError(f"timeout after {timeout:.0f}s")
        if rss_bytes(proc.pid) > rss_cap:
            proc.kill()
            proc.wait(timeout=10)
            raise RuntimeError(f"rss cap {rss_cap} bytes")
        time.sleep(0.4)
    stdout, stderr = proc.communicate()
    wall = time.perf_counter() - started
    if proc.returncode != 0:
        tail = (stderr or stdout or "")[-800:]
        raise RuntimeError(f"exit {proc.returncode}: {tail}")
    return stdout or "", stderr or "", wall


def refuse_probe(extra: list[str]) -> None:
    index = 0
    while index < len(extra):
        option = extra[index]
        value = None
        if index + 1 < len(extra) and not str(extra[index + 1]).startswith("-"):
            value = str(extra[index + 1])
            index += 2
        else:
            index += 1
        if option == "--threads" and value != "32":
            raise RuntimeError("worker-count probe refused")
        if option in {"-b", "--block-size"} and value != "2.0":
            raise RuntimeError("block-size probe refused")
        if option in {"-c", "--index-chunks"}:
            try:
                number = int(float(value or ""))
            except ValueError as exc:
                raise RuntimeError("index-chunk probe refused") from exc
            if number > 64:
                raise RuntimeError("index-chunk probe refused")


def concrete_argv(db: Path, query: Path, out: Path, extra: list[str] | None = None) -> list[str]:
    argv = s1_argv(str(DIAMOND), k="0")
    repl = {"{reference}": str(db), "{input}": str(query), "{output}": str(out)}
    argv = [repl.get(token, token) for token in argv]
    if extra:
        argv = apply_extra_argv(argv, extra)
    return argv


def makedb(fasta: Path) -> float:
    dmnd = Path(str(fasta) + ".dmnd")
    stamp = Path(str(fasta) + ".dmnd.ok")
    if dmnd.is_file() and stamp.is_file():
        return 0.0
    if dmnd.is_file():
        dmnd.unlink()
    log(f"makedb {fasta.name}")
    _out, _err, wall = run_cmd(
        [str(DIAMOND), "makedb", "--in", str(fasta), "--db", str(fasta), "--threads", "32"],
        3600,
        STOCK_RSS,
    )
    stamp.write_text("ok\n")
    return wall


def letters(fasta: Path) -> int:
    stdout, _err, _wall = run_cmd(
        [str(DIAMOND), "dbinfo", "--db", str(fasta)],
        120,
        STOCK_RSS,
    )
    return dbinfo_letters(stdout)


def blast(
    db: Path,
    query: Path,
    out: Path,
    extra: list[str] | None = None,
    *,
    probe: bool = False,
) -> float:
    if extra and probe:
        refuse_probe(list(extra))
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_suffix(out.suffix + ".partial")
    cmd = concrete_argv(db, query, partial, extra)
    _stdout, _stderr, wall = run_cmd(
        cmd,
        600 if probe else 3600,
        PROBE_RSS if probe else STOCK_RSS,
    )
    partial.replace(out)
    return wall


def body_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def write_queries(records, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for rec in records:
            desc = f" {rec.description}" if rec.description else ""
            handle.write(f">{rec.name}{desc}\n{rec.sequence}\n")


def subset_fasta(entries, path: Path) -> Path:
    digest = hashlib.sha256("".join(entry.content_hash for entry in entries).encode()).hexdigest()[:16]
    dest = path.parent / f"{path.name}.{digest}.faa"
    if not dest.is_file():
        write_entries(list(entries), dest)
    return dest


def index_pairs(lines: list[str]) -> dict[tuple[str, str], list[str]]:
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for line in lines:
        cells = line.split()
        if len(cells) < 2:
            continue
        grouped[(cells[0], cells[1])].append(line)
    return grouped


def classify_bodies(stock_text: str, other_text: str) -> dict:
    stock = index_pairs(body_lines(stock_text))
    other = index_pairs(body_lines(other_text))
    counts: Counter[str] = Counter()
    both = set(stock) & set(other)
    for key in set(stock) - set(other):
        counts["row_missing"] += len(stock[key])
    for key in set(other) - set(stock):
        counts["row_extra"] += len(other[key])
    identical = 0
    for key in both:
        left, right = stock[key], other[key]
        if left == right:
            identical += len(left)
            continue
        # One reported HSP per pair under the locked default. Extra copies are extra rows.
        n = min(len(left), len(right))
        for index in range(n):
            a = left[index].split()
            b = right[index].split()
            if len(a) > 9 and len(b) > 9 and tuple(a[i] for i in INTERVAL) == tuple(b[i] for i in INTERVAL):
                counts["same_hsp_different_value"] += 1
            else:
                counts["different_hsp"] += 1
        if len(left) > n:
            counts["row_missing"] += len(left) - n
        if len(right) > n:
            counts["row_extra"] += len(right) - n
    stock_n = sum(len(rows) for rows in stock.values())
    other_n = sum(len(rows) for rows in other.values())
    shared = sum(min(len(stock[key]), len(other[key])) for key in both)
    result = {
        "stock_rows": stock_n,
        "other_rows": other_n,
        "shared_rows": shared,
        "shared_byte_identical": identical,
        "shared_byte_fraction": (identical / shared) if shared else None,
        "only_stock": counts["row_missing"],
        "only_other": counts["row_extra"],
        "same_hsp_different_value": counts["same_hsp_different_value"],
        "different_hsp": counts["different_hsp"],
        "row_missing": counts["row_missing"],
        "row_extra": counts["row_extra"],
        "bodies_equal": body_lines(stock_text) == body_lines(other_text),
    }
    counts_zero = not any(
        result[name]
        for name in ("same_hsp_different_value", "different_hsp", "row_missing", "row_extra")
    )
    result["line_order_only"] = (not result["bodies_equal"]) and counts_zero
    return result


def tie_pairs(values: list[float]) -> int:
    counts = Counter(values)
    return sum(count * (count - 1) // 2 for count in counts.values())


class _Fenwick:
    def __init__(self, n: int) -> None:
        self.n = n
        self.tree = [0] * (n + 1)

    def add(self, index: int) -> None:
        while index <= self.n:
            self.tree[index] += 1
            index += index & -index

    def sum(self, index: int) -> int:
        total = 0
        while index:
            total += self.tree[index]
            index -= index & -index
        return total


def kendall_tau(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    n0 = n * (n - 1) // 2
    n1 = tie_pairs(xs)
    n2 = tie_pairs(ys)
    denom = ((n0 - n1) * (n0 - n2)) ** 0.5
    if denom == 0:
        return None
    order = sorted(set(ys))
    rank = {value: index + 1 for index, value in enumerate(order)}
    bit = _Fenwick(len(order))
    concordant = 0
    discordant = 0
    indices = sorted(range(n), key=lambda i: (xs[i], ys[i]))
    cursor = 0
    while cursor < n:
        end = cursor
        while end < n and xs[indices[end]] == xs[indices[cursor]]:
            end += 1
        for pos in range(cursor, end):
            ry = rank[ys[indices[pos]]]
            less = bit.sum(ry - 1)
            greater = bit.sum(len(order)) - bit.sum(ry)
            concordant += less
            discordant += greater
        for pos in range(cursor, end):
            bit.add(rank[ys[indices[pos]]])
        cursor = end
    return (concordant - discordant) / denom


def correlation(stock_text: str, other_text: str) -> dict:
    stock = index_pairs(body_lines(stock_text))
    other = index_pairs(body_lines(other_text))
    xs: list[float] = []
    ys: list[float] = []
    duplicates = 0
    for key in set(stock) & set(other):
        if len(stock[key]) != 1 or len(other[key]) != 1:
            duplicates += 1
            continue
        left = stock[key][0].split()
        right = other[key][0].split()
        if len(left) <= EVALUE_COL or len(right) <= EVALUE_COL:
            continue
        try:
            xs.append(float(left[EVALUE_COL]))
            ys.append(float(right[EVALUE_COL]))
        except ValueError:
            continue
    base = classify_bodies(stock_text, other_text)
    base["evalue_pearson"] = pearson(xs, ys)
    base["evalue_kendall_tau"] = kendall_tau(xs, ys)
    base["n_correlation"] = len(xs)
    base["n_duplicate_pairs_skipped"] = duplicates
    return base


def is_decoy(option: str, help_line: str) -> bool:
    if option in DECOY_TOKENS:
        return True
    blob = f"{option} {help_line}".lower()
    return "seed" in blob or "shape" in blob


def load_contract() -> list[dict]:
    payload = json.loads(D2.read_text())
    tables = payload["fit"]["tables"]
    members = [col.get("member") for table in tables for col in table.get("columns") or []]
    if "total_entry_length" not in members or "entry_count" in members:
        raise SystemExit(f"STOP D2 contract members are {sorted(set(members))}")
    return tables


def key_index(entries) -> dict[str, int]:
    found: dict[str, int] = {}
    for index, entry in enumerate(entries):
        for token in entry.keys:
            found.setdefault(token, index)
    return found


def stratified_half(w: list[int], hit: set[int], rng: random.Random) -> list[int]:
    w_hit = [i for i in w if i in hit]
    w_fill = [i for i in w if i not in hit]
    selected = set(rng.sample(w_hit, len(w_hit) // 2)) if w_hit else set()
    if w_fill:
        selected.update(rng.sample(w_fill, len(w_fill) // 2))
    if len(selected) < 200:
        for index in w_fill + w_hit:
            if len(selected) >= 200:
                break
            selected.add(index)
    return [i for i in w if i in selected]


def build_heldout(new_entries, held_records) -> dict:
    n = len(held_records)
    draw = sorted(random.Random(20261018).sample(range(n), 300))
    drawn = [held_records[i] for i in draw]
    query_path = WORK / "k_draw.faa"
    write_queries(drawn, query_path)
    makedb(NEW_FA)
    out = WORK / "k_construct.m8"
    log("DX-K sample construction: 300 held-out queries on 2026_03")
    built_search = ensure_search(NEW_FA, query_path, out)
    wall = built_search["wall_s"]
    lines = body_lines(out.read_text())
    hit_names = {line.split()[0] for line in lines if line.split()}
    chosen: list[int] = []
    for index in draw:
        if held_records[index].name in hit_names:
            chosen.append(index)
        if len(chosen) == 50:
            break
    report = {
        "label": "SAMPLE-CONSTRUCTION",
        "wall_s": wall,
        "draw_n": 300,
        "body_rows": len(lines),
        "queries_with_hit": sum(1 for i in draw if held_records[i].name in hit_names),
        "q_n": len(chosen),
    }
    if len(chosen) < 50:
        report["verdict"] = "INCONCLUSIVE"
        report["why"] = "fewer than 50 queries with a hit"
        return report
    lookup = key_index(new_entries)
    matched: set[int] = set()
    unmatched = 0
    q_names = {held_records[i].name for i in chosen}
    q_subjects = {line.split()[1] for line in lines if line.split()[0] in q_names and len(line.split()) > 1}
    for subject in q_subjects:
        index = lookup.get(subject)
        if index is None:
            unmatched += 1
        else:
            matched.add(index)
    hit_order = [i for i in range(len(new_entries)) if i in matched]
    truncated = len(hit_order) > 400
    if truncated:
        w = hit_order[:400]
    else:
        rest = [i for i in range(len(new_entries)) if i not in matched]
        need = 400 - len(hit_order)
        if len(rest) < need:
            report["verdict"] = "INCONCLUSIVE"
            report["why"] = "fewer than 400 entries available for W"
            report["hit_entries"] = len(hit_order)
            return report
        fill = random.Random(20261018).sample(rest, need)
        w_set = set(hit_order) | set(fill)
        w = [i for i in range(len(new_entries)) if i in w_set]
    half = stratified_half(w, matched, random.Random(20261018))
    if len(w) < 400 or len(half) != 200:
        report["verdict"] = "INCONCLUSIVE"
        report["why"] = f"|W|={len(w)} |H|={len(half)}"
        return report
    report.update(
        {
            "unmatched_subjects": unmatched,
            "hit_entries": len(hit_order),
            "w_truncated": truncated,
            "w_n": len(w),
            "h_n": len(half),
            "q_indices": chosen,
            "w_indices": w,
            "h_indices": half,
        }
    )
    return report


def run_dx_k(new_entries) -> dict:
    checkpoint = WORK / "dx_k.json"
    if checkpoint.is_file():
        log("DX-K checkpoint present")
        return json.loads(checkpoint.read_text())
    held = read_records(Q_HELD)
    built = build_heldout(new_entries, held)
    if built.get("verdict") == "INCONCLUSIVE":
        write_json(checkpoint, built)
        return built
    q = [held[i] for i in built["q_indices"]]
    whole = [new_entries[i] for i in built["w_indices"]]
    half = [new_entries[i] for i in built["h_indices"]]
    argv = s1_argv(str(DIAMOND), k="0")
    help_text = capture_help_argv(argv)
    candidates = parse_help_options(help_text)
    call_log: list[dict] = []
    subset_dir = WORK / "k_subsets"
    subset_dir.mkdir(parents=True, exist_ok=True)

    def invoke(records, entries, extra):
        query = subset_dir / f"q{len(call_log)}.faa"
        write_queries(records, query)
        reference = subset_fasta(entries, subset_dir / "ref")
        makedb(reference)
        dest = subset_dir / f"out{len(call_log)}.m8"
        started = time.perf_counter()
        wall = blast(reference, query, dest, list(extra), probe=True)
        text = dest.read_text()
        call_log.append(
            {
                "n_records": len(records),
                "n_entries": len(entries),
                "extra": list(extra),
                "rows": len(body_lines(text)),
                "wall_s": wall,
                "clock_s": time.perf_counter() - started,
            }
        )
        return {"out": text}

    log(f"DX-K infer_knobs candidates={len(candidates)}")
    started = time.perf_counter()
    result = infer_knobs(help_text, q, whole, half, load_contract(), invoke)
    decoys = []
    for candidate in result.get("candidates") or []:
        if not is_decoy(candidate["option"], candidate.get("help_line") or ""):
            continue
        norms = candidate.get("normalizer") or {}
        if any(value == "accept" for value in norms.values()):
            decoys.append({"option": candidate["option"], "as": "pin"})
    for threshold in result.get("thresholds") or []:
        if is_decoy(threshold.get("option") or "", ""):
            decoys.append({"option": threshold.get("option"), "as": "threshold"})
    pin = result.get("pin")
    verdict = "PASS" if pin == EXPECTED_PIN and not decoys else "KILL"
    payload = {
        "verdict": verdict,
        "expected_pin": EXPECTED_PIN,
        "pin": pin,
        "reason": result.get("reason"),
        "decoys_accepted": decoys,
        "help_candidates": len(candidates),
        "tool_calls": result.get("tool_calls"),
        "members": result.get("members"),
        "thresholds": result.get("thresholds"),
        "candidates": result.get("candidates"),
        "construction": {k: v for k, v in built.items() if not k.endswith("indices")},
        "calls": call_log,
        "wall_s": time.perf_counter() - started,
    }
    write_json(checkpoint, payload)
    log(f"DX-K {verdict} pin={pin!r} candidates={len(candidates)}")
    return payload


def queries_300():
    records = read_records(Q_MAIN)
    indices = sorted(random.Random(20261017).sample(range(len(records)), 300))
    chosen = [records[i] for i in indices]
    path = WORK / "q300.faa"
    if not path.is_file():
        write_queries(chosen, path)
    return chosen, path


def ensure_search(db: Path, query: Path, out: Path, extra: list[str] | None = None) -> dict:
    if out.is_file() and out.stat().st_size > 0:
        return {"wall_s": None, "reused": True, "rows": len(body_lines(out.read_text())), "path": str(out)}
    log(f"blast {db.name} -> {out.name}")
    wall = blast(db, query, out, extra, probe=False)
    return {"wall_s": wall, "reused": False, "rows": len(body_lines(out.read_text())), "path": str(out)}


def run_dx_e1(new_entries, qrecs, qpath, pin: str) -> dict:
    checkpoint = WORK / "dx_e1.json"
    if checkpoint.is_file():
        return json.loads(checkpoint.read_text())
    stock = ensure_search(NEW_FA, qpath, WORK / "stock_2026_03.m8")
    stock_text = (WORK / "stock_2026_03.m8").read_text()
    lines = body_lines(stock_text)
    hit_names = {line.split()[0] for line in lines}
    subjects = {line.split()[1] for line in lines if len(line.split()) > 1}
    lookup = key_index(new_entries)
    matched = {lookup[s] for s in subjects if s in lookup}
    union = [new_entries[i] for i in range(len(new_entries)) if i in matched]
    replay_q = [rec for rec in qrecs if rec.name in hit_names]
    q_replay = WORK / "e1_queries.faa"
    write_queries(replay_q, q_replay)
    reference = subset_fasta(union, WORK / "e1_union.faa")
    makedb(reference)
    values = pin_values(new_entries)
    extra = pin_tokens(pin, values)
    r_path = WORK / "e1_R.m8"
    rn_path = WORK / "e1_Rn.m8"
    r_wall = blast(reference, q_replay, r_path, extra, probe=False)
    rn_wall = blast(reference, q_replay, rn_path, None, probe=False)
    r_text = r_path.read_text()
    rn_text = rn_path.read_text()
    compared = classify_bodies(stock_text, r_text)
    rn_equal = body_lines(rn_text) == body_lines(stock_text)
    verdict = "PASS" if compared["bodies_equal"] and not rn_equal else "KILL"
    payload = {
        "verdict": verdict,
        "pin_argv": extra,
        "pin_value": values,
        "queries_with_hit": len(replay_q),
        "union_entries": len(union),
        "unmatched_subjects": len(subjects - set(lookup)),
        "stock": stock,
        "r_wall_s": r_wall,
        "rn_wall_s": rn_wall,
        "rn_differs": not rn_equal,
        "compare": compared,
    }
    write_json(checkpoint, payload)
    log(f"DX-E1 {verdict}")
    return payload


def changed_entries(old_entries, new_entries):
    old_hashes = {entry.content_hash for entry in old_entries}
    return [entry for entry in new_entries if entry.content_hash not in old_hashes]


def run_dx_e2(old_entries, new_entries, qrecs, qpath, pin: str) -> dict:
    checkpoint = WORK / "dx_e2.json"
    if checkpoint.is_file():
        return json.loads(checkpoint.read_text())
    changed = changed_entries(old_entries, new_entries)
    old_hashes = {entry.content_hash for entry in old_entries}
    by_key = key_index(new_entries)
    unchanged = {
        new_entries[i].content_hash
        for i in range(len(new_entries))
        if new_entries[i].content_hash in old_hashes
    }
    stock_old = ensure_search(OLD_FA, qpath, WORK / "stock_2026_01.m8")
    stock_new = ensure_search(NEW_FA, qpath, WORK / "stock_2026_03.m8")
    delta = WORK / "delta.faa"
    write_entries(changed, delta)
    makedb(delta)
    discovery = ensure_search(delta, qpath, WORK / "discovery_slack.m8", ["--evalue", "0.002"])
    cached = []
    for line in body_lines((WORK / "stock_2026_01.m8").read_text()):
        cells = line.split()
        index = by_key.get(cells[1]) if len(cells) > 1 else None
        if index is not None and new_entries[index].content_hash in unchanged:
            cached.append(line)
    discovered = body_lines((WORK / "discovery_slack.m8").read_text())
    wanted: set[str] = set()
    query_names: set[str] = set()
    for line in cached + discovered:
        cells = line.split()
        if len(cells) < 2:
            continue
        index = by_key.get(cells[1])
        if index is None:
            continue
        wanted.add(new_entries[index].content_hash)
        query_names.add(cells[0])
    union = [entry for entry in new_entries if entry.content_hash in wanted]
    replay_q = [rec for rec in qrecs if rec.name in query_names]
    q_replay = WORK / "e2_queries.faa"
    write_queries(replay_q, q_replay)
    reference = subset_fasta(union, WORK / "e2_union.faa")
    makedb(reference)
    extra = pin_tokens(pin, pin_values(new_entries))
    r_path = WORK / "e2_R.m8"
    wall = blast(reference, q_replay, r_path, extra, probe=False)
    compared = classify_bodies((WORK / "stock_2026_03.m8").read_text(), r_path.read_text())
    verdict = "PASS" if compared["bodies_equal"] else "KILL"
    payload = {
        "verdict": verdict,
        "changed_or_new": len(changed),
        "cached_rows": len(cached),
        "discovery_rows": len(discovered),
        "union_entries": len(union),
        "replay_queries": len(replay_q),
        "pin_argv": extra,
        "slack": {"option": "--evalue", "value": "0.002", "factor": 2},
        "stock_old": stock_old,
        "stock_new": stock_new,
        "discovery": discovery,
        "replay_wall_s": wall,
        "compare": compared,
    }
    write_json(checkpoint, payload)
    log(f"DX-E2 {verdict}")
    return payload


def run_dx_i(old_entries, new_entries, qpath, acts_text: str | None) -> dict:
    checkpoint = WORK / "dx_i.json"
    if checkpoint.is_file():
        return json.loads(checkpoint.read_text())
    changed = changed_entries(old_entries, new_entries)
    delta = WORK / "delta.faa"
    write_entries(changed, delta)
    makedb(OLD_FA)
    makedb(NEW_FA)
    makedb(delta)
    stock_old = ensure_search(OLD_FA, qpath, WORK / "stock_2026_01.m8")
    stock_new = ensure_search(NEW_FA, qpath, WORK / "stock_2026_03.m8")
    delta_search = ensure_search(delta, qpath, WORK / "delta_s1.m8")
    l_old = letters(OLD_FA)
    l_delta = letters(delta)
    merged = WORK / "idiamond.m8"
    cmd = [
        str(PY),
        str(ISEQ / "source" / "main.py"),
        "--default",
        str(WORK / "stock_2026_01.m8"),
        str(WORK / "delta_s1.m8"),
        str(merged),
        str(l_old),
        str(l_delta),
    ]
    log("DX-I iSeqSearch merge")
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=ISEQ / "source", check=False, capture_output=True, text=True)
    wall = time.perf_counter() - started
    payload: dict = {
        "l_old": l_old,
        "l_delta": l_delta,
        "l_sum": l_old + l_delta,
        "changed_or_new": len(changed),
        "stock_old": stock_old,
        "stock_new": stock_new,
        "delta": delta_search,
        "merger_wall_s": wall,
        "merger_exit": proc.returncode,
    }
    stock_text = (WORK / "stock_2026_03.m8").read_text()
    if proc.returncode != 0 or not merged.is_file():
        payload["ran"] = False
        payload["why"] = (proc.stderr or proc.stdout or "")[-1000:]
    else:
        payload["ran"] = True
        payload["idiamond"] = correlation(stock_text, merged.read_text())
    if acts_text is None:
        payload["acts"] = {"ran": False, "why": "DX-E2 did not produce a body"}
    else:
        payload["acts"] = correlation(stock_text, acts_text)
        payload["acts"]["ran"] = True
    write_json(checkpoint, payload)
    log(f"DX-I ran={payload['ran']}")
    return payload


def diamond_version() -> str:
    proc = subprocess.run([str(DIAMOND), "version"], check=False, capture_output=True, text=True)
    text = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0 or "2.2.5" not in text:
        raise SystemExit(f"STOP diamond version is not 2.2.5: {text}")
    return text


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    df_text = assert_not_tmpfs(WORK)
    try:
        identities = {
            "new": check_identity(NEW_FA, EXPECTED["new"], "2026_03"),
            "old": check_identity(OLD_FA, EXPECTED["old"], "2026_01"),
            "queries": check_identity(Q_MAIN, EXPECTED["queries"], "GCF_002853805.1"),
            "iseq_main": check_identity(ISEQ / "source" / "main.py", EXPECTED["iseq_main"], "iSeqSearch main.py"),
        }
    except SystemExit as exc:
        write_json(OUT, {"verdict": "STOP_INPUTS", "why": str(exc)})
        raise
    identities["heldout_queries"] = file_id(Q_HELD)
    identities["diamond"] = file_id(DIAMOND)
    version = diamond_version()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PIPE.parents[0], check=False, capture_output=True, text=True
    ).stdout.strip()
    log(f"diamond {version} head {head}")
    log("parsing 2026_03")
    new_entries = parse_reference(NEW_FA)
    log(f"2026_03 entries {len(new_entries)}")
    qrecs, qpath = queries_300()
    payload: dict = {
        "test": "D-X",
        "diamond_version": version,
        "git_head_at_start": head,
        "scratch_df": df_text,
        "inputs": identities,
        "s1": s1_argv(str(DIAMOND), k="0"),
        "query_n": 300,
        "new_entries": len(new_entries),
        "new_letters": sum(entry.length for entry in new_entries),
    }
    k = run_dx_k(new_entries)
    payload["dx_k"] = k
    write_json(OUT, payload)
    acts_text = None
    if k.get("verdict") != "PASS":
        payload["dx_e1"] = {"verdict": "NOT_RUN", "why": k.get("verdict")}
        payload["dx_e2"] = {"verdict": "NOT_RUN", "why": k.get("verdict")}
        payload["exact_mode"] = "not claimed"
    else:
        e1 = run_dx_e1(new_entries, qrecs, qpath, k["pin"])
        payload["dx_e1"] = e1
        write_json(OUT, payload)
        if e1.get("verdict") != "PASS":
            payload["dx_e2"] = {"verdict": "NOT_RUN", "why": "DX-E1 kill"}
            payload["exact_mode"] = "not claimed"
        else:
            log("parsing 2026_01")
            old_entries = parse_reference(OLD_FA)
            e2 = run_dx_e2(old_entries, new_entries, qrecs, qpath, k["pin"])
            payload["dx_e2"] = e2
            payload["exact_mode"] = "claimed" if e2.get("verdict") == "PASS" else "not claimed"
            if (WORK / "e2_R.m8").is_file():
                acts_text = (WORK / "e2_R.m8").read_text()
            write_json(OUT, payload)
            payload["old_entries"] = len(old_entries)
            payload["old_letters"] = sum(entry.length for entry in old_entries)
    if "old_entries" not in payload:
        log("parsing 2026_01")
        old_entries = parse_reference(OLD_FA)
        payload["old_entries"] = len(old_entries)
        payload["old_letters"] = sum(entry.length for entry in old_entries)
    payload["dx_i"] = run_dx_i(old_entries, new_entries, qpath, acts_text)
    payload["provenance"] = provenance(versions={"diamond": version})
    write_json(OUT, payload)
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
