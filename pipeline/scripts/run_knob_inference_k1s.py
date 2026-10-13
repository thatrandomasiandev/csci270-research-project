#!/usr/bin/env python3
"""K1s driver for the 2026-10-12 redesign addendum in docs/KNOB_INFERENCE_PROTOCOL.md.

The held-out sample decides the verdict. The secondary sample is the K1r
sample and is reported only. This file names the tool. acts/infer_knobs.py
does not.
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

HELDOUT_GZ = ROOT / "data" / "recurrence" / "A" / "GCF_002090355.1_protein.faa.gz"
SECONDARY_GZ = ROOT / "data" / "recurrence" / "A" / "GCF_002853805.1_protein.faa.gz"
REF_GZ = ROOT / "data" / "hmmer" / "Pfam-A.hmm.gz"
WORK = Path("/tmp/acts_knob_k1s")
OUT = ROOT / "results" / "knob_inference" / "k1s.json"

N_DRAW = 300
N_QUERY = 50
N_MODELS = 400
N_HALF = 200
POWER_FLOOR = 30
# HMMER 3.4 tblout field 4 is the full-sequence E-value. domtblout field 12
# is the independent domain E-value, which is the domain cutoff.
TBL_FULL_E = 4
DOM_DOMAIN_E = 12
DECOYS = ("--F1", "--F2", "--F3", "--seed", "--cpu", "--domZ", "-Z")
INCLUSION = ("--incE", "--incdomE")
BITSCORE = ("-T", "--domT", "--incT", "--incdomT")
NOT_REPORTING = frozenset(
    {
        "accept",
    }
)


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


def _headers(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("#")]


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


def _select_h(hit_pos: list[int], fill_pos: list[int], seed: int, n: int = N_HALF) -> list[int]:
    """Stratified half. Remainder is file order, fill stratum first."""
    rng = random.Random(seed)
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
    even = _select_h(list(range(200)), list(range(200, 400)), 20261016)
    if len(even) != 200 or even != _select_h(list(range(200)), list(range(200, 400)), 20261016):
        raise RuntimeError("H draw is not a stable 200")
    odd = _select_h(list(range(201)), list(range(201, 400)), 20261016)
    if len(odd) != 200:
        raise RuntimeError("odd strata did not yield 200")


def _press_full(hmmpress: str, gz: Path, prefix: Path) -> dict:
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


def _drop_full_press(prefix: Path) -> None:
    for suffix in ("", ".h3m", ".h3i", ".h3f", ".h3p"):
        Path(str(prefix) + suffix).unlink(missing_ok=True)


def _option_row(result: dict, option: str) -> dict:
    for candidate in result.get("candidates") or []:
        if candidate.get("option") == option:
            return {
                "present": True,
                "normalizer": candidate.get("normalizer") or {},
                "threshold": candidate.get("threshold"),
                "probes": candidate.get("probes") or [],
            }
    return {"present": False, "normalizer": {}, "threshold": "absent from help", "probes": []}


def _accepted_normalizer(row: dict) -> bool:
    return any(value == "accept" for value in (row.get("normalizer") or {}).values())


def _pairs(result: dict) -> list[tuple[str, str]]:
    return [(item["option"], item["table"]) for item in result.get("thresholds") or []]


def _column_indexes(spec: str, table: str) -> set[int]:
    found: set[int] = set()
    for part in str(spec).split(","):
        if not part or ":" not in part:
            continue
        name, raw = part.split(":", 1)
        if name == table:
            found.add(int(raw))
    return found


def _judge_arm(arm: str, result: dict) -> dict:
    """Mechanical checks from the K1s addendum. The secondary sample is not judged here."""
    pin = str(result.get("pin"))
    thresholds = list(result.get("thresholds") or [])
    pairs = _pairs(result)
    failures: list[str] = []
    if pin != "-Z {entry_count}":
        failures.append(f"pin is {pin!r}")
    z_row = _option_row(result, "-Z")
    if not _accepted_normalizer(z_row):
        failures.append("-Z was not accepted as a normalizer")
    if _accepted_normalizer(_option_row(result, "--domZ")):
        failures.append("--domZ was accepted as a normalizer")
    for option in DECOYS:
        if any(pair[0] == option for pair in pairs):
            failures.append(f"accepted decoy reporting threshold {option}")
    for option in INCLUSION + BITSCORE:
        if any(pair[0] == option for pair in pairs):
            failures.append(f"accepted reporting threshold {option}")
    if arm == "K1s-a" and thresholds:
        failures.append(
            "accepted reporting thresholds: "
            + ", ".join(f"{item['option']} on {item['table']}" for item in thresholds)
        )
    if arm == "K1s-b":
        expected = {("-E", "tbl"), ("--domE", "dom")}
        if set(pairs) != expected:
            failures.append(f"reporting pairs {pairs} are not exactly -E on tblout and --domE on domtblout")
        for item in thresholds:
            if item["option"] == "-E" and item["table"] == "tbl":
                if TBL_FULL_E not in _column_indexes(item.get("column", ""), "tbl"):
                    failures.append(f"-E bounding columns {item.get('column')!r} omit the full-sequence E-value")
            if item["option"] == "--domE" and item["table"] == "dom":
                if DOM_DOMAIN_E not in _column_indexes(item.get("column", ""), "dom"):
                    failures.append(
                        f"--domE bounding columns {item.get('column')!r} omit the domain E-value"
                    )
    watched = {}
    for option in ("-Z", "--domZ", "-E", "--domE", *INCLUSION, *BITSCORE, *DECOYS):
        watched[option] = _option_row(result, option)
        watched[option].pop("probes", None)
    return {
        "verdict": "KILL" if failures else "PASS",
        "failures": failures,
        "pin": pin,
        "thresholds": thresholds,
        "reporting_pairs": [{"option": option, "table": table} for option, table in pairs],
        "watched": watched,
    }


def _fit_summary(fit) -> dict:
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


def main() -> int:
    _self_check()
    WORK.mkdir(parents=True, exist_ok=True)
    hmmscan = shutil.which("hmmscan")
    hmmpress = shutil.which("hmmpress")
    help_text = capture_help(hmmscan) if hmmscan else ""
    banner = [line for line in help_text.splitlines() if line.startswith("#")][:3]
    meta = {
        "protocol": "docs/KNOB_INFERENCE_PROTOCOL.md",
        "addendum": "2026-10-12 K1s",
        "redesign_after": "K1r-b KILL",
        "git": _git_hash(),
        "host": platform.node(),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "banner": banner,
        "table_slots": {"tbl": "tblout", "dom": "domtblout"},
        "bounding_columns": {
            "tbl_full_sequence_evalue": TBL_FULL_E,
            "dom_domain_evalue": DOM_DOMAIN_E,
        },
        "verdict_sample": "held-out",
    }
    if not hmmscan or not hmmpress or not HELDOUT_GZ.is_file() or not SECONDARY_GZ.is_file() or not REF_GZ.is_file():
        meta.update({"verdict": "INCONCLUSIVE", "reason": "missing binary or data"})
        _dump(meta)
        _log("INCONCLUSIVE missing binary or data")
        return 0

    _log("cataloguing reference")
    catalog = _catalog(REF_GZ)
    key_to_index: dict[str, int] = {}
    for index, (name, acc) in enumerate(catalog):
        for token in _keys_for(name, acc):
            key_to_index.setdefault(token, index)
    try:
        press = _press_full(hmmpress, REF_GZ, WORK / "pfam38.2.hmm")
    except Exception as exc:
        meta.update({"verdict": "INCONCLUSIVE", "reason": f"press failed: {exc}"})
        _dump(meta)
        _log(f"INCONCLUSIVE {exc}")
        return 0

    specs = (
        {
            "name": "held-out",
            "decides_verdict": True,
            "query_gz": HELDOUT_GZ,
            "query_seed": 20261016,
            "fill_seed": 20261016,
            "label": "SAMPLE-CONSTRUCTION",
        },
        {
            "name": "secondary",
            "decides_verdict": False,
            "query_gz": SECONDARY_GZ,
            "query_seed": 20261012,
            "fill_seed": 20261015,
            "label": "SECONDARY-SAMPLE",
        },
    )
    built: dict[str, dict] = {}
    meta["samples"] = {}
    for spec in specs:
        sample = _construct(spec, catalog, key_to_index, press, hmmscan)
        meta["samples"][spec["name"]] = sample["construction"]
        _dump(meta)
        if sample.get("stop"):
            _log(f"{spec['name']} construction stopped: {sample['construction'].get('reason')}")
            continue
        built[spec["name"]] = sample
    _drop_full_press(WORK / "pfam38.2.hmm")

    meta["samples_ran"] = {}
    for spec in specs:
        sample = built.get(spec["name"])
        if sample is None:
            continue
        _log(f"running {spec['name']}")
        ran = _run_sample(spec, sample, help_text, hmmscan, hmmpress)
        meta["samples_ran"][spec["name"]] = ran
        _dump(meta)
        _log(f"{spec['name']} arms done")

    if "held-out" not in built:
        meta["verdict"] = "INCONCLUSIVE"
        meta["reason"] = (meta["samples"].get("held-out") or {}).get("reason", "held-out sample was not built")
        meta["held_out_verdicts"] = {}
        _dump(meta)
        _log(f"INCONCLUSIVE {meta['reason']}")
        return 0
    held = meta["samples_ran"].get("held-out") or {}
    verdicts = {name: (held.get("arms") or {}).get(name, {}).get("verdict") for name in ("K1s-a", "K1s-b")}
    if any(value == "KILL" for value in verdicts.values()):
        meta["verdict"] = "KILL"
    elif verdicts == {"K1s-a": "PASS", "K1s-b": "PASS"}:
        meta["verdict"] = "PASS"
    else:
        meta["verdict"] = "INCONCLUSIVE"
        meta["reason"] = "held-out arms did not both pass"
    meta["held_out_verdicts"] = verdicts
    _dump(meta)
    _log(f"overall {meta['verdict']} held-out {verdicts}")
    return 0


def _construct(spec: dict, catalog: list[tuple[str, str]], key_to_index: dict[str, int], press: dict, hmmscan: str) -> dict:
    name = spec["name"]
    all_records = read_records(spec["query_gz"])
    construction: dict = {
        "label": spec["label"],
        "genome": spec["query_gz"].name,
        "query_seed": spec["query_seed"],
        "fill_seed": spec["fill_seed"],
        "decides_verdict": spec["decides_verdict"],
        "press": press,
        "model_total": len(catalog),
    }
    if len(all_records) < N_DRAW:
        construction.update({"stop": True, "reason": f"only {len(all_records)} records"})
        return {"stop": True, "construction": construction}
    draw = sorted(random.Random(spec["query_seed"]).sample(range(len(all_records)), N_DRAW))
    drawn = [all_records[i] for i in draw]
    queries = WORK / f"{name}_q300.faa"
    write_record_file(drawn, queries)
    tbl_path = WORK / f"{name}_construct.tbl"
    dom_path = WORK / f"{name}_construct.dom"
    cmd = [
        hmmscan,
        "--noali",
        "--tblout",
        str(tbl_path),
        "--domtblout",
        str(dom_path),
        str(WORK / "pfam38.2.hmm"),
        str(queries),
    ]
    _log(f"{spec['label']} scan of 300 against full reference")
    started = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - started
    construction["wall_s"] = wall
    if proc.returncode != 0:
        construction.update(
            {
                "stop": True,
                "reason": f"construction scan failed ({proc.returncode}): {(proc.stderr or '')[-500:]}",
            }
        )
        return {"stop": True, "construction": construction}
    body = _body_fields(tbl_path.read_text())
    construction["tblout_body_rows"] = len(body)
    construction["domtblout_body_rows"] = len(_body_fields(dom_path.read_text()))
    construction["tblout_header"] = _headers(tbl_path.read_text())[:3]
    construction["domtblout_header"] = _headers(dom_path.read_text())[:3]
    _log(f"{name} construction wall={wall:.1f}s tblout_body={len(body)}")
    queries_with_hits = {fields[2] for fields in body if len(fields) >= 3}
    q_index = [i for i in draw if all_records[i].name in queries_with_hits][:N_QUERY]
    construction["queries_with_hits_in_draw"] = len(queries_with_hits)
    if len(q_index) < N_QUERY:
        construction.update({"stop": True, "reason": f"only {len(q_index)} of the draw have a tblout row"})
        return {"stop": True, "construction": construction}
    q_names = {all_records[i].name for i in q_index}
    hit_indices: set[int] = set()
    unmatched: set[str] = set()
    q_rows = 0
    for fields in body:
        if len(fields) < 3 or fields[2] not in q_names:
            continue
        q_rows += 1
        index = key_to_index.get(fields[0])
        if index is None:
            index = key_to_index.get(fields[1])
        if index is None:
            unmatched.add(fields[0])
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
            construction.update({"stop": True, "reason": f"only {len(hit_sorted)} hit models and {len(pool)} fill"})
            return {"stop": True, "construction": construction}
        fill_global = random.Random(spec["fill_seed"]).sample(pool, need)
        w_global = sorted(hit_sorted + fill_global)
    if len(w_global) < N_MODELS:
        construction.update({"stop": True, "reason": f"|W|={len(w_global)}"})
        return {"stop": True, "construction": construction}
    want = set(w_global)
    _log(f"{name} extracting {len(want)} models")
    blocks = [raw for index, raw in enumerate(iter_profile_raw(REF_GZ)) if index in want]
    if len(blocks) != len(want):
        raise RuntimeError(f"extracted {len(blocks)} of {len(want)}")
    entries = parse_reference_text("".join(blocks))
    if len(entries) != N_MODELS:
        raise RuntimeError(f"parsed {len(entries)} models")
    hit_set = set(hit_sorted)
    hit_pos = [k for k, gi in enumerate(w_global) if gi in hit_set]
    fill_pos = [k for k, gi in enumerate(w_global) if gi not in hit_set]
    h_pos = _select_h(hit_pos, fill_pos, spec["fill_seed"])
    h_set = set(h_pos)
    complement = [k for k in range(N_MODELS) if k not in h_set]
    if len(complement) != N_HALF or len(h_pos) != N_HALF:
        raise RuntimeError("partition is not 200/200")
    construction.update(
        {
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
            "query_names": [all_records[i].name for i in q_index],
        }
    )
    records = [all_records[i] for i in q_index]
    write_record_file(records, WORK / f"{name}_queries.faa")
    return {
        "stop": False,
        "construction": construction,
        "records": records,
        "entries": entries,
        "h_pos": h_pos,
        "complement": complement,
        "query_path": WORK / f"{name}_queries.faa",
    }


def _run_sample(spec: dict, sample: dict, help_text: str, hmmscan: str, hmmpress: str) -> dict:
    name = spec["name"]
    records = sample["records"]
    entries = sample["entries"]
    h_pos = sample["h_pos"]
    complement = sample["complement"]
    half = [entries[i] for i in h_pos]
    half_keys = {token for entry in half for token in entry.keys}
    scans = {"n": 0}
    cache: dict[tuple, dict[str, str]] = {}

    def reference_file(subset) -> Path:
        digest = hashlib.sha256("".join(entry.content_hash for entry in subset).encode()).hexdigest()[:16]
        path = WORK / f"{name}-{digest}.hmm"
        if path.exists() and Path(str(path) + ".h3m").exists():
            return path
        write_entries(list(subset), path)
        _log(f"press {name} {len(subset)} models")
        proc_press = subprocess.run(
            [hmmpress, "-f", str(path)], check=False, capture_output=True, text=True
        )
        if proc_press.returncode != 0:
            detail = (proc_press.stderr or proc_press.stdout or "")[-500:]
            raise RuntimeError(f"press failed ({proc_press.returncode}): {detail}")
        return path

    def scan(subset, extra: list[str], arm: str) -> dict[str, str]:
        key = (name, arm, tuple(entry.content_hash for entry in subset), tuple(extra))
        if key in cache:
            return cache[key]
        paired = list(extra)
        for index, token in enumerate(paired):
            if token == "--cpu" and index + 1 < len(paired) and paired[index + 1] != "1":
                raise RuntimeError("worker-count probe refused")
        scans["n"] += 1
        ref = reference_file(subset)
        call = WORK / f"{name}-{arm}-call{scans['n']}"
        call.mkdir(parents=True, exist_ok=True)
        base = [hmmscan, "--noali", "--cpu", "1", "--tblout", str(call / "tbl"), "--domtblout", str(call / "dom")]
        if arm == "K1s-a":
            base.insert(1, "--cut_ga")
        cmd_scan = apply_extra_argv(base, paired) + [str(ref), str(sample["query_path"])]
        t0 = time.perf_counter()
        proc_scan = subprocess.run(cmd_scan, check=False, capture_output=True, text=True)
        elapsed = time.perf_counter() - t0
        _log(f"scan {name} {scans['n']} {arm} n={len(subset)} extra={paired} {elapsed:.1f}s rc={proc_scan.returncode}")
        if proc_scan.returncode != 0:
            detail = (proc_scan.stderr or proc_scan.stdout or "")[-400:]
            raise RuntimeError(f"tool failed ({proc_scan.returncode}): {detail}")
        tables = {}
        for slot in ("tbl", "dom"):
            dest = call / slot
            if not dest.is_file():
                raise RuntimeError(f"tool did not write {slot}")
            tables[slot] = dest.read_text()
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
            "tblout_header": _headers(whole_out["tbl"])[:3],
            "domtblout_header": _headers(whole_out["dom"])[:3],
        }

    def run_arm(arm: str, monotone: bool) -> dict:
        _log(f"{name} {arm} power floor")
        try:
            floor = shared_count(arm)
        except Exception as exc:
            return {"verdict": "INCONCLUSIVE", "reason": f"power floor failed: {exc}", "tool_calls": 0, "P": 0}
        _log(f"{name} {arm} shared={floor['shared_tblout_rows_on_H']}")
        if floor["shared_tblout_rows_on_H"] < POWER_FLOOR:
            return {
                "verdict": "INCONCLUSIVE",
                "reason": f"power floor {floor['shared_tblout_rows_on_H']} < {POWER_FLOOR}",
                "power_floor": floor,
                "tool_calls": 0,
                "P": 0,
            }
        _log(f"{name} {arm} fitting monotone={monotone}")
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
        summary = _fit_summary(fit)
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
        _log(f"{name} {arm} inferring")
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
            "structural": result.get("structural"),
            "reason_pin": result.get("reason"),
            "rejected": result.get("rejected"),
            "candidates": result.get("candidates"),
            "members": result.get("members"),
            "tool_calls": result.get("tool_calls"),
            "P": result.get("tool_calls"),
        }

    out: dict = {"arms": {}, "subprocess_calls": 0}
    arm_b = run_arm("K1s-b", True)
    out["arms"]["K1s-b"] = arm_b
    if arm_b.get("verdict") == "INCONCLUSIVE" and "power floor" in str(arm_b.get("reason")):
        out["verdict"] = "INCONCLUSIVE"
        out["reason"] = arm_b["reason"]
        out["subprocess_calls"] = scans["n"]
        return out
    arm_a = run_arm("K1s-a", False)
    out["arms"]["K1s-a"] = arm_a
    out["subprocess_calls"] = scans["n"]
    return out


if __name__ == "__main__":
    raise SystemExit(main())
