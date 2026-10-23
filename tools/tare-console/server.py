#!/usr/bin/env python3
"""TARE console backend.

Reads committed result files under pipeline/results (the research board) and
serves the run console: projects, preflight, runs, verification and exports
(engine.py). Runs call `python3 -m acts run` on this machine.

  python3 tools/tare-console/server.py
  python3 tools/tare-console/server.py --check
  python3 tools/tare-console/server.py --port 8768

API
  GET /api/health
  GET /api/board              full payload for the desk
  GET /api/cases             [{id, tool, verdict, …}] summary list
  GET /api/cases/<id>        one case (hmmer | infernal | diamond | blast)
  GET /api/exactness         exactness totals only

Static files under tools/tare-console/static/ are served for the UI you build.
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import engine

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
RESULTS = REPO / "pipeline" / "results"
STATIC = ROOT / "static"
HOST = "127.0.0.1"
PORT = 8768

CASE_ORDER = ("hmmer", "infernal", "diamond", "blast")

EXACTNESS_LABELS = {
    "hmmer_replay_300": "HMMER replay, 300 proteins",
    "hmmer_replay_3_genomes": "HMMER replay, 3 genomes",
    "hmmer_tool_2_laptop": "HMMER, 2 laptop genomes",
    "hmmer_tool_server_genomes": "HMMER, server genomes",
    "hmmer_tool_diverse_genomes": "HMMER, diverse genomes",
    "infernal_replay_10": "Infernal replay, 10 genomes",
    "infernal_tool_family_removal": "Infernal, one family removal",
    "infernal_tool_10_genomes": "Infernal, 10 genomes",
}


def _load(rel: str) -> Any:
    path = RESULTS / rel
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _rel(path: str) -> str:
    return path if path.startswith("pipeline/") else f"pipeline/results/{path}"


def _error_case(case_id: str, tool: str, exc: BaseException) -> dict[str, Any]:
    return {
        "id": case_id,
        "tool": tool,
        "verdict": "error",
        "error": f"{type(exc).__name__}: {exc}",
    }


def _hmmer() -> dict[str, Any]:
    headline = _load("exact_replay/headline_carc.json")
    kill = _load("reference_kill_r1.json")
    genomes = headline["genomes"]
    exact = [g for g in genomes if g.get("outcome") == "EXACT" and g.get("S_g") is not None]
    refused = [g for g in genomes if g.get("outcome") != "EXACT"]

    kept = int(kill["unchanged_strict"])
    shared = int(kill["shared"])
    added = int(kill["added"])
    removed = int(kill["removed"])
    z_new = int(kill["z_new"])
    edited = shared - kept
    if kept + edited + added != z_new:
        raise ValueError(f"release parts {kept}+{edited}+{added} != z_new {z_new}")

    command = None
    cpu_model = None
    repeats = None
    for genome in exact:
        measured = _load(genome["path"].removeprefix("results/"))
        command = measured.get("argv_acts")
        cpu_model = measured.get("cpu_model")
        repeats = (measured.get("cv") or {}).get("n")
        break

    ci = headline["bootstrap_ci95"]
    rows = []
    for genome in genomes:
        rows.append(
            {
                "id": genome["proteome"],
                "proteome": genome["proteome"],
                "outcome": genome.get("outcome"),
                "shipped": genome.get("outcome") == "EXACT",
                "in_headline": genome.get("outcome") == "EXACT" and genome.get("S_g") is not None,
                "stock_median_s": genome.get("stock_median_s"),
                "tare_median_s": genome.get("tare_median_s"),
                "speedup": genome.get("S_g"),
                "predicted_speedup": genome.get("S_pred"),
                "cv_stock": genome.get("cv_A"),
                "cv_tare": genome.get("cv_B"),
                "flags": list(genome.get("flags") or []),
                "fail_reasons": list(genome.get("fail_reasons") or []),
                "stopped": genome.get("stopped"),
                "job_id": genome.get("job_id"),
                "source": _rel(genome["path"]),
            }
        )

    limits = []
    if refused:
        first = refused[0]
        limits.append(
            {
                "kind": "excluded_from_median",
                "proteomes": [g["proteome"] for g in refused],
                "stopped": first.get("stopped"),
                "fail_reasons": list(first.get("fail_reasons") or []),
            }
        )
    flagged = [g for g in exact if g.get("flags")]
    if flagged:
        limits.append(
            {
                "kind": "cv_flag",
                "n_flagged": len(flagged),
                "n_shipped": len(exact),
                "threshold": 0.05,
                "max_cv_stock": max((g.get("cv_A") or 0.0) for g in exact),
                "proteomes": [g["proteome"] for g in flagged],
            }
        )

    return {
        "id": "hmmer",
        "tool": "HMMER",
        "program": "hmmscan",
        "release": {
            "old": kill["old_release"],
            "new": kill["new_release"],
            "pair": f"{kill['old_release']} → {kill['new_release']}",
        },
        "verdict": "ship",
        "headline": {
            "median_speedup": float(headline["headline_median"]),
            "geometric_mean_speedup": float(headline["geometric_mean"]),
            "predicted_speedup": float(headline["S_pred"]),
            "ci95": {
                "low": float(ci["low"]),
                "high": float(ci["high"]),
                "resamples": int(ci["resamples"]),
                "seed": ci.get("seed"),
            },
            "range": [float(headline["range"][0]), float(headline["range"][1])],
            "n_speedups": int(headline["n_speedups"]),
            "n_genomes": len(genomes),
            "n_exact": len(exact),
            "n_refused": len(refused),
            "max_prediction_error": float(headline["max_prediction_error"]),
            "repeats": repeats,
            "cpu_model": cpu_model,
            "walls_indicative": False,
        },
        "release_diff": {
            "z_old": int(kill["z_old"]),
            "z_new": z_new,
            "unchanged": kept,
            "edited": edited,
            "added": added,
            "removed": removed,
            "rerun": edited + added,
            "rerun_fraction": (edited + added) / z_new,
            "unchanged_fraction": kept / z_new,
        },
        "cost_model": {
            "a": float(headline["a"]),
            "c": float(headline["c"]),
            "f": float(headline["f"]),
            "S_pred": float(headline["S_pred"]),
            "break_even_n_median": float(headline["break_even_n_median"]),
            "first_run_overhead_median": float(headline["first_run_overhead_median"]),
        },
        "command": command,
        "genomes": rows,
        "limits": limits,
        "sources": [
            "pipeline/results/exact_replay/headline_carc.json",
            "pipeline/results/reference_kill_r1.json",
            "pipeline/results/exact_replay/headline_measured/",
        ],
    }


def _infernal_arm(summary: dict[str, Any], genomes: dict[str, Any], order: list[str], key: str) -> dict[str, Any]:
    block = summary[key]
    outcomes = block["outcomes"]
    ci = block["bootstrap_median"]
    audits: set[str] = set()
    pads: set[str] = set()
    whys: set[str] = set()
    rows = []
    for accession in order:
        arm = genomes[accession][key]
        for run in arm.get("runs") or []:
            tare = run.get("tare") or {}
            if tare.get("audit"):
                audits.add(str(tare["audit"]))
            if tare.get("random_pads"):
                pads.add(str(tare["random_pads"]))
            if tare.get("why"):
                whys.add(str(tare["why"]))
        outcome = outcomes.get(accession, arm.get("outcome"))
        rows.append(
            {
                "id": accession,
                "genome": accession,
                "outcome": outcome,
                "shipped": outcome == "EXACT",
                "stock_median_s": arm.get("median_stock_s"),
                "tare_median_s": arm.get("median_tare_s"),
                "speedup": arm.get("s_g"),
                "cv_stock": arm.get("cv_stock"),
                "cv_tare": arm.get("cv_tare"),
                "body_lines": arm.get("body_lines"),
                "residues": genomes[accession].get("residues"),
                "z": genomes[accession].get("z"),
            }
        )
    return {
        "id": key,
        "label": "No clan" if key == "noclan" else "Clan",
        "median_speedup": float(block["median_s_g"]),
        "geometric_mean_speedup": float(block["geometric_mean_s_g"]),
        "predicted_speedup": float(block["predicted_s"]),
        "ci95": {
            "low": float(ci["p2.5"]),
            "high": float(ci["p97.5"]),
            "resamples": int(ci["draws"]),
            "seed": ci.get("seed"),
        },
        "range": [float(block["range_s_g"][0]), float(block["range_s_g"][1])],
        "n_finished": int(block["genomes_finished"]),
        "body_lines": int(block["body_lines"]),
        "max_cv": float(block["max_cv"]),
        "max_relative_error": float(block["max_relative_error"]),
        "cost_model": {
            "a": float(block["a"]),
            "c": float(block["c"]),
            "f": float(block["f"]),
        },
        "audits": sorted(audits),
        "random_pads": sorted(pads),
        "reasons": sorted(whys),
        "genomes": rows,
    }


def _infernal() -> dict[str, Any]:
    measured = _load("infernal/measured2.json")
    if measured.get("walls_indicative") is not True:
        raise ValueError("expected walls_indicative true")
    summary = measured["summary"]
    variants = {
        key: _infernal_arm(summary, measured["genomes"], measured["order"], key)
        for key in ("noclan", "clan")
    }
    noclan = variants["noclan"]
    fraction = float(noclan["cost_model"]["f"])

    limits = [
        {
            "kind": "walls_indicative",
            "walls_indicative": True,
            "note": "Headline dedicated-server timing is the HMMER case.",
        }
    ]
    if noclan["audits"] or noclan["random_pads"]:
        limits.append(
            {
                "kind": "checks_skipped",
                "audits": noclan["audits"],
                "random_pads": noclan["random_pads"],
            }
        )

    return {
        "id": "infernal",
        "tool": "Infernal",
        "program": "cmscan",
        "release": {
            "old": "Rfam 15.0",
            "new": "Rfam 15.1",
            "pair": "Rfam 15.0 → 15.1",
            "pair_source": "pipeline/docs/INFERNAL_PROTOCOL.md",
        },
        "verdict": "ship",
        "headline": {
            "median_speedup": noclan["median_speedup"],
            "geometric_mean_speedup": noclan["geometric_mean_speedup"],
            "predicted_speedup": noclan["predicted_speedup"],
            "ci95": noclan["ci95"],
            "range": noclan["range"],
            "n_speedups": noclan["n_finished"],
            "n_genomes": len(measured["order"]),
            "n_exact": noclan["n_finished"],
            "n_refused": 0,
            "walls_indicative": True,
            "default_variant": "noclan",
        },
        "release_diff": {
            "rerun_fraction": fraction,
            "family_counts_available": False,
        },
        "variants": variants,
        "command": None,
        "genomes": noclan["genomes"],
        "limits": limits,
        "sources": [
            "pipeline/results/infernal/measured2.json",
            "pipeline/docs/INFERNAL_PROTOCOL.md",
        ],
    }


def _diamond() -> dict[str, Any]:
    dx = _load("reference_diamond/dx.json")
    dx2 = _load("reference_diamond/dx2.json")
    dx3 = _load("reference_diamond/dx3.json")
    idiom = dx["dx_i"]["idiamond"]
    pin = dx["dx_k"]
    e1 = dx2["dx2_e1"]
    judgment = dx3["judgment"]
    klass = dx3["classification"]
    version = str(dx["diamond_version"]).removeprefix("diamond version ").strip()

    checks = [
        {
            "id": "contract",
            "title": "Contract",
            "verdict": str(pin.get("verdict")),
            "expected_pin": pin.get("expected_pin"),
            "found_pin": pin.get("pin"),
            "reason": pin.get("reason"),
            "exact_mode": dx.get("exact_mode"),
            "source": "pipeline/results/reference_diamond/dx.json",
        },
        {
            "id": "iseqsearch",
            "title": "iSeqSearch comparison",
            "shared_rows": int(idiom["shared_rows"]),
            "shared_byte_identical": int(idiom["shared_byte_identical"]),
            "shared_byte_fraction": float(idiom["shared_byte_fraction"]),
            "row_extra": int(idiom["row_extra"]),
            "evalue_kendall_tau": float(idiom["evalue_kendall_tau"]),
            "evalue_pearson": float(idiom["evalue_pearson"]),
            "source": "pipeline/results/reference_diamond/dx.json",
        },
        {
            "id": "declared_pin",
            "title": "Declared --dbsize pin",
            "outcome": e1.get("outcome"),
            "stock_rows": int(e1["classification"]["stock_rows"]),
            "row_missing": int(e1["classification"]["row_missing"]),
            "bodies_equal": bool(e1.get("bodies_equal")),
            "ic_pass": bool(e1.get("ic_pass")),
            "source": "pipeline/results/reference_diamond/dx2.json",
        },
        {
            "id": "neighbor_pad",
            "title": "Neighbor-pad check",
            "outcome": judgment.get("outcome"),
            "cases": int(judgment["cases"]),
            "stock_rows": int(klass["stock_rows"]),
            "row_missing": int(klass["row_missing"]),
            "row_extra": int(klass["row_extra"]),
            "ic_pass": bool(judgment.get("ic_pass")),
            "true_refusal": bool(judgment.get("true_refusal")),
            "pin": dx3.get("pin"),
            "source": "pipeline/results/reference_diamond/dx3.json",
        },
    ]

    return {
        "id": "diamond",
        "tool": "DIAMOND",
        "program": "diamond",
        "version": version,
        "release": {
            "old": "Swiss-Prot (old)",
            "new": "Swiss-Prot (new)",
            "pair": "Swiss-Prot",
            "old_entries": int(dx["old_entries"]),
            "new_entries": int(dx["new_entries"]),
            "old_letters": int(dx["old_letters"]),
            "new_letters": int(dx["new_letters"]),
        },
        "verdict": "refuse",
        "headline": {
            "refuse_lines": int(judgment["cases"]),
            "stock_rows": int(klass["stock_rows"]),
            "outcome": judgment.get("outcome"),
        },
        "checks": checks,
        "command": None,
        "genomes": [],
        "limits": [
            {
                "kind": "blind_certificate",
                "dx2_row_missing": int(e1["classification"]["row_missing"]),
                "dx2_ic_pass": bool(e1.get("ic_pass")),
                "refusing_check": "neighbor_pad",
            }
        ],
        "sources": [
            "pipeline/results/reference_diamond/dx.json",
            "pipeline/results/reference_diamond/dx2.json",
            "pipeline/results/reference_diamond/dx3.json",
        ],
    }


def _blast() -> dict[str, Any]:
    boundary = _load("reference_boundary_blast.json")
    pilot = _load("blast_diagnosis/pin_pilot.json")
    positive = pilot["controls"]["positive"]
    negative = pilot["controls"]["negative"]
    if positive["vs_stock"]["byte_identical"] is not True:
        raise ValueError("positive control was not byte-identical")
    if negative["vs_stock"]["missing"] != 780 or negative["dropped"] != 748:
        raise ValueError("negative-control counts moved")
    whys = {arm.get("why") for arm in pilot["cli"].values()}
    if whys != {"duplicate rows have no row-index column"}:
        raise ValueError(f"unexpected BLAST refuse reasons: {whys}")

    version = "2.14.1"
    for token in pilot["stock_vs_stock"]["argv"]:
        if "blast-plus-" in token:
            version = token.split("blast-plus-", 1)[1].split("-", 1)[0]
            break

    checks = [
        {
            "id": "boundary_fit",
            "title": "Earlier fit",
            "decision": boundary["decision"],
            "reason": boundary["reason"],
            "source": "pipeline/results/reference_boundary_blast.json",
        },
        {
            "id": "size_pin",
            "title": "Size pin",
            "pin": pilot["pin"],
            "dbsize": int(pilot["controls"]["dbsize"]),
            "n_lines": int(positive["n_lines"]),
            "byte_identical": True,
            "source": "pipeline/results/blast_diagnosis/pin_pilot.json",
        },
        {
            "id": "drop_control",
            "title": "Drop control",
            "dropped_subjects": int(negative["dropped"]),
            "missing_rows": int(negative["vs_stock"]["missing"]),
            "extra_rows": int(negative["vs_stock"]["extra"]),
            "pass": bool(negative.get("pass")),
            "source": "pipeline/results/blast_diagnosis/pin_pilot.json",
        },
        {
            "id": "shipped_command",
            "title": "Shipped command",
            "outcome": pilot["outcome"],
            "cli": {
                name: {"decision": arm.get("decision"), "why": arm.get("why")}
                for name, arm in pilot["cli"].items()
            },
            "source": "pipeline/results/blast_diagnosis/pin_pilot.json",
        },
    ]

    return {
        "id": "blast",
        "tool": "BLAST+",
        "program": "blastp",
        "version": version,
        "release": {
            "old": "Swiss-Prot 2026_01",
            "new": "Swiss-Prot 2026_03",
            "pair": "Swiss-Prot 2026_01 → 2026_03",
        },
        "verdict": "refuse",
        "headline": {
            "pin_matched_lines": int(positive["n_lines"]),
            "outcome": pilot["outcome"],
            "refuse_reason": "duplicate rows have no row-index column",
        },
        "checks": checks,
        "command": None,
        "genomes": [],
        "limits": [
            {
                "kind": "pin_not_ship",
                "pin_matched_lines": int(positive["n_lines"]),
                "note": "Matching pin is a control; the shipped command refuses.",
            }
        ],
        "sources": [
            "pipeline/results/blast_diagnosis/pin_pilot.json",
            "pipeline/results/reference_boundary_blast.json",
        ],
    }


def _exactness() -> dict[str, Any]:
    exact = _load("exact_replay/exactness_totals.json")
    rows = exact["rows"]
    total = int(exact["total_lines"])
    if sum(int(v) for v in rows.values()) != total:
        raise ValueError("exactness rows do not sum to total_lines")
    return {
        "total_lines": total,
        "p_up": float(exact["p_up"]),
        "n_server_exact_genomes": int(exact["n_server_exact_genomes"]),
        "n_diverse_passed_genomes": int(exact["n_diverse_passed_genomes"]),
        "headline_max_cv": float(exact["headline_max_cv"]),
        "parts": [
            {
                "id": key,
                "label": EXACTNESS_LABELS.get(key, key),
                "count": int(value),
            }
            for key, value in rows.items()
        ],
        "scope": "HMMER and Infernal only; DIAMOND and BLAST+ are not in this total.",
        "source": "pipeline/results/exact_replay/exactness_totals.json",
    }


def build_case(case_id: str) -> dict[str, Any]:
    builders = {
        "hmmer": ("HMMER", _hmmer),
        "infernal": ("Infernal", _infernal),
        "diamond": ("DIAMOND", _diamond),
        "blast": ("BLAST+", _blast),
    }
    if case_id not in builders:
        raise KeyError(case_id)
    tool, builder = builders[case_id]
    try:
        return builder()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _error_case(case_id, tool, exc)


def build_board() -> dict[str, Any]:
    cases = [build_case(case_id) for case_id in CASE_ORDER]
    exactness = None
    exactness_error = None
    try:
        exactness = _exactness()
    except Exception as exc:  # noqa: BLE001
        exactness_error = f"{type(exc).__name__}: {exc}"
    return {
        "schema_version": 1,
        "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "results_root": "pipeline/results",
        "cases": cases,
        "exactness": exactness,
        "exactness_error": exactness_error,
    }


def case_summary(case: dict[str, Any]) -> dict[str, Any]:
    if case.get("verdict") == "error":
        return {
            "id": case["id"],
            "tool": case["tool"],
            "verdict": "error",
            "error": case.get("error"),
        }
    headline = case.get("headline") or {}
    release = case.get("release") or {}
    summary: dict[str, Any] = {
        "id": case["id"],
        "tool": case["tool"],
        "program": case.get("program"),
        "verdict": case["verdict"],
        "pair": release.get("pair"),
    }
    if case["verdict"] == "ship":
        summary["median_speedup"] = headline.get("median_speedup")
        summary["ci95"] = headline.get("ci95")
        summary["n_speedups"] = headline.get("n_speedups")
        summary["walls_indicative"] = headline.get("walls_indicative", False)
    else:
        summary["outcome"] = headline.get("outcome")
        if "refuse_lines" in headline:
            summary["refuse_lines"] = headline["refuse_lines"]
        if "pin_matched_lines" in headline:
            summary["pin_matched_lines"] = headline["pin_matched_lines"]
        if "refuse_reason" in headline:
            summary["refuse_reason"] = headline["refuse_reason"]
    return summary


def project_payload(pid: str) -> dict[str, Any]:
    project = engine.load_project(pid)
    engine.touch_recent(pid)
    refs = {}
    for side, ref_id in project["references"].items():
        try:
            refs[side] = engine.reference(ref_id) if ref_id else None
        except KeyError:
            refs[side] = None
    return {
        "project": project,
        "references": refs,
        "runs": [engine.run_summary(run) for run in engine.list_runs(pid)],
        "cache": engine.cache_info(pid),
        "tool": engine.tool_row(project["tool"]),
    }


def get_route(path: str, query: dict[str, str]) -> Any:
    parts = path.removeprefix("/api/").split("/")
    head = parts[0]
    if head == "app":
        engine.ensure_demo()
        return {
            "setup": engine.SETUP | {"ready": engine.demo_ready()},
            "projects": [{"id": p["id"], "name": p["name"], "tool": p["tool"]} for p in engine.list_projects()],
            "recent": engine.recent_projects(),
            "presets": engine.presets(),
            "tools": engine.detect_tools(),
            "references": engine.references(),
            "system": engine.system(),
            "connection": engine.CONNECTION,
            "demo_id": engine.DEMO_ID,
        }
    if head == "system":
        return engine.system()
    if head == "events":
        return {"events": engine.events(int(query.get("limit", 200)), query.get("project"))}
    if head == "projects" and len(parts) >= 2:
        pid = parts[1]
        if len(parts) == 2:
            return project_payload(pid)
        sub = parts[2]
        if sub == "preflight":
            return engine.preflight(pid)
        if sub == "diff":
            project = engine.load_project(pid)
            return engine.reference_diff(project["references"]["old"], project["references"]["new"])
        if sub == "command":
            return engine.command_preview(pid)
        if sub == "cache":
            return engine.cache_info(pid)
    if head == "runs" and len(parts) >= 2:
        if parts[1] == "compare":
            return engine.compare_runs(query["a"], query["b"])
        rid = parts[1]
        if len(parts) == 2:
            run = engine.load_run(rid)
            run["queue"] = engine.WORKER.status()
            return run
        sub = parts[2]
        if sub == "log":
            return engine.read_log(rid, int(query.get("after", 0)))
        if sub == "files":
            return {"files": engine.run_files(rid)}
        if sub == "download":
            name, data = engine.results_zip(rid)
            return name, data, "application/zip"
        if sub == "bundle":
            name, data = engine.bundle_zip(rid)
            return name, data, "application/zip"
        if sub == "report":
            name, data = engine.report_html(rid)
            return name, data, "text/html; charset=utf-8"
    raise KeyError(path)


def post_route(path: str, body: dict[str, Any]) -> Any:
    parts = path.removeprefix("/api/").split("/")
    head = parts[0]
    if head == "projects" and len(parts) == 1:
        return engine.create_project(body["name"], body.get("tool", "hmmer"), body.get("copy_from"))
    if head == "projects":
        pid, sub = parts[1], parts[2]
        if sub == "settings":
            return engine.update_settings(pid, body)
        if sub == "inputs":
            return engine.add_inputs(pid, body.get("paths") or [])
        if sub == "inputs-remove":
            return engine.remove_input(pid, body["id"])
        if sub == "tool":
            return engine.set_tool(pid, body["tool"])
        if sub == "references":
            return engine.set_references(pid, body.get("old"), body.get("new"))
        if sub == "import-release":
            meta = engine.register_reference(engine.Path(body["path"]), body["label"])
            if body.get("use_as") in ("old", "new"):
                project = engine.load_project(pid)
                refs = dict(project["references"])
                if body["use_as"] == "new" and refs.get("new"):
                    refs["old"] = refs["new"]
                refs[body["use_as"]] = meta["id"]
                engine.set_references(pid, refs.get("old"), refs.get("new"))
            return meta
        if sub == "presets":
            return engine.save_preset(pid, body["name"])
        if sub == "apply-preset":
            return engine.apply_preset(pid, body["name"])
        if sub == "runs":
            return engine.create_run(pid, body.get("kind", "update"), body.get("inputs"))
        if sub == "cache-validate":
            return engine.validate_cache(pid)
        if sub == "cache-invalidate":
            return engine.invalidate_cache(pid)
        if sub == "cleanup":
            return engine.clean_up(pid, int(body.get("keep", 3)))
        if sub == "open":
            folder = engine.project_dir(pid)
            if body.get("run"):
                folder = engine.run_dir(pid, body["run"]) / (body.get("sub") or "")
            engine.open_path(folder)
            return {"opened": engine.rel(folder)}
    if head == "runs":
        rid, sub = parts[1], parts[2]
        if sub == "cancel":
            engine.WORKER.cancel(rid)
            return {"cancelled": rid}
        if sub == "retry":
            return engine.retry_failed(rid)
        if sub == "again":
            return engine.run_again(rid)
        if sub == "compare-full":
            return engine.full_compare(rid, body.get("inputs"))
    if head == "connection":
        return engine.test_connection(body.get("compute", "local"))
    if head == "setup-demo":
        engine.ensure_demo()
        return engine.SETUP
    raise KeyError(path)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[tare] {self.address_string()} {fmt % args}")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/")
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            self._json(post_route(path, body))
        except KeyError as exc:
            self._json({"error": f"not found: {exc}"}, status=404)
        except ValueError as exc:
            self._json({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json({"error": f"{type(exc).__name__}: {exc}"}, status=500)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        try:
            if path.startswith("/api/") and not path.startswith(("/api/health", "/api/board", "/api/cases", "/api/exactness")):
                result = get_route(path, query)
                if isinstance(result, tuple):
                    name, data, kind = result
                    self._download(name, data, kind)
                else:
                    self._json(result)
                return
            if path == "/api/health":
                self._json(
                    {
                        "ok": True,
                        "service": "tare-console",
                        "schema_version": 1,
                        "results_root": str(RESULTS),
                        "results_exists": RESULTS.is_dir(),
                    }
                )
                return
            if path == "/api/board":
                self._json(build_board())
                return
            if path == "/api/cases":
                board = build_board()
                self._json(
                    {
                        "schema_version": board["schema_version"],
                        "read_at": board["read_at"],
                        "cases": [case_summary(case) for case in board["cases"]],
                    }
                )
                return
            if path.startswith("/api/cases/"):
                case_id = path.removeprefix("/api/cases/")
                if case_id not in CASE_ORDER:
                    self._json({"error": "unknown case", "id": case_id}, status=404)
                    return
                case = build_case(case_id)
                status = 500 if case.get("verdict") == "error" else 200
                self._json(case, status=status)
                return
            if path == "/api/exactness":
                try:
                    self._json(_exactness())
                except Exception as exc:  # noqa: BLE001
                    self._json({"error": f"{type(exc).__name__}: {exc}"}, status=500)
                return
            if path in {"/", "/index.html"}:
                index = STATIC / "index.html"
                if index.is_file():
                    self._file(index)
                else:
                    self._json(
                        {
                            "service": "tare-console",
                            "message": "UI not present. Hit /api/board or drop files in tools/tare-console/static/.",
                            "endpoints": [
                                "/api/health",
                                "/api/board",
                                "/api/cases",
                                "/api/cases/<id>",
                                "/api/exactness",
                            ],
                        }
                    )
                return
            if path.startswith("/static/"):
                rel = path.removeprefix("/static/")
                if not rel or ".." in rel.split("/"):
                    self.send_error(404)
                    return
                self._file(STATIC / rel)
                return
            self._json({"error": "not found", "path": path}, status=404)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json({"error": f"{type(exc).__name__}: {exc}"}, status=500)

    def _download(self, name: str, data: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        kind = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".ico": "image/x-icon",
            ".json": "application/json; charset=utf-8",
            ".map": "application/json; charset=utf-8",
        }.get(path.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the TARE console API")
    parser.add_argument("--check", action="store_true", help="Build the board and exit")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    board = build_board()
    if args.check:
        for case in board["cases"]:
            verdict = case.get("verdict", "error")
            if verdict == "error":
                print(f"{case['id']:10} ERROR    {case.get('error', '')[:88]}")
            elif verdict == "ship":
                median = (case.get("headline") or {}).get("median_speedup")
                print(f"{case['id']:10} ship     median={median}")
            else:
                print(f"{case['id']:10} refuse   {(case.get('headline') or {})}")
        if board["exactness_error"]:
            raise SystemExit(board["exactness_error"])
        if any(case.get("verdict") == "error" for case in board["cases"]):
            raise SystemExit(1)
        print(f"exactness lines={board['exactness']['total_lines']}")
        return
    engine.recover_interrupted()
    engine.ensure_demo()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"TARE API  http://{args.host}:{args.port}")
    print("  /api/health  /api/board  /api/cases  /api/cases/<id>  /api/exactness")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
