#!/usr/bin/env python3
"""E3 of docs/EXACT_REPLAY_PROTOCOL.md: pinned replay under E-value reporting.

Experiment driver, not the shipped path. Parameters are the pre-registered
addendum (commit 4ae39ab). Body = lines that do not start with '#'.
Walls are one run and indicative.
"""
from __future__ import annotations

import argparse, gzip, hashlib, json, os, platform, random, re, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acts.entry_hash import entry_content_hash  # noqa: E402
from acts.reference_formats import PROFILE_VOLATILE_TAGS  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PIPE = Path(__file__).resolve().parents[1]
PRE_REG = "4ae39ab66c9283d547e5930bcb99d5022fd9d864"
Z_STATED = {"38.1": 27481, "38.2": 30134}
CPU = 4
BASE_E = 10
MIN_FREE = 6 * 1024 ** 3

HMMER = os.environ.get("HMMER_BIN", "")


def tool(name: str) -> str:
    return str(Path(HMMER) / name) if HMMER else name


def strict_entry_hash(block: str) -> str:
    return entry_content_hash(block, PROFILE_VOLATILE_TAGS)


def git_head() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def hmmscan_version() -> str:
    text = subprocess.run([tool("hmmscan"), "-h"], check=True, capture_output=True, text=True).stdout
    for line in text.splitlines():
        if "HMMER" in line:
            return line
    return text.splitlines()[1]


def iter_models(path: Path):
    """Yield (name, acc, block) in file order. Same walker as the E1 driver."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:
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
    return [ln for ln in path.read_text().splitlines(keepends=True) if not ln.startswith("#")]


def read_fasta(path: Path) -> list[str]:
    recs: list[str] = []
    buf: list[str] = []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith(">"):
                if buf:
                    recs.append("".join(buf))
                buf = [line]
            elif buf:
                buf.append(line)
        if buf:
            recs.append("".join(buf))
    return recs


def write_sample(recs: list[str], dest: Path, seed: int, k: int) -> dict:
    rng = random.Random(seed)
    idxs = rng.sample(range(len(recs)), k)
    idxs.sort()
    dest.write_text("".join(recs[i] for i in idxs))
    digest = hashlib.sha256(",".join(map(str, idxs)).encode()).hexdigest()
    return {"seed": seed, "k": k, "n_records": len(recs), "sample_sha256": digest,
            "index_first": idxs[0], "index_last": idxs[-1]}


def subset_fasta(src: Path, keep: set[str], dest: Path) -> int:
    n = on = 0
    out: list[str] = []
    for line in src.read_text().splitlines(keepends=True):
        if line.startswith(">"):
            on = line[1:].split()[0] in keep
            n += on
        if on:
            out.append(line)
    dest.write_text("".join(out))
    return n


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def require_free(path: Path) -> None:
    free = shutil.disk_usage(path).free
    if free < MIN_FREE:
        raise SystemExit(f"need {MIN_FREE} bytes free under {path}, have {free}")


def index_release(gz: Path, dest: Path, stated_z: int) -> dict:
    if dest.exists():
        payload = json.loads(dest.read_text())
        if payload.get("z") != stated_z or payload.get("duplicate_name") or payload.get("duplicate_hash"):
            why = payload.get("duplicate_name") or payload.get("duplicate_hash") or payload.get("z")
            raise SystemExit(f"INCONCLUSIVE: {gz.name} index is not usable ({why})")
        log(f"index reuse {gz.name} z={payload['z']} wall={payload['wall_s']:.1f}s")
        return payload
    log(f"indexing {gz}")
    t = time.perf_counter()
    entries: list[list[str]] = []
    by_name: dict[str, str] = {}
    by_hash: dict[str, str] = {}
    dup_name = dup_hash = ""
    for name, _acc, block in iter_models(gz):
        digest = strict_entry_hash(block)
        if not dup_name and name in by_name:
            dup_name = name
        if not dup_hash and digest in by_hash:
            dup_hash = digest
        by_name[name] = digest
        by_hash[digest] = name
        entries.append([name, digest])
    wall = time.perf_counter() - t
    payload = {
        "z": len(entries),
        "wall_s": wall,
        "duplicate_name": dup_name,
        "duplicate_hash": dup_hash,
        "entries": entries,
    }
    dest.write_text(json.dumps(payload))
    log(f"indexed {gz.name} z={payload['z']} in {wall:.1f}s")
    if payload["z"] != stated_z:
        raise SystemExit(f"INCONCLUSIVE: {gz.name} has {payload['z']} models, stated {stated_z}")
    if dup_name or dup_hash:
        raise SystemExit(f"INCONCLUSIVE: duplicate {'name '+dup_name if dup_name else 'hash '+dup_hash[:12]}")
    return payload


def press_full(gz: Path, prefix: Path) -> dict:
    stamp = Path(str(prefix) + ".pressed.json")
    h3m = Path(str(prefix) + ".h3m")
    if stamp.exists() and h3m.exists():
        payload = json.loads(stamp.read_text())
        log(f"press reuse {prefix.name} ({payload.get('pressed_models')} models)")
        return payload
    require_free(prefix.parent)
    log(f"decompress {gz.name}")
    t = time.perf_counter()
    with gzip.open(gz, "rb") as src, open(prefix, "wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    decomp_s = time.perf_counter() - t
    log(f"hmmpress {prefix.name} ({prefix.stat().st_size} bytes text)")
    t = time.perf_counter()
    proc = subprocess.run([tool("hmmpress"), "-f", str(prefix)], capture_output=True, text=True)
    press_s = time.perf_counter() - t
    if proc.returncode != 0:
        raise SystemExit(f"hmmpress failed: {proc.stderr[-2000:]}")
    match = re.search(r"Pressed and indexed (\d+) HMMs", proc.stdout + proc.stderr)
    pressed = int(match.group(1)) if match else None
    prefix.unlink()
    payload = {"decomp_s": decomp_s, "press_s": press_s, "pressed_models": pressed,
               "free_after": shutil.disk_usage(prefix.parent).free}
    stamp.write_text(json.dumps(payload))
    log(f"pressed {prefix.name}: decomp {decomp_s:.1f}s press {press_s:.1f}s models={pressed} free={payload['free_after']}")
    return payload


def write_mini(gz: Path, names: set[str], dest: Path) -> dict:
    """Extract `names` in gz file order, hmmpress, delete the text."""
    stamp = Path(str(dest) + ".pressed.json")
    if stamp.exists() and Path(str(dest) + ".h3m").exists():
        return json.loads(stamp.read_text())
    t = time.perf_counter()
    n = 0
    with open(dest, "w") as fh:
        for name, _acc, block in iter_models(gz):
            if name in names:
                fh.write(block)
                n += 1
    extract_s = time.perf_counter() - t
    if n != len(names):
        raise SystemExit(f"mini-ref {dest.name}: wrote {n} of {len(names)} models")
    t = time.perf_counter()
    proc = subprocess.run([tool("hmmpress"), "-f", str(dest)], capture_output=True, text=True)
    press_s = time.perf_counter() - t
    if proc.returncode != 0:
        raise SystemExit(f"hmmpress {dest.name} failed: {proc.stderr[-2000:]}")
    dest.unlink()
    payload = {"models": n, "extract_s": extract_s, "press_s": press_s,
               "discovery_or_replay_press_s": extract_s + press_s}
    stamp.write_text(json.dumps(payload))
    log(f"mini {dest.name}: {n} models extract {extract_s:.1f}s press {press_s:.1f}s")
    return payload


def scan(db: Path, queries: Path, tag: Path, erep: int, z: int | None) -> float:
    stamp = Path(str(tag) + ".done.json")
    if stamp.exists() and Path(str(tag) + ".tbl").exists() and Path(str(tag) + ".dom").exists():
        wall = float(json.loads(stamp.read_text())["wall_s"])
        log(f"scan reuse {tag.name} {wall:.1f}s")
        return wall
    cmd = [
        tool("hmmscan"), "--noali", "--cpu", str(CPU),
        "--tblout", f"{tag}.tbl", "--domtblout", f"{tag}.dom",
        "-o", os.devnull, "-E", str(erep), "--domE", str(erep),
    ]
    if z is not None:
        cmd += ["-Z", str(z)]
    cmd += [str(db), str(queries)]
    log(f"scan {' '.join(cmd)}")
    t = time.perf_counter()
    proc = subprocess.run(cmd)
    wall = time.perf_counter() - t
    if proc.returncode != 0:
        raise SystemExit(f"hmmscan failed ({proc.returncode}) tag={tag.name}")
    stamp.write_text(json.dumps({"wall_s": wall, "cmd": cmd}))
    log(f"scan done {tag.name} {wall:.1f}s")
    return wall


def pairs(path: Path, qcol: int) -> tuple[set[tuple[str, str]], list[str]]:
    lines = body(path)
    found: set[tuple[str, str]] = set()
    for line in lines:
        fields = line.split()
        found.add((fields[0], fields[qcol]))
    return found, lines


def mapped_pairs(path: Path, qcol: int, src_name_hash: dict[str, str], tgt_hash_name: dict[str, str]):
    """Cache rows on unchanged models, retargeted to the target-release NAME."""
    lines = body(path)
    found: set[tuple[str, str]] = set()
    kept: list[tuple[str, str]] = []
    dropped = 0
    for line in lines:
        fields = line.split()
        query = fields[qcol]
        digest = src_name_hash.get(fields[0])
        target = tgt_hash_name.get(digest) if digest else None
        if target is None:
            dropped += 1
            continue
        found.add((target, query))
        kept.append((target, query))
    return found, kept, dropped, len(lines)


def count_crossed_out(kept: list[tuple[str, str]], stock: set[tuple[str, str]]) -> int:
    return sum(1 for pair in kept if pair not in stock)


def count_crossed_in(stock_lines: list[str], qcol: int, s1: set[tuple[str, str]], slack: set[tuple[str, str]]) -> int:
    n = 0
    for line in stock_lines:
        fields = line.split()
        pair = (fields[0], fields[qcol])
        if pair not in s1 and pair in slack:
            n += 1
    return n


def count_band(stock_lines: list[str], qcol: int, candidates: set[tuple[str, str]]) -> int:
    return sum(1 for line in stock_lines if (line.split()[0], line.split()[qcol]) not in candidates)


def compare(replay: Path, stock: Path) -> dict:
    res = {}
    for ext in ("tbl", "dom"):
        got, want = body(Path(f"{replay}.{ext}")), body(Path(f"{stock}.{ext}"))
        diff = sum(
            1 for i in range(max(len(got), len(want)))
            if (got[i] if i < len(got) else None) != (want[i] if i < len(want) else None)
        )
        item = {"lines_replay": len(got), "lines_stock": len(want), "equal": got == want,
                "differing_positions": diff}
        if got != want:
            i = next(i for i in range(max(len(got), len(want)))
                     if (got[i] if i < len(got) else None) != (want[i] if i < len(want) else None))
            item["first_replay"] = (got[i] if i < len(got) else "")[:180]
            item["first_stock"] = (want[i] if i < len(want) else "")[:180]
        res[ext] = item
    return res


def name_hash(entries: list[list[str]]) -> dict[str, str]:
    return {name: digest for name, digest in entries}


def hash_name(entries: list[list[str]]) -> dict[str, str]:
    return {digest: name for name, digest in entries}


def discovery_names(src: list[list[str]], tgt: list[list[str]]) -> list[str]:
    src_hashes = {digest for _name, digest in src}
    return [name for name, digest in tgt if digest not in src_hashes]


def run_arm(
    *,
    work: Path,
    tag: str,
    gz_tgt: Path,
    queries: Path,
    z_tgt: int,
    slack: int,
    cache_tag: Path,
    cache_wall: float,
    cache_source: str,
    s1_tag: Path,
    stock_tag: Path,
    stock_wall: float,
    src_entries: list[list[str]],
    tgt_entries: list[list[str]],
    hash_diff_s: float,
    expect_equal: bool,
    count_band_rows: bool,
) -> dict:
    erep_fill = BASE_E * slack
    src_nh, tgt_hn = name_hash(src_entries), hash_name(tgt_entries)
    disc_list = discovery_names(src_entries, tgt_entries)
    disc_set = set(disc_list)
    log(f"{tag}: discovery models {len(disc_set)} slack={slack} fill_E={erep_fill}")
    built = write_mini(gz_tgt, disc_set, work / f"{tag}_disc.hmm")
    disc_wall = scan(work / f"{tag}_disc.hmm", queries, work / f"{tag}_D", erep_fill, None)

    cand: set[tuple[str, str]] = set()
    crossed_out = {}
    dropped = {}
    cache_pairs: dict[str, set[tuple[str, str]]] = {}
    for ext, qcol in (("tbl", 2), ("dom", 3)):
        found, kept, drop, n_lines = mapped_pairs(
            Path(f"{cache_tag}.{ext}"), qcol, src_nh, tgt_hn,
        )
        d_pairs, _d_lines = pairs(work / f"{tag}_D.{ext}", qcol)
        cache_pairs[ext] = found
        cand |= found | d_pairs
        stock_pairs, _stock_lines = pairs(Path(f"{stock_tag}.{ext}"), qcol)
        crossed_out[ext] = count_crossed_out(kept, stock_pairs)
        dropped[ext] = {"cache_lines": n_lines, "source_only_lines": drop}
    queries_kept = {query for _tgt, query in cand}
    models = {tgt for tgt, _query in cand}
    q_n = subset_fasta(queries, queries_kept, work / f"{tag}_q.faa")
    replay_built = write_mini(gz_tgt, models, work / f"{tag}_rep.hmm") if models else {"discovery_or_replay_press_s": 0.0}
    if q_n and models:
        rep_wall = scan(work / f"{tag}_rep.hmm", work / f"{tag}_q.faa", work / f"{tag}_R", BASE_E, z_tgt)
    else:
        for ext in ("tbl", "dom"):
            Path(f"{work}/{tag}_R.{ext}").write_text("")
        rep_wall = 0.0
    check = compare(work / f"{tag}_R", stock_tag)
    equal = all(v["equal"] for v in check.values())

    s1_pairs: dict[str, set[tuple[str, str]]] = {}
    crossed_in = {"tbl": 0, "dom": 0}
    if slack == 1:
        crossed_in = {"tbl": 0, "dom": 0}
    else:
        for ext, qcol in (("tbl", 2), ("dom", 3)):
            s1, _kept, _drop, _n = mapped_pairs(Path(f"{s1_tag}.{ext}"), qcol, src_nh, tgt_hn)
            s1_pairs[ext] = s1
            _stock_pairs, stock_lines = pairs(Path(f"{stock_tag}.{ext}"), qcol)
            crossed_in[ext] = count_crossed_in(stock_lines, qcol, s1, cache_pairs[ext])

    band = None
    if count_band_rows:
        band = {}
        for ext, qcol in (("tbl", 2), ("dom", 3)):
            _p, stock_lines = pairs(Path(f"{stock_tag}.{ext}"), qcol)
            band[ext] = count_band(stock_lines, qcol, cand)

    report = {
        "slack": slack,
        "z_target": z_tgt,
        "fill_E": erep_fill,
        "replay_E": BASE_E,
        "discovery_models": len(disc_set),
        "candidate_pairs": len(cand),
        "replay_models": len(models),
        "replay_queries": q_n,
        "cache_lines_dropped_source_only": dropped,
        "crossed_out_rows": crossed_out,
        "crossed_in_rows": crossed_in,
        "band_rows": band,
        "walls_s": {
            "indicative": True,
            "stock_target": stock_wall,
            "cache_fill": cache_wall,
            "cache_fill_source": cache_source,
            "hash_diff": hash_diff_s,
            "discovery_press": built["discovery_or_replay_press_s"],
            "discovery_scan": disc_wall,
            "replay_press": replay_built["discovery_or_replay_press_s"],
            "replay_scan": rep_wall,
        },
        "check": check,
        "equal": equal,
        "differs": not equal,
        "pass": equal if expect_equal else (not equal),
        "killed": (not equal) if expect_equal else False,
    }
    log(f"{tag}: equal={equal} pairs={len(cand)} models={len(models)} queries={q_n} "
        f"crossed_out={crossed_out} crossed_in={crossed_in} band={band}")
    return report


def evaluate(work: Path, recs: list[str], seed: int, k: int, indexes: dict, dbs: dict, gz: dict, out_report: dict, out_path: Path) -> dict:
    tag = f"Q{k}"
    meta = write_sample(recs, work / f"{tag}.faa", seed, k)
    log(f"{tag} sample sha {meta['sample_sha256'][:12]}")
    queries = work / f"{tag}.faa"
    wall_381 = scan(dbs["38.1"], queries, work / f"{tag}_stock_38.1", BASE_E, None)
    wall_382 = scan(dbs["38.2"], queries, work / f"{tag}_stock_38.2", BASE_E, None)
    hash_diff_s = indexes["38.1"]["wall_s"] + indexes["38.2"]["wall_s"]
    e3a = run_arm(
        work=work, tag=f"{tag}_E3a", gz_tgt=gz["38.2"], queries=queries,
        z_tgt=Z_STATED["38.2"], slack=1,
        cache_tag=work / f"{tag}_stock_38.1", cache_wall=wall_381, cache_source="stock_38.1_E10",
        s1_tag=work / f"{tag}_stock_38.1",
        stock_tag=work / f"{tag}_stock_38.2", stock_wall=wall_382,
        src_entries=indexes["38.1"]["entries"], tgt_entries=indexes["38.2"]["entries"],
        hash_diff_s=hash_diff_s, expect_equal=True, count_band_rows=False,
    )
    sample = {"sample": meta, "stock_walls_s": {"38.1_E10": wall_381, "38.2_E10": wall_382, "indicative": True},
              "E3a": e3a}
    out_report[tag] = sample
    out_path.write_text(json.dumps(out_report, indent=2) + "\n")
    if e3a["killed"]:
        sample["verdict"] = "KILL"
        sample["stopped_after"] = "E3a"
        return sample

    wall_slack = scan(dbs["38.2"], queries, work / f"{tag}_cache_38.2_E20", BASE_E * 2, None)
    e3b = run_arm(
        work=work, tag=f"{tag}_E3b", gz_tgt=gz["38.1"], queries=queries,
        z_tgt=Z_STATED["38.1"], slack=2,
        cache_tag=work / f"{tag}_cache_38.2_E20", cache_wall=wall_slack, cache_source="38.2_E20",
        s1_tag=work / f"{tag}_stock_38.2",
        stock_tag=work / f"{tag}_stock_38.1", stock_wall=wall_381,
        src_entries=indexes["38.2"]["entries"], tgt_entries=indexes["38.1"]["entries"],
        hash_diff_s=hash_diff_s, expect_equal=True, count_band_rows=False,
    )
    sample["E3b"] = e3b
    sample["slack_cache_wall_s"] = wall_slack
    out_path.write_text(json.dumps(out_report, indent=2) + "\n")
    if e3b["killed"]:
        sample["verdict"] = "KILL"
        sample["stopped_after"] = "E3b"
        return sample

    e3c = run_arm(
        work=work, tag=f"{tag}_E3c", gz_tgt=gz["38.1"], queries=queries,
        z_tgt=Z_STATED["38.1"], slack=1,
        cache_tag=work / f"{tag}_stock_38.2", cache_wall=wall_382, cache_source="stock_38.2_E10",
        s1_tag=work / f"{tag}_stock_38.2",
        stock_tag=work / f"{tag}_stock_38.1", stock_wall=wall_381,
        src_entries=indexes["38.2"]["entries"], tgt_entries=indexes["38.1"]["entries"],
        hash_diff_s=hash_diff_s, expect_equal=False, count_band_rows=True,
    )
    sample["E3c"] = e3c
    if e3c["differs"]:
        sample["verdict"] = "PASS"
    else:
        sample["verdict"] = "CONTROL_UNDERPOWERED"
    out_path.write_text(json.dumps(out_report, indent=2) + "\n")
    return sample


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    gz = {
        "38.1": PIPE / "data/hmmer/pfam38.1/Pfam-A.hmm.gz",
        "38.2": PIPE / "data/hmmer/Pfam-A.hmm.gz",
    }
    queries_gz = PIPE / "data/recurrence/A/GCF_002853805.1_protein.faa.gz"
    for path in (*gz.values(), queries_gz):
        if not path.exists():
            raise SystemExit(f"missing {path}")
    report: dict = {
        "protocol": "docs/EXACT_REPLAY_PROTOCOL.md",
        "test": "E3",
        "pre_registration": PRE_REG,
        "git_head": git_head(),
        "host": platform.node(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "hmmscan": hmmscan_version(),
        "cpu": CPU,
        "walls_indicative": True,
        "stated_Z": Z_STATED,
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    log(f"E3 pre-registration {PRE_REG} head {report['git_head']} host {report['host']}")
    recs = read_fasta(queries_gz)
    indexes = {}
    try:
        for rel, path in gz.items():
            indexes[rel] = index_release(path, a.work / f"idx_{rel}.json", Z_STATED[rel])
    except SystemExit as exc:
        report["verdict"] = "INCONCLUSIVE"
        report["reason"] = exc.code if isinstance(exc.code, str) else str(exc)
        a.out.write_text(json.dumps(report, indent=2) + "\n")
        raise
    report["measured_Z"] = {rel: indexes[rel]["z"] for rel in indexes}
    report["hash_diff_s"] = {rel: indexes[rel]["wall_s"] for rel in indexes}
    dbs = {}
    presses = {}
    for rel, path in gz.items():
        prefix = a.work / f"db_{rel}.hmm"
        presses[rel] = press_full(path, prefix)
        if presses[rel].get("pressed_models") != Z_STATED[rel]:
            report["verdict"] = "INCONCLUSIVE"
            report["reason"] = f"hmmpress {rel} counted {presses[rel].get('pressed_models')}, stated {Z_STATED[rel]}"
            a.out.write_text(json.dumps(report, indent=2) + "\n")
            raise SystemExit(report["reason"])
        dbs[rel] = prefix
    report["press_s"] = presses
    a.out.write_text(json.dumps(report, indent=2) + "\n")

    q300 = evaluate(a.work, recs, 20261012, 300, indexes, dbs, gz, report, a.out)
    if q300["verdict"] == "KILL":
        report["verdict"] = "KILL"
        report["reason"] = "E3a or E3b body differed; exact mode stays --cut_ga-only"
    elif q300["verdict"] == "CONTROL_UNDERPOWERED":
        report["Q300_control"] = "underpowered; rerunning Q1000 under the locked rule"
        q1000 = evaluate(a.work, recs, 20261013, 1000, indexes, dbs, gz, report, a.out)
        if q1000["verdict"] == "KILL":
            report["verdict"] = "KILL"
            report["reason"] = "Q1000 E3a or E3b body differed; exact mode stays --cut_ga-only"
        elif q1000["verdict"] == "CONTROL_UNDERPOWERED":
            report["verdict"] = "INCONCLUSIVE"
            report["reason"] = "E3c did not differ on Q300 or Q1000; slack control is uninformative; do not ship"
        else:
            report["verdict"] = "PASS"
            report["sample_of_record"] = "Q1000"
    else:
        report["verdict"] = "PASS"
        report["sample_of_record"] = "Q300"
    a.out.write_text(json.dumps(report, indent=2) + "\n")
    log(f"verdict {report['verdict']}")


if __name__ == "__main__":
    main()
