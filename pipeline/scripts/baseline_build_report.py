"""Assemble capability-probe and build logs into results/baseline_build.json."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from baseline_match import provenance

PROTOCOL = "pipeline/docs/BASELINES_PROTOCOL.md"
PROTOCOL_COMMIT = "a29c3181adab72feaafa61b52c68549f66510402"


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes()
    if len(data) > 12000:
        data = data[-12000:]
    return data.decode("utf-8", errors="replace")


def _exit(path: Path) -> int | None:
    if not path.is_file():
        return None
    text = path.read_text().strip()
    try:
        return int(text)
    except ValueError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    probe = Path(args.probe_dir)
    probes = {}
    for name in ("ptrace", "seccomp_bpf", "unshare_user", "overlayfs", "docker", "mergerfs", "strace", "ptrace_scope"):
        code = _exit(probe / f"{name}.exit")
        log = _read(probe / f"{name}.log")
        probes[name] = {
            "ok": code == 0,
            "exit_code": code,
            "output": log.strip(),
        }
    tools = {}
    for name in ("riker", "processcache_sha256", "processcache_mtime", "incr", "hmmer"):
        info = {
            "ok": _exit(probe / f"{name}.exit") == 0,
            "exit_code": _exit(probe / f"{name}.exit"),
            "log_tail": _read(probe / f"{name}.log").strip(),
        }
        meta_path = probe / f"{name}.json"
        if meta_path.is_file():
            try:
                info.update(json.loads(meta_path.read_text()))
            except json.JSONDecodeError as exc:
                info["meta_error"] = str(exc)
                info["meta_raw"] = _read(meta_path)
        if not info["ok"] and not info.get("error"):
            info["error"] = (info.get("log_tail") or "build failed")[-2000:]
        tools[name] = info
    payload = {
        "protocol": PROTOCOL,
        "protocol_locked_commit": PROTOCOL_COMMIT,
        "phase": "capability_and_build",
        "node_class_deviation": (
            "Shared xeon-4116, not exclusive, not epyc-7542. "
            "The locked plan asked for one exclusive epyc-7542 for the capability probe."
        ),
        "eggNOG": "not installed and not downloaded; ~45 GB database needs Josh's approval",
        "probes": probes,
        "tools": tools,
        "host_text": {
            "uname": _read(probe / "uname.log").strip(),
            "os_release": _read(probe / "os-release.log").strip(),
            "lscpu": _read(probe / "lscpu.log").strip(),
            "scontrol": _read(probe / "scontrol.log").strip(),
            "df": _read(probe / "df.log").strip(),
        },
        "provenance": provenance(),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
