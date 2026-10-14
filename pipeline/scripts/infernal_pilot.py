#!/usr/bin/env python3
"""Pilot for cmscan --cut_ga against one locked genome.

The genome was drawn before any scan. This process does not draw another.
Walls are Mac-indicative. Scratch lives under ~/tmp/infernal_work.
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.exact_certificate import judge, neighbor_ids, pad_indices, sample_keys  # noqa: E402
from acts.reference_formats import _tag_value, iter_profile_raw  # noqa: E402
from acts.reference_run import IC2_SAMPLE_SEED, IC2_SAMPLE_SIZE  # noqa: E402

ROOT = PIPE / "data" / "infernal"
SRC = ROOT / "src" / "infernal-1.1.5" / "src"
CMSCAN = SRC / "cmscan"
CMPRESS = SRC / "cmpress"
CM = ROOT / "rfam" / "15.1" / "Rfam.cm"
CLANIN = ROOT / "rfam" / "15.1" / "Rfam.clanin"
GENOME = ROOT / "genomes" / (
    "GCF_049949635.1_Hybrid_genome_assembly_using_MiSeq_and_MinION_genomic.fna.gz"
)
WORK = Path.home() / "tmp" / "infernal_work"
FASTA = WORK / "pilot.fa"
STATE = WORK / "pilot_state.json"
OUT = PIPE / "results" / "infernal" / "pilot.json"
DROP_SEED = 20261043
CPU = "4"
# Format 1 body: target, query, seq from, seq to, strand.
KEY_FMT1 = (0, 2, 7, 8, 9)
# Format 2 inserts idx and clan name before mdl.
KEY_FMT2 = (1, 3, 9, 10, 11)


def log(message: str) -> None:
    print(time.strftime("%H:%M:%S"), message, flush=True)


def load_state() -> dict:
    if STATE.is_file():
        return json.loads(STATE.read_text())
    return {}


def save(state: dict) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(STATE)


def require_free() -> None:
    free = shutil.disk_usage(WORK).free
    if free < 8 * 1024**3:
        raise SystemExit(f"stop: {free} bytes free under {WORK}")


def z_string(fasta: Path) -> tuple[str, int]:
    residues = 0
    for line in fasta.read_text().splitlines():
        if line.startswith(">"):
            continue
        residues += sum(1 for ch in line if not ch.isspace())
    target = residues * 2
    text = f"{target / 1_000_000:.6f}"
    cast = int(float(text) * 1_000_000)
    if cast != target:
        raise SystemExit(f"-Z {text} casts to {cast}, not {target}")
    return text, residues


def body(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines(keepends=True) if line.strip() and not line.startswith("#")]


def classify(replay: list[str], stock: list[str], kind: str) -> dict:
    keys = KEY_FMT2 if kind == "fmt2" else KEY_FMT1

    def row_key(tokens: list[str]) -> tuple:
        return tuple(tokens[i] for i in keys)

    n = max(len(replay), len(stock))
    rt = [line.split() for line in replay]
    st = [line.split() for line in stock]
    for label, rows in (("replay", rt), ("stock", st)):
        if rows and (rows[0][keys[-1]] not in {"+", "-"}):
            raise SystemExit(f"{label} strand column is {rows[0][keys[-1]]!r}; row key is wrong")
    byte_equal = replay == stock
    token_equal = rt == st
    out: dict = {
        "lines_replay": len(replay),
        "lines_stock": len(stock),
        "byte_equal": byte_equal,
        "token_equal": token_equal,
        "classes": [],
    }
    if byte_equal:
        return out
    if token_equal:
        out["classes"] = ["whitespace-only"]
        return out
    from collections import Counter

    rk = [row_key(toks) for toks in rt]
    sk = [row_key(toks) for toks in st]
    rc, sc = Counter(rk), Counter(sk)
    missing = [list(key) for key in sc if sc[key] > rc[key]]
    extra = [list(key) for key in rc if rc[key] > sc[key]]
    classes: list[str] = []
    if missing:
        classes.append("missing")
    if extra:
        classes.append("extra")
    if not missing and not extra and rk != sk:
        classes.append("order")
    buckets: dict[tuple, list[list[str]]] = {}
    for toks in rt:
        buckets.setdefault(row_key(toks), []).append(toks)
    value = False
    for toks in st:
        group = buckets.get(row_key(toks))
        if not group:
            continue
        if group.pop(0) != toks:
            value = True
    if value:
        classes.append("value-only")
    out["classes"] = classes
    out["missing_keys"] = len(missing)
    out["extra_keys"] = len(extra)
    return out


def scan(tag: Path, argv: list[str]) -> dict:
    """One cmscan. ``argv`` is everything after the binary, including --tblout."""
    meta_path = Path(str(tag) + ".json")
    tbl = Path(str(tag) + ".tbl")
    if meta_path.is_file() and tbl.is_file() and tbl.stat().st_size > 0:
        meta = json.loads(meta_path.read_text())
        log(f"reuse {tag.name} wall={meta['wall_s']:.1f}s rows={meta['body_rows']}")
        return meta
    require_free()
    tag.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(CMSCAN), *argv]
    log(" ".join(cmd))
    stdout = Path(str(tag) + ".stdout")
    t0 = time.perf_counter()
    with stdout.open("w") as handle:
        proc = subprocess.run(cmd, stdout=handle, stderr=subprocess.PIPE, text=True)
    wall = time.perf_counter() - t0
    stdout.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise SystemExit(f"cmscan failed ({proc.returncode}): {(proc.stderr or '')[-800:]}")
    rows = body(tbl)
    meta = {"wall_s": wall, "argv": cmd, "tbl_bytes": tbl.stat().st_size, "body_rows": len(rows)}
    meta_path.write_text(json.dumps(meta) + "\n")
    log(f"done {tag.name} {wall:.1f}s rows={len(rows)}")
    return meta


def base_argv(
    z: str, tbl: Path, db: Path, clan: bool, clanin: Path | None = None, fasta: Path | None = None
) -> list[str]:
    argv = ["--cpu", CPU, "-Z", z, "--cut_ga", "--rfam", "--nohmmonly", "--tblout", str(tbl)]
    if clan:
        argv += ["--fmt", "2", "--clanin", str(clanin or CLANIN)]
    argv += [str(db), str(fasta or FASTA)]
    return argv


def filter_clanin(keep: set[str], dest: Path) -> int:
    """Drop clan members that are not in this CM file.

    cmscan.c read_clan_info_file rejects a --clanin name that is absent
    from the pressed index. A clan line with no remaining member is omitted.
    A line with one member is kept so that member still receives its clan name.
    """
    lines: list[str] = []
    for line in CLANIN.read_text().splitlines():
        parts = line.split()
        if not parts:
            continue
        kept = [parts[0]] + [token for token in parts[1:] if token in keep]
        if len(kept) > 1:
            lines.append("\t".join(kept))
    dest.write_text("\n".join(lines) + ("\n" if lines else ""))
    return len(lines)


def model_names(tbl: Path, kind: str) -> dict[str, set[str]]:
    col = 1 if kind == "fmt2" else 0
    query_col = 3 if kind == "fmt2" else 2
    found: dict[str, set[str]] = {}
    for line in body(tbl):
        fields = line.split()
        found.setdefault(fields[query_col], set()).add(fields[col])
    return found


def write_subset(keep: set[str], dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dest.open("w") as out:
        for raw in iter_profile_raw(CM):
            if _tag_value(raw, "NAME") in keep:
                out.write(raw if raw.endswith("\n") else raw + "\n")
                n += 1
    for ext in (".i1m", ".i1i", ".i1f", ".i1p"):
        Path(str(dest) + ext).unlink(missing_ok=True)
    proc = subprocess.run([str(CMPRESS), "-F", str(dest)], check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"cmpress failed: {(proc.stderr or proc.stdout)[-500:]}")
    return n


def entry_order() -> list[SimpleNamespace]:
    names: list[SimpleNamespace] = []
    for raw in iter_profile_raw(CM):
        name = _tag_value(raw, "NAME")
        if not name:
            raise SystemExit("profile entry has no NAME")
        names.append(SimpleNamespace(primary=name))
    return names


def adopt_stock(z: str) -> None:
    """The first no-clan scan ran before this script. Keep its wall."""
    tag = WORK / "noclan" / "stock_a"
    meta = Path(str(tag) + ".json")
    tbl = Path(str(tag) + ".tbl")
    if meta.is_file() and tbl.is_file():
        return
    legacy = WORK / "noclan_stock1.tbl"
    if not legacy.is_file() or legacy.stat().st_size == 0:
        return
    tag.parent.mkdir(parents=True, exist_ok=True)
    if not tbl.is_file():
        shutil.copyfile(legacy, tbl)
    rows = body(tbl)
    payload = {
        "wall_s": 276.25,
        "wall_source": "time -p real, before this script",
        "argv": [
            str(CMSCAN), "--cpu", CPU, "-Z", z, "--cut_ga", "--rfam", "--nohmmonly",
            "--tblout", str(WORK / "noclan_stock1.tbl"), str(CM), str(FASTA),
        ],
        "tbl_bytes": tbl.stat().st_size,
        "body_rows": len(rows),
    }
    meta.write_text(json.dumps(payload) + "\n")
    log(f"adopted stock_a rows={len(rows)} wall=276.25s")


def safety(kind: str, stock_tbl: Path, cand: dict[str, set[str]], entries, z: str, clan: bool, folder: Path) -> dict:
    u_ids = {name for names in cand.values() for name in names}
    expanded: dict[str, set[str]] = {}
    neighbor_pad: set[str] = set()
    for key, tokens in cand.items():
        extra = neighbor_ids(entries, tokens)
        expanded[key] = set(tokens) | extra
        neighbor_pad |= extra
    neighbor_pad -= u_ids
    subject_col = 1 if kind == "fmt2" else 0
    record_col = 3 if kind == "fmt2" else 2
    reports = []

    def one(name: str, models: set[str], pad_ids: set[str], keep: set[str] | None) -> dict:
        dest = folder / f"{name}.cm"
        n_models = write_subset(models, dest)
        clanin = None
        if clan:
            clanin = folder / f"{name}.clanin"
            filter_clanin(models, clanin)
        tag = folder / name
        meta = scan(tag, base_argv(z, Path(str(tag) + ".tbl"), dest, clan, clanin))
        plus = Path(str(tag) + ".tbl").read_text()
        replay = stock_tbl.read_text()
        if keep is not None:
            def filt(text: str) -> str:
                lines = []
                for line in text.splitlines():
                    if not line.strip() or line.startswith("#"):
                        continue
                    fields = line.split()
                    if record_col < len(fields) and fields[record_col] in keep:
                        lines.append(line)
                return "\n".join(lines) + "\n"
            replay, plus = filt(replay), filt(plus)
        verdict = judge(replay, plus, u_ids, pad_ids, subject_col)
        for ext in (".i1m", ".i1i", ".i1f", ".i1p"):
            Path(str(dest) + ext).unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        return {"name": name, "models": n_models, "wall_s": meta["wall_s"], "verdict": verdict}

    union = set().union(*expanded.values()) if expanded else set()
    reports.append(one("neighbor", union, neighbor_pad, None))
    order = list(cand)
    sample = sample_keys(order, IC2_SAMPLE_SIZE, IC2_SAMPLE_SEED)
    keep = set(sample)
    for name, indices in pad_indices(entries, u_ids):
        if not name.startswith("random") or not indices:
            continue
        pad_ids = {entries[i].primary for i in indices}
        models = set(u_ids) | pad_ids
        reports.append(one(name, models, pad_ids, keep))
    return {
        "pads": reports,
        "refused": any(not row["verdict"]["pass"] for row in reports),
        "sample_records": sample,
    }


def run_cli(z: str, clan: bool, out: Path, fasta: Path | None = None) -> dict:
    stamp = out / "cli.json"
    if stamp.is_file():
        log(f"reuse cli {out.name}")
        return json.loads(stamp.read_text())
    out.mkdir(parents=True, exist_ok=True)
    require_free()
    tool = [
        str(CMSCAN), "--cpu", CPU, "-Z", z, "--cut_ga", "--rfam", "--nohmmonly",
        "--tblout", "{output:tblout}",
    ]
    if clan:
        tool += ["--fmt", "2", "--clanin", str(CLANIN)]
    tool += ["{reference}", "{input}"]
    cmd = [
        sys.executable, "-m", "acts", "run",
        "--strategy", "reference",
        "--pin",
        "--verify", "audit",
        "--prep", f"{CMPRESS} -F {{reference}}",
        "--input", str(fasta or FASTA),
        "--reference", str(CM),
        "--cache", str(out / "cache.sqlite"),
        "-o", str(out),
        "--",
        *tool,
    ]
    log(f"cli clan={clan}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=PIPE, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    decision = (out / "decision.txt").read_text() if (out / "decision.txt").is_file() else ""
    payload = {
        "returncode": proc.returncode,
        "wall_s": wall,
        "decision_text": decision,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-800:],
    }
    stamp.write_text(json.dumps(payload, indent=2) + "\n")
    log(f"cli clan={clan} rc={proc.returncode} {wall:.1f}s")
    return payload


def dx2_unit() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_exact_certificate.py"],
        cwd=PIPE,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-500:],
        "stderr_tail": proc.stderr[-500:],
    }


def variant(state: dict, clan: bool, z: str, entries) -> dict:
    name = "clan" if clan else "noclan"
    kind = "fmt2" if clan else "fmt1"
    folder = WORK / name
    folder.mkdir(parents=True, exist_ok=True)
    stock_a = scan(folder / "stock_a", base_argv(z, folder / "stock_a.tbl", CM, clan))
    stock_b = scan(folder / "stock_b", base_argv(z, folder / "stock_b.tbl", CM, clan))
    det = classify(body(folder / "stock_b.tbl"), body(folder / "stock_a.tbl"), kind)
    det["file_byte_equal"] = (folder / "stock_a.tbl").read_bytes() == (folder / "stock_b.tbl").read_bytes()
    report: dict = {"stock_a": stock_a, "stock_b": stock_b, "determinism": det}
    if not det["byte_equal"]:
        report["stopped"] = "stock-vs-stock bodies differ"
        return report
    cand = model_names(folder / "stock_a.tbl", kind)
    models = {item for names in cand.values() for item in names}
    oracle_cm = folder / "oracle.cm"
    n_oracle = write_subset(models, oracle_cm)
    oracle_clanin = folder / "oracle.clanin" if clan else None
    if oracle_clanin is not None:
        filter_clanin(models, oracle_clanin)
    oracle = scan(folder / "oracle", base_argv(z, folder / "oracle.tbl", oracle_cm, clan, oracle_clanin))
    e1 = classify(body(folder / "oracle.tbl"), body(folder / "stock_a.tbl"), kind)
    e1["file_byte_equal"] = (folder / "oracle.tbl").read_bytes() == (folder / "stock_a.tbl").read_bytes()
    e1["models"] = n_oracle
    e1["candidate_models"] = len(models)
    report["e1"] = e1
    k = max(1, int(round(0.05 * len(models))))
    dropped = sorted(random.Random(DROP_SEED).sample(sorted(models), k))
    kept = models - set(dropped)
    drop_cm = folder / "drop.cm"
    n_drop = write_subset(kept, drop_cm)
    drop_clanin = folder / "drop.clanin" if clan else None
    if drop_clanin is not None:
        filter_clanin(kept, drop_clanin)
    drop = scan(folder / "drop", base_argv(z, folder / "drop.tbl", drop_cm, clan, drop_clanin))
    dropped_cmp = classify(body(folder / "drop.tbl"), body(folder / "stock_a.tbl"), kind)
    report["drop"] = {
        "seed": DROP_SEED,
        "dropped": k,
        "dropped_names": dropped,
        "replay_models": n_drop,
        "wall_s": drop["wall_s"],
        "vs_stock": dropped_cmp,
        "differs": not dropped_cmp["byte_equal"],
    }
    if not clan:
        omit = scan(folder / "omit_z", ["--cpu", CPU, "--cut_ga", "--rfam", "--nohmmonly", "--tblout", str(folder / "omit_z.tbl"), str(CM), str(FASTA)])
        omit_cmp = classify(body(folder / "omit_z.tbl"), body(folder / "stock_a.tbl"), kind)
        report["omit_z"] = {"wall_s": omit["wall_s"], "vs_stock": omit_cmp}
    report["safety"] = safety(kind, folder / "stock_a.tbl", cand, entries, z, clan, folder / "pads")
    report["cli"] = run_cli(z, clan, folder / "cli")
    for path in (oracle_cm, drop_cm):
        path.unlink(missing_ok=True)
        for ext in (".i1m", ".i1i", ".i1f", ".i1p"):
            Path(str(path) + ext).unlink(missing_ok=True)
    return report


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PIPE.parents[0], check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    if not FASTA.is_file():
        raise SystemExit(f"missing {FASTA}")
    if not CM.is_file() or not CMSCAN.is_file():
        raise SystemExit("cmscan or Rfam.cm is missing")
    z, residues = z_string(FASTA)
    adopt_stock(z)
    state = load_state()
    state["discarded_header_z"] = {
        "z": "9.188506",
        "reason": "counted letters in FASTA headers as residues; not compared",
        "wall_s": 276.25,
    }
    state["z"] = z
    state["residues"] = residues
    state["z_cast_ok"] = True
    if "entries" not in state:
        n = sum(1 for _ in iter_profile_raw(CM))
        state["entries"] = n
        log(f"parsed entries {n}")
        save(state)
    if state["entries"] != 4227:
        raise SystemExit(f"entry count {state['entries']} is not 4227")
    entries = entry_order()
    if "noclan" not in state:
        state["noclan"] = variant(state, False, z, entries)
        save(state)
    if "clan" not in state:
        state["clan"] = variant(state, True, z, entries)
        save(state)
    if "dx2_unit" not in state:
        state["dx2_unit"] = dx2_unit()
        save(state)
    banner = subprocess.run([str(CMSCAN), "-h"], check=False, capture_output=True, text=True).stdout.splitlines()
    state["cmscan_banner"] = banner[1] if len(banner) > 1 else banner[0]
    state["git_head"] = git_head()
    state["pilot_genome"] = "GCF_049949635.1"
    state["seed"] = 20261041
    state["drop_seed"] = DROP_SEED
    state["walls_indicative"] = True
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(state, indent=2) + "\n")
    log(f"wrote {OUT}")


if __name__ == "__main__":
    main()
