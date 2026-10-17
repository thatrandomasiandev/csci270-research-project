#!/usr/bin/env python3
"""Residue-budget pilot. One genome. Not a measured result.

Seed 20261046 draws one accession from the Infernal genome pool after
removing the earlier pilots, the Test I ten, and seed 20261045's ten.
The script recomputes that draw and stops if it is not the locked accession.
"""
from __future__ import annotations

import ast
import csv
import gzip
import json
import random
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

ROOT = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS-infernal/pipeline/data/infernal")
SRC = ROOT / "src" / "infernal-1.1.5" / "src"
CMSCAN = SRC / "cmscan"
CMPRESS = SRC / "cmpress"
CM_OLD = ROOT / "rfam" / "15.0" / "Rfam.cm"
CM_NEW = ROOT / "rfam" / "15.1" / "Rfam.cm"
CM_STOCK = CM_NEW
CLAN_OLD = ROOT / "rfam" / "15.0" / "Rfam.clanin"
CLAN_NEW = ROOT / "rfam" / "15.1" / "Rfam.clanin"
CLAN_STOCK = CLAN_NEW
INPUTS = PIPE / "results" / "infernal" / "inputs.tsv"
WORK = Path.home() / "tmp" / "infernal3_work" / "pilot"
STATE = WORK / "state.json"
OUT = PIPE / "results" / "infernal" / "budget_pilot.json"
SEED = 20261046
LOCKED = "GCF_010365405.1"
REPEATS = 3
CPU = "4"
F_DELTA = 457 / 4227
EXCLUDE = {
    "GCF_049949635.1",
    "GCF_058683675.1",
    "GCF_003956185.1",
    "GCF_013168095.1",
    "GCF_022846215.1",
    "GCF_028743355.1",
    "GCF_030515405.1",
    "GCF_030708175.1",
    "GCF_037287675.1",
    "GCF_054510725.1",
    "GCF_055382035.1",
    "GCF_059615465.1",
    "GCF_001515725.1",
    "GCF_003722195.1",
    "GCF_005389605.2",
    "GCF_017654165.1",
    "GCF_023657995.1",
    "GCF_032384295.1",
    "GCF_041235215.1",
    "GCF_048568975.1",
    "GCF_059131955.1",
    "GCF_059719525.1",
}


def log(message: str) -> None:
    print(time.strftime("%H:%M:%S"), message, flush=True)


def on_ac_power() -> bool:
    proc = subprocess.run(["pmset", "-g", "batt"], check=False, capture_output=True, text=True)
    return "AC Power" in proc.stdout


def require_power() -> None:
    if not on_ac_power():
        raise SystemExit("pause: not on AC power")


def require_free() -> None:
    free = shutil.disk_usage(Path.home() / "tmp").free
    if free < 8 * 1024**3:
        raise SystemExit(f"stop: {free} bytes free")


def load() -> dict:
    if STATE.is_file():
        return json.loads(STATE.read_text())
    return {"variants": {}}


def save(state: dict) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(STATE)
    if OUT.parent.is_dir() or True:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        snapshot = dict(state)
        snapshot["partial"] = True
        OUT.write_text(json.dumps(snapshot, indent=2) + "\n")


def stage_release(release: str, role: str) -> tuple[Path, Path]:
    """Copy a release into the work directory. The source tree is not written."""
    src = ROOT / "rfam" / release
    dest = WORK / "db" / f"{release}-{role}"
    dest.mkdir(parents=True, exist_ok=True)
    cm = dest / "Rfam.cm"
    if not cm.is_file():
        shutil.copy2(src / "Rfam.cm", cm)
        for ext in (".i1m", ".i1i", ".i1f", ".i1p"):
            side = Path(str(src / "Rfam.cm") + ext)
            if side.is_file():
                shutil.copy2(side, Path(str(cm) + ext))
    clan = dest / "Rfam.clanin"
    if not clan.is_file():
        shutil.copy2(src / "Rfam.clanin", clan)
    return cm, clan


def stage_databases() -> None:
    global CM_OLD, CLAN_OLD, CM_NEW, CLAN_NEW, CM_STOCK, CLAN_STOCK
    CM_OLD, CLAN_OLD = stage_release("15.0", "fill")
    CM_NEW, CLAN_NEW = stage_release("15.1", "update")
    CM_STOCK, CLAN_STOCK = stage_release("15.1", "stock")


def check_draw() -> None:
    pool: list[str] = []
    with INPUTS.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["kind"] == "genome":
                pool.append(row["name"])
    pool = sorted(set(pool) - EXCLUDE)
    got = random.Random(SEED).choice(pool)
    if got != LOCKED:
        raise SystemExit(f"draw {got} is not {LOCKED}")


def fasta_for(acc: str) -> Path:
    hits = sorted((ROOT / "genomes").glob(f"{acc}*_genomic.fna.gz"))
    if len(hits) != 1:
        raise SystemExit(f"{acc}: {len(hits)} genome files")
    dest = WORK / f"{acc}.fa"
    if not dest.is_file():
        dest.write_bytes(gzip.decompress(hits[0].read_bytes()))
    return dest


def z_string(fasta: Path) -> tuple[str, int]:
    residues = 0
    for line in fasta.read_text().splitlines():
        if line.startswith(">"):
            continue
        residues += sum(1 for ch in line if not ch.isspace())
    target = residues * 2
    text = f"{target / 1_000_000:.6f}"
    if int(float(text) * 1_000_000) != target:
        raise SystemExit(f"-Z {text} does not cast back to {target}")
    return text, residues


def body(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [line for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]


def run_timed(cmd: list[str], cwd: Path) -> dict:
    require_free()
    timed = ["/usr/bin/time", "-p", *cmd]
    t0 = time.perf_counter()
    proc = subprocess.run(timed, cwd=cwd, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    user = sys_t = None
    for line in proc.stderr.splitlines():
        if line.startswith("user "):
            user = float(line.split()[1])
        elif line.startswith("sys "):
            sys_t = float(line.split()[1])
    return {
        "returncode": proc.returncode,
        "wall_s": wall,
        "cpu_user_s": user,
        "cpu_sys_s": sys_t,
        "cpu_s": None if user is None or sys_t is None else user + sys_t,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def stock_scan(tag: Path, z: str, clan: bool, fasta: Path) -> dict:
    meta_path = tag.with_suffix(".json")
    tbl = tag.with_suffix(".tbl")
    if meta_path.is_file() and tbl.is_file() and tbl.stat().st_size > 0:
        log(f"reuse {tag.name}")
        return json.loads(meta_path.read_text())
    clanin = CLAN_STOCK if clan else None
    argv = [str(CMSCAN), "--cpu", CPU, "-Z", z, "--cut_ga", "--rfam", "--nohmmonly", "--tblout", str(tbl)]
    if clan:
        argv += ["--fmt", "2", "--clanin", str(clanin)]
    argv += [str(CM_STOCK), str(fasta)]
    log(f"stock {tag.name}")
    timed = run_timed(argv, PIPE)
    if timed["returncode"] != 0:
        raise SystemExit(f"cmscan failed ({timed['returncode']}): {timed['stderr'][-500:]}")
    rows = body(tbl)
    meta = {
        "wall_s": timed["wall_s"],
        "cpu_s": timed["cpu_s"],
        "cpu_user_s": timed["cpu_user_s"],
        "cpu_sys_s": timed["cpu_sys_s"],
        "body_rows": len(rows),
        "body_sha256": __import__("hashlib").sha256("".join(rows).encode()).hexdigest(),
    }
    meta_path.write_text(json.dumps(meta) + "\n")
    log(f"stock {tag.name} {timed['wall_s']:.1f}s rows={len(rows)}")
    return meta


def parse_decision(path: Path) -> dict:
    text = path.read_text() if path.is_file() else ""
    out: dict = {"text": text}
    for line in text.splitlines():
        if line.startswith("decision:"):
            out["decision"] = line.split(":", 1)[1].strip()
        elif line.startswith("why:"):
            out["why"] = line.split(":", 1)[1].strip()
        elif line.startswith("audit:"):
            out["audit"] = line.split(":", 1)[1].strip()
        elif line.startswith("random_pads:"):
            out["random_pads"] = line.split(":", 1)[1].strip()
        elif line.startswith("phases:"):
            out["phases"] = ast.literal_eval(line.split(":", 1)[1].strip())
    return out


def tare_run(out: Path, cache: Path, z: str, clan: bool, fasta: Path, reference: Path, clanin: Path | None) -> dict:
    stamp = out / "run.json"
    if stamp.is_file() and (out / "decision.txt").is_file():
        log(f"reuse {out.name}")
        return json.loads(stamp.read_text())
    out.mkdir(parents=True, exist_ok=True)
    tool = [
        str(CMSCAN), "--cpu", CPU, "-Z", z, "--cut_ga", "--rfam", "--nohmmonly",
        "--tblout", "{output:tblout}",
    ]
    cmd = [
        sys.executable, "-m", "acts", "run",
        "--strategy", "reference",
        "--pin",
        "--verify", "audit",
        "--prep", f"{CMPRESS} -F {{reference}}",
        "--input", str(fasta),
        "--reference", str(reference),
        "--cache", str(cache),
        "-o", str(out),
    ]
    if clan:
        tool += ["--fmt", "2", "--clanin", str(clanin)]
        cmd += [
            "--subset-aux", "{arg-after:--clanin}:tokens",
            "--invalidate-group", "{arg-after:--clanin}",
        ]
    cmd += ["--", *tool, "{reference}", "{input}"]
    log(f"tare {out.name} clan={clan}")
    timed = run_timed(cmd, PIPE)
    decision = parse_decision(out / "decision.txt")
    rows = body(out / "tables" / "tblout")
    payload = {
        "returncode": timed["returncode"],
        "wall_s": timed["wall_s"],
        "cpu_s": timed["cpu_s"],
        "cpu_user_s": timed["cpu_user_s"],
        "cpu_sys_s": timed["cpu_sys_s"],
        "decision": decision.get("decision"),
        "why": decision.get("why"),
        "audit": decision.get("audit"),
        "random_pads": decision.get("random_pads"),
        "phases": decision.get("phases"),
        "body_rows": len(rows),
        "stdout_tail": timed["stdout"][-1500:],
        "stderr_tail": timed["stderr"][-800:],
    }
    stamp.write_text(json.dumps(payload, indent=2) + "\n")
    log(f"tare {out.name} {decision.get('decision')} {timed['wall_s']:.1f}s rows={len(rows)}")
    return payload


def compare(stock_tbl: Path, tare_dir: Path) -> dict:
    stock_rows = body(stock_tbl)
    tare_rows = body(tare_dir / "tables" / "tblout")
    return {
        "byte_equal": stock_rows == tare_rows,
        "token_equal": [line.split() for line in stock_rows] == [line.split() for line in tare_rows],
        "stock_rows": len(stock_rows),
        "tare_rows": len(tare_rows),
    }


def rates(stock_s: float, tare: dict) -> dict:
    phases = tare.get("phases") or {}
    # The decision clock stores discovery_s. The 20261046 pilot file read
    # the absent key "discovery" and stored a = 0; the protocol recomputes
    # from discovery_s and does not rewrite that file.
    discovery = float(phases.get("discovery_s", phases.get("discovery", 0.0)) or 0.0)
    if stock_s <= 0:
        return {}
    a = discovery / (F_DELTA * stock_s)
    c = (tare["wall_s"] - discovery) / stock_s
    denom = a * F_DELTA + c
    return {
        "f": F_DELTA,
        "discovery_s": discovery,
        "a": a,
        "c": c,
        "predicted_s": (1.0 / denom) if denom else None,
        "pair_s": stock_s / tare["wall_s"] if tare["wall_s"] else None,
    }


def variant(state: dict, name: str, clan: bool, z: str, fasta: Path) -> None:
    if name in state["variants"] and state["variants"][name].get("done"):
        log(f"reuse variant {name}")
        return
    folder = WORK / name
    folder.mkdir(parents=True, exist_ok=True)
    block = state["variants"].setdefault(name, {"runs": []})
    if "fill" not in block:
        require_power()
        fill_cache = folder / "fill" / "cache.sqlite"
        block["fill"] = tare_run(
            folder / "fill", fill_cache, z, clan, fasta, CM_OLD, CLAN_OLD if clan else None
        )
        save(state)
    fill_cache = folder / "fill" / "cache.sqlite"
    while len(block["runs"]) < REPEATS:
        index = len(block["runs"])
        require_power()
        stock = stock_scan(folder / f"stock_{index}", z, clan, fasta)
        save(state)
        require_power()
        run_dir = folder / f"update_{index}"
        cache = run_dir / "cache.sqlite"
        if not (run_dir / "run.json").is_file():
            run_dir.mkdir(parents=True, exist_ok=True)
            if cache.is_file():
                cache.unlink()
            copy_cache(fill_cache, cache)
        tare = tare_run(run_dir, cache, z, clan, fasta, CM_NEW, CLAN_NEW if clan else None)
        paired = {
            "stock": stock,
            "tare": tare,
            "compare": compare(folder / f"stock_{index}.tbl", run_dir),
        }
        block["runs"].append(paired)
        save(state)
        if not paired["compare"]["byte_equal"] and tare.get("decision") == "SHIP":
            log(f"stop: {name} update {index} shipped a body that is not the stock body")
    stocks = [row["stock"]["wall_s"] for row in block["runs"]]
    tares = [row["tare"]["wall_s"] for row in block["runs"]]
    block["median_stock_s"] = float(statistics.median(stocks))
    block["median_tare_s"] = float(statistics.median(tares))
    block["s_g"] = block["median_stock_s"] / block["median_tare_s"] if block["median_tare_s"] else None
    block["rates_first_pair"] = rates(block["runs"][0]["stock"]["wall_s"], block["runs"][0]["tare"])
    block["byte_equal"] = all(row["compare"]["byte_equal"] for row in block["runs"])
    block["done"] = True
    save(state)


def copy_cache(src: Path, dest: Path) -> None:
    import sqlite3

    dest.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(src)
    target = sqlite3.connect(dest)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PIPE.parents[0], check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    check_draw()
    require_power()
    sources = (
        CMSCAN, CMPRESS,
        ROOT / "rfam" / "15.0" / "Rfam.cm", ROOT / "rfam" / "15.1" / "Rfam.cm",
        ROOT / "rfam" / "15.0" / "Rfam.clanin", ROOT / "rfam" / "15.1" / "Rfam.clanin",
    )
    for path in sources:
        if not path.is_file():
            raise SystemExit(f"missing {path}")
    stage_databases()
    fasta = fasta_for(LOCKED)
    z, residues = z_string(fasta)
    state = load()
    state.update({"genome": LOCKED, "seed": SEED, "z": z, "residues": residues})
    save(state)
    log(f"{LOCKED} Z={z} residues={residues}")
    variant(state, "noclan", False, z, fasta)
    variant(state, "clan", True, z, fasta)
    state["git_head"] = git_head()
    state["partial"] = False
    state["walls_indicative"] = True
    save(state)
    OUT.write_text(json.dumps(state, indent=2) + "\n")
    log(f"wrote {OUT}")


if __name__ == "__main__":
    main()
