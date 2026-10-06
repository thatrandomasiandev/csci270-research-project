#!/usr/bin/env python3
"""T1 and T2 for the pre-registered reference fitter.

Uses the historical R2p / R3c / R2n splits (Random.shuffle, seeds 20261003
and 20261004). It does not re-draw those halves with the Fisher–Yates probe.
Regenerates the work directory with scripts/reference_kill_tests.py when the
tables are absent, and does not rewrite the committed kill-test JSON.

Work files stay under /tmp. Result JSON is results/reference_fitter_t1.json
and results/reference_fitter_t2.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import reference_kill_tests as kill  # noqa: E402

from acts.provenance import provenance  # noqa: E402
from acts.reference_fit import (  # noqa: E402
    ENTRY_COUNT,
    PER_KEY,
    TOTAL_LENGTH,
    _family,
    _residual_summary,
    disambiguating_indices,
    fit_observations,
    resolve_ties,
)
from acts.reference_formats import alias_map, parse_reference, read_records  # noqa: E402

WORK = Path("/tmp/acts_reference_fitter")
PROTOCOL = "pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md"
EVALUE = {
    "tblout": (4, 7),
    "domtblout": (6, 11, 12),
}


def log(msg: str) -> None:
    print(msg, flush=True)


def parts_from_files(full: Path, half1: Path) -> tuple[list, list[int], list[int]]:
    entries = parse_reference(full)
    in_first = {entry.content_hash for entry in parse_reference(half1)}
    part1 = [i for i, entry in enumerate(entries) if entry.content_hash in in_first]
    part2 = [i for i, entry in enumerate(entries) if entry.content_hash not in in_first]
    if not part1 or not part2 or len(part1) + len(part2) != len(entries):
        raise SystemExit(f"historical halves do not partition {full}")
    return entries, part1, part2


def read_table(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"missing table {path}")
    return path.read_text()


def scan(entries, fasta: Path, dest: Path, *, cut_ga: bool, domtbl: Path | None) -> None:
    if dest.is_file() and (domtbl is None or domtbl.is_file()):
        log(f"reuse {dest.name}")
        return
    hmm = dest.with_suffix(".hmm")
    hmm.write_text("".join(entry.raw for entry in entries))
    log(f"press+scan {dest.name} entries={len(entries)} cut_ga={cut_ga}")
    t0 = time.perf_counter()
    subprocess.run(["hmmpress", "-f", str(hmm)], check=True, capture_output=True, text=True)
    cmd = ["hmmscan", "--cpu", "4", "--noali"]
    if cut_ga:
        cmd.append("--cut_ga")
    cmd += ["--tblout", str(dest)]
    if domtbl is not None:
        cmd += ["--domtblout", str(domtbl)]
    cmd += [str(hmm), str(fasta)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    log(f"  done in {time.perf_counter() - t0:.1f}s")


def fit_case(work: Path, *, dom: bool, cut_ga: bool) -> dict:
    entries, part1, part2 = parts_from_files(work / "R.hmm", work / "R1.hmm")
    records = read_records(work / "q.faa")
    names = ["tblout"] + (["domtblout"] if dom else [])
    whole = {"tblout": read_table(work / "R.tbl")}
    parts = [
        {"tblout": read_table(work / "R1.tbl")},
        {"tblout": read_table(work / "R2.tbl")},
    ]
    if dom:
        whole["domtblout"] = read_table(work / "R.domtbl")
        parts[0]["domtblout"] = read_table(work / "R1.domtbl")
        parts[1]["domtblout"] = read_table(work / "R2.domtbl")
    primary = fit_observations(
        entries_n=len(entries),
        lengths=[entry.length for entry in entries],
        part_index_lists=[part1, part2],
        record_ids={rec.key for rec in records},
        alias_to_index=alias_map(entries),
        whole_tables=whole,
        part_tables=parts,
    )
    primary_residuals = both_candidate_residuals(primary)
    result = primary
    if result.decision == "TIE":
        split = disambiguating_indices(
            [entry.length for entry in entries],
            [entry.content_hash for entry in entries],
        )
        if split is None:
            result.decision = "REFUSE"
            result.reason = "tie stands; the disambiguating partition is empty"
        else:
            left, right = split
            for label, indices in (("L", left), ("S", right)):
                subset = [entries[i] for i in sorted(indices)]
                scan(
                    subset,
                    work / "q.faa",
                    work / f"{label}.tbl",
                    cut_ga=cut_ga,
                    domtbl=(work / f"{label}.domtbl") if dom else None,
                )
            tie_tables = [
                {"tblout": read_table(work / "L.tbl")},
                {"tblout": read_table(work / "S.tbl")},
            ]
            if dom:
                tie_tables[0]["domtblout"] = read_table(work / "L.domtbl")
                tie_tables[1]["domtblout"] = read_table(work / "S.domtbl")
            result = resolve_ties(
                result,
                entries_n=len(entries),
                lengths=[entry.length for entry in entries],
                tie_parts=[left, right],
                record_ids={rec.key for rec in records},
                alias_to_index=alias_map(entries),
                whole_tables=whole,
                tie_tables=tie_tables,
            )
    payload = result.as_dict()
    payload["n_entries"] = len(entries)
    payload["n_records"] = len(records)
    payload["half_sizes"] = [len(part1), len(part2)]
    payload["tables_present"] = names
    payload["primary_residuals"] = primary_residuals
    return payload


def both_candidate_residuals(result) -> dict:
    """Primary-partition residuals for entry count and total length on E-value columns.

    The tie-break residual is stored on the column when a tie actually ran.
    Columns the primary split already separated have no tie-break block; this
    records both candidates there too.
    """
    bundles = {bundle.name: bundle for bundle in getattr(result, "_bundles", [])}
    phi_for = getattr(result, "_phi_for", None)
    names = getattr(result, "_names", [])
    if phi_for is None:
        return {}
    wanted = {ENTRY_COUNT, TOTAL_LENGTH, PER_KEY}
    out: dict = {}
    for table, indices in EVALUE.items():
        bundle = bundles.get(table)
        if bundle is None or not bundle.aligned:
            continue
        width = min(len(row.whole) for row in bundle.aligned)
        out[table] = {}
        for index in indices:
            if index >= width:
                continue
            out[table][str(index)] = {}
            for label, kind, count_table in _family(names):
                if kind not in wanted:
                    continue
                if kind == PER_KEY and count_table != "tblout":
                    continue
                phi_of = phi_for(kind, count_table)
                out[table][str(index)][label] = _residual_summary(bundle.aligned, index, phi_of)
    return out


def column_map(fit: dict) -> dict[str, dict[int, dict]]:
    out: dict[str, dict[int, dict]] = {}
    for table in fit.get("tables") or []:
        out[table["name"]] = {col["index"]: col for col in table["columns"]}
    return out


def evalue_residuals(fit: dict) -> dict:
    """Tie-break residual for every candidate on every E-value column."""
    report = {}
    columns = column_map(fit)
    for table, indices in EVALUE.items():
        if table not in columns:
            continue
        report[table] = {}
        for index in indices:
            col = columns[table].get(index)
            if col is None:
                report[table][str(index)] = None
                continue
            report[table][str(index)] = {
                "member": col.get("member"),
                "count_table": col.get("count_table"),
                "primary_fits": col.get("primary_fits"),
                "tie_break": col.get("tie_break"),
            }
    return report


def expect_numeric(fit: dict, table: str, index: int, member: str, count_table: str | None) -> str | None:
    col = column_map(fit).get(table, {}).get(index)
    if col is None:
        return f"{table} column {index} missing"
    if col.get("role") != "numeric":
        return f"{table} column {index} is {col.get('role')}"
    if col.get("member") != member:
        return f"{table} column {index} assigned {col.get('member')} not {member}"
    if member == "per_key_row_count" and col.get("count_table") != count_table:
        return f"{table} column {index} counts {col.get('count_table')} not {count_table}"
    return None


def other_numeric_are_identity(fit: dict, expected: dict[str, set[int]]) -> list[str]:
    bad = []
    for table in fit.get("tables") or []:
        special = expected.get(table["name"], set())
        for col in table["columns"]:
            if col.get("role") != "numeric" or col["index"] in special:
                continue
            if col.get("member") != "identity":
                bad.append(
                    f"{table['name']} column {col['index']} assigned {col.get('member')}"
                )
    return bad


def judge_t1(r2p: dict, r3c: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for label, fit in (("r2p", r2p), ("r3c", r3c)):
        if fit.get("decision") != "SHIP":
            reasons.append(f"{label} {fit.get('decision')}: {fit.get('reason')}")
    if reasons:
        return False, reasons
    for index in (4, 7):
        for label, fit in (("r2p", r2p), ("r3c", r3c)):
            err = expect_numeric(fit, "tblout", index, "entry_count", None)
            if err:
                reasons.append(f"{label} {err}")
    for index in (6, 12):
        err = expect_numeric(r3c, "domtblout", index, "entry_count", None)
        if err:
            reasons.append(err)
    err = expect_numeric(r3c, "domtblout", 11, "per_key_row_count", "tblout")
    if err:
        reasons.append(err)
    reasons.extend(
        "r2p " + item
        for item in other_numeric_are_identity(r2p, {"tblout": {4, 7}})
    )
    reasons.extend(
        other_numeric_are_identity(
            r3c, {"tblout": {4, 7}, "domtblout": {6, 11, 12}}
        )
    )
    return not reasons, reasons


def tool_banner(binary: str) -> str:
    proc = subprocess.run([binary, "-h"], capture_output=True, text=True)
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        if "HMMER" in line:
            return line.lstrip("# ").strip()
    return ""


def provenance_record() -> dict:
    rec = provenance()
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    rec["git_status_short"] = status.stdout.splitlines()
    rec["tools"] = {"hmmscan": tool_banner("hmmscan"), "hmmpress": tool_banner("hmmpress")}
    return rec


def amdahl() -> dict:
    """PROJECTED from the pre-registered break-even model. No new fit."""
    screen = json.loads((ROOT / "results" / "headline_screen.json").read_text())
    block = next(row for row in screen["modes"] if row.get("mode") == "hmmscan")
    a = block["a_s"]
    b = block["b_s_per_record"]
    n = block["N"]
    r1 = json.loads((ROOT / "results" / "reference_kill_r1.json").read_text())
    c = (r1["z_new"] - r1["unchanged_strict"]) / r1["z_new"]
    bn = b * n
    return {
        "label": "PROJECTED",
        "dominant_term": "b*n_changed",
        "formula": "(a + b*n) / (a + c*b*n)",
        "assumptions": (
            "Pre-registered break-even model: T_stock = a + b*n, "
            "T_inc = a + c*b*n, startup a does not shrink, b scales with "
            "the fraction of entries searched, merge ignored. "
            "a and b are MEASURED in results/headline_screen.json; "
            "c is MEASURED in results/reference_kill_r1.json."
        ),
        "a_s": a,
        "b_s_per_record": b,
        "n": n,
        "c_r1": c,
        "speedup_at_c_r1": (a + bn) / (a + c * bn),
        "sources": [
            "results/headline_screen.json",
            "results/reference_kill_r1.json",
            "pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md",
        ],
    }


def ensure(work: Path, kind: str) -> None:
    work.mkdir(parents=True, exist_ok=True)
    marker = work / ("R.domtbl" if kind == "r3c" else "R.tbl")
    if marker.is_file() and (work / "R.hmm").is_file() and (work / "q.faa").is_file():
        log(f"{kind}: reuse {work}")
        return
    log(f"{kind}: regenerating with historical seeds in {work}")
    t0 = time.perf_counter()
    if kind == "r2p":
        kill.r2(work, powered=True, cut_ga=True, write_json=False)
    elif kind == "r2n":
        kill.r2(work, powered=True, cut_ga=False, write_json=False)
    elif kind == "r3c":
        kill.r3c(work, write_json=False)
    else:
        raise SystemExit(kind)
    log(f"{kind}: regeneration done in {time.perf_counter() - t0:.1f}s")


def main() -> int:
    t1_r2p = WORK / "r2p"
    t1_r3c = WORK / "r3c"
    t2_r2n = WORK / "r2n"
    ensure(t1_r2p, "r2p")
    ensure(t1_r3c, "r3c")
    log("fitting r2p")
    r2p = fit_case(t1_r2p, dom=False, cut_ga=True)
    log(f"r2p decision {r2p['decision']}: {r2p['reason']}")
    log("fitting r3c")
    r3c = fit_case(t1_r3c, dom=True, cut_ga=True)
    log(f"r3c decision {r3c['decision']}: {r3c['reason']}")
    passed, reasons = judge_t1(r2p, r3c)
    t1 = {
        "protocol": PROTOCOL,
        "test": "T1",
        "pass": passed,
        "reasons": reasons,
        "amdahl": amdahl(),
        "tie_break_residuals": {"r2p": evalue_residuals(r2p), "r3c": evalue_residuals(r3c)},
        "r2p": r2p,
        "r3c": r3c,
        "provenance": provenance_record(),
    }
    dest1 = ROOT / "results" / "reference_fitter_t1.json"
    dest1.write_text(json.dumps(t1, indent=2) + "\n")
    log(f"T1 {'PASS' if passed else 'FAIL'} -> {dest1}")

    ensure(t2_r2n, "r2n")
    log("fitting r2n")
    r2n = fit_case(t2_r2n, dom=False, cut_ga=False)
    t2_pass = r2n.get("decision") == "REFUSE"
    t2 = {
        "protocol": PROTOCOL,
        "test": "T2",
        "pass": t2_pass,
        "reasons": [] if t2_pass else [f"expected REFUSE, got {r2n.get('decision')}"],
        "r2n": r2n,
        "provenance": provenance_record(),
    }
    dest2 = ROOT / "results" / "reference_fitter_t2.json"
    dest2.write_text(json.dumps(t2, indent=2) + "\n")
    log(f"T2 {'PASS' if t2_pass else 'FAIL'} -> {dest2} ({r2n.get('reason')})")
    return 0 if passed and t2_pass else 1


if __name__ == "__main__":
    sys.exit(main())
