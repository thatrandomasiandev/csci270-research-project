#!/usr/bin/env python3
"""Score diverse-genome CARC JSON. Pilot lines are not added to N."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PAPER_N = 96902
POOLED_FLOOR = 50_000
PILOT = (
    "GCF_052510705.1",
    "GCF_000226115.1",
    "GCA_003676205.1",
)


def load_genomes(directory: Path) -> list[dict]:
    rows = []
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(".partial"):
            continue
        payload = json.loads(path.read_text())
        genome = payload.get("genome")
        if isinstance(genome, dict) and genome.get("accession"):
            genome["_source"] = path.name
            genome["_git_head"] = payload.get("git_head")
            genome["_host"] = payload.get("host")
            rows.append(genome)
    return rows


def pilot_gate(rows: list[dict]) -> dict:
    by_acc = {row.get("accession"): row for row in rows if row.get("cohort") == "pilot" or row.get("role") == "pilot"}
    missing = [acc for acc in PILOT if acc not in by_acc]
    problems = []
    if missing:
        problems.append("missing " + ", ".join(missing))
    for acc in PILOT:
        row = by_acc.get(acc)
        if row is None:
            continue
        identity = ((row.get("stock_repeat") or {}).get("compare") or {}).get("byte_equal")
        if row.get("outcome") == "indeterminism" or identity is not True:
            problems.append(f"{acc} stock pair is not byte-identical")
        if row.get("decision") != "SHIP" or not (row.get("compare") or {}).get("byte_equal"):
            problems.append(f"{acc} TARE update is not a byte-identical SHIP")
        control = (row.get("negative") or {}).get("control")
        if control != "pass":
            problems.append(f"{acc} negative control is {control}")
        if row.get("claim_class") == "UNSAFE" or row.get("outcome") == "UNSAFE":
            problems.append(f"{acc} is UNSAFE")
    return {"holds": not problems, "problems": problems, "present": sorted(by_acc)}


def summarize(rows: list[dict], cohort: str) -> dict:
    groups: dict[str, dict] = {}
    unsafe = []
    needless = []
    passed_lines = 0
    kept = [
        row for row in rows
        if row.get("cohort") == cohort or row.get("role") == cohort
    ]
    for row in kept:
        group = str(row.get("group") or "?")
        bucket = groups.setdefault(group, {
            "genomes": 0,
            "pass": 0,
            "UNSAFE": 0,
            "needless_refusal": 0,
            "refusal": 0,
            "INCONCLUSIVE": 0,
            "indeterminism": 0,
            "tbl_lines": 0,
            "dom_lines": 0,
        })
        bucket["genomes"] += 1
        kind = str(row.get("outcome") or row.get("claim_class") or "INCONCLUSIVE")
        if kind not in bucket:
            kind = "INCONCLUSIVE"
        bucket[kind] += 1
        bucket["tbl_lines"] += int(row.get("stock_tbl_lines") or 0)
        bucket["dom_lines"] += int(row.get("stock_dom_lines") or 0)
        if kind == "UNSAFE":
            unsafe.append(row.get("accession"))
        if kind == "needless_refusal":
            needless.append({
                "accession": row.get("accession"),
                "decision": row.get("decision"),
            })
        if cohort == "measured" and kind == "pass":
            passed_lines += int(row.get("stock_tbl_lines") or 0) + int(row.get("stock_dom_lines") or 0)
    summary: dict = {
        "cohort": cohort,
        "n_genomes": len(kept),
        "by_group": groups,
        "unsafe": unsafe,
        "needless_refusals": needless,
    }
    if cohort == "measured":
        summary["passed_lines_L"] = passed_lines
        if unsafe:
            summary["pooled"] = "UNSAFE"
            summary["p_up"] = None
        else:
            n_new = PAPER_N + passed_lines
            summary["N_new"] = n_new
            summary["p_up"] = 1.0 - (0.05 ** (1.0 / n_new))
            summary["pooled"] = "pass" if passed_lines >= POOLED_FLOOR else "INCONCLUSIVE"
    return summary


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: diverse_genomes_score.py <results-dir> <pilot|measured>", file=sys.stderr)
        return 2
    directory = Path(sys.argv[1])
    cohort = sys.argv[2]
    rows = load_genomes(directory)
    if cohort == "pilot":
        report = pilot_gate(rows)
    elif cohort == "measured":
        report = summarize(rows, "measured")
    else:
        print("cohort must be pilot or measured", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    if cohort == "pilot" and not report["holds"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
