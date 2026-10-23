"""TARE console run engine.

Projects, references, inputs, presets and runs live under tools/tare-console/state/
(git-ignored). A run calls `python3 -m acts run --strategy reference` once per
input, in a background worker, and streams its output into the run log. Nothing
here is simulated: every count, time and outcome comes from the acts output
directory (decision.txt, tables/) or from a stock tool run.

The demo project is built from the local Pfam 38.1 and 38.2 files: a fixed
subset of families (first SUBSET_FAMILIES of 38.1, the same families from 38.2,
plus up to SUBSET_NEW families that are new in 38.2) and ten 200-protein slices
of the three local E. coli proteomes.
"""

from __future__ import annotations

import ast
import gzip
import hashlib
import io
import json
import os
import platform
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
PIPE = REPO / "pipeline"
DATA = PIPE / "data"
STATE = ROOT / "state"
PROJECTS = STATE / "projects"
REFS = STATE / "references"
INPUTS = STATE / "inputs"
EVENTS = STATE / "events.jsonl"
PRESETS = STATE / "presets.json"
RECENT = STATE / "recent.json"

sys.path.insert(0, str(PIPE))
from acts.reference_formats import parse_reference  # noqa: E402

SUBSET_FAMILIES = 1000
SUBSET_NEW = 60
SLICE = 200
DEMO_ID = "pfam-release-update"

LOCK = threading.RLock()

TOOLS = {
    "hmmer": {
        "id": "hmmer",
        "label": "HMMER",
        "program": "hmmscan",
        "prep": "hmmpress",
        "prep_cmd": "hmmpress -f {reference}",
        "outputs": ("tblout", "domtblout"),
        "supported": True,
        "default_args": "--cut_ga --noali",
    },
    "infernal": {
        "id": "infernal",
        "label": "Infernal",
        "program": "cmscan",
        "prep": "cmpress",
        "prep_cmd": "cmpress -F {reference}",
        "outputs": ("tblout",),
        "supported": False,
        "default_args": "--cut_ga --nohmmonly",
    },
    "diamond": {
        "id": "diamond",
        "label": "DIAMOND",
        "program": "diamond",
        "prep": "diamond",
        "prep_cmd": None,
        "outputs": ("out",),
        "supported": False,
        "default_args": "blastp --outfmt 6",
    },
    "blast": {
        "id": "blast",
        "label": "BLAST+",
        "program": "blastp",
        "prep": "makeblastdb",
        "prep_cmd": None,
        "outputs": ("out",),
        "supported": False,
        "default_args": "-outfmt 6",
    },
}

PIN_TEMPLATES = {"default": "-Z {entry_count}"}


# ---------------------------------------------------------------- helpers


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    tmp.replace(path)


def rel(path: Path | str) -> str:
    path = Path(path)
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dir_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def event(kind: str, message: str, **extra: Any) -> None:
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    row = {"t": now(), "kind": kind, "message": message, **extra}
    with LOCK, EVENTS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def events(limit: int = 200, project: str | None = None) -> list[dict[str, Any]]:
    if not EVENTS.is_file():
        return []
    rows = []
    for line in EVENTS.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if project and row.get("project") not in (None, project):
            continue
        rows.append(row)
    return rows[-limit:][::-1]


def parse_limit(text: str) -> int | None:
    text = (text or "").strip()
    if not text:
        return None
    parts = [int(p) for p in text.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    hours, minutes, seconds = parts[-3:]
    return hours * 3600 + minutes * 60 + seconds


def count_fasta(path: Path) -> tuple[int, int]:
    records = residues = 0
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as handle:
        for line in handle:
            if line.startswith(">"):
                records += 1
            else:
                residues += len(line.strip())
    return records, residues


# ---------------------------------------------------------------- tools


_TOOL_CACHE: dict[str, Any] = {}


def detect_tools(refresh: bool = False) -> list[dict[str, Any]]:
    if _TOOL_CACHE and not refresh:
        return _TOOL_CACHE["tools"]
    rows = []
    for tool in TOOLS.values():
        binary = shutil.which(tool["program"])
        prep = shutil.which(tool["prep"]) if tool["prep"] else None
        version = None
        if binary:
            try:
                out = subprocess.run([binary, "-h"], capture_output=True, text=True, timeout=10).stdout
                match = re.search(r"HMMER\s+([\d.]+)|INFERNAL\s+([\d.]+)", out)
                if match:
                    version = next(g for g in match.groups() if g)
                if tool["id"] == "diamond":
                    out = subprocess.run([binary, "version"], capture_output=True, text=True, timeout=10).stdout
                    version = out.strip().split()[-1] if out.strip() else None
                if tool["id"] == "blast":
                    out = subprocess.run([binary, "-version"], capture_output=True, text=True, timeout=10).stdout
                    match = re.search(r"([\d.]+)", out)
                    version = match.group(1) if match else None
            except (OSError, subprocess.SubprocessError):
                pass
        rows.append(
            {
                **{k: v for k, v in tool.items() if k != "outputs"},
                "binary": binary,
                "prep_binary": prep,
                "installed": bool(binary and (prep or not tool["prep"])),
                "version": version,
                "runnable": bool(binary and prep and tool["supported"]),
            }
        )
    _TOOL_CACHE["tools"] = rows
    return rows


def tool_row(tool_id: str) -> dict[str, Any]:
    for row in detect_tools():
        if row["id"] == tool_id:
            return row
    raise KeyError(tool_id)


# ---------------------------------------------------------------- references


def _blocks(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as handle:
        block: list[str] = []
        for line in handle:
            block.append(line)
            if line.startswith("//"):
                yield block
                block = []


def _acc(block: list[str]) -> str | None:
    for line in block:
        if line.startswith("ACC "):
            return line.split()[1].split(".")[0]
    return None


def _release(path: Path) -> str | None:
    version = path.parent / "Pfam.version.gz"
    if not version.is_file():
        return None
    with gzip.open(version, "rt") as handle:
        for line in handle:
            if line.startswith("Pfam release"):
                return line.split(":", 1)[1].strip()
    return None


def register_reference(path: Path, label: str, *, ref_id: str | None = None, note: str = "") -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"no such file: {path}")
    entries = parse_reference(path)
    ref_id = ref_id or re.sub(r"[^a-z0-9.]+", "-", label.lower()).strip("-")
    dest = REFS / ref_id
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / path.name
    if target.resolve() != path:
        shutil.copy2(path, target)
    meta = {
        "id": ref_id,
        "label": label,
        "path": rel(target),
        "entries": len(entries),
        "length": sum(e.length for e in entries),
        "format": entries[0].format_name if entries else None,
        "sha256": sha256_file(target),
        "bytes": target.stat().st_size,
        "note": note,
        "imported_at": now(),
    }
    write_json(dest / "meta.json", meta)
    event("reference", f"Imported reference {label} ({len(entries):,} entries)", ref=ref_id)
    return meta


def references() -> list[dict[str, Any]]:
    rows = []
    if REFS.is_dir():
        for meta in sorted(REFS.glob("*/meta.json")):
            row = read_json(meta)
            if row:
                rows.append(row)
    return rows


def reference(ref_id: str) -> dict[str, Any]:
    meta = read_json(REFS / ref_id / "meta.json")
    if not meta:
        raise KeyError(ref_id)
    return meta


def ref_path(ref_id: str) -> Path:
    return REPO / reference(ref_id)["path"]


_DIFF_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


def reference_diff(old_id: str, new_id: str) -> dict[str, Any]:
    old_meta, new_meta = reference(old_id), reference(new_id)
    key = (old_meta["sha256"], new_meta["sha256"])
    if key in _DIFF_CACHE:
        return _DIFF_CACHE[key]
    old = parse_reference(ref_path(old_id))
    new = parse_reference(ref_path(new_id))
    old_hash = {e.content_hash for e in old}
    old_keys = {e.primary for e in old}
    new_keys = {e.primary for e in new}
    unchanged = [e for e in new if e.content_hash in old_hash]
    changed = [e for e in new if e.content_hash not in old_hash and e.primary in old_keys]
    added = [e for e in new if e.primary not in old_keys]
    removed = sorted(old_keys - new_keys)
    length_new = sum(e.length for e in new)
    length_fresh = length_new - sum(e.length for e in unchanged)
    result = {
        "old": old_meta["label"],
        "new": new_meta["label"],
        "n_old": len(old),
        "n_new": len(new),
        "unchanged": len(unchanged),
        "changed": len(changed),
        "added": len(added),
        "removed": len(removed),
        "rerun": len(changed) + len(added),
        "length_new": length_new,
        "length_fresh": length_fresh,
        "rerun_fraction_length": length_fresh / length_new if length_new else 0.0,
        "examples": {
            "changed": [e.primary for e in changed[:12]],
            "added": [e.primary for e in added[:12]],
            "removed": removed[:12],
        },
    }
    _DIFF_CACHE[key] = result
    return result


def pressed(ref_id: str) -> Path:
    """A stock-pressed copy of a reference, for full comparison runs."""
    src = ref_path(ref_id)
    dest = REFS / ref_id / "pressed" / src.name
    if not (dest.parent / (src.name + ".h3m")).is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        subprocess.run(["hmmpress", "-f", str(dest)], check=True, capture_output=True, text=True)
    return dest


# ---------------------------------------------------------------- demo setup


SETUP: dict[str, Any] = {"state": "idle", "message": "", "error": None}


def demo_ready() -> bool:
    return (PROJECTS / DEMO_ID / "project.json").is_file()


def _build_demo() -> None:
    old_src = DATA / "hmmer" / "pfam38.1" / "Pfam-A.hmm.gz"
    new_src = DATA / "hmmer" / "Pfam-A.hmm.gz"
    for path in (old_src, new_src):
        if not path.is_file():
            raise FileNotFoundError(f"missing {rel(path)}")
    old_label = f"Pfam {_release(old_src) or '38.1'}"
    new_label = f"Pfam {_release(new_src) or '38.2'}"

    SETUP["message"] = f"Reading {old_label} families"
    keep_old: list[list[str]] = []
    subset: set[str] = set()
    all_old: set[str] = set()
    for block in _blocks(old_src):
        acc = _acc(block)
        if acc:
            all_old.add(acc)
        if len(keep_old) < SUBSET_FAMILIES:
            keep_old.append(block)
            if acc:
                subset.add(acc)

    SETUP["message"] = f"Reading {new_label} families"
    keep_new: list[list[str]] = []
    n_new = 0
    for block in _blocks(new_src):
        acc = _acc(block)
        if acc in subset:
            keep_new.append(block)
        elif acc and acc not in all_old and n_new < SUBSET_NEW:
            keep_new.append(block)
            n_new += 1

    tmp = STATE / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    note = (
        f"Subset: the first {SUBSET_FAMILIES} families of Pfam 38.1, the same families "
        f"from 38.2, and {SUBSET_NEW} families new in 38.2."
    )
    pairs = ((old_label, keep_old, "pfam-38.1-subset"), (new_label, keep_new, "pfam-38.2-subset"))
    metas = []
    for label, blocks, ref_id in pairs:
        SETUP["message"] = f"Registering {label}"
        out = tmp / "Pfam-A.hmm"
        with out.open("w") as handle:
            for block in blocks:
                handle.writelines(block)
        metas.append(register_reference(out, label, ref_id=ref_id, note=note))
        out.unlink()

    SETUP["message"] = "Slicing proteomes"
    INPUTS.mkdir(parents=True, exist_ok=True)
    plan = (("MG1655", 4), ("W3110", 3), ("BW25113", 3))
    inputs = []
    for strain, n_slices in plan:
        records: list[str] = []
        with gzip.open(DATA / "kprot" / f"{strain}.faa.gz", "rt") as handle:
            current: list[str] = []
            for line in handle:
                if line.startswith(">"):
                    if current:
                        records.append("".join(current))
                    current = []
                    if len(records) >= SLICE * n_slices:
                        break
                current.append(line)
            if current and len(records) < SLICE * n_slices:
                records.append("".join(current))
        for i in range(n_slices):
            lo, hi = i * SLICE, (i + 1) * SLICE
            name = f"{strain}_{lo + 1:04d}-{hi:04d}.faa"
            path = INPUTS / name
            path.write_text("".join(records[lo:hi]))
            inputs.append(_input_row(path, f"{strain} · proteins {lo + 1}–{hi}"))
    for i, row in enumerate(inputs):
        row["id"] = f"proteome_{i + 1:03d}"

    SETUP["message"] = "Creating project"
    project = _new_project(
        DEMO_ID,
        "Pfam release update",
        tool="hmmer",
        inputs=inputs,
        old_ref=metas[0]["id"],
        new_ref=metas[1]["id"],
    )
    save_project(project)
    touch_recent(DEMO_ID)
    event("project", "Created demo project Pfam release update", project=DEMO_ID)


def ensure_demo(background: bool = True) -> None:
    if demo_ready() or SETUP["state"] == "running":
        return

    def work() -> None:
        SETUP.update(state="running", error=None, message="Starting")
        try:
            _build_demo()
            SETUP.update(state="done", message="Demo project ready")
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            SETUP.update(state="error", error=f"{type(exc).__name__}: {exc}")

    if background:
        threading.Thread(target=work, daemon=True).start()
    else:
        work()


# ---------------------------------------------------------------- projects


def _input_row(path: Path, label: str | None = None) -> dict[str, Any]:
    records, residues = count_fasta(path)
    return {
        "id": path.stem,
        "name": path.stem,
        "label": label or path.name,
        "path": rel(path),
        "records": records,
        "residues": residues,
        "bytes": path.stat().st_size,
    }


def default_settings(tool: str = "hmmer") -> dict[str, Any]:
    return {
        "compute": "local",
        "threads": 4,
        "memory_gb": 32,
        "time_limit": "02:00:00",
        "arguments": TOOLS[tool]["default_args"],
        "pin": "default",
        "pin_template": PIN_TEMPLATES["default"],
        "verify": "audit",
        "output_dir": "",
    }


def _new_project(pid: str, name: str, *, tool: str, inputs: list, old_ref: str | None, new_ref: str | None) -> dict:
    return {
        "id": pid,
        "name": name,
        "tool": tool,
        "inputs": inputs,
        "references": {"old": old_ref, "new": new_ref},
        "settings": default_settings(tool),
        "settings_recorded_at": now(),
        "cache": {"built_against": None, "built_at": None, "built_by": None},
        "presets": [],
        "next_run": 1,
        "created_at": now(),
        "updated_at": now(),
    }


def project_dir(pid: str) -> Path:
    return PROJECTS / pid


def load_project(pid: str) -> dict[str, Any]:
    project = read_json(project_dir(pid) / "project.json")
    if not project:
        raise KeyError(pid)
    return project


def save_project(project: dict[str, Any]) -> None:
    with LOCK:
        project["updated_at"] = now()
        write_json(project_dir(project["id"]) / "project.json", project)


def list_projects() -> list[dict[str, Any]]:
    rows = []
    if PROJECTS.is_dir():
        for path in sorted(PROJECTS.glob("*/project.json")):
            project = read_json(path)
            if project:
                rows.append(project)
    return rows


def touch_recent(pid: str) -> None:
    with LOCK:
        recent = [p for p in (read_json(RECENT, []) or []) if p != pid]
        write_json(RECENT, [pid, *recent][:8])


def recent_projects() -> list[dict[str, Any]]:
    rows = []
    for pid in read_json(RECENT, []) or []:
        try:
            project = load_project(pid)
        except KeyError:
            continue
        rows.append({"id": pid, "name": project["name"]})
    return rows


def create_project(name: str, tool: str = "hmmer", copy_from: str | None = None) -> dict[str, Any]:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"
    pid = base
    n = 2
    while project_dir(pid).exists():
        pid = f"{base}-{n}"
        n += 1
    inputs, old_ref, new_ref = [], None, None
    if copy_from:
        src = load_project(copy_from)
        inputs, old_ref, new_ref = src["inputs"], src["references"]["old"], src["references"]["new"]
        tool = src["tool"]
    project = _new_project(pid, name, tool=tool, inputs=inputs, old_ref=old_ref, new_ref=new_ref)
    save_project(project)
    touch_recent(pid)
    event("project", f"Created project {name}", project=pid)
    return project


def cache_path(project: dict[str, Any]) -> Path:
    return project_dir(project["id"]) / "cache.sqlite"


SETTING_KEYS = {
    "compute": str,
    "threads": int,
    "memory_gb": int,
    "time_limit": str,
    "arguments": str,
    "pin": str,
    "pin_template": str,
    "verify": str,
    "output_dir": str,
}


def update_settings(pid: str, changes: dict[str, Any]) -> dict[str, Any]:
    with LOCK:
        project = load_project(pid)
        clean = {}
        for key, value in changes.items():
            if key not in SETTING_KEYS:
                continue
            clean[key] = SETTING_KEYS[key](value)
        if "threads" in clean and not 1 <= clean["threads"] <= 256:
            raise ValueError("threads must be 1–256")
        if "memory_gb" in clean and not 1 <= clean["memory_gb"] <= 4096:
            raise ValueError("memory must be 1–4096 GB")
        if "time_limit" in clean:
            parse_limit(clean["time_limit"])
        if clean.get("pin") not in (None, "default", "infer", "custom"):
            raise ValueError("pin must be default, infer or custom")
        if clean.get("verify") not in (None, "audit", "full"):
            raise ValueError("verify must be audit or full")
        if clean.get("compute") not in (None, "local", "carc"):
            raise ValueError("compute must be local or carc")
        if "arguments" in clean:
            shlex.split(clean["arguments"])
        project["settings"].update(clean)
        project["settings_recorded_at"] = now()
        save_project(project)
    if clean:
        event("settings", "Changed " + ", ".join(f"{k}={v}" for k, v in clean.items()), project=pid)
    return project


def add_inputs(pid: str, paths: list[str]) -> dict[str, Any]:
    added = []
    with LOCK:
        project = load_project(pid)
        have = {i["path"] for i in project["inputs"]}
        for raw in paths:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = (REPO / path).resolve()
            if not path.is_file():
                raise ValueError(f"no such file: {raw}")
            row = _input_row(path)
            if row["records"] == 0:
                raise ValueError(f"no FASTA records in {raw}")
            if row["path"] in have:
                continue
            ids = {i["id"] for i in project["inputs"]}
            row["id"] = f"proteome_{len(ids) + 1:03d}"
            while row["id"] in ids:
                row["id"] += "b"
            project["inputs"].append(row)
            added.append(row["label"])
        save_project(project)
    if added:
        event("inputs", "Added inputs " + ", ".join(added), project=pid)
    return project


def remove_input(pid: str, input_id: str) -> dict[str, Any]:
    with LOCK:
        project = load_project(pid)
        project["inputs"] = [i for i in project["inputs"] if i["id"] != input_id]
        save_project(project)
    event("inputs", f"Removed input {input_id}", project=pid)
    return project


def set_tool(pid: str, tool: str) -> dict[str, Any]:
    if tool not in TOOLS:
        raise ValueError(f"unknown tool {tool}")
    row = tool_row(tool)
    if not row["runnable"]:
        why = "not installed on this machine" if not row["installed"] else "not wired into the console yet"
        raise ValueError(f"{row['label']} is {why}")
    with LOCK:
        project = load_project(pid)
        project["tool"] = tool
        save_project(project)
    event("tool", f"Selected tool {row['label']} {row['program']}", project=pid)
    return project


def set_references(pid: str, old: str | None, new: str | None) -> dict[str, Any]:
    for ref_id in (old, new):
        if ref_id:
            reference(ref_id)
    with LOCK:
        project = load_project(pid)
        project["references"] = {"old": old, "new": new}
        save_project(project)
    event("references", f"References set: {old} → {new}", project=pid)
    return project


def presets() -> list[dict[str, Any]]:
    return read_json(PRESETS, []) or []


def save_preset(pid: str, name: str) -> dict[str, Any]:
    project = load_project(pid)
    rows = [p for p in presets() if p["name"] != name]
    row = {"name": name, "tool": project["tool"], "settings": dict(project["settings"]), "saved_at": now()}
    rows.append(row)
    write_json(PRESETS, rows)
    event("preset", f"Saved preset {name}", project=pid)
    return row


def apply_preset(pid: str, name: str) -> dict[str, Any]:
    for row in presets():
        if row["name"] == name:
            project = update_settings(pid, row["settings"])
            event("preset", f"Applied preset {name}", project=pid)
            return project
    raise KeyError(name)


# ---------------------------------------------------------------- preflight


def build_argv(project: dict[str, Any], *, input_path: Path, ref: Path, out: Path, settings: dict | None = None) -> list[str]:
    settings = settings or project["settings"]
    tool = TOOLS[project["tool"]]
    pin = settings.get("pin", "default")
    if pin == "default":
        pin_args = ["--pin", PIN_TEMPLATES["default"]]
    elif pin == "infer":
        pin_args = ["--pin"]
    else:
        pin_args = ["--pin", settings.get("pin_template") or PIN_TEMPLATES["default"]]
    return [
        sys.executable, "-m", "acts", "run",
        "--strategy", "reference",
        *pin_args,
        "--verify", settings.get("verify", "audit"),
        "--prep", tool["prep_cmd"],
        "--input", str(input_path),
        "--reference", str(ref),
        "--cache", str(cache_path(project)),
        "-o", str(out),
        "--",
        tool["program"],
        *shlex.split(settings.get("arguments", "")),
        "--cpu", str(settings.get("threads", 4)),
        "--tblout", "{output:tblout}",
        "--domtblout", "{output:domtblout}",
        "-o", "/dev/null",
        "{reference}", "{input}",
    ]


def command_preview(pid: str) -> dict[str, Any]:
    project = load_project(pid)
    new = project["references"].get("new")
    ref = ref_path(new) if new else Path("<new reference>")
    first = project["inputs"][0] if project["inputs"] else None
    argv = build_argv(
        project,
        input_path=REPO / first["path"] if first else Path("<input>"),
        ref=ref,
        out=project_dir(pid) / "runs" / "<run>" / "items" / (first["id"] if first else "<input>"),
    )
    argv[0] = "python3"
    return {
        "argv": argv,
        "shell": " ".join(shlex.quote(a) for a in argv),
        "cwd": rel(PIPE),
        "stock": f"{TOOLS[project['tool']]['program']} {project['settings']['arguments']} "
        f"--cpu {project['settings']['threads']} --tblout T --domtblout D -o /dev/null <reference> <input>",
        "recorded_at": project.get("settings_recorded_at"),
    }


def cache_compatible(project: dict[str, Any]) -> tuple[str, str]:
    cache = project.get("cache") or {}
    old = project["references"].get("old")
    path = cache_path(project)
    if not path.is_file() or path.stat().st_size == 0:
        return "missing", "No cache yet. Build it against the previous release first, or the update scans every family."
    built = cache.get("built_against") or []
    if isinstance(built, str):
        built = [built]
    if old and old in built:
        return "compatible", f"Cache holds results for {reference(old)['label']}."
    return "stale", "Cache was not built against the previous release; reuse will be partial."


def preflight(pid: str) -> dict[str, Any]:
    project = load_project(pid)
    checks: list[dict[str, Any]] = []

    def add(cid: str, title: str, status: str, detail: str) -> None:
        checks.append({"id": cid, "title": title, "status": status, "detail": detail})

    tool = tool_row(project["tool"])
    add(
        "tool",
        f"{tool['label']} {tool['program']} installed",
        "pass" if tool["binary"] else "fail",
        tool["binary"] or f"{tool['program']} not on PATH",
    )
    add(
        "prep",
        f"{tool['prep']} installed",
        "pass" if tool["prep_binary"] else "fail",
        tool["prep_binary"] or f"{tool['prep']} not on PATH",
    )
    acts_ok = (PIPE / "acts" / "__main__.py").is_file()
    add("acts", "TARE runner present", "pass" if acts_ok else "fail", rel(PIPE / "acts"))

    refs = project["references"]
    for side in ("old", "new"):
        ref_id = refs.get(side)
        title = "Previous release" if side == "old" else "New release"
        if not ref_id:
            add(f"ref_{side}", title, "fail", "not set")
            continue
        try:
            meta = reference(ref_id)
            ok = (REPO / meta["path"]).is_file()
            add(f"ref_{side}", title, "pass" if ok else "fail", f"{meta['label']} · {meta['entries']:,} entries")
        except KeyError:
            add(f"ref_{side}", title, "fail", f"unknown reference {ref_id}")

    missing = [i["label"] for i in project["inputs"] if not (REPO / i["path"]).is_file()]
    if not project["inputs"]:
        add("inputs", "Inputs", "fail", "no inputs added")
    elif missing:
        add("inputs", "Inputs", "fail", "missing: " + ", ".join(missing))
    else:
        n = sum(i["records"] for i in project["inputs"])
        add("inputs", "Inputs", "pass", f"{len(project['inputs'])} proteomes · {n:,} proteins")

    status, detail = cache_compatible(project)
    add("cache", "Cache", {"compatible": "pass", "missing": "warn", "stale": "warn"}[status], detail)

    settings = project["settings"]
    if settings["compute"] == "carc":
        add("compute", "Compute", "fail", "CARC execution is not wired into the console; choose This Mac")
    else:
        add("compute", "Compute", "pass", f"This Mac · {settings['threads']} threads")
    ncpu = os.cpu_count() or 1
    if settings["threads"] > ncpu:
        add("threads", "Threads", "warn", f"{settings['threads']} threads requested, {ncpu} cores present")
    free = shutil.disk_usage(STATE).free
    add("disk", "Disk space", "pass" if free > 5 << 30 else "warn", f"{free / (1 << 30):.0f} GB free")
    try:
        shlex.split(settings["arguments"])
        bad = [a for a in ("--tblout", "--domtblout", "-o", "-Z", "--cpu") if a in shlex.split(settings["arguments"])]
        add(
            "args",
            "Arguments",
            "warn" if bad else "pass",
            f"{', '.join(bad)} set by TARE; remove from arguments" if bad else settings["arguments"],
        )
    except ValueError as exc:
        add("args", "Arguments", "fail", str(exc))

    diff = None
    if refs.get("old") and refs.get("new"):
        try:
            diff = reference_diff(refs["old"], refs["new"])
        except Exception as exc:  # noqa: BLE001
            add("diff", "Reference comparison", "fail", str(exc))
    ok = all(c["status"] != "fail" for c in checks)
    return {"ok": ok, "checks": checks, "diff": diff, "checked_at": now()}


# ---------------------------------------------------------------- runs


def run_dir(pid: str, rid: str) -> Path:
    return project_dir(pid) / "runs" / rid


def split_rid(rid: str) -> tuple[str, str]:
    pid, _, _ = rid.rpartition("--")
    if not pid:
        raise KeyError(rid)
    return pid, rid


def load_run(rid: str) -> dict[str, Any]:
    pid, rid = split_rid(rid)
    run = read_json(run_dir(pid, rid) / "run.json")
    if not run:
        raise KeyError(rid)
    return run


def save_run(run: dict[str, Any]) -> None:
    with LOCK:
        write_json(run_dir(run["project"], run["id"]) / "run.json", run)


def list_runs(pid: str) -> list[dict[str, Any]]:
    root = project_dir(pid) / "runs"
    rows = []
    if root.is_dir():
        for path in root.glob("*/run.json"):
            run = read_json(path)
            if run:
                rows.append(run)
    rows.sort(key=lambda r: r["number"], reverse=True)
    return rows


def run_summary(run: dict[str, Any]) -> dict[str, Any]:
    items = run["items"]
    return {
        "id": run["id"],
        "name": run["name"],
        "kind": run["kind"],
        "status": run["status"],
        "stage": run["stage"],
        "number": run["number"],
        "created_at": run["created_at"],
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "n_items": len(items),
        "n_done": sum(1 for i in items if i["status"] in ("done", "refused")),
        "n_failed": sum(1 for i in items if i["status"] == "failed"),
        "wall_s": run.get("wall_s"),
    }


def log(run: dict[str, Any], message: str, level: str = "info", item: str | None = None) -> None:
    path = run_dir(run["project"], run["id"]) / "log.jsonl"
    row = {"t": now(), "level": level, "message": message}
    if item:
        row["item"] = item
    with LOCK, path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def read_log(rid: str, after: int = 0) -> dict[str, Any]:
    pid, rid = split_rid(rid)
    path = run_dir(pid, rid) / "log.jsonl"
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return {"total": len(rows), "rows": rows[after:]}


KIND_NAMES = {"update": "Update", "cache": "Cache build", "full": "Full run"}


def create_run(pid: str, kind: str, input_ids: list[str] | None = None, origin: str | None = None) -> dict[str, Any]:
    if kind not in KIND_NAMES:
        raise ValueError(f"unknown run kind {kind}")
    with LOCK:
        project = load_project(pid)
        if project["settings"]["compute"] != "local":
            raise ValueError("CARC execution is not wired into the console yet; set Compute to This Mac")
        refs = project["references"]
        if not refs.get("new") or (kind == "cache" and not refs.get("old")):
            raise ValueError("set both releases first")
        if not tool_row(project["tool"])["runnable"]:
            raise ValueError("selected tool is not runnable here")
        chosen = [i for i in project["inputs"] if not input_ids or i["id"] in input_ids]
        if not chosen:
            raise ValueError("no inputs selected")
        number = project["next_run"]
        project["next_run"] = number + 1
        save_project(project)
    rid = f"{pid}--{number:03d}"
    ref_id = refs["old"] if kind == "cache" else refs["new"]
    run = {
        "id": rid,
        "project": pid,
        "number": number,
        "name": f"{KIND_NAMES[kind]} {number:03d}",
        "kind": kind,
        "origin": origin,
        "status": "queued",
        "stage": "prepare",
        "created_at": now(),
        "started_at": None,
        "finished_at": None,
        "tool": project["tool"],
        "references": {"old": refs.get("old"), "new": refs.get("new"), "used": ref_id},
        "reference_labels": {
            side: reference(refs[side])["label"] for side in ("old", "new") if refs.get(side)
        },
        "settings": dict(project["settings"]),
        "diff": None,
        "items": [
            {
                "id": i["id"],
                "label": i["label"],
                "path": i["path"],
                "records": i["records"],
                "status": "queued",
                "stage_label": "Queued",
                "elapsed_s": None,
                "decision": None,
                "outcome": None,
                "full_compare": None,
            }
            for i in chosen
        ],
        "checks": [],
        "verification": None,
    }
    run_dir(pid, rid).mkdir(parents=True, exist_ok=True)
    save_run(run)
    log(run, f"{run['name']} queued: {len(chosen)} inputs, {KIND_NAMES[kind].lower()} against {reference(ref_id)['label']}")
    event("run", f"Queued {run['name']} ({len(chosen)} inputs)", project=pid, run=rid)
    WORKER.submit(rid)
    return run


def parse_decision(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if key in ("phases", "probe_phases"):
            try:
                out[key] = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                out[key] = {}
            continue
        if re.fullmatch(r"-?\d+", value):
            out[key] = int(value)
        elif re.fullmatch(r"-?\d+\.\d+(e-?\d+)?", value):
            out[key] = float(value)
        else:
            out[key] = value
    return out


def body_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [line for line in path.read_text().splitlines() if not line.startswith("#")]


def compare_bodies(replay: list[str], stock: list[str]) -> dict[str, Any]:
    if replay == stock:
        return {"byte_equal": True, "lines": len(stock), "classes": []}
    rk = Counter(" ".join(line.split()[:4]) for line in replay)
    sk = Counter(" ".join(line.split()[:4]) for line in stock)
    missing = sum((sk - rk).values())
    extra = sum((rk - sk).values())
    classes = []
    if missing:
        classes.append("missing")
    if extra:
        classes.append("extra")
    if not missing and not extra:
        token_equal = [line.split() for line in replay] == [line.split() for line in stock]
        classes.append("whitespace-only" if token_equal else ("order" if sorted(replay) == sorted(stock) else "value-only"))
    return {
        "byte_equal": False,
        "lines": len(stock),
        "lines_replay": len(replay),
        "missing": missing,
        "extra": extra,
        "classes": classes,
    }


class Worker:
    """One background thread; runs execute one at a time in queue order."""

    def __init__(self) -> None:
        self.queue: list[str] = []
        self.active: str | None = None
        self.proc: subprocess.Popen | None = None
        self.cancelled: set[str] = set()
        self.cond = threading.Condition()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def submit(self, rid: str) -> None:
        with self.cond:
            self.queue.append(rid)
            self.cond.notify()

    def cancel(self, rid: str) -> None:
        with self.cond:
            self.cancelled.add(rid)
            if rid in self.queue:
                self.queue.remove(rid)
                run = load_run(rid)
                run["status"] = "cancelled"
                run["finished_at"] = now()
                for item in run["items"]:
                    if item["status"] == "queued":
                        item.update(status="cancelled", stage_label="Cancelled")
                save_run(run)
                log(run, "Cancelled before start", "warn")
            proc = self.proc
        if self.active == rid and proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                pass

    def status(self) -> dict[str, Any]:
        return {"active": self.active, "queued": list(self.queue)}

    def _loop(self) -> None:
        while True:
            with self.cond:
                while not self.queue:
                    self.cond.wait()
                rid = self.queue.pop(0)
                self.active = rid
            try:
                self._execute(rid)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                try:
                    run = load_run(rid)
                    run["status"] = "failed"
                    run["error"] = f"{type(exc).__name__}: {exc}"
                    run["finished_at"] = now()
                    save_run(run)
                    log(run, f"Run failed: {exc}", "error")
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
            finally:
                with self.cond:
                    self.active = None
                    self.proc = None

    # -- one run

    def _stage(self, run: dict[str, Any], stage: str, message: str) -> None:
        run["stage"] = stage
        save_run(run)
        log(run, message)

    def _execute(self, rid: str) -> None:
        run = load_run(rid)
        if rid in self.cancelled:
            return
        project = load_project(run["project"])
        run["status"] = "running"
        run["started_at"] = now()
        t_run = time.monotonic()
        limit = parse_limit(run["settings"].get("time_limit", ""))
        self._stage(run, "prepare", "Preparing: checking tool, references and inputs")

        pre = preflight(run["project"])
        run["checks"] = [c for c in pre["checks"]]
        hard = [c for c in pre["checks"] if c["status"] == "fail"]
        for check in pre["checks"]:
            level = {"pass": "info", "warn": "warn", "fail": "error"}[check["status"]]
            if check["status"] != "pass":
                log(run, f"{check['title']}: {check['detail']}", level)
        if hard:
            run["status"] = "failed"
            run["error"] = "; ".join(f"{c['title']}: {c['detail']}" for c in hard)
            run["finished_at"] = now()
            save_run(run)
            log(run, "Preflight failed", "error")
            return
        log(run, "Reference compatibility checks passed")

        self._stage(run, "check", "Checking reuse: comparing releases")
        refs = run["references"]
        if run["kind"] == "update" and refs.get("old"):
            run["diff"] = reference_diff(refs["old"], refs["new"])
            d = run["diff"]
            log(run, f"{d['unchanged']:,} unchanged entries; {d['rerun']:,} changed or new; {d['removed']:,} removed")
        ref = ref_path(refs["used"])

        self._stage(run, "replay", "Replay: scanning changed entries and reusing cached results" if run["kind"] == "update" else "Scanning")
        for item in run["items"]:
            if item["status"] in ("done", "refused"):
                continue
            if rid in self.cancelled:
                item.update(status="cancelled", stage_label="Cancelled")
                continue
            if limit and time.monotonic() - t_run > limit:
                item.update(status="failed", stage_label="Time limit reached", error="run time limit reached")
                log(run, f"{item['label']}: time limit reached", "error", item["id"])
                continue
            self._item(run, project, item, ref, None if not limit else max(1, limit - (time.monotonic() - t_run)))
            save_run(run)

        if rid in self.cancelled:
            run["status"] = "cancelled"
            run["finished_at"] = now()
            run["wall_s"] = time.monotonic() - t_run
            save_run(run)
            log(run, "Run cancelled", "warn")
            event("run", f"Cancelled {run['name']}", project=run["project"], run=rid)
            return

        self._stage(run, "verify", "Verify: collecting sampled checks")
        run["verification"] = summarize_verification(run)
        if run["settings"].get("verify") == "full" and run["kind"] == "update":
            log(run, "Verification policy is full comparison: running the stock tool on each input")
            for item in run["items"]:
                if item["status"] == "done" and rid not in self.cancelled:
                    self._full_compare(run, project, item)
                    save_run(run)
            run["verification"] = summarize_verification(run)

        failed = [i for i in run["items"] if i["status"] == "failed"]
        run["status"] = "failed" if failed and len(failed) == len(run["items"]) else "completed"
        run["stage"] = "complete"
        run["finished_at"] = now()
        run["wall_s"] = time.monotonic() - t_run
        if run["kind"] in ("cache", "update") and any(i["status"] == "done" for i in run["items"]):
            with LOCK:
                project = load_project(run["project"])
                built = project["cache"].get("built_against") or []
                if isinstance(built, str):
                    built = [built]
                if refs["used"] not in built:
                    built.append(refs["used"])
                project["cache"] = {"built_against": built, "built_at": now(), "built_by": rid}
                save_project(project)
        save_run(run)
        msg = f"{run['name']} {run['status']}: {sum(1 for i in run['items'] if i['status'] == 'done')} of {len(run['items'])} inputs in {run['wall_s']:.1f}s"
        log(run, msg, "warn" if failed else "info")
        event("run", msg, project=run["project"], run=rid)

    def _item(self, run: dict, project: dict, item: dict, ref: Path, budget: float | None) -> None:
        out = run_dir(run["project"], run["id"]) / "items" / item["id"]
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        if run["kind"] == "full":
            self._stock_item(run, project, item, out, budget)
            return
        argv = build_argv(project, input_path=REPO / item["path"], ref=ref, out=out, settings=run["settings"])
        item.update(status="running", stage_label="Replaying changed entries" if run["kind"] == "update" else "Scanning all entries",
                    started_at=now(), argv=argv, error=None)
        save_run(run)
        log(run, f"{item['label']}: started", "info", item["id"])
        t0 = time.monotonic()
        lines: list[str] = []
        with (out / "stdout.txt").open("w") as sink:
            proc = subprocess.Popen(
                argv, cwd=PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True
            )
            with self.cond:
                self.proc = proc
            timer = None
            if budget:
                def kill() -> None:
                    if proc.poll() is None:
                        item["timed_out"] = True
                        os.killpg(proc.pid, signal.SIGTERM)
                timer = threading.Timer(budget, kill)
                timer.start()
            assert proc.stdout is not None
            for line in proc.stdout:
                sink.write(line)
                lines.append(line.rstrip())
                text = line.strip()
                if text and not text.startswith("wrote "):
                    log(run, f"{item['label']}: {text}", "warn" if "warn" in text.lower() else "info", item["id"])
            rc = proc.wait()
            if timer:
                timer.cancel()
        item["elapsed_s"] = time.monotonic() - t0
        item["returncode"] = rc
        for folder in ("calls", "calls_pinned", "calls_infer", "calls_slack"):
            if (out / folder).is_dir():
                shutil.rmtree(out / folder)
        decision = parse_decision(out / "decision.txt")
        item["decision"] = {k: v for k, v in decision.items() if k != "phases"} or None
        item["phases"] = decision.get("phases")
        if run["id"] in self.cancelled:
            item.update(status="cancelled", stage_label="Cancelled", outcome="Cancelled")
            log(run, f"{item['label']}: cancelled", "warn", item["id"])
            return
        if rc != 0 or not decision:
            reason = "time limit reached" if item.get("timed_out") else (lines[-1] if lines else f"exit {rc}")
            item.update(status="failed", stage_label="Failed", outcome="Failed", error=reason)
            log(run, f"{item['label']}: failed ({reason})", "error", item["id"])
            return
        verdict = str(decision.get("decision", ""))
        stable = int(decision.get("n_stable", 0) or 0)
        if verdict == "SHIP":
            item["status"] = "done"
            if run["kind"] == "update":
                item["stage_label"] = "Used cache (reuse)" if stable else "Scanned all (no reusable cache)"
            else:
                item["stage_label"] = "Cache filled"
            checks_ok = decision.get("ic2") in (None, "pass")
            item["outcome"] = "Checks passed" if checks_ok else "Check failed"
        else:
            item["status"] = "refused"
            item["stage_label"] = "Reuse declined"
            item["outcome"] = "Reuse declined"
            item["error"] = decision.get("why")
            log(run, f"{item['label']}: reuse declined ({decision.get('why')})", "warn", item["id"])
        log(run, f"{item['label']}: {item['outcome'].lower()} in {item['elapsed_s']:.1f}s"
                 f" · {stable} of {decision.get('n_entries', '?')} entries reused", "info", item["id"])

    def _stock_item(self, run: dict, project: dict, item: dict, out: Path, budget: float | None) -> None:
        tool = TOOLS[project["tool"]]
        tables = out / "tables"
        tables.mkdir()
        argv = [
            tool["program"], *shlex.split(run["settings"]["arguments"]), "--cpu", str(run["settings"]["threads"]),
            "--tblout", str(tables / "tblout"), "--domtblout", str(tables / "domtblout"), "-o", os.devnull,
            str(pressed(run["references"]["used"])), str(REPO / item["path"]),
        ]
        item.update(status="running", stage_label="Full scan (stock tool)", started_at=now(), argv=argv, error=None)
        save_run(run)
        log(run, f"{item['label']}: stock {tool['program']} started", "info", item["id"])
        t0 = time.monotonic()
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        with self.cond:
            self.proc = proc
        try:
            text, _ = proc.communicate(timeout=budget)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            text, _ = proc.communicate()
            item["timed_out"] = True
        item["elapsed_s"] = time.monotonic() - t0
        item["returncode"] = proc.returncode
        (out / "stdout.txt").write_text(text or "")
        if run["id"] in self.cancelled:
            item.update(status="cancelled", stage_label="Cancelled", outcome="Cancelled")
            return
        if proc.returncode != 0:
            reason = "time limit reached" if item.get("timed_out") else ((text or "").strip().splitlines() or [f"exit {proc.returncode}"])[-1]
            item.update(status="failed", stage_label="Failed", outcome="Failed", error=reason)
            log(run, f"{item['label']}: failed ({reason})", "error", item["id"])
            return
        rows = sum(len(body_lines(tables / name)) for name in tool["outputs"])
        item.update(status="done", stage_label="Full scan (stock tool)", outcome="Completed")
        log(run, f"{item['label']}: completed in {item['elapsed_s']:.1f}s · {rows} rows", "info", item["id"])

    def _full_compare(self, run: dict, project: dict, item: dict) -> None:
        compare_item(run, project, item)


def compare_item(run: dict, project: dict, item: dict) -> None:
    ref_id = run["references"]["used"]
    pressed_ref = pressed(ref_id)
    out = run_dir(run["project"], run["id"]) / "stock" / item["id"]
    out.mkdir(parents=True, exist_ok=True)
    tool = TOOLS[project["tool"]]
    argv = [
        tool["program"], *shlex.split(run["settings"]["arguments"]), "--cpu", str(run["settings"]["threads"]),
        "--tblout", str(out / "tblout"), "--domtblout", str(out / "domtblout"), "-o", os.devnull,
        str(pressed_ref), str(REPO / item["path"]),
    ]
    log(run, f"{item['label']}: full computation with stock {tool['program']}", "info", item["id"])
    t0 = time.monotonic()
    proc = subprocess.run(argv, capture_output=True, text=True)
    wall = time.monotonic() - t0
    if proc.returncode != 0:
        item["full_compare"] = {"error": (proc.stderr or proc.stdout).strip()[-300:], "argv": argv}
        log(run, f"{item['label']}: stock run failed", "error", item["id"])
        return
    tables = {}
    replay_dir = run_dir(run["project"], run["id"]) / "items" / item["id"] / "tables"
    for name in tool["outputs"]:
        tables[name] = compare_bodies(body_lines(replay_dir / name), body_lines(out / name))
    equal = all(t["byte_equal"] for t in tables.values())
    item["full_compare"] = {
        "byte_equal": equal,
        "tables": tables,
        "stock_wall_s": wall,
        "tare_wall_s": item.get("elapsed_s"),
        "speedup": (wall / item["elapsed_s"]) if item.get("elapsed_s") else None,
        "argv": argv,
        "compared_at": now(),
    }
    if equal:
        log(run, f"{item['label']}: output body byte-identical to full run ({sum(t['lines'] for t in tables.values())} lines)", "info", item["id"])
    else:
        classes = sorted({c for t in tables.values() for c in t["classes"]})
        log(run, f"{item['label']}: differs from full run ({', '.join(classes)})", "error", item["id"])


def summarize_verification(run: dict[str, Any]) -> dict[str, Any]:
    done = [i for i in run["items"] if i["status"] == "done"]
    audited = sum(int((i.get("decision") or {}).get("audit_checked", 0) or 0) for i in done)
    pads = sum(1 for i in done if (i.get("decision") or {}).get("ic2") == "pass")
    compared = [i for i in run["items"] if (i.get("full_compare") or {}).get("byte_equal") is not None]
    equal = [i for i in compared if i["full_compare"]["byte_equal"]]
    refused = [i for i in run["items"] if i["status"] == "refused"]
    return {
        "items_checked": len(done),
        "records_audited": audited,
        "neighbor_checks_passed": pads,
        "full_compared": len(compared),
        "full_equal": len(equal),
        "refused": len(refused),
        "policy": run["settings"].get("verify"),
        "state": (
            "differs" if len(equal) < len(compared)
            else "full" if compared and len(compared) == len(done) and done
            else "sampled" if done
            else "none"
        ),
    }


def full_compare(rid: str, input_ids: list[str] | None = None) -> dict[str, Any]:
    run = load_run(rid)
    if run["status"] == "running":
        raise ValueError("wait for the run to finish")
    project = load_project(run["project"])
    targets = [i for i in run["items"] if i["status"] == "done" and (not input_ids or i["id"] in input_ids)]
    if not targets:
        raise ValueError("no completed inputs to compare")

    def work() -> None:
        with LOCK:
            run2 = load_run(rid)
            run2["comparing"] = True
            save_run(run2)
        log(run2, f"Full computation started on {len(targets)} inputs")
        for target in targets:
            fresh = load_run(rid)
            item = next(i for i in fresh["items"] if i["id"] == target["id"])
            compare_item(fresh, project, item)
            fresh["verification"] = summarize_verification(fresh)
            save_run(fresh)
        fresh = load_run(rid)
        fresh["comparing"] = False
        fresh["verification"] = summarize_verification(fresh)
        save_run(fresh)
        v = fresh["verification"]
        log(fresh, f"Full comparison done: {v['full_equal']} of {v['full_compared']} byte-identical")
        event("verify", f"{fresh['name']}: {v['full_equal']} of {v['full_compared']} byte-identical to full run",
              project=fresh["project"], run=rid)

    threading.Thread(target=work, daemon=True).start()
    return {"started": len(targets)}


def retry_failed(rid: str) -> dict[str, Any]:
    run = load_run(rid)
    ids = [i["id"] for i in run["items"] if i["status"] in ("failed", "cancelled", "refused")]
    if not ids:
        raise ValueError("nothing to retry")
    return create_run(run["project"], run["kind"], ids, origin=rid)


def run_again(rid: str) -> dict[str, Any]:
    run = load_run(rid)
    return create_run(run["project"], run["kind"], [i["id"] for i in run["items"]], origin=rid)


def compare_runs(a: str, b: str) -> dict[str, Any]:
    ra, rb = load_run(a), load_run(b)
    rows = []
    ids = [i["id"] for i in ra["items"]] + [i["id"] for i in rb["items"] if i["id"] not in {x["id"] for x in ra["items"]}]
    ia = {i["id"]: i for i in ra["items"]}
    ib = {i["id"]: i for i in rb["items"]}
    for iid in ids:
        x, y = ia.get(iid), ib.get(iid)
        same = None
        if x and y and x["status"] == "done" and y["status"] == "done":
            same = all(
                body_lines(run_dir(ra["project"], a) / "items" / iid / "tables" / t)
                == body_lines(run_dir(rb["project"], b) / "items" / iid / "tables" / t)
                for t in TOOLS[ra["tool"]]["outputs"]
            )
        rows.append(
            {
                "id": iid,
                "label": (x or y)["label"],
                "a": {"status": x["status"], "elapsed_s": x.get("elapsed_s"), "reused": (x.get("decision") or {}).get("n_stable")} if x else None,
                "b": {"status": y["status"], "elapsed_s": y.get("elapsed_s"), "reused": (y.get("decision") or {}).get("n_stable")} if y else None,
                "same_output": same,
            }
        )
    return {"a": run_summary(ra), "b": run_summary(rb), "rows": rows,
            "settings_diff": {k: [ra["settings"].get(k), rb["settings"].get(k)] for k in set(ra["settings"]) | set(rb["settings"])
                              if ra["settings"].get(k) != rb["settings"].get(k)}}


# ---------------------------------------------------------------- cache


CACHE_TABLES = ("records", "rows", "namespaces", "contracts", "coverage", "fingerprints")


def _cache_counts(path: Path) -> dict[str, int]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        have = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        return {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in CACHE_TABLES if t in have}
    finally:
        con.close()


def cache_info(pid: str) -> dict[str, Any]:
    project = load_project(pid)
    path = cache_path(project)
    status, detail = cache_compatible(project)
    built = project["cache"].get("built_against") or []
    if isinstance(built, str):
        built = [built]
    info = {
        "path": rel(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "counts": {},
        "status": status,
        "detail": detail,
        "built_against": [reference(r)["label"] for r in built if (REFS / r).is_dir()],
        "built_at": project["cache"].get("built_at"),
        "built_by": project["cache"].get("built_by"),
    }
    if path.is_file():
        try:
            info["counts"] = _cache_counts(path)
        except sqlite3.Error as exc:
            info["error"] = str(exc)
    return info


def validate_cache(pid: str) -> dict[str, Any]:
    project = load_project(pid)
    path = cache_path(project)
    if not path.is_file():
        return {"ok": False, "detail": "no cache file", "counts": {}, "integrity": None}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        integrity = con.execute("pragma integrity_check").fetchone()[0]
        con.close()
        counts = _cache_counts(path)
    except sqlite3.Error as exc:
        integrity, counts = f"error: {exc}", {}
    status, detail = cache_compatible(project)
    result = {"ok": integrity == "ok", "integrity": integrity, "counts": counts,
              "compatibility": status, "detail": detail, "checked_at": now()}
    event("cache", f"Validated cache: integrity {integrity}, {counts.get('rows', 0):,} rows, {status}", project=pid)
    return result


def invalidate_cache(pid: str) -> dict[str, Any]:
    project = load_project(pid)
    if WORKER.active and WORKER.active.startswith(pid + "--"):
        raise ValueError("a run is using this cache")
    size = 0
    for path in project_dir(pid).glob("cache.sqlite*"):
        size += path.stat().st_size
        path.unlink()
    with LOCK:
        project = load_project(pid)
        project["cache"] = {"built_against": None, "built_at": None, "built_by": None}
        save_project(project)
    event("cache", f"Invalidated cache ({size / 1e6:.1f} MB removed)", project=pid)
    return {"removed_bytes": size}


def clean_up(pid: str, keep: int = 3) -> dict[str, Any]:
    runs = list_runs(pid)
    finished = [r for r in runs if r["status"] in ("completed", "failed", "cancelled")]
    removed, freed = [], 0
    for run in finished[keep:]:
        path = run_dir(pid, run["id"])
        freed += dir_size(path)
        shutil.rmtree(path, ignore_errors=True)
        removed.append(run["name"])
    event("cleanup", f"Removed {len(removed)} old runs ({freed / 1e6:.1f} MB)", project=pid)
    return {"removed": removed, "freed_bytes": freed}


# ---------------------------------------------------------------- exports


def run_files(rid: str) -> list[dict[str, Any]]:
    run = load_run(rid)
    root = run_dir(run["project"], rid)
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.name.endswith(".tmp"):
            rows.append({"path": str(path.relative_to(root)), "bytes": path.stat().st_size})
    return rows


def results_zip(rid: str) -> tuple[str, bytes]:
    run = load_run(rid)
    root = run_dir(run["project"], rid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in run["items"]:
            tables = root / "items" / item["id"] / "tables"
            if tables.is_dir():
                for table in tables.iterdir():
                    zf.write(table, f"{item['id']}/{table.name}")
    return f"{rid}-results.zip", buf.getvalue()


def bundle_zip(rid: str) -> tuple[str, bytes]:
    run = load_run(rid)
    project = load_project(run["project"])
    root = run_dir(run["project"], rid)
    tools = {t["id"]: {"binary": t["binary"], "version": t["version"]} for t in detect_tools()}
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "pipeline/acts"], cwd=REPO, capture_output=True, text=True).stdout.strip())
    manifest = {
        "run": run,
        "project": {k: project[k] for k in ("id", "name", "tool", "references")},
        "references": {side: reference(r) for side, r in run["references"].items() if r and side != "used"},
        "inputs": [
            {"id": i["id"], "path": i["path"], "sha256": sha256_file(REPO / i["path"])}
            for i in run["items"] if (REPO / i["path"]).is_file()
        ],
        "tools": tools,
        "acts_git_head": git,
        "acts_dirty": dirty,
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "exported_at": now(),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        commands = [" ".join(shlex.quote(a) for a in i["argv"]) for i in run["items"] if i.get("argv")]
        zf.writestr("commands.sh", "#!/bin/sh\n# run from pipeline/\nset -e\n" + "\n".join(commands) + "\n")
        for path in root.rglob("*"):
            if path.is_file() and path.name in ("decision.txt", "stdout.txt", "run.json", "log.jsonl"):
                zf.write(path, str(path.relative_to(root)))
    event("export", f"Exported reproducibility bundle for {run['name']}", project=run["project"], run=rid)
    return f"{rid}-bundle.zip", buf.getvalue()


def report_html(rid: str) -> tuple[str, bytes]:
    run = load_run(rid)
    v = run.get("verification") or summarize_verification(run)
    d = run.get("diff") or {}
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    rows = "".join(
        f"<tr><td>{esc(i['label'])}</td><td>{esc(i['stage_label'])}</td><td>{esc(i.get('outcome') or '')}</td>"
        f"<td>{(i.get('elapsed_s') or 0):.1f}s</td><td>{esc((i.get('decision') or {}).get('n_stable', ''))}</td>"
        f"<td>{esc('identical' if (i.get('full_compare') or {}).get('byte_equal') else ('differs' if i.get('full_compare') else 'not compared'))}</td></tr>"
        for i in run["items"]
    )
    labels = run.get("reference_labels", {})
    html = f"""<!doctype html><meta charset="utf-8"><title>{esc(run['name'])} report</title>
<style>body{{font:14px/1.5 system-ui;margin:2rem;max-width:60rem}}table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #ddd;padding:4px 8px;text-align:left}}th{{background:#f3f5f8}}</style>
<h1>{esc(run['name'])}</h1>
<p>{esc(TOOLS[run['tool']]['label'])} · {esc(labels.get('old', ''))} → {esc(labels.get('new', ''))} · {len(run['items'])} inputs ·
status {esc(run['status'])} · wall {run.get('wall_s') or 0:.1f}s</p>
<p>Reference entries: {d.get('unchanged', '–')} unchanged, {d.get('rerun', '–')} changed or new, {d.get('removed', '–')} removed.</p>
<p>Verification ({esc(v.get('policy'))}): {v.get('items_checked')} inputs with sampled checks, {v.get('records_audited')} records audited;
full comparison {v.get('full_equal')} of {v.get('full_compared')} byte-identical.</p>
<table><tr><th>Input</th><th>Stage</th><th>Outcome</th><th>Elapsed</th><th>Entries reused</th><th>Full run</th></tr>{rows}</table>
<p style="color:#666">Generated {now()} by the TARE console from {esc(rel(run_dir(run['project'], rid)))}.</p>"""
    event("export", f"Exported report for {run['name']}", project=run["project"], run=rid)
    return f"{rid}-report.html", html.encode()


def open_path(target: Path) -> None:
    target = target.resolve()
    if STATE.resolve() not in target.parents and target != STATE.resolve():
        raise ValueError("can only open folders under the console state directory")
    if not target.exists():
        raise ValueError("folder does not exist yet")
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(target)])


# ---------------------------------------------------------------- system


_CPU: dict[str, Any] = {"t": 0.0, "value": None}


def system() -> dict[str, Any]:
    ncpu = os.cpu_count() or 1
    if time.time() - _CPU["t"] > 2:
        try:
            out = subprocess.run(["ps", "-A", "-o", "%cpu="], capture_output=True, text=True, timeout=3).stdout
            _CPU["value"] = min(100.0, sum(float(x) for x in out.split() if x.strip()) / ncpu)
        except (OSError, ValueError, subprocess.SubprocessError):
            _CPU["value"] = None
        _CPU["t"] = time.time()
    mem_total = mem_used = None
    if sys.platform == "darwin":
        try:
            mem_total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
            vm = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
            page = int(re.search(r"page size of (\d+)", vm).group(1))
            def pages(name: str) -> int:
                m = re.search(rf"{name}:\s+(\d+)", vm)
                return int(m.group(1)) if m else 0
            mem_used = (pages("Pages active") + pages("Pages wired down") + pages("Pages occupied by compressor")) * page
        except (OSError, ValueError, AttributeError):
            pass
    disk = shutil.disk_usage(STATE if STATE.exists() else REPO)
    cache_bytes = sum(p.stat().st_size for p in PROJECTS.glob("*/cache.sqlite*")) if PROJECTS.is_dir() else 0
    return {
        "cpu_percent": _CPU["value"],
        "ncpu": ncpu,
        "mem_total": mem_total,
        "mem_used": mem_used,
        "disk_free": disk.free,
        "cache_bytes": cache_bytes,
        "host": platform.node(),
        "queue": WORKER.status(),
    }


def test_connection(compute: str) -> dict[str, Any]:
    t0 = time.monotonic()
    if compute == "local":
        tool = shutil.which("hmmscan")
        ok = bool(tool)
        result = {"ok": ok, "target": "This Mac", "detail": f"{platform.node()} · {os.cpu_count()} cores · hmmscan {'found' if ok else 'missing'}"}
    else:
        try:
            proc = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "discovery", "hostname; sinfo -h -o %P 2>/dev/null | head -3 | tr '\\n' ' '"],
                capture_output=True, text=True, timeout=20,
            )
            ok = proc.returncode == 0
            detail = proc.stdout.strip() if ok else (proc.stderr.strip().splitlines() or ["ssh failed"])[-1]
        except subprocess.TimeoutExpired:
            ok, detail = False, "ssh timed out"
        result = {"ok": ok, "target": "CARC · discovery", "detail": detail}
    result["latency_s"] = time.monotonic() - t0
    result["checked_at"] = now()
    CONNECTION[compute] = result
    event("connection", f"Tested {result['target']}: {'ok' if result['ok'] else 'failed'} ({result['detail']})")
    return result


CONNECTION: dict[str, dict[str, Any]] = {}


def recover_interrupted() -> None:
    """Runs left 'running' or 'queued' by a server restart are marked interrupted."""
    for project in list_projects():
        for run in list_runs(project["id"]):
            if run["status"] in ("running", "queued"):
                run["status"] = "failed"
                run["error"] = "console restarted while this run was in progress"
                for item in run["items"]:
                    if item["status"] in ("running", "queued"):
                        item.update(status="failed", stage_label="Interrupted", outcome="Failed", error="console restarted")
                run["finished_at"] = run.get("finished_at") or now()
                save_run(run)


WORKER = Worker()
