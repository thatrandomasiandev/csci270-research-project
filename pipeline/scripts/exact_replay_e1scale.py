#!/usr/bin/env python3
"""Measured E1-scale run. Locked by the E1-scale addendum before this process starts.

The Q1000 draw is pilot data and is not an input here.
"""
from __future__ import annotations

import json
import platform
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exact_replay_e1scale_pilot as pilot  # noqa: E402

DATA = pilot.DATA
WORK = pilot.WORK
PFAM_382 = pilot.PFAM_382
PFAM_381 = pilot.PFAM_381
Z_NEW = pilot.Z_NEW
ROOT = DATA / "recurrence/A"
EXCLUDE = {
    "GCF_002853805.1_protein.faa.gz",
    "GCF_002090355.1_protein.faa.gz",
}
LOCKED = [
    "GCF_013315695.1_protein.faa.gz",
    "GCF_049201905.1_protein.faa.gz",
    "GCF_059719525.1_protein.faa.gz",
]
SEED = 20261014
FLOOR = 5000


def count_models(path: Path) -> int:
    n = 0
    with open(path) as fh:
        for line in fh:
            if line.startswith("NAME "):
                n += 1
    return n


def choose() -> list[Path]:
    pool = sorted(path.name for path in ROOT.glob("*.faa.gz") if path.name not in EXCLUDE)
    draw = random.Random(SEED).sample(pool, 3)
    got = sorted(draw)
    if got != LOCKED:
        raise SystemExit(f"proteome draw {got} is not the locked list {LOCKED}")
    return [ROOT / name for name in LOCKED]


def outcome(e1: dict, e2: dict, rn: dict) -> str:
    rn_differs = (not rn["tbl"]["byte_equal"]) and (not rn["dom"]["byte_equal"])
    if not rn_differs:
        return "FAIL"
    pairs = (e1["tbl"], e1["dom"], e2["tbl"], e2["dom"])
    if any(not row["token_equal"] for row in pairs):
        return "FAIL"
    if all(row["byte_equal"] for row in pairs):
        return "EXACT"
    return "TOKEN-EQUAL"


def clean(folder: Path) -> None:
    if not folder.is_dir():
        return
    for path in folder.glob("*.hmm"):
        path.unlink(missing_ok=True)
        for ext in (".h3f", ".h3i", ".h3m", ".h3p"):
            Path(str(path) + ext).unlink(missing_ok=True)


def main() -> None:
    proteomes = choose()
    if not PFAM_382.is_file() or not PFAM_381.is_file():
        raise SystemExit("pressed Pfam is missing; press pfam38.2.hmm and pfam38.1.hmm in the work directory first")
    z382, z381 = count_models(PFAM_382), count_models(PFAM_381)
    if (z382, z381) != (30134, 27481):
        raise SystemExit(f"INCONCLUSIVE: pressed model counts are {z382}, {z381}")
    # The pilot press counted these. A different count stops the arm.
    report: dict = {
        "pilot": False,
        "protocol": "docs/EXACT_REPLAY_PROTOCOL.md",
        "addendum": "E1-scale",
        "git_head": pilot.git_head(),
        "host": platform.node(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "hmmscan": pilot.hmm_version(),
        "cpu": 4,
        "z_new": Z_NEW,
        "walls_indicative": True,
        "seed": SEED,
        "proteomes_locked": LOCKED,
        "pressed_models": {"38.2": z382, "38.1": z381},
        "input_md5": {
            "Pfam-A.hmm.gz": pilot.md5_file(pilot.PFAM_382_GZ),
            "pfam38.1/Pfam-A.hmm.gz": pilot.md5_file(pilot.PFAM_381_GZ),
        },
        "proteomes": [],
    }
    first = proteomes[0]
    tag = WORK / "measured" / first.name.replace("_protein.faa.gz", "")
    tag.mkdir(parents=True, exist_ok=True)
    queries = tag / "queries.faa"
    if not queries.is_file():
        pilot.log(f"expanding {first.name}")
        text = pilot.read_fasta(first)
        queries.write_text("".join(text))
        report_n = len(text)
    else:
        report_n = sum(1 for line in queries.read_text().splitlines() if line.startswith(">"))
    t1 = pilot.scan(PFAM_382, queries, tag / "S382_a")
    t2 = pilot.scan(PFAM_382, queries, tag / "S382_b")
    determinism = pilot.classify_pair(tag / "S382_a", tag / "S382_b")
    report["determinism"] = {
        "proteome": first.name,
        "n_records": report_n,
        "walls_s": {"run_1": t1, "run_2": t2},
        "vs": determinism,
        "pass": pilot.both_byte(determinism),
    }
    if not report["determinism"]["pass"]:
        dest = pilot.PIPE / "results/exact_replay/e1scale.json"
        report["overall"] = "STOPPED"
        report["why"] = "stock-vs-stock failed on proteome 1; no proteome was scored"
        dest.write_text(json.dumps(report, indent=2) + "\n")
        raise SystemExit(report["why"])
    pilot.log("proteome 1 stock-vs-stock byte-identical")

    total_tbl = 0
    for index, src in enumerate(proteomes):
        folder = WORK / "measured" / src.name.replace("_protein.faa.gz", "")
        folder.mkdir(parents=True, exist_ok=True)
        qpath = folder / "queries.faa"
        if not qpath.is_file():
            pilot.log(f"expanding {src.name}")
            recs = pilot.read_fasta(src)
            qpath.write_text("".join(recs))
            n_records = len(recs)
        else:
            n_records = sum(1 for line in qpath.read_text().splitlines() if line.startswith(">"))
        wall_new = pilot.scan(PFAM_382, qpath, folder / "S382") if index else t1
        if index == 0:
            # The first stock-vs-stock run is the stock target. Do not scan a third time.
            shutil.copyfile(folder / "S382_a.tbl", folder / "S382.tbl")
            shutil.copyfile(folder / "S382_a.dom", folder / "S382.dom")
            wall_new = t1
        wall_old = pilot.scan(PFAM_381, qpath, folder / "S381")
        driver = pilot.run_driver(qpath, folder / "S382", folder / "S381", folder / "driver", folder / "driver.json")
        e1 = pilot.classify_pair(folder / "driver" / "e1_R", folder / "S382")
        e2 = pilot.classify_pair(folder / "driver" / "e2_R", folder / "S382")
        rn = pilot.classify_pair(folder / "driver" / "e1_Rn", folder / "S382")
        label = outcome(e1, e2, rn)
        total_tbl += e1["tbl"]["lines_stock"]
        row = {
            "proteome": src.name,
            "n_records": n_records,
            "input_md5": pilot.md5_file(src),
            "walls_s": {
                "stock_38.2": wall_new,
                "stock_38.1": wall_old,
                "indicative": True,
                "driver_E1_R": driver.get("E1", {}).get("wall_R_s"),
                "driver_E1_Rn": driver.get("E1", {}).get("wall_Rn_s"),
                "driver_E2": driver.get("E2", {}).get("wall_s"),
            },
            "E1": {"summary": driver.get("E1"), "vs_stock": e1},
            "E2": {"summary": driver.get("E2"), "vs_stock": e2},
            "Rn": {"vs_stock": rn},
            "tblout_body_lines": e1["tbl"]["lines_stock"],
            "domtblout_body_lines": e1["dom"]["lines_stock"],
            "candidate_models_E1": driver.get("E1", {}).get("models_replayed"),
            "candidate_queries_E1": driver.get("E1", {}).get("queries_replayed"),
            "candidate_pairs_E2": driver.get("E2", {}).get("candidate_pairs"),
            "replay_models_E2": driver.get("E2", {}).get("replay_models"),
            "changed_or_new_models": driver.get("E2", {}).get("changed_or_new_models"),
            "classes": {
                "E1_tbl": e1["tbl"]["classes"],
                "E1_dom": e1["dom"]["classes"],
                "E2_tbl": e2["tbl"]["classes"],
                "E2_dom": e2["dom"]["classes"],
                "Rn_tbl": rn["tbl"]["classes"],
                "Rn_dom": rn["dom"]["classes"],
            },
            "outcome": label,
        }
        report["proteomes"].append(row)
        clean(folder / "driver")
        pilot.log(f"{src.name} {label} tbl={row['tblout_body_lines']} dom={row['domtblout_body_lines']}")

    labels = [row["outcome"] for row in report["proteomes"]]
    if total_tbl < FLOOR:
        overall = "INCONCLUSIVE"
    elif any(label == "FAIL" for label in labels):
        overall = "FAIL"
    elif any(label == "TOKEN-EQUAL" for label in labels):
        overall = "TOKEN-EQUAL"
    elif all(label == "EXACT" for label in labels):
        overall = "EXACT"
    else:
        overall = "FAIL"
    report["tblout_body_lines_total"] = total_tbl
    report["power_floor"] = FLOOR
    report["overall"] = overall
    for path in (PFAM_382, PFAM_381):
        path.unlink(missing_ok=True)
    report["free_bytes_end"] = pilot.free_bytes()
    dest = pilot.PIPE / "results/exact_replay/e1scale.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    pilot.log(f"{overall} tblout_lines={total_tbl} wrote {dest}")


if __name__ == "__main__":
    main()
