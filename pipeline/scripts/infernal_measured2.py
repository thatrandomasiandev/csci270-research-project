#!/usr/bin/env python3
"""Measured run 2, locked by docs/INFERNAL_PROTOCOL.md on 2026-10-17.

Does not draw a new list. Recomputes seed 20261047 and stops on a mismatch.
Writes results/infernal/measured2.json after every stock scan and update.
"""
from __future__ import annotations

import csv
import json
import math
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "scripts"))

import infernal_budget_pilot as bp  # noqa: E402

SEED = 20261047
FLOOR = 2000
REPEATS = 3
BOOTSTRAP_DRAWS = 10_000
EXCLUDE = bp.EXCLUDE | {"GCF_010365405.1"}
LOCKED = [
    "GCF_002058765.1",
    "GCF_002090355.1",
    "GCF_009433135.1",
    "GCF_013315695.1",
    "GCF_020034635.1",
    "GCF_020905655.1",
    "GCF_024918035.1",
    "GCF_045689345.1",
    "GCF_049949335.1",
    "GCF_900196535.2",
]
PREDICTED = {
    "noclan": {
        "f": 457 / 4227,
        "a": 0.5664645860536466,
        "c": 0.4189125397333216,
        "predicted_s": 2.0826583074972143,
    },
    "clan": {
        "f": 457 / 4227,
        "a": 0.6355455932375328,
        "c": 0.4199626238665531,
        "predicted_s": 2.0463526744530274,
    },
}
WORK = Path.home() / "tmp" / "infernal3_work" / "measured2"
STATE = WORK / "state.json"
OUT = PIPE / "results" / "infernal" / "measured2.json"
RANK = {
    "UNSAFE": 5,
    "TOKEN-EQUAL": 4,
    "SAFE-REFUSE true": 3,
    "SAFE-REFUSE needless": 3,
    "SAFE-REFUSE": 3,
    "EXACT": 2,
    "INCONCLUSIVE": 1,
}


def log(message: str) -> None:
    print(time.strftime("%H:%M:%S"), message, flush=True)


def check_draw() -> None:
    pool: list[str] = []
    with bp.INPUTS.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["kind"] == "genome":
                pool.append(row["name"])
    rest = sorted(set(pool) - EXCLUDE)
    got = sorted(random.Random(SEED).sample(rest, 10))
    if got != LOCKED:
        raise SystemExit(f"draw {got} is not the locked list")


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PIPE.parents[0], check=True, capture_output=True, text=True
    ).stdout.strip()


def load() -> dict:
    if STATE.is_file():
        return json.loads(STATE.read_text())
    return {"genomes": {}, "order": LOCKED, "seed": SEED, "partial": True}


def save(state: dict) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(state, indent=2) + "\n"
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(text)
    tmp.replace(STATE)
    out_tmp = OUT.with_suffix(".tmp")
    out_tmp.write_text(text)
    out_tmp.replace(OUT)


def median(values: list[float]) -> float:
    return float(statistics.median(values))


def cv(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    if mean == 0:
        return None
    return statistics.stdev(values) / mean


def run_outcome(paired: dict) -> str:
    decision = paired["tare"].get("decision") or ""
    compared = paired["compare"]
    why = paired["tare"].get("why") or ""
    if decision == "SHIP" and compared["byte_equal"]:
        return "EXACT"
    if decision == "SHIP" and compared["token_equal"]:
        return "TOKEN-EQUAL"
    if decision == "SHIP":
        return "UNSAFE"
    if not decision.startswith("REFUSE"):
        return "INCONCLUSIVE"
    # An ic2 failure does not write the replay, so an empty body is not
    # evidence that the replay differed from stock.
    if compared["tare_rows"] == 0:
        if "differs from a full run" in why:
            return "SAFE-REFUSE true"
        return "SAFE-REFUSE"
    if "differs from a full run" in why or not compared["byte_equal"]:
        return "SAFE-REFUSE true"
    return "SAFE-REFUSE needless"


def worst(outcomes: list[str]) -> str:
    return max(outcomes, key=lambda item: RANK.get(item, 0))


def finish_block(block: dict) -> None:
    runs = block["runs"]
    stocks = [row["stock"]["body_sha256"] for row in runs]
    if len(set(stocks)) != 1:
        block["outcome"] = "INCONCLUSIVE"
        block["stock_bodies_equal"] = False
        block["done"] = True
        return
    block["stock_bodies_equal"] = True
    per_run = [run_outcome(row) for row in runs]
    block["run_outcomes"] = per_run
    block["outcome"] = worst(per_run)
    stock_walls = [row["stock"]["wall_s"] for row in runs]
    tare_walls = [row["tare"]["wall_s"] for row in runs]
    block["median_stock_s"] = median(stock_walls)
    block["median_tare_s"] = median(tare_walls)
    block["s_g"] = block["median_stock_s"] / block["median_tare_s"] if block["median_tare_s"] else None
    block["cv_stock"] = cv(stock_walls)
    block["cv_tare"] = cv(tare_walls)
    block["median_stock_cpu_s"] = median([row["stock"]["cpu_s"] for row in runs])
    block["median_tare_cpu_s"] = median([row["tare"]["cpu_s"] for row in runs])
    block["body_lines"] = runs[0]["stock"]["body_rows"]
    block["done"] = True


def one_variant(state: dict, acc: str, name: str, clan: bool, z: str, fasta: Path) -> str | None:
    """Run one variant. Returns 'stop' on UNSAFE or a battery pause message."""
    folder = WORK / acc / name
    folder.mkdir(parents=True, exist_ok=True)
    genome = state["genomes"].setdefault(acc, {})
    block = genome.setdefault(name, {"runs": []})
    if block.get("done"):
        log(f"reuse {acc} {name}")
        return "stop" if block.get("outcome") == "UNSAFE" else None
    if "fill" not in block:
        if not bp.on_ac_power():
            return "pause: not on AC power"
        fill_cache = folder / "fill" / "cache.sqlite"
        block["fill"] = bp.tare_run(
            folder / "fill", fill_cache, z, clan, fasta, bp.CM_OLD, bp.CLAN_OLD if clan else None
        )
        save(state)
    fill_cache = folder / "fill" / "cache.sqlite"
    while len(block["runs"]) < REPEATS:
        index = len(block["runs"])
        if not bp.on_ac_power():
            return "pause: not on AC power"
        stock = bp.stock_scan(folder / f"stock_{index}", z, clan, fasta)
        save(state)
        if not bp.on_ac_power():
            return "pause: not on AC power"
        run_dir = folder / f"update_{index}"
        cache = run_dir / "cache.sqlite"
        if not (run_dir / "run.json").is_file():
            run_dir.mkdir(parents=True, exist_ok=True)
            if cache.is_file():
                cache.unlink()
            bp.copy_cache(fill_cache, cache)
        tare = bp.tare_run(run_dir, cache, z, clan, fasta, bp.CM_NEW, bp.CLAN_NEW if clan else None)
        paired = {
            "stock": stock,
            "tare": tare,
            "compare": bp.compare(folder / f"stock_{index}.tbl", run_dir),
        }
        block["runs"].append(paired)
        save(state)
        label = run_outcome(paired)
        log(f"{acc} {name} update {index} {label}")
        if label == "UNSAFE":
            finish_block(block)
            state["stopped"] = f"UNSAFE {acc} {name} update {index}"
            save(state)
            return "stop"
    finish_block(block)
    save(state)
    log(f"{acc} {name} {block['outcome']} S_g={block.get('s_g')}")
    return "stop" if block["outcome"] == "UNSAFE" else None


def geometric_mean(values: list[float]) -> float | None:
    if not values or any(item <= 0 for item in values):
        return None
    return math.exp(sum(math.log(item) for item in values) / len(values))


def bootstrap_median(values: list[float], seed: int) -> dict | None:
    if not values:
        return None
    rng = random.Random(seed)
    size = len(values)
    draws = [statistics.median(rng.choices(values, k=size)) for _ in range(BOOTSTRAP_DRAWS)]
    draws.sort()
    return {
        "seed": seed,
        "draws": BOOTSTRAP_DRAWS,
        "p2.5": draws[int(0.025 * (BOOTSTRAP_DRAWS - 1))],
        "p97.5": draws[int(0.975 * (BOOTSTRAP_DRAWS - 1))],
    }


def summarize(state: dict) -> None:
    state["summary"] = {}
    for name, pred in PREDICTED.items():
        blocks = []
        lines = 0
        for acc in LOCKED:
            block = state["genomes"].get(acc, {}).get(name)
            if not block or not block.get("done"):
                continue
            if block.get("stock_bodies_equal") and block.get("outcome") != "INCONCLUSIVE":
                lines += int(block.get("body_lines") or 0)
                if block.get("s_g") is not None and block["outcome"] != "UNSAFE":
                    blocks.append(block)
        ratios = [block["s_g"] for block in blocks]
        cvs = [block["cv_stock"] for block in blocks if block.get("cv_stock") is not None]
        cvs += [block["cv_tare"] for block in blocks if block.get("cv_tare") is not None]
        errors = []
        for block in blocks:
            hat = (pred["a"] * pred["f"] + pred["c"]) * block["median_stock_s"]
            if block["median_tare_s"]:
                errors.append(abs(hat - block["median_tare_s"]) / block["median_tare_s"])
        state["summary"][name] = {
            "genomes_finished": sum(
                1 for acc in LOCKED if state["genomes"].get(acc, {}).get(name, {}).get("done")
            ),
            "body_lines": lines,
            "power": "INCONCLUSIVE" if lines < FLOOR else "met",
            "floor": FLOOR,
            "s_g": ratios,
            "median_s_g": median(ratios) if ratios else None,
            "geometric_mean_s_g": geometric_mean(ratios),
            "range_s_g": [min(ratios), max(ratios)] if ratios else None,
            "max_cv": max(cvs) if cvs else None,
            "max_relative_error": max(errors) if errors else None,
            "bootstrap_median": bootstrap_median(ratios, SEED),
            "predicted_s": pred["predicted_s"],
            "a": pred["a"],
            "c": pred["c"],
            "f": pred["f"],
            "outcomes": {
                acc: state["genomes"][acc][name]["outcome"]
                for acc in LOCKED
                if name in state["genomes"].get(acc, {}) and state["genomes"][acc][name].get("outcome")
            },
        }


def main() -> None:
    for pred in PREDICTED.values():
        got = 1.0 / (pred["a"] * pred["f"] + pred["c"])
        if abs(got - pred["predicted_s"]) > 1e-12:
            raise SystemExit(f"prediction {got} != {pred['predicted_s']}")
    check_draw()
    bp.WORK = WORK
    if not bp.on_ac_power():
        raise SystemExit("pause: not on AC power")
    for path in (
        bp.CMSCAN, bp.CMPRESS,
        bp.ROOT / "rfam" / "15.0" / "Rfam.cm", bp.ROOT / "rfam" / "15.1" / "Rfam.cm",
        bp.ROOT / "rfam" / "15.0" / "Rfam.clanin", bp.ROOT / "rfam" / "15.1" / "Rfam.clanin",
    ):
        if not path.is_file():
            raise SystemExit(f"missing {path}")
    bp.stage_databases()
    state = load()
    state["seed"] = SEED
    state["order"] = LOCKED
    state["predicted"] = PREDICTED
    state["git_head_start"] = state.get("git_head_start") or git_head()
    state["walls_indicative"] = True
    state["partial"] = True
    save(state)
    for acc in LOCKED:
        if state.get("stopped"):
            break
        genome = state["genomes"].setdefault(acc, {})
        if "z" not in genome:
            if not bp.on_ac_power():
                state["stopped"] = "pause: not on AC power"
                save(state)
                break
            fasta = bp.fasta_for(acc)
            z, residues = bp.z_string(fasta)
            genome["z"] = z
            genome["residues"] = residues
            genome["fasta"] = str(fasta)
            save(state)
            log(f"{acc} Z={z} residues={residues}")
        else:
            fasta = Path(genome["fasta"])
            z = genome["z"]
        for name, clan in (("noclan", False), ("clan", True)):
            status = one_variant(state, acc, name, clan, z, fasta)
            if status == "stop":
                break
            if status:
                state["stopped"] = status
                save(state)
                break
        else:
            continue
        break
    summarize(state)
    state["git_head"] = git_head()
    state["partial"] = bool(state.get("stopped")) or any(
        not state["genomes"].get(acc, {}).get(name, {}).get("done")
        for acc in LOCKED
        for name in ("noclan", "clan")
    )
    save(state)
    log(f"wrote {OUT} partial={state['partial']}")
    if state.get("stopped"):
        raise SystemExit(state["stopped"])


if __name__ == "__main__":
    main()
