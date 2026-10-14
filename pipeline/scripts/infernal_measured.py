#!/usr/bin/env python3
"""Measured cmscan run locked by docs/INFERNAL_PROTOCOL.md.

Does not draw genomes. Recomputes the locked draw and stops on a mismatch.
"""
from __future__ import annotations

import csv
import gzip
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "scripts"))

import infernal_pilot as ip  # noqa: E402

LOCKED = [
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
]
TIMING = LOCKED[0]
PILOT = "GCF_049949635.1"
SEED = 20261042
FLOOR = 2000
REPEATS = 3
WORK = Path.home() / "tmp" / "infernal_work" / "measured"
STATE = WORK / "state.json"
OUT = PIPE / "results" / "infernal" / "test_i.json"


def log(message: str) -> None:
    print(time.strftime("%H:%M:%S"), message, flush=True)


def check_draw() -> None:
    pool: list[str] = []
    with (PIPE / "results" / "infernal" / "inputs.tsv").open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["kind"] != "genome":
                continue
            pool.append("_".join(row["name"].split("_")[:2]))
    pool = sorted(set(pool) - {PILOT})
    got = sorted(random.Random(SEED).sample(pool, 10))
    if got != LOCKED:
        raise SystemExit(f"draw {got} is not the locked list")


def fasta_for(acc: str) -> Path:
    hits = sorted((ip.ROOT / "genomes").glob(f"{acc}*_genomic.fna.gz"))
    if len(hits) != 1:
        raise SystemExit(f"{acc}: {len(hits)} genome files")
    dest = WORK / f"{acc}.fa"
    if not dest.is_file():
        dest.write_bytes(gzip.decompress(hits[0].read_bytes()))
    return dest


def load() -> dict:
    if STATE.is_file():
        return json.loads(STATE.read_text())
    return {"genomes": {}}


def save(state: dict) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(STATE)


def median(values: list[float]) -> float:
    return float(statistics.median(values))


def arm(acc: str, clan: bool, fasta: Path, z: str, repeats: int) -> dict:
    kind = "fmt2" if clan else "fmt1"
    name = "clan" if clan else "noclan"
    folder = WORK / acc / name
    folder.mkdir(parents=True, exist_ok=True)
    stocks = []
    for index in range(repeats):
        tag = folder / f"stock_{index}"
        stocks.append(ip.scan(tag, ip.base_argv(z, Path(str(tag) + ".tbl"), ip.CM, clan, fasta=fasta)))
    bodies = [ip.body(folder / f"stock_{index}.tbl") for index in range(repeats)]
    det = all(body == bodies[0] for body in bodies)
    report: dict = {
        "stock_walls": [row["wall_s"] for row in stocks],
        "body_rows": len(bodies[0]),
        "stock_bodies_equal": det,
    }
    if not det:
        report["stopped"] = "stock repeats differ"
        return report
    cand = ip.model_names(folder / "stock_0.tbl", kind)
    models = {item for names in cand.values() for item in names}
    oracle_cm = folder / "oracle.cm"
    n_models = ip.write_subset(models, oracle_cm)
    clanin = None
    if clan:
        clanin = folder / "oracle.clanin"
        ip.filter_clanin(models, clanin)
    oracles = []
    compared = []
    for index in range(repeats):
        tag = folder / f"oracle_{index}"
        oracles.append(ip.scan(tag, ip.base_argv(z, Path(str(tag) + ".tbl"), oracle_cm, clan, clanin, fasta)))
        compared.append(ip.classify(ip.body(Path(str(tag) + ".tbl")), bodies[0], kind))
    report["oracle_models"] = n_models
    report["candidate_models"] = len(models)
    report["oracle_walls"] = [row["wall_s"] for row in oracles]
    report["oracle"] = compared
    report["body_equal"] = all(row["byte_equal"] for row in compared)
    ratios = [s / o for s, o in zip(report["stock_walls"], report["oracle_walls"]) if o > 0]
    report["ratios"] = ratios
    if repeats == REPEATS:
        report["median_ratio"] = median(ratios)
    oracle_cm.unlink(missing_ok=True)
    for ext in (".i1m", ".i1i", ".i1f", ".i1p"):
        Path(str(oracle_cm) + ext).unlink(missing_ok=True)
    return report


def main() -> None:
    check_draw()
    WORK.mkdir(parents=True, exist_ok=True)
    state = load()
    for acc in LOCKED:
        if acc in state["genomes"]:
            log(f"reuse {acc}")
            continue
        fasta = fasta_for(acc)
        z, residues = ip.z_string(fasta)
        repeats = REPEATS if acc == TIMING else 1
        log(f"{acc} Z={z} residues={residues} repeats={repeats}")
        state["genomes"][acc] = {
            "z": z,
            "residues": residues,
            "noclan": arm(acc, False, fasta, z, repeats),
            "clan": arm(acc, True, fasta, z, repeats),
        }
        save(state)
    if "cli" not in state:
        fasta = fasta_for(TIMING)
        z = state["genomes"][TIMING]["z"]
        state["cli"] = {
            "genome": TIMING,
            "noclan": ip.run_cli(z, False, WORK / TIMING / "cli_noclan", fasta),
            "clan": ip.run_cli(z, True, WORK / TIMING / "cli_clan", fasta),
        }
        save(state)
    rows = {
        "noclan": sum(state["genomes"][acc]["noclan"]["body_rows"] for acc in LOCKED),
        "clan": sum(state["genomes"][acc]["clan"]["body_rows"] for acc in LOCKED),
    }
    def outcome(variant: str) -> str:
        matched = all(state["genomes"][acc][variant].get("body_equal") for acc in LOCKED)
        if not matched:
            return "NOT-EXACT"
        if rows[variant] < FLOOR:
            return "INCONCLUSIVE"
        return "EXACT"
    banner = subprocess.run([str(ip.CMSCAN), "-h"], check=False, capture_output=True, text=True).stdout.splitlines()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PIPE.parents[0], check=True, capture_output=True, text=True
    ).stdout.strip()
    payload = {
        "protocol": "docs/INFERNAL_PROTOCOL.md",
        "pilot": "results/infernal/pilot.json",
        "git_head": head,
        "cmscan_banner": banner[1] if len(banner) > 1 else "",
        "seed": SEED,
        "floor": FLOOR,
        "timing_genome": TIMING,
        "rows": rows,
        "outcome": {"noclan": outcome("noclan"), "clan": outcome("clan")},
        "cli": {
            "genome": TIMING,
            "noclan": state["cli"]["noclan"]["stdout_tail"],
            "clan": state["cli"]["clan"]["stdout_tail"],
            "noclan_wall_s": state["cli"]["noclan"]["wall_s"],
            "clan_wall_s": state["cli"]["clan"]["wall_s"],
        },
        "genomes": state["genomes"],
        "walls_indicative": True,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    log(f"wrote {OUT} rows={rows} outcome={payload['outcome']}")


if __name__ == "__main__":
    main()
