#!/usr/bin/env python3
"""POST-HOC dump of INCR's recorded dependencies before a genome-2 replay.

Procedure: pipeline/docs/BASELINES_PROTOCOL.md, addendum
"INCR replay dependency diagnosis". Same image, same argv, same
73-model by 300-protein subset as the uniform behavioral smoke.
The observer decodes data.incr. It does not edit INCR and it does
not set DEBUG.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import baseline_docker_uniform as uniform  # noqa: E402

DUMP_SRC = Path(__file__).resolve().parent / "baseline_incr_cache_dump"
DUMP_BIN = "/tmp/baseline_incr_cache_dump/target/release/baseline_incr_cache_dump"
COLUMNS = ("incr_default", "incr_annotations")


def insert_replay_dumps(script: str) -> str:
    """Stat INCR's cache immediately before each replay incr.sh.

    The dump sits after the harness's tblout sha256/mtime read and
    before incr.sh. Genome 1 and genome 2 are not dumped: those steps
    have no prior cache entry for that command.
    """
    lines: list[str] = []
    pending_after: str | None = None
    for line in script.splitlines():
        if pending_after is not None:
            lines.append(pending_after)
            pending_after = None
        if "bash ./src/incr.sh " in line and "_replay.log" in line:
            parts = line.split()
            if len(parts) < 4 or parts[3].startswith(">"):
                raise SystemExit(f"cannot parse incr invocation: {line}")
            cache = parts[3]
            bits = cache.strip("/").split("/")
            if len(bits) != 4 or bits[0] != "data" or bits[3] != "cache":
                raise SystemExit(f"unexpected cache path: {cache}")
            column, mode = bits[1], bits[2]
            out = f"/work/out/deps_{column}_{mode}.json"
            lines.append(f"echo ACTS_DUMP {column} {mode}")
            lines.append(f"{DUMP_BIN} {cache} {out}")
            lines.append('echo "ACTS_DUMP_RC $?"')
            lines.append(
                f'find {cache} -name data.incr -printf "%p %s %T@\\n" | sort '
                f"> /work/out/cache_files_before_{column}_{mode}.txt"
            )
            pending_after = (
                f'find {cache} -name data.incr -printf "%p %s %T@\\n" | sort '
                f"> /work/out/cache_files_after_{column}_{mode}.txt"
            )
        lines.append(line)
    if pending_after is not None:
        lines.append(pending_after)
    return "\n".join(lines) + "\n"


def compile_preamble() -> str:
    return f"""
echo ACTS_DEPCHECK_BUILD
rm -rf /tmp/baseline_incr_cache_dump
cp -a /work/depcheck /tmp/baseline_incr_cache_dump
if ! cargo build --release --manifest-path /tmp/baseline_incr_cache_dump/Cargo.toml > /work/out/depcheck_build.log 2>&1; then
  echo ACTS_DEPCHECK_BUILD_FAIL
  exit 0
fi
echo ACTS_DEPCHECK_BUILD_OK
if ! {DUMP_BIN} --selfcheck /work/out/depcheck_selfcheck.json; then
  echo ACTS_DEPCHECK_SELFCHECK_FAIL
  exit 0
fi
echo ACTS_DEPCHECK_SELFCHECK_OK
"""


def diagnosis_script(column: str) -> str:
    if column not in COLUMNS:
        raise SystemExit(column)
    body = insert_replay_dumps(uniform.sequence_script(column))
    preamble = compile_preamble()
    if not body.startswith("set -u\n"):
        raise SystemExit("sequence_script no longer starts with set -u")
    return "set -u\n" + preamble + body[len("set -u\n"):]


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def _summarize_deps(payload: dict | None) -> dict:
    if payload is None:
        return {"present": False}
    mismatches = []
    for entry in payload.get("entries") or []:
        for row in entry.get("mismatches") or []:
            mismatches.append(row)
    return {
        "present": True,
        "would_pass": payload.get("would_pass"),
        "n_data_files": payload.get("n_data_files"),
        "decode_errors": payload.get("decode_errors"),
        "entries": [
            {
                "batch_dir": entry.get("batch_dir"),
                "exit_code": entry.get("exit_code"),
                "would_pass": entry.get("would_pass"),
                "fail_reasons": entry.get("fail_reasons"),
                "n_dependencies": entry.get("n_dependencies"),
                "n_mismatches": entry.get("n_mismatches"),
                "n_write_outputs": entry.get("n_write_outputs"),
                "stdout_incr": entry.get("stdout_incr"),
                "stderr_incr": entry.get("stderr_incr"),
                "outputs_dir": entry.get("outputs_dir"),
            }
            for entry in payload.get("entries") or []
        ],
        "mismatches": mismatches,
    }


def assemble(work: Path, columns: dict, log_text: str) -> dict:
    modes = {}
    for column in columns:
        modes[column] = {}
        for mode in ("hmmscan", "hmmsearch"):
            deps = _read_json(work / "out" / f"deps_{column}_{mode}.json")
            before = work / "out" / f"cache_files_before_{column}_{mode}.txt"
            after = work / "out" / f"cache_files_after_{column}_{mode}.txt"
            modes[column][mode] = {
                "before_replay": _summarize_deps(deps),
                "cache_files_before": before.read_text() if before.is_file() else "",
                "cache_files_after": after.read_text() if after.is_file() else "",
                "deps_path": f"deps_{column}_{mode}.json",
            }
    return {
        "label": "POST-HOC",
        "decides": "which recorded INCR dependency failed check_cache_valid before the replay incr.sh",
        "protocol": "pipeline/docs/BASELINES_PROTOCOL.md",
        "addendum": "2026-10-10 INCR replay dependency diagnosis",
        "image": uniform.IMAGE,
        "observer": "pipeline/scripts/baseline_incr_cache_dump",
        "incr_source": "4b8e5ddf8e275d947518c7cc0f5d2713fe992307",
        "debug_stays_false": True,
        "build_ok": "ACTS_DEPCHECK_BUILD_OK" in log_text,
        "selfcheck_ok": "ACTS_DEPCHECK_SELFCHECK_OK" in log_text,
        "provenance": uniform.host_provenance(),
        "columns": modes,
    }


def run(data_root: Path, work: Path, out: Path) -> dict:
    if work.exists():
        shutil.rmtree(work)
    uniform.prepare_work(work, data_root)
    dest = work / "depcheck"
    shutil.copytree(DUMP_SRC, dest)
    out_dir = work / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    combined: dict = {}
    logs: list[str] = []
    for column in COLUMNS:
        script = diagnosis_script(column)
        (out_dir / f"script_{column}.sh").write_text(script)
        argv = uniform.docker_argv(column, work, script)
        proc = subprocess.run(argv, check=False, text=True, capture_output=True)
        text = (proc.stdout or "") + (proc.stderr or "")
        (out_dir / f"docker_{column}.log").write_text(text)
        logs.append(text)
        combined[column] = {"docker_exit": proc.returncode}
        if "ACTS_DEPCHECK_BUILD_OK" not in text:
            break
    payload = assemble(work, combined, "\n".join(logs))
    for column, row in combined.items():
        payload["columns"].setdefault(column, {})
        payload["columns"][column]["docker_exit"] = row["docker_exit"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    for column in COLUMNS:
        for mode in ("hmmscan", "hmmsearch"):
            src = work / "out" / f"deps_{column}_{mode}.json"
            if src.is_file():
                target = out.parent / f"baseline_incr_deps_{column}_{mode}.json"
                shutil.copyfile(src, target)
    return payload


def main() -> None:
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=Path("/tmp/acts-incr-diagnosis"))
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "results" / "baseline_incr_replay_diagnosis.json",
    )
    args = parser.parse_args()
    payload = run(args.data_root, args.work, args.out)
    print(f"wrote {args.out}")
    print("build_ok", payload["build_ok"], "selfcheck_ok", payload["selfcheck_ok"])


if __name__ == "__main__":
    main()
