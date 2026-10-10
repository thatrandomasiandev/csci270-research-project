#!/usr/bin/env python3
"""First-run overhead ratios for stock HMMER, Riker, and both INCR columns.

The timed repeats are pre-registered in BASELINES_PROTOCOL.md and
refuse to start until that addendum names the same model and protein
counts. --size is a one-run stock probe used to choose that subset.
It is not an overhead ratio.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import baseline_docker_uniform as uniform  # noqa: E402
from acts.fasta import copy_fasta_head  # noqa: E402

PROTOCOL = ROOT / "docs" / "BASELINES_PROTOCOL.md"
ACCESSION = "GCF_002853805.1"
TOOLS = ("stock", "riker", "incr_default", "incr_annotations")
MODES = ("hmmscan", "hmmsearch")
N_REPEATS = 4


def lock_sentence(n_models: int, n_proteins: int) -> str:
    return (
        f"Locked subset: {n_models} models, {n_proteins} proteins "
        f"of {ACCESSION}."
    )


def subset_is_locked(protocol_text: str, n_models: int, n_proteins: int) -> bool:
    return lock_sentence(n_models, n_proteins) in protocol_text


def repeat_order(repeat: int) -> list[str]:
    shift = repeat % len(TOOLS)
    return list(TOOLS[shift:] + TOOLS[:shift])


def extract_first_models(gz_path: Path, dest: Path, n: int) -> list[str]:
    found: list[str] = []
    buf: list[str] = []
    name: str | None = None
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(gz_path, "rt", errors="replace") as src, dest.open("w") as out:
        for line in src:
            if line.startswith("HMMER3/"):
                buf = [line]
                name = None
                continue
            if not buf:
                continue
            buf.append(line)
            if line.startswith("NAME") and name is None:
                parts = line.split()
                name = parts[1] if len(parts) > 1 else None
            if line.strip() == "//":
                if name:
                    out.writelines(buf)
                    found.append(name)
                    if len(found) >= n:
                        break
                buf = []
                name = None
    if len(found) < n:
        raise SystemExit(f"Pfam file yielded {len(found)} models, wanted {n}")
    return found


def prepare_subset(work: Path, data_root: Path, n_models: int, n_proteins: int) -> dict:
    inn = work / "in"
    if inn.exists():
        shutil.rmtree(inn)
    inn.mkdir(parents=True)
    (work / "out").mkdir(parents=True, exist_ok=True)
    pfam = data_root / "hmmer" / "Pfam-A.hmm.gz"
    names = extract_first_models(pfam, inn / "subset.hmm", n_models)
    fasta_gz = data_root / "recurrence" / "A" / f"{ACCESSION}_protein.faa.gz"
    with gzip.open(fasta_gz, "rt") as src:
        kept = copy_fasta_head(src, inn / "genome1.faa", n_proteins)
    if kept != n_proteins:
        raise SystemExit(f"{ACCESSION} yielded {kept} records, wanted {n_proteins}")
    return {
        "n_models": len(names),
        "n_proteins": kept,
        "accession": ACCESSION,
        "first_model": names[0],
        "last_model": names[-1],
        "subset_hmm_sha256": uniform.sha256_file(inn / "subset.hmm"),
        "subset_hmm_bytes": (inn / "subset.hmm").stat().st_size,
        "fasta_sha256": uniform.sha256_file(inn / "genome1.faa"),
        "pfam_gz_sha256": uniform.sha256_file(pfam),
    }


def setup_lines(tool: str, mode: str) -> str:
    """Create the command file before the clock starts. A fresh container has no cache."""
    argv = uniform.hmmer_argv(mode, "/data/out.tbl", "/data/genome1.faa")
    if tool == "stock":
        return ""
    if tool == "riker":
        rendered = " ".join(argv)
        return "\n".join([
            "mkdir -p /data/run",
            f"printf '%s\\n' {uniform._sh_quote(rendered)} > /data/run/Rikerfile",
            "cd /data/run",
        ])
    home = "/data/run"
    body = "#!/bin/bash\n" + " ".join(__import__("shlex").quote(part) for part in argv) + "\n"
    lines = [
        f"mkdir -p {home}/cache",
        f"cat > {home}/run.sh <<'ENDSCRIPT'\n{body}ENDSCRIPT",
        f"chmod +x {home}/run.sh",
        "cd /opt/incr",
    ]
    if tool == "incr_annotations":
        lines.append('export INCR_SYS_PATH="/opt/incr/target/release/incr --enable_annotations"')
    else:
        lines.append("unset INCR_SYS_PATH || true")
    lines.append("export INCR_TOP=/opt/incr")
    return "\n".join(lines)


def timed_command(tool: str, mode: str) -> str:
    argv = uniform.hmmer_argv(mode, "/data/out.tbl", "/data/genome1.faa")
    if tool == "stock":
        return " ".join(argv)
    if tool == "riker":
        return "/opt/riker/release/bin/rkr --show"
    return "bash ./src/incr.sh /data/run/run.sh /data/run/cache"


def timed_script(tool: str, mode: str) -> str:
    return f"""set -u
mkdir -p /data /work/out
cp -a /work/in/subset.hmm /work/in/genome1.faa /data/
if [ ! -f /data/subset.hmm.h3m ]; then hmmpress -f /data/subset.hmm >/tmp/hmmpress.log 2>&1; fi
test -s /data/subset.hmm.h3m
echo "ACTS_PRESSED $?"
{setup_lines(tool, mode)}
echo ACTS_T0 $(date +%s.%N)
{timed_command(tool, mode)} > /work/out/tool.log 2>&1
echo "ACTS_EXIT $?"
echo ACTS_T1 $(date +%s.%N)
if [ -f /data/out.tbl ]; then cp -a /data/out.tbl /work/out/out.tbl; fi
"""


def docker_argv(tool: str, work: Path, script: str) -> list[str]:
    argv = ["docker", "run", "--rm", "--platform", "linux/arm64"]
    if tool.startswith("incr"):
        argv.append("--privileged")
    elif tool == "riker":
        argv.extend(["--cap-add", "SYS_PTRACE"])
    argv.extend([
        "-v", f"{work}:/work",
        "-w", "/data",
        uniform.IMAGE,
        "bash", "-lc", script,
    ])
    return argv


def docker_run(tool: str, work: Path, script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(docker_argv(tool, work, script), check=False, text=True, capture_output=True)


def parse_timing(text: str) -> dict:
    t0 = t1 = exit_code = None
    for line in text.splitlines():
        if line.startswith("ACTS_T0 "):
            t0 = Decimal(line.split()[1])
        elif line.startswith("ACTS_T1 "):
            t1 = Decimal(line.split()[1])
        elif line.startswith("ACTS_EXIT "):
            exit_code = int(line.split()[1])
    wall = None if t0 is None or t1 is None else t1 - t0
    return {"t0": None if t0 is None else format(t0, "f"), "t1": None if t1 is None else format(t1, "f"),
            "exit_code": exit_code, "wall_s": None if wall is None else format(wall, "f")}


def table_ok(path: Path, mode: str) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    text = path.read_text(errors="replace")
    return uniform.tblout_has_header(text)


def one_run(tool: str, mode: str, work: Path) -> dict:
    out = work / "out"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    proc = docker_run(tool, work, timed_script(tool, mode))
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    (out / "docker.log").write_text(text)
    parsed = parse_timing(proc.stdout or "")
    ok = parsed["exit_code"] == 0 and parsed["wall_s"] is not None and table_ok(out / "out.tbl", mode)
    parsed.update({
        "tool": tool,
        "mode": mode,
        "docker_exit": proc.returncode,
        "tblout_bytes": (out / "out.tbl").stat().st_size if (out / "out.tbl").is_file() else 0,
        "valid": ok,
    })
    return parsed


def mean_std(values: list[Decimal]) -> tuple[str, str]:
    mean = sum(values, Decimal(0)) / Decimal(len(values))
    if len(values) < 2:
        return format(mean, "f"), "0"
    var = sum((v - mean) ** 2 for v in values) / Decimal(len(values) - 1)
    std = var.sqrt()
    return format(mean, "f"), format(std, "f")


def summarize(runs: list[dict], prepared: dict) -> dict:
    by_mode: dict[str, dict] = {}
    for mode in MODES:
        mode_runs = [row for row in runs if row["mode"] == mode]
        if not mode_runs:
            continue
        stock = {row["repeat"]: Decimal(row["wall_s"]) for row in mode_runs if row["tool"] == "stock" and row["valid"]}
        tools = {}
        for tool in TOOLS:
            rows = [row for row in mode_runs if row["tool"] == tool]
            valid = [row for row in rows if row["valid"]]
            walls = [Decimal(row["wall_s"]) for row in valid]
            paired = []
            for row in valid:
                if row["repeat"] in stock and stock[row["repeat"]] > 0:
                    paired.append(Decimal(row["wall_s"]) / stock[row["repeat"]])
            mean_w, std_w = mean_std(walls) if walls else ("", "")
            mean_r, std_r = mean_std(paired) if paired else ("", "")
            ratio_of_means = ""
            if walls and tool != "stock":
                stock_walls = [stock[row["repeat"]] for row in valid if row["repeat"] in stock]
                if stock_walls:
                    ratio_of_means = format(
                        (sum(walls, Decimal(0)) / len(walls)) / (sum(stock_walls, Decimal(0)) / len(stock_walls)),
                        "f",
                    )
            tools[tool] = {
                "n_valid": len(valid),
                "n_planned": len(rows),
                "wall_s": [row["wall_s"] for row in rows],
                "valid": [row["valid"] for row in rows],
                "mean_wall_s": mean_w,
                "stdev_wall_s": std_w,
                "paired_ratio_vs_stock": [format(v, "f") for v in paired],
                "mean_paired_ratio": mean_r if tool != "stock" else "1",
                "stdev_paired_ratio": std_r if tool != "stock" else "0",
                "ratio_of_means": "1" if tool == "stock" else ratio_of_means,
            }
        by_mode[mode] = tools
    projected = {
        tool: {
            "label": "PROJECTED",
            "factor": uniform.dec_str(uniform.FACTORS[tool]),
            "source": uniform.OVERHEAD_SOURCE[tool],
        }
        for tool in TOOLS
        if tool != "stock"
    }
    return {
        "label": "MEASURED",
        "decides": "first-run wall ratio versus stock HMMER in this container",
        "comparable_to_epyc": False,
        "use": "ratios_only",
        "primary": "mean of within-repeat wall ratios, tool / stock",
        "secondary_projected_factor": projected,
        "workload": prepared,
        "modes": by_mode,
        "runs": runs,
    }


def run_size(data_root: Path, work: Path, out: Path, n_models: int, n_proteins: int) -> dict:
    prepared = prepare_subset(work, data_root, n_models, n_proteins)
    runs = []
    for mode in MODES:
        row = one_run("stock", mode, work)
        row["repeat"] = 0
        row["role"] = "sizing"
        runs.append(row)
        print(mode, row["wall_s"], "valid", row["valid"], flush=True)
    payload = {
        "label": "SIZING",
        "not_an_overhead_ratio": True,
        "n": 1,
        "workload": prepared,
        "runs": runs,
        "provenance": uniform.host_provenance(),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def run_measure(data_root: Path, work: Path, out: Path, n_models: int, n_proteins: int, modes: list[str]) -> dict:
    protocol = PROTOCOL.read_text()
    if not subset_is_locked(protocol, n_models, n_proteins):
        raise SystemExit(
            "subset is not locked in BASELINES_PROTOCOL.md: " + lock_sentence(n_models, n_proteins)
        )
    prepared = prepare_subset(work, data_root, n_models, n_proteins)
    runs = []
    partial = work / "partial.json"
    for repeat in range(N_REPEATS):
        for tool in repeat_order(repeat):
            for mode in modes:
                print(f"repeat {repeat} {tool} {mode}", flush=True)
                row = one_run(tool, mode, work)
                row["repeat"] = repeat
                row["role"] = "measurement"
                runs.append(row)
                partial.write_text(json.dumps(runs, indent=2) + "\n")
                print(" ", row["wall_s"], "valid", row["valid"], flush=True)
    payload = summarize(runs, prepared)
    payload["provenance"] = uniform.host_provenance()
    payload["protocol"] = "pipeline/docs/BASELINES_PROTOCOL.md"
    payload["addendum"] = "2026-10-10 measured first-run overhead"
    payload["repeats"] = N_REPEATS
    payload["order"] = [repeat_order(i) for i in range(N_REPEATS)]
    payload["assumption"] = (
        "Each run is a new container, so the tool cache is empty. "
        "hmmpress finishes before ACTS_T0 and is not in the wall. "
        "The kernel page cache is not flushed. "
        "Absolute seconds are this arm64 container; only ratios are used. "
        "The ratio is the first-run cost that applies to genome 2, because every tool re-executes a new FASTA."
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=Path("/tmp/acts-baseline-overhead"))
    parser.add_argument("--models", type=int, required=True)
    parser.add_argument("--proteins", type=int, required=True)
    parser.add_argument("--size", action="store_true")
    parser.add_argument("--measure", action="store_true")
    parser.add_argument("--modes", default="hmmscan,hmmsearch")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.size == args.measure:
        raise SystemExit("pass exactly one of --size or --measure")
    modes = [part.strip() for part in args.modes.split(",") if part.strip()]
    for mode in modes:
        if mode not in MODES:
            raise SystemExit(mode)
    if args.size:
        out = args.out or (ROOT / "results" / "baseline_overhead_sizing.json")
        run_size(args.data_root, args.work, out, args.models, args.proteins)
    else:
        out = args.out or (ROOT / "results" / "baseline_overhead.json")
        run_measure(args.data_root, args.work, out, args.models, args.proteins, modes)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
