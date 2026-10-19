#!/usr/bin/env python3
"""Fit TARE server cost-model coefficients from the headline measurements.

The model is the one already used by the paper and by make_figures.fig_model:

    T_TARE = a * f * T_stock + c * T_stock
    S      = 1 / (a * f + c)

a is the discovery coefficient and c is every other cost as a fraction of a
stock run. Neither symbol is redefined here.

Laptop (published a=1.06, c=0.152), one observation per proteome, from
results/exact_replay/costpass_measured.json:

    a_g = discovery_s / (f * stock_wall_s)
    c_g = (tare_wall_s - discovery_s) / stock_wall_s
    a   = sum(a_g) / n
    c   = sum(c_g) / n

Server, same ratios, from the nine EXACT headline genomes. Each genome has
three alternating A/B repeats. B repeat r is paired with A repeat r:

    a_{g,r} = discovery_s / (f * A_wall_s)
    c_{g,r} = (B_wall_s - discovery_s) / A_wall_s
    a_g     = sum_r a_{g,r} / 3
    c_g     = sum_r c_{g,r} / 3
    a       = sum_g a_g / 9
    c       = sum_g c_g / 9

B_wall_s is the repeat's wall_s, not phases.total_s. f is the Pfam
38.1->38.2 changed fraction. With three repeats on every included genome,
sum_g a_g / 9 equals the arithmetic mean of all 27 paired ratios.

This is a reduction of committed JSON. It does not draw a sample and it
does not time anything.
"""
from __future__ import annotations

import json
import math
import platform
import subprocess
import sys
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
HEADLINE = PIPELINE / "results" / "exact_replay" / "headline_carc.json"
PAIRS = PIPELINE / "results" / "release_chain" / "pairs.json"
LAPTOP = PIPELINE / "results" / "exact_replay" / "costpass_measured.json"
DEFAULT_OUT = PIPELINE / "results" / "exact_replay" / "server_cost_fit.json"

# Published rounding of the laptop fit. The control recomputes the ratios.
PUBLISHED_LAPTOP_A = 1.06
PUBLISHED_LAPTOP_C = 0.152

PAD_KEYS = (
    "ic2_random_20261031_s",
    "ic2_random_20261032_s",
    "ic2_random_20261033_s",
)
PHASE_KEYS = ("discovery_s", "replay_s", "verify_s", "ic2_neighbor_s") + PAD_KEYS


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PIPELINE, text=True
    ).strip()


def arithmetic_mean(values: list[float]) -> float:
    """sum/n, the reduction make_figures.fig_model already uses."""
    if not values:
        raise ValueError("empty mean")
    return sum(values) / len(values)


def stage_split(phases: dict, wall_s: float) -> dict[str, float]:
    """Four bars: discovery, replay, check + audit, everything else.

    check is the neighbor pad, the three random pads, and verify. On the
    headline files this is the same sum as the startswith('ic2_random_')
    filter with exactly three underscores that make_figures used for the
    shipped laptop bars.
    """
    missing = [key for key in PHASE_KEYS if key not in phases]
    if missing:
        raise KeyError(f"phases missing {missing}")
    random_keys = sorted(
        key for key in phases if key.startswith("ic2_random_") and key.count("_") == 3
    )
    if random_keys != sorted(PAD_KEYS):
        raise ValueError(f"unexpected random-pad keys {random_keys}")
    check = phases["ic2_neighbor_s"] + sum(phases[key] for key in PAD_KEYS) + phases["verify_s"]
    stages = {
        "discovery": float(phases["discovery_s"]),
        "replay": float(phases["replay_s"]),
        "check": float(check),
    }
    stages["other"] = float(wall_s) - sum(stages.values())
    if stages["other"] < -1e-6:
        raise ValueError(f"stage split exceeds wall_s by {-stages['other']}")
    return stages


def _pair_rows(payload: dict) -> list[dict]:
    stock = {row["repeat"]: row for row in payload["repeats"] if row["arm"] == "A"}
    tare = {row["repeat"]: row for row in payload["repeats"] if row["arm"] == "B"}
    if set(stock) != {1, 2, 3} or set(tare) != {1, 2, 3}:
        raise ValueError(f"{payload.get('proteome')} repeats are not A1-3 and B1-3")
    rows = []
    for repeat in (1, 2, 3):
        stock_row = stock[repeat]
        tare_row = tare[repeat]
        phases = tare_row["phases"]
        discovery = float(phases["discovery_s"])
        stock_wall = float(stock_row["wall_s"])
        tare_wall = float(tare_row["wall_s"])
        rows.append({
            "repeat": repeat,
            "repeats_index": payload["repeats"].index(tare_row),
            "stock_wall_s": stock_wall,
            "tare_wall_s": tare_wall,
            "discovery_s": discovery,
            "phases_total_s": float(phases["total_s"]) if "total_s" in phases else None,
            "decision": tare_row.get("decision"),
            "byte_equal": (tare_row.get("compare") or {}).get("byte_equal"),
            "stock_row": stock_row,
            "tare_row": tare_row,
        })
    return rows


def _median_index(walls: list[float]) -> int:
    """Middle of the sorted runs. For three runs this is the median wall."""
    order = sorted(range(len(walls)), key=lambda index: walls[index])
    return order[len(walls) // 2]


def laptop_reference(f_delta: float) -> dict:
    measured = json.loads(LAPTOP.read_text())
    per_genome = []
    for proteome in measured["proteomes"]:
        stock = float(proteome["stock"]["wall_s"])
        discovery = float(proteome["e2"]["phases"]["discovery_s"])
        wall = float(proteome["e2"]["wall_s"])
        per_genome.append({
            "proteome": proteome["proteome"],
            "stock_wall_s": stock,
            "discovery_s": discovery,
            "tare_wall_s": wall,
            "a_g": discovery / (f_delta * stock),
            "c_g": (wall - discovery) / stock,
        })
    a_value = arithmetic_mean([row["a_g"] for row in per_genome])
    c_value = arithmetic_mean([row["c_g"] for row in per_genome])
    passed = (
        round(a_value, 2) == PUBLISHED_LAPTOP_A
        and round(c_value, 3) == PUBLISHED_LAPTOP_C
    )
    return {
        "role": "positive control and dashed reference curve",
        "source": "results/exact_replay/costpass_measured.json",
        "formula": (
            "a_g = discovery_s / (f * stock_wall_s); "
            "c_g = (tare_wall_s - discovery_s) / stock_wall_s; "
            "a, c = arithmetic means over the two proteomes. "
            "One run each, which is the published laptop fit."
        ),
        "published_a": PUBLISHED_LAPTOP_A,
        "published_c": PUBLISHED_LAPTOP_C,
        "recomputed_a": a_value,
        "recomputed_c": c_value,
        "rounding_matches_published": passed,
        "proteomes": per_genome,
    }


def _f_delta(pairs: list[dict]) -> tuple[float, int]:
    matches = [
        (index, pair) for index, pair in enumerate(pairs)
        if pair["old_release"] == "38.1" and pair["new_release"] == "38.2"
    ]
    if len(matches) != 1:
        raise ValueError("expected one 38.1->38.2 pair")
    index, pair = matches[0]
    f_delta = float(pair["f_delta"])
    if f_delta != 4052 / 30134:
        raise ValueError(f"f_delta {f_delta} is not 4052/30134")
    return f_delta, index


def fit(pipeline: Path = PIPELINE) -> dict:
    headline = json.loads((pipeline / "results" / "exact_replay" / "headline_carc.json").read_text())
    pairs_doc = json.loads((pipeline / "results" / "release_chain" / "pairs.json").read_text())
    pairs = pairs_doc["pairs"]
    f_delta, f_index = _f_delta(pairs)
    laptop = laptop_reference(f_delta)
    if not laptop["rounding_matches_published"]:
        raise SystemExit(
            "laptop control failed: "
            f"a={laptop['recomputed_a']} c={laptop['recomputed_c']}"
        )

    included = []
    excluded = []
    for genome in headline["genomes"]:
        path = pipeline / genome["path"]
        payload = json.loads(path.read_text())
        if genome["outcome"] != "EXACT" or payload.get("outcome") != "EXACT":
            excluded.append({
                "proteome": genome["proteome"],
                "path": genome["path"],
                "outcome": genome.get("outcome"),
                "reason": (
                    "Headline set, not EXACT. Task 3 refused at cache fill and "
                    "has no B-arm phases. Listed, not imputed, not in the mean."
                ),
            })
            continue
        paired = _pair_rows(payload)
        for row in paired:
            if row["decision"] != "SHIP" or row["byte_equal"] is not True:
                raise ValueError(f"{genome['proteome']} repeat {row['repeat']} is not an exact ship")
            if row["stock_wall_s"] <= 0 or f_delta <= 0:
                raise ValueError("non-positive stock wall or f")
        a_rs = [row["discovery_s"] / (f_delta * row["stock_wall_s"]) for row in paired]
        c_rs = [(row["tare_wall_s"] - row["discovery_s"]) / row["stock_wall_s"] for row in paired]
        stock_walls = [row["stock_wall_s"] for row in paired]
        tare_walls = [row["tare_wall_s"] for row in paired]
        s_g = statistics_median(stock_walls) / statistics_median(tare_walls)
        if abs(s_g - float(genome["S_g"])) > 1e-9:
            raise ValueError(f"{genome['proteome']} S_g {s_g} != headline {genome['S_g']}")
        repeat_records = []
        for row, a_gr, c_gr in zip(paired, a_rs, c_rs):
            repeat_records.append({
                "repeat": row["repeat"],
                "repeats_index": row["repeats_index"],
                "stock_wall_s": row["stock_wall_s"],
                "tare_wall_s": row["tare_wall_s"],
                "discovery_s": row["discovery_s"],
                "phases_total_s_not_used": row["phases_total_s"],
                "a_g_r": a_gr,
                "c_g_r": c_gr,
                "decision": row["decision"],
                "byte_equal": row["byte_equal"],
            })
        included.append({
            "proteome": payload["proteome"],
            "path": genome["path"],
            "job_id": str(payload.get("job_id")),
            "task": payload.get("task"),
            "outcome": payload["outcome"],
            "acts_commit": payload.get("acts_commit"),
            "measurement_git_head": payload.get("git_head"),
            "seed": payload.get("seed"),
            "cpu_model": payload.get("cpu_model"),
            "cv_A": genome.get("cv_A"),
            "cv_B": genome.get("cv_B"),
            "cv_flag_A": genome.get("cv_flag_A"),
            "cv_flag_B": genome.get("cv_flag_B"),
            "S_g": s_g,
            "a_g": arithmetic_mean(a_rs),
            "c_g": arithmetic_mean(c_rs),
            "repeats": repeat_records,
            "_paired": paired,
        })

    if len(included) != 9:
        raise SystemExit(f"expected 9 EXACT genomes, found {len(included)}")

    # Partials and the pilot sit beside the scored files and must not enter.
    measured_dir = pipeline / "results" / "exact_replay" / "headline_measured"
    used_names = {Path(row["path"]).name for row in included}
    already_excluded = {item["path"] for item in excluded}
    for path in sorted(measured_dir.glob("*.json")):
        rel = f"results/exact_replay/headline_measured/{path.name}"
        if path.name in used_names or rel in already_excluded:
            continue
        if path.name in {
            "headline_pilot.json",
            "headline_pilot_13138266.json",
        }:
            reason = (
                "Pilot genome, job 13138266. Its three paired runs are the "
                "pre-registered prior a=1.0146410126797523, c=0.10846594102974193. "
                "Not part of the nine."
            )
        elif path.name in {
            "headline_measured_13208152_2.json",
            "headline_measured_13208152_4.json",
            "headline_measured_13208152_5.json",
        }:
            reason = (
                "Timed out at 4 h. Superseded by the complete 8 h rerun "
                "13227819 of the same task. The partial file is not merged."
            )
        elif path.name == "headline_measured_13208152_3.json":
            reason = "FAIL genome GCF_015290725.1. Already excluded by outcome."
        else:
            reason = "Present in headline_measured/ and not in the nine EXACT paths."
        excluded.append({"path": rel, "reason": reason})

    a_value = arithmetic_mean([row["a_g"] for row in included])
    c_value = arithmetic_mean([row["c_g"] for row in included])
    all_a = [repeat["a_g_r"] for row in included for repeat in row["repeats"]]
    all_c = [repeat["c_g_r"] for row in included for repeat in row["repeats"]]
    if len(all_a) != 27:
        raise SystemExit(f"expected 27 paired repeats, found {len(all_a)}")
    if abs(arithmetic_mean(all_a) - a_value) > 1e-12 or abs(arithmetic_mean(all_c) - c_value) > 1e-12:
        raise SystemExit("mean of genome means is not the mean of the 27 pairs")

    # Known-bad reductions. Recorded so a later edit cannot quietly adopt them.
    flagged = [row for row in included if row["cv_flag_A"] or row["cv_flag_B"]]
    unflagged = [row for row in included if row not in flagged]
    median_only_a = []
    median_only_c = []
    unpaired_a = []
    unpaired_c = []
    for row in included:
        walls = [repeat["tare_wall_s"] for repeat in row["repeats"]]
        chosen = row["repeats"][_median_index(walls)]
        median_only_a.append(chosen["a_g_r"])
        median_only_c.append(chosen["c_g_r"])
        stock_med = statistics_median([repeat["stock_wall_s"] for repeat in row["repeats"]])
        tare_med = statistics_median(walls)
        disc_med = statistics_median([repeat["discovery_s"] for repeat in row["repeats"]])
        unpaired_a.append(disc_med / (f_delta * stock_med))
        unpaired_c.append((tare_med - disc_med) / stock_med)
    dropped_a = arithmetic_mean([row["a_g"] for row in included if row["a_g"] != min(row["a_g"] for row in included)])
    if math.isclose(dropped_a, a_value):
        raise SystemExit("dropping a genome did not change a; the negative control is blind")

    by_speedup = sorted(included, key=lambda row: row["S_g"])
    phase_indexes = [0, len(by_speedup) // 2, len(by_speedup) - 1]
    phase_roles = ["lowest_S_g", "median_S_g", "highest_S_g"]
    phase_genomes = []
    for role, index in zip(phase_roles, phase_indexes):
        row = by_speedup[index]
        walls = [repeat["tare_wall_s"] for repeat in row["repeats"]]
        chosen = row["repeats"][_median_index(walls)]
        stages = stage_split(row["_paired"][chosen["repeat"] - 1]["tare_row"]["phases"], chosen["tare_wall_s"])
        phase_genomes.append({
            "role": role,
            "proteome": row["proteome"],
            "source_path": row["path"],
            "job_id": row["job_id"],
            "repeat": chosen["repeat"],
            "repeats_index": chosen["repeats_index"],
            "S_g": row["S_g"],
            "stock_median_s": statistics_median([repeat["stock_wall_s"] for repeat in row["repeats"]]),
            "tare_wall_s": chosen["tare_wall_s"],
            "stages_s": stages,
            "stage_sources": {
                "discovery": f"repeats.{chosen['repeats_index']}.phases.discovery_s",
                "replay": f"repeats.{chosen['repeats_index']}.phases.replay_s",
                "check": (
                    f"repeats.{chosen['repeats_index']}.phases.ic2_neighbor_s"
                    f" + ic2_random_20261031_s + ic2_random_20261032_s"
                    f" + ic2_random_20261033_s + verify_s"
                ),
                "other": f"repeats.{chosen['repeats_index']}.wall_s - (discovery + replay + check)",
            },
        })

    predictions = []
    for index, pair in enumerate(pairs):
        speedup = 1.0 / (a_value * pair["f_delta"] + c_value)
        predictions.append({
            "pair_index": index,
            "old_release": pair["old_release"],
            "new_release": pair["new_release"],
            "f_delta": pair["f_delta"],
            "f_delta_source": f"results/release_chain/pairs.json pairs.{index}.f_delta",
            "speedup": speedup,
            "formula": "1 / (a * f_delta + c) with the server a and c",
        })

    for row in included:
        row.pop("_paired", None)

    return {
        "system": "TARE",
        "equation": "T_TARE = a * f * T_stock + c * T_stock",
        "speedup_equation": "S = 1 / (a * f + c)",
        "formulas": {
            "f": (
                "f_delta of Pfam 38.1->38.2 in results/release_chain/pairs.json. "
                "Equals 4052/30134."
            ),
            "pairing": "B-arm repeat r is paired with A-arm repeat r (the alternating A B A B A B design).",
            "a_g_r": "phases.discovery_s / (f * A.wall_s)",
            "c_g_r": "(B.wall_s - phases.discovery_s) / A.wall_s",
            "a_g": "arithmetic mean of a_g_r over repeats 1, 2, 3",
            "c_g": "arithmetic mean of c_g_r over repeats 1, 2, 3",
            "a": "arithmetic mean of a_g over the 9 EXACT genomes",
            "c": "arithmetic mean of c_g over the 9 EXACT genomes",
            "mean": "sum of the values divided by the count, the same reduction as make_figures.fig_model",
            "identity": (
                "Every included genome has exactly 3 paired repeats, so the mean "
                "of a_g equals the arithmetic mean of all 27 a_g_r values. Same for c."
            ),
            "not_used": (
                "phases.total_s is not U. Medians are not used inside a or c. "
                "S_g = median(A.wall_s) / median(B.wall_s) is recorded and is not an input."
            ),
        },
        "inclusion_rule": (
            "The paper's headline set, as scored in results/exact_replay/headline_carc.json: "
            "tasks 0, 1, and 6-9 from array 13208152 and tasks 2, 4, and 5 from the "
            "8 h rerun 13227819. Include a genome only when both headline_carc.json "
            "and the task file say outcome EXACT. Arithmetic mean over those 9. "
            "CV flags stay in the mean. Do not drop a genome because its a_g is low. "
            "The FAIL genome, the pilot, and the three timed-out partial files are excluded."
        ),
        "f": f_delta,
        "f_pair_index": f_index,
        "f_numerator_denominator": {"changed_or_new": 4052, "z_new": 30134},
        "a": a_value,
        "c": c_value,
        "n_genomes": len(included),
        "n_paired_repeats": len(all_a),
        "one_over_c": 1.0 / c_value,
        "speedup_at_headline_f": 1.0 / (a_value * f_delta + c_value),
        "laptop_reference": laptop,
        "excluded": excluded,
        "genomes": included,
        "predictions": predictions,
        "phase_bars": {
            "rule": (
                "Lowest, median, and highest S_g among the 9. The bar is the B "
                "repeat whose wall_s is the middle of the three sorted B walls. "
                "The stock tick is the median of the three A walls."
            ),
            "genomes": phase_genomes,
        },
        "sensitivity_not_used": {
            "median_wall_pair_only": {
                "a": arithmetic_mean(median_only_a),
                "c": arithmetic_mean(median_only_c),
                "why_not": "Uses one of the three repeats. The definition averages every paired repeat.",
            },
            "unpaired_ratio_of_medians": {
                "a": arithmetic_mean(unpaired_a),
                "c": arithmetic_mean(unpaired_c),
                "why_not": (
                    "median(discovery) / (f * median(stock)) is not the per-repeat "
                    "ratio followed by the arithmetic mean."
                ),
            },
            "drop_cv_flagged_arms": {
                "n": len(unflagged),
                "n_flagged_excluded": len(flagged),
                "a": arithmetic_mean([row["a_g"] for row in unflagged]),
                "c": arithmetic_mean([row["c_g"] for row in unflagged]),
                "why_not": "A CV flag is not a drop rule. These genomes stay in a and c.",
            },
            "drop_lowest_a_g": {
                "a": dropped_a,
                "why_not": "Dropping a genome to move the fit is the negative control. It is not the result.",
            },
        },
        "controls": {
            "laptop_rounding_matches_published": laptop["rounding_matches_published"],
            "n_exact": len(included),
            "refused_genome_excluded": "GCF_015290725.1",
            "cv_flagged_genomes_kept": [row["proteome"] for row in flagged],
            "mean_of_27_matches_mean_of_genomes": True,
        },
        "provenance": {
            "analysis": "reduction of committed JSON; no new timing run and no new seed",
            "git_head": git_head(),
            "frozen_acts_commit": sorted({row["acts_commit"] for row in included}),
            "headline_score": "results/exact_replay/headline_carc.json",
            "host": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "argv": sys.argv,
            "cpu_model_of_measurements": sorted({row["cpu_model"] for row in included}),
        },
    }


def statistics_median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        raise ValueError("empty median")
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def main() -> None:
    payload = fit()
    DEFAULT_OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"wrote {DEFAULT_OUT.relative_to(PIPELINE)} "
        f"a={payload['a']:.6f} c={payload['c']:.6f} "
        f"1/c={payload['one_over_c']:.4f} "
        f"S(f)={payload['speedup_at_headline_f']:.4f}"
    )


if __name__ == "__main__":
    main()
