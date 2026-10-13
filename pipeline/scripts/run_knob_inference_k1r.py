#!/usr/bin/env python3
"""K1r driver for the 2026-10-12 addendum in docs/KNOB_INFERENCE_PROTOCOL.md.

Sample construction and the two arms are locked there. This file names the
tool. acts/infer_knobs.py does not.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.infer_knobs import apply_extra_argv, capture_help, infer_knobs  # noqa: E402
from acts.reference_formats import (  # noqa: E402
    iter_profile_raw,
    parse_reference_text,
    read_records,
    write_entries,
)
from acts.reference_run import probe_fit, write_record_file  # noqa: E402

QUERY_GZ = ROOT / "data" / "recurrence" / "A" / "GCF_002853805.1_protein.faa.gz"
REF_GZ = ROOT / "data" / "hmmer" / "Pfam-A.hmm.gz"
WORK = Path("/tmp/acts_knob_k1r")
OUT = ROOT / "results" / "knob_inference" / "k1r.json"

E1_SEED = 20261012
FILL_SEED = 20261015
N_E1 = 300
N_QUERY = 50
N_MODELS = 400
N_HALF = 200
POWER_FLOOR = 30
DECOYS = ("--F1", "--F2", "--F3", "--seed", "--cpu", "--domZ")
EVALUE_FLAGS = ("-E", "--domE", "--incE", "--incdomE")
BITSCORE_FLAGS = ("-T", "--domT", "--incT", "--incdomT")


def _log(message: str) -> None:
    print(time.strftime("%H:%M:%S"), message, file=sys.stderr, flush=True)


def _git_hash() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT.parents[0],
        check=False,
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "").strip()


def _dump(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")


def _body_fields(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        rows.append(line.split())
    return rows


def _tag(raw: str, tag: str) -> str:
    prefix = tag + " "
    for line in raw.splitlines():
        if line.startswith(prefix):
            return line.split(None, 1)[1].strip()
    return ""


def _keys_for(name: str, acc: str) -> tuple[str, ...]:
    found: list[str] = []
    for token in (name, acc):
        if token and token not in found:
            found.append(token)
    if acc and "." in acc:
        bare = acc.split(".", 1)[0]
        if bare and bare not in found:
            found.append(bare)
    return tuple(found)


def _catalog(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for raw in iter_profile_raw(path):
        rows.append((_tag(raw, "NAME"), _tag(raw, "ACC")))
    return rows


def _select_h(hit_pos: list[int], fill_pos: list[int], n: int = N_HALF) -> list[int]:
    """Stratified half. Remainder is file order, fill stratum first."""
    rng = random.Random(FILL_SEED)
    chosen = set(rng.sample(hit_pos, len(hit_pos) // 2)) if hit_pos else set()
    if fill_pos:
        chosen.update(rng.sample(fill_pos, len(fill_pos) // 2))
    if len(chosen) < n:
        for index in fill_pos + hit_pos:
            if index in chosen:
                continue
            chosen.add(index)
            if len(chosen) == n:
                break
    if len(chosen) != n:
        raise RuntimeError(f"H has {len(chosen)} models, wanted {n}")
    return sorted(chosen)


def _self_check() -> None:
    even = _select_h(list(range(200)), list(range(200, 400)))
    if len(even) != 200:
        raise RuntimeError("even strata did not yield 200")
    odd = _select_h(list(range(201)), list(range(201, 400)))
    if len(odd) != 200:
        raise RuntimeError("odd strata did not yield 200")
    hits_only = _select_h(list(range(400)), [])
    if len(hits_only) != 200:
        raise RuntimeError("hit-only W did not yield 200")
    # The two Random(20261015) draws in one call must be stable.
    if even != _select_h(list(range(200)), list(range(200, 400))):
        raise RuntimeError("H draw is not stable")


def _press_full(hmmpress: str, gz: Path, prefix: Path) -> dict:
    """Decompress and press. Not a probe call. Text is removed after press."""
    h3m = Path(str(prefix) + ".h3m")
    stamp = Path(str(prefix) + ".pressed.json")
    if stamp.exists() and h3m.exists():
        payload = json.loads(stamp.read_text())
        _log(f"press reuse models={payload.get('pressed_models')}")
        return payload
    free = shutil.disk_usage(prefix.parent).free
    if free < 8 * 1024**3:
        raise RuntimeError(f"need 8 GiB free to press, have {free}")
    _log(f"decompress {gz.name}")
    started = time.perf_counter()
    with gzip.open(gz, "rb") as src, open(prefix, "wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    decomp_s = time.perf_counter() - started
    _log(f"hmmpress {prefix.name} ({prefix.stat().st_size} bytes)")
    started = time.perf_counter()
    proc = subprocess.run([hmmpress, "-f", str(prefix)], check=False, capture_output=True, text=True)
    press_s = time.perf_counter() - started
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "")[-500:]
        raise RuntimeError(f"press failed ({proc.returncode}): {detail}")
    prefix.unlink(missing_ok=True)
    text = (proc.stdout or "") + (proc.stderr or "")
    pressed = None
    marker = "Pressed and indexed "
    if marker in text:
        pressed = int(text.split(marker, 1)[1].split()[0])
    payload = {"decomp_s": decomp_s, "press_s": press_s, "pressed_models": pressed}
    stamp.write_text(json.dumps(payload))
    _log(f"pressed models={pressed} decomp={decomp_s:.1f}s press={press_s:.1f}s")
    return payload


def _option_row(result: dict, option: str) -> dict:
    for candidate in result.get("candidates") or []:
        if candidate.get("option") == option:
            return {
                "present": True,
                "normalizer": candidate.get("normalizer") or {},
                "threshold": candidate.get("threshold"),
            }
    return {"present": False, "normalizer": {}, "threshold": "absent from help"}


def _accepted_normalizer(row: dict) -> bool:
    return any(value == "accept" for value in (row.get("normalizer") or {}).values())


def _judge_arm(arm: str, result: dict) -> dict:
    """Mechanical checks from the K1r addendum. No extra kills."""
    pin = str(result.get("pin"))
    thresholds = list(result.get("thresholds") or [])
    accepted = [item["option"] for item in thresholds]
    failures: list[str] = []
    if pin != "-Z {entry_count}":
        failures.append(f"pin is {pin!r}")
    z_row = _option_row(result, "-Z")
    if not _accepted_normalizer(z_row):
        failures.append("-Z was not accepted as a normalizer")
    for option in DECOYS:
        row = _option_row(result, option)
        if _accepted_normalizer(row):
            failures.append(f"accepted decoy normalizer {option}")
        if row.get("threshold") == "accept":
            failures.append(f"accepted decoy threshold {option}")
    if arm == "K1r-a" and accepted:
        failures.append("accepted thresholds: " + ", ".join(accepted))
    if arm == "K1r-b":
        for option in ("-E", "--domE"):
            if option not in accepted:
                failures.append(f"missing threshold {option}")
    watched = {}
    for option in ("-Z", "--domZ", *EVALUE_FLAGS, *BITSCORE_FLAGS, *DECOYS):
        watched[option] = _option_row(result, option)
    return {
        "verdict": "KILL" if failures else "PASS",
        "failures": failures,
        "pin": pin,
        "thresholds": thresholds,
        "watched": watched,
    }


def main() -> int:
    _self_check()
    WORK.mkdir(parents=True, exist_ok=True)
    hmmscan = shutil.which("hmmscan")
    hmmpress = shutil.which("hmmpress")
    help_text = capture_help(hmmscan) if hmmscan else ""
    banner = [line for line in help_text.splitlines() if line.startswith("#")][:3]
    meta = {
        "protocol": "docs/KNOB_INFERENCE_PROTOCOL.md",
        "addendum": "2026-10-12 K1r",
        "git": _git_hash(),
        "host": platform.node(),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "banner": banner,
        "seeds": {"e1": E1_SEED, "fill_and_h": FILL_SEED},
    }
    if not hmmscan or not hmmpress or not QUERY_GZ.is_file() or not REF_GZ.is_file():
        meta.update({"verdict": "INCONCLUSIVE", "reason": "missing binary or data"})
        _dump(meta)
        _log("INCONCLUSIVE missing binary or data")
        return 0

    all_records = read_records(QUERY_GZ)
    if len(all_records) < N_E1:
        meta.update({"verdict": "INCONCLUSIVE", "reason": f"only {len(all_records)} records"})
        _dump(meta)
        return 0
    e1_index = sorted(random.Random(E1_SEED).sample(range(len(all_records)), N_E1))
    e1_records = [all_records[i] for i in e1_index]
    queries_300 = WORK / "e1_q300.faa"
    write_record_file(e1_records, queries_300)

    try:
        press = _press_full(hmmpress, REF_GZ, WORK / "pfam38.2.hmm")
    except Exception as exc:
        meta.update({"verdict": "INCONCLUSIVE", "reason": f"press failed: {exc}"})
        _dump(meta)
        _log(f"INCONCLUSIVE {exc}")
        return 0

    construct_tbl = WORK / "construct.tbl"
    construct_dom = WORK / "construct.dom"
    cmd = [
        hmmscan,
        "--noali",
        "--tblout",
        str(construct_tbl),
        "--domtblout",
        str(construct_dom),
        str(WORK / "pfam38.2.hmm"),
        str(queries_300),
    ]
    _log("SAMPLE-CONSTRUCTION scan of E1 300 against full reference")
    started = time.perf_counter()
    stdout_path = WORK / "construct.stdout"
    stderr_path = WORK / "construct.stderr"
    with stdout_path.open("w") as stdout, stderr_path.open("w") as stderr:
        proc = subprocess.run(cmd, check=False, stdout=stdout, stderr=stderr)
    wall = time.perf_counter() - started
    if proc.returncode != 0:
        detail = stderr_path.read_text(errors="replace")[-500:]
        meta.update(
            {
                "verdict": "INCONCLUSIVE",
                "reason": f"construction scan failed ({proc.returncode}): {detail}",
                "sample_construction": {"wall_s": wall, "press": press},
            }
        )
        _dump(meta)
        _log("INCONCLUSIVE construction scan failed")
        return 0
    tbl_text = construct_tbl.read_text()
    body = _body_fields(tbl_text)
    _log(f"construction wall={wall:.1f}s tblout_body={len(body)}")

    queries_with_hits = {fields[2] for fields in body if len(fields) >= 3}
    q_index = [i for i in e1_index if all_records[i].name in queries_with_hits][:N_QUERY]
    if len(q_index) < N_QUERY:
        meta.update(
            {
                "verdict": "INCONCLUSIVE",
                "reason": f"only {len(q_index)} of the E1 sample have a tblout row",
                "sample_construction": {
                    "wall_s": wall,
                    "tblout_body_rows": len(body),
                    "queries_with_hits_in_e1": len(queries_with_hits),
                    "press": press,
                },
            }
        )
        _dump(meta)
        _log("INCONCLUSIVE fewer than 50 queries with a hit")
        return 0

    _log("cataloguing reference")
    catalog = _catalog(REF_GZ)
    key_to_index: dict[str, int] = {}
    for index, (name, acc) in enumerate(catalog):
        for token in _keys_for(name, acc):
            key_to_index.setdefault(token, index)
    q_names = {all_records[i].name for i in q_index}
    hit_indices: set[int] = set()
    unmatched: set[str] = set()
    q_rows = 0
    for fields in body:
        if len(fields) < 3 or fields[2] not in q_names:
            continue
        q_rows += 1
        name, acc = fields[0], fields[1]
        index = key_to_index.get(name)
        if index is None:
            index = key_to_index.get(acc)
        if index is None:
            unmatched.add(name)
            continue
        hit_indices.add(index)
    hit_sorted = sorted(hit_indices)
    truncated = len(hit_sorted) > N_MODELS
    if truncated:
        w_global = hit_sorted[:N_MODELS]
        fill_global: list[int] = []
    elif len(hit_sorted) == N_MODELS:
        w_global = hit_sorted
        fill_global = []
    else:
        need = N_MODELS - len(hit_sorted)
        pool = [i for i in range(len(catalog)) if i not in hit_indices]
        if len(pool) < need:
            meta.update(
                {
                    "verdict": "INCONCLUSIVE",
                    "reason": f"only {len(hit_sorted)} hit models and {len(pool)} fill",
                    "sample_construction": {"wall_s": wall, "tblout_body_rows": len(body)},
                }
            )
            _dump(meta)
            return 0
        fill_global = random.Random(FILL_SEED).sample(pool, need)
        w_global = sorted(hit_sorted + fill_global)
    if len(w_global) < N_MODELS:
        meta.update({"verdict": "INCONCLUSIVE", "reason": f"|W|={len(w_global)}"})
        _dump(meta)
        return 0

    want = set(w_global)
    _log(f"extracting {len(want)} models")
    blocks = [raw for index, raw in enumerate(iter_profile_raw(REF_GZ)) if index in want]
    if len(blocks) != len(want):
        raise RuntimeError(f"extracted {len(blocks)} of {len(want)}")
    entries = parse_reference_text("".join(blocks))
    if len(entries) != N_MODELS:
        raise RuntimeError(f"parsed {len(entries)} models")
    hit_set = set(hit_sorted)
    hit_pos = [k for k, gi in enumerate(w_global) if gi in hit_set]
    fill_pos = [k for k, gi in enumerate(w_global) if gi not in hit_set]
    h_pos = _select_h(hit_pos, fill_pos)
    h_set = set(h_pos)
    complement = [k for k in range(N_MODELS) if k not in h_set]
    if len(complement) != N_HALF or len(h_pos) != N_HALF:
        raise RuntimeError("partition is not 200/200")

    for suffix in ("", ".h3m", ".h3i", ".h3f", ".h3p"):
        Path(str(WORK / "pfam38.2.hmm") + suffix).unlink(missing_ok=True)

    sample_construction = {
        "label": "SAMPLE-CONSTRUCTION",
        "wall_s": wall,
        "tblout_body_rows": len(body),
        "domtblout_body_rows": len(_body_fields(construct_dom.read_text())),
        "e1_queries": N_E1,
        "queries_with_hits_in_e1": len(queries_with_hits),
        "q": N_QUERY,
        "q_tblout_rows": q_rows,
        "hit_models": len(hit_sorted),
        "hits_truncated_at_400": truncated,
        "unmatched_targets": sorted(unmatched),
        "fill_models": len(fill_pos),
        "W": N_MODELS,
        "H": N_HALF,
        "H_hit_models": sum(1 for k in h_pos if k in set(hit_pos)),
        "H_fill_models": sum(1 for k in h_pos if k in set(fill_pos)),
        "model_total": len(catalog),
        "press": press,
        "query_names": [all_records[i].name for i in q_index],
    }
    meta["sample_construction"] = sample_construction
    _dump(meta)
    _log(
        f"Q={N_QUERY} hits={len(hit_sorted)} truncated={truncated} "
        f"fill={len(fill_pos)} H_hit={sample_construction['H_hit_models']}"
    )

    records = [all_records[i] for i in q_index]
    write_record_file(records, WORK / "queries.faa")
    half = [entries[i] for i in h_pos]
    half_keys = {token for entry in half for token in entry.keys}
    scans = {"n": 0}
    cache: dict[tuple, dict[str, str]] = {}

    def reference_file(subset) -> Path:
        digest = hashlib.sha256("".join(entry.content_hash for entry in subset).encode()).hexdigest()[:16]
        path = WORK / f"{digest}.hmm"
        if path.exists() and Path(str(path) + ".h3m").exists():
            return path
        write_entries(list(subset), path)
        _log(f"press {len(subset)} models")
        proc_press = subprocess.run(
            [hmmpress, "-f", str(path)], check=False, capture_output=True, text=True
        )
        if proc_press.returncode != 0:
            detail = (proc_press.stderr or proc_press.stdout or "")[-500:]
            raise RuntimeError(f"press failed ({proc_press.returncode}): {detail}")
        return path

    def scan(subset, extra: list[str], arm: str) -> dict[str, str]:
        key = (arm, tuple(entry.content_hash for entry in subset), tuple(extra))
        if key in cache:
            return cache[key]
        paired = list(extra)
        for index, token in enumerate(paired):
            if token == "--cpu" and index + 1 < len(paired) and paired[index + 1] != "1":
                raise RuntimeError("worker-count probe refused")
        scans["n"] += 1
        ref = reference_file(subset)
        call = WORK / f"call{scans['n']}"
        call.mkdir(parents=True, exist_ok=True)
        base = [hmmscan, "--noali", "--cpu", "1", "--tblout", str(call / "tbl"), "--domtblout", str(call / "dom")]
        if arm == "K1r-a":
            base.insert(1, "--cut_ga")
        cmd_scan = apply_extra_argv(base, paired) + [str(ref), str(WORK / "queries.faa")]
        t0 = time.perf_counter()
        proc_scan = subprocess.run(cmd_scan, check=False, capture_output=True, text=True)
        elapsed = time.perf_counter() - t0
        _log(f"scan {scans['n']} {arm} n={len(subset)} extra={paired} {elapsed:.1f}s rc={proc_scan.returncode}")
        if proc_scan.returncode != 0:
            detail = (proc_scan.stderr or proc_scan.stdout or "")[-500:]
            raise RuntimeError(f"tool failed ({proc_scan.returncode}): {detail}")
        tables = {}
        for name in ("tbl", "dom"):
            dest = call / name
            if not dest.is_file():
                raise RuntimeError(f"tool did not write {name}")
            tables[name] = dest.read_text()
        cache[key] = tables
        return tables

    def shared_count(arm: str) -> dict:
        half_out = scan(half, [], arm)
        whole_out = scan(entries, [], arm)

        def pairs(text: str) -> set[tuple[str, str]]:
            found: set[tuple[str, str]] = set()
            for fields in _body_fields(text):
                if len(fields) < 3:
                    continue
                if fields[0] in half_keys or fields[1] in half_keys:
                    found.add((fields[2], fields[0]))
            return found

        h_pairs = pairs(half_out["tbl"])
        w_pairs = pairs(whole_out["tbl"])
        return {
            "shared_tblout_rows_on_H": len(h_pairs & w_pairs),
            "tblout_rows_H": len(_body_fields(half_out["tbl"])),
            "tblout_rows_W": len(_body_fields(whole_out["tbl"])),
            "domtblout_rows_H": len(_body_fields(half_out["dom"])),
            "domtblout_rows_W": len(_body_fields(whole_out["dom"])),
        }

    def fit_summary(fit) -> dict:
        columns = [
            {"table": table.name, "index": col.index, "role": col.role, "member": col.member}
            for table in fit.tables
            for col in table.columns
        ]
        return {
            "decision": fit.decision,
            "reason": fit.reason,
            "probe_invocations": fit.probe_invocations,
            "columns": columns,
            "has_entry_count": any(col["member"] == "entry_count" for col in columns),
        }

    def run_arm(arm: str, monotone: bool) -> dict:
        _log(f"{arm} power floor")
        try:
            floor = shared_count(arm)
        except Exception as exc:
            return {"verdict": "INCONCLUSIVE", "reason": f"power floor failed: {exc}"}
        _log(f"{arm} shared={floor['shared_tblout_rows_on_H']}")
        if floor["shared_tblout_rows_on_H"] < POWER_FLOOR:
            return {
                "verdict": "INCONCLUSIVE",
                "reason": f"power floor {floor['shared_tblout_rows_on_H']} < {POWER_FLOOR}",
                "power_floor": floor,
                "tool_calls": 0,
                "P": 0,
            }
        _log(f"{arm} fitting monotone={monotone}")
        before = scans["n"]
        try:
            fit = probe_fit(
                entries,
                records,
                lambda recs, subset, arm=arm: scan(subset, [], arm),
                primary_parts=[h_pos, complement],
                sample=False,
                monotone=monotone,
            )
        except Exception as exc:
            return {
                "verdict": "INCONCLUSIVE",
                "reason": f"fit failed: {exc}",
                "power_floor": floor,
                "tool_calls": 0,
                "P": 0,
            }
        summary = fit_summary(fit)
        fit_calls = scans["n"] - before
        if not summary["has_entry_count"]:
            return {
                "verdict": "INCONCLUSIVE",
                "reason": "fit assigned no entry_count column",
                "power_floor": floor,
                "fit": summary,
                "fit_calls": fit_calls,
                "tool_calls": 0,
                "P": 0,
            }
        _log(f"{arm} inferring")
        result = infer_knobs(
            help_text,
            records,
            entries,
            half,
            fit.tables,
            lambda recs, subset, extra, arm=arm: scan(subset, list(extra), arm),
        )
        judgment = _judge_arm(arm, result)
        return {
            **judgment,
            "power_floor": floor,
            "fit": summary,
            "fit_calls": fit_calls,
            "reason_pin": result.get("reason"),
            "rejected": result.get("rejected"),
            "candidates": result.get("candidates"),
            "members": result.get("members"),
            "tool_calls": result.get("tool_calls"),
            "P": result.get("tool_calls"),
        }

    meta["arms"] = {}
    arm_b = run_arm("K1r-b", True)
    meta["arms"]["K1r-b"] = arm_b
    _dump(meta)
    _log(f"K1r-b {arm_b.get('verdict')}")
    if arm_b.get("verdict") == "INCONCLUSIVE" and "power floor" in str(arm_b.get("reason")):
        meta["verdict"] = "INCONCLUSIVE"
        meta["reason"] = arm_b["reason"]
        meta["subprocess_calls"] = scans["n"]
        _dump(meta)
        _log("INCONCLUSIVE power floor; stopped")
        return 0
    arm_a = run_arm("K1r-a", False)
    meta["arms"]["K1r-a"] = arm_a
    verdicts = {name: meta["arms"][name].get("verdict") for name in meta["arms"]}
    if any(value == "KILL" for value in verdicts.values()):
        meta["verdict"] = "KILL"
    elif all(value == "PASS" for value in verdicts.values()) and set(verdicts) == {"K1r-a", "K1r-b"}:
        meta["verdict"] = "PASS"
    else:
        meta["verdict"] = "INCONCLUSIVE"
    meta["subprocess_calls"] = scans["n"]
    _dump(meta)
    _log(f"overall {meta['verdict']} subprocess={scans['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
