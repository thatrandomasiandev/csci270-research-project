#!/usr/bin/env python3
"""Uniform behavioral smoke for Riker, ProcessCache, and INCR.

Pre-registered in pipeline/docs/BASELINES_PROTOCOL.md
(addendum 2026-10-10). One container per column. Genome 1, then
genome 2, then an exact replay of genome 2. Classification does
not use wall time.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import shlex
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from acts.fasta import copy_fasta_head  # noqa: E402
from baseline_match import nonempty_body, tables_match  # noqa: E402
import repro_savings_desc_stop as repro  # noqa: E402

IMAGE = "acts-baselines-uniform:local"
DOCKERFILE = ROOT / "docker" / "Dockerfile.baselines_uniform"
N_PROTEINS = 300
SAMPLE_HOURS = {"hmmscan": Decimal("5.10"), "hmmsearch": Decimal("1.05")}
SAMPLE_GENOMES = 6
COLLECTION_N = {"A": 30, "B": 40}
GENOMES = {
    "genome1": {"position": 1, "accession": "GCF_002853805.1", "proteins_in_file": 5117},
    "genome2": {"position": 2, "accession": "GCF_002090355.1", "proteins_in_file": 4091},
}
REPLAY_MARKERS = ("Skip the execution!", "Cache valid:")
HMMER_HEADER_MARKERS = ("# hmmscan ::", "# hmmsearch ::", "--- full sequence ----")

# Paper overheads. Not HMMER measurements.
FACTORS = {
    "riker": Decimal("1.088"),
    "processcache": Decimal("1.69"),
    "incr_default": Decimal("2.0105"),
    "incr_annotations": Decimal("1.4355"),
}
OVERHEAD_SOURCE = {
    "riker": (
        "Curtsinger and Barowy, USENIX ATC 2022, abstract and Figure 3: "
        "median full-build overhead 8.8% on 14 software packages. "
        "A build overhead, not a measured HMMER overhead."
    ),
    "processcache": (
        "Shiptoski, PhD thesis, University of Pennsylvania, 2023: "
        "empty-cache overhead 1.69x mean under content hashing. "
        "Not a measured overhead on this HMMER argv."
    ),
    "incr_default": (
        "Xie, Lamprou, Xia, and Vasilakis, USENIX OSDI 2026, introduction "
        "and section 8.5: first execution slower by 101.05% with no "
        "annotations (Figure 5 mean first-run ratio 2.01x on benchmarks "
        "over five seconds). A shell-suite overhead, not a measured HMMER overhead."
    ),
    "incr_annotations": (
        "Xie et al., USENIX OSDI 2026, section 8.5: with crowdsourced "
        "annotations, first-run overhead falls from 101.05% to 43.55%. "
        "That figure is their Unix suite. It is applied here only as the "
        "annotated first-run overhead, and it does not mean FASTA records were split."
    ),
}

ABI_C = r"""
#define _GNU_SOURCE
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/ptrace.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>
#ifndef PTRACE_GET_SYSCALL_INFO
#define PTRACE_GET_SYSCALL_INFO 0x420e
#endif
struct abi_info { unsigned char raw[128]; };
int main(void) {
  pid_t child = fork();
  if (child == 0) {
    ptrace(PTRACE_TRACEME, 0, 0, 0);
    raise(SIGSTOP);
    syscall(SYS_getpid);
    _exit(0);
  }
  int status = 0;
  waitpid(child, &status, 0);
  ptrace(PTRACE_SYSCALL, child, 0, 0);
  waitpid(child, &status, 0);
  struct abi_info info;
  memset(&info, 0, sizeof info);
  errno = 0;
  long rc = ptrace(PTRACE_GET_SYSCALL_INFO, child, (void *)sizeof info, &info);
  printf("request=0x420e rc=%ld errno=%d %s\n", rc, errno, strerror(errno));
  ptrace(PTRACE_KILL, child, 0, 0);
  waitpid(child, &status, 0);
  return 0;
}
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dec_str(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def project_hours(column: str, mode: str) -> dict:
    per = (SAMPLE_HOURS[mode] / SAMPLE_GENOMES) * FACTORS[column]
    return {
        "label": "PROJECTED",
        "formula": "T = (T_sample / 6) * factor hours per genome",
        "T_sample_h": format(SAMPLE_HOURS[mode], "f"),
        "factor": dec_str(FACTORS[column]),
        "overhead_source": OVERHEAD_SOURCE[column],
        "hours_per_genome": dec_str(per),
        "hours_A30": dec_str(COLLECTION_N["A"] * per),
        "hours_B40": dec_str(COLLECTION_N["B"] * per),
        "assumption": (
            "Every later genome is a new FASTA, so the replay skip does not "
            "apply across the collection. Proteome size stays the locked "
            "stand-in and is not scaled to 300 proteins. The factor is the "
            "tool paper's own overhead, not a time measured in this container."
        ),
    }


def hmmer_argv(mode: str, tblout: str, fasta: str) -> list[str]:
    binary = f"/opt/hmmer/bin/{mode}"
    if mode == "hmmscan":
        return [
            binary, "--cpu", "32", "--cut_ga", "--noali", "--tblout", tblout,
            "/data/subset.hmm", fasta,
        ]
    if mode == "hmmsearch":
        return [
            binary, "--cpu", "32", "--noali", "--tblout", tblout,
            "-Z", "1000000", "--domZ", "1000000",
            "/data/subset.hmm", fasta,
        ]
    raise ValueError(mode)


def fasta_for(step: str) -> str:
    if step == "genome1":
        return "/data/genome1.faa"
    if step in ("genome2", "replay"):
        return "/data/genome2.faa"
    raise ValueError(step)


def tblout_for(column: str, mode: str, step: str) -> str:
    name = "genome1.tbl" if step == "genome1" else "genome2.tbl"
    return f"/data/{column}/{mode}/{name}"


def step_plan(column: str, mode: str, step: str) -> dict:
    fasta = fasta_for(step)
    tbl = tblout_for(column, mode, step)
    return {
        "column": column,
        "mode": mode,
        "step": step,
        "fasta": fasta,
        "tblout": tbl,
        "argv": hmmer_argv(mode, tbl, fasta),
        "rewrite_command": step != "replay",
    }


def judge_behavioral(
    *,
    exit_code: int,
    tblout_nonempty: bool,
    tblout_header: bool,
    newly_written: bool,
    replay_marker: bool,
    riker_must_run: bool | None,
    match: bool,
) -> str:
    """executed, replayed, or invalid. Wall time is not an input.

    riker_must_run is None unless the step invoked ``rkr --show``.
    False means ``rkr`` exited 0 and did not print the HMMER binary.
    """
    riker_skipped = riker_must_run is False and exit_code == 0
    said_replay = bool(replay_marker or riker_skipped)
    table_ok = bool(tblout_nonempty and tblout_header)
    if said_replay and table_ok and match:
        return "replayed"
    if newly_written and table_ok and not said_replay:
        return "executed"
    return "invalid"


def tblout_has_header(text: str) -> bool:
    return any(marker in text for marker in HMMER_HEADER_MARKERS)


def log_says_replay(text: str) -> bool:
    return any(marker in text for marker in REPLAY_MARKERS)


def riker_must_run_lines(log: str, mode: str) -> list[str]:
    hits = []
    for line in log.splitlines():
        if line.startswith(("Query:", "Description:", "Accession:", "Scores ")):
            break
        fields = line.split()
        if fields and fields[0] == mode:
            hits.append(line)
    return hits


def _sh_quote(text: str) -> str:
    return shlex.quote(text)


def sequence_script(column: str) -> str:
    """Bash for one column, both modes, inside one container.

    Inputs are copied onto the container root filesystem (/data)
    before any tool runs. /tmp is not a FASTA path: INCR drops it.
    Replay does not rewrite the command file or the tblout.
    """
    lines = [
        "set -u",
        "mkdir -p /data /work/out /root/incr",
        'cp -a /work/in/subset.hmm /work/in/genome1.faa /work/in/genome2.faa /work/in/abi.c /data/',
        'echo "ACTS_UNAME $(uname -a)"',
        'echo "ACTS_UNSHARE $(unshare --version | head -n 1)"',
        'echo "ACTS_PYTHON $(python3 --version 2>&1)"',
        'echo "ACTS_HMMER $(hmmscan -h | sed -n 2p)"',
        'if unshare --help 2>&1 | grep -q -- "--root"; then echo ACTS_UNSHARE_ROOT yes; else echo ACTS_UNSHARE_ROOT no; fi',
        'python3 -c "import libbash, libdash" >/tmp/libbash.probe 2>&1',
        'echo "ACTS_LIBBASH $?"',
        'gcc -O2 -Wall -o /data/abi /data/abi.c >/tmp/abi.build 2>&1 || true',
        'if [ -x /data/abi ]; then /data/abi; else echo "request=0x420e rc=missing errno=missing"; fi',
        'echo "ACTS_CPU_BYTES $(tr -d \'\\n\' < /sys/devices/system/cpu/online)"',
        "if [ ! -f /data/subset.hmm.h3m ]; then hmmpress -f /data/subset.hmm; fi",
        'test -s /data/subset.hmm.h3m && test -s /data/subset.hmm.h3i && test -s /data/subset.hmm.h3f && test -s /data/subset.hmm.h3p',
        'echo "ACTS_PRESSED $?"',
    ]
    for mode in ("hmmscan", "hmmsearch"):
        lines.append(f"mkdir -p /data/stock/{mode}")
        for step in ("genome1", "genome2"):
            argv = hmmer_argv(mode, f"/data/stock/{mode}/{step}.tbl", fasta_for(step))
            lines.append("echo ACTS_STOCK_BEGIN")
            lines.append(" ".join(argv))
            lines.append("echo ACTS_STOCK_END")
    lines.append("mkdir -p /work/out/stock")
    lines.append("cp -a /data/stock/. /work/out/stock/")
    lines.append(f"mkdir -p /work/out/{column}")
    if column == "processcache":
        lines.append(
            'if [ ! -x /usr/local/bin/process_cache ]; then echo ACTS_BINARY_MISSING processcache; '
            'tail -c 2000 /opt/ProcessCache.build.log 2>/dev/null || true; exit 0; fi'
        )
        lines.append('grep -n DONT_HASH_FILES /opt/ProcessCache/src/condition_generator.rs | head -n 1')
    if column.startswith("incr"):
        lines.append(
            'if [ ! -x /opt/incr/target/release/incr ]; then echo ACTS_BINARY_MISSING incr; exit 0; fi'
        )
        lines.append("cd /opt/incr")
        if column == "incr_annotations":
            lines.append('export INCR_SYS_PATH="/opt/incr/target/release/incr --enable_annotations"')
        else:
            lines.append("unset INCR_SYS_PATH || true")
        lines.append("export INCR_TOP=/opt/incr")
    for mode in ("hmmscan", "hmmsearch"):
        home = f"/data/{column}/{mode}"
        lines.append(f"mkdir -p {home}/cache /work/out/{column}/{mode}")
        for step in ("genome1", "genome2", "replay"):
            plan = step_plan(column, mode, step)
            argv = plan["argv"]
            log = f"/work/out/{column}/{mode}_{step}.log"
            marker = f"/work/out/{column}/{mode}_{step}.marker"
            lines.append(f"echo ACTS_STEP {column} {mode} {step}")
            lines.append(
                f'echo "ACTS_CPU_MTIME $(stat -c %Y /sys/devices/system/cpu/online)"'
            )
            if column == "riker":
                if plan["rewrite_command"]:
                    rendered = " ".join(argv)
                    lines.append(
                        f"printf '%s\\n' {_sh_quote(rendered)} > {home}/Rikerfile"
                    )
                lines.append(f'echo "ACTS_CMD_SHA $(sha256sum {home}/Rikerfile | awk \'{{print $1}}\')"')
            elif column.startswith("incr"):
                if plan["rewrite_command"]:
                    body = "#!/bin/bash\n" + " ".join(shlex.quote(part) for part in argv) + "\n"
                    lines.append(f"cat > {home}/run.sh <<'ENDSCRIPT'\n{body}ENDSCRIPT")
                    lines.append(f"chmod +x {home}/run.sh")
                lines.append(f'echo "ACTS_CMD_SHA $(sha256sum {home}/run.sh | awk \'{{print $1}}\')"')
            else:
                lines.append(f'echo "ACTS_CMD_SHA $(printf %s {_sh_quote(" ".join(argv))} | sha256sum | awk \'{{print $1}}\')"')
            lines.append(f'echo "ACTS_FASTA_SHA $(sha256sum {plan["fasta"]} | awk \'{{print $1}}\')"')
            lines.append('echo "ACTS_HMM_SHA $(sha256sum /data/subset.hmm | awk \'{print $1}\')"')
            lines.append(
                f'if [ -f {plan["tblout"]} ]; then echo "ACTS_TBLOUT_BEFORE $(sha256sum {plan["tblout"]} | awk \'{{print $1}}\')"; '
                f'echo "ACTS_TBLOUT_MTIME_BEFORE $(stat -c %Y.%N {plan["tblout"]})"; '
                f'else echo ACTS_TBLOUT_BEFORE absent; echo ACTS_TBLOUT_MTIME_BEFORE absent; fi'
            )
            if column.startswith("incr"):
                lines.append(
                    'if [ -f /root/incr/debug_log.txt ]; then debug_before=$(wc -c < /root/incr/debug_log.txt); '
                    'else debug_before=0; fi'
                )
                lines.append('echo "ACTS_DEBUG_BEFORE ${debug_before}"')
            lines.append(f"mkdir -p /work/out/{column}")
            if column == "riker":
                lines.append(f"cd {home}")
                lines.append(
                    f"/opt/riker/release/bin/rkr --show > {log} 2>&1"
                )
            elif column == "processcache":
                lines.append(f"cd {home}")
                lines.append(
                    "RUST_LOG=debug /usr/local/bin/process_cache -- "
                    + " ".join(shlex.quote(part) for part in argv)
                    + f" > {log} 2>&1"
                )
            else:
                lines.append("cd /opt/incr")
                lines.append(
                    f"bash ./src/incr.sh {home}/run.sh {home}/cache > {log} 2>&1"
                )
            lines.append('echo "ACTS_EXIT $?"')
            lines.append(
                f'if [ -f {plan["tblout"]} ]; then echo "ACTS_TBLOUT_AFTER $(sha256sum {plan["tblout"]} | awk \'{{print $1}}\')"; '
                f'echo "ACTS_TBLOUT_MTIME_AFTER $(stat -c %Y.%N {plan["tblout"]})"; '
                f'cp -a {plan["tblout"]} /work/out/{column}/{mode}_{step}.tbl; '
                f'else echo ACTS_TBLOUT_AFTER absent; echo ACTS_TBLOUT_MTIME_AFTER absent; fi'
            )
            if column == "riker":
                lines.append(f"cp -a {log} /work/out/{column}/{mode}_{step}.show")
                lines.append(f": > {marker}")
            elif column.startswith("incr"):
                lines.append(
                    'if [ -f /root/incr/debug_log.txt ]; then debug_after=$(wc -c < /root/incr/debug_log.txt); '
                    'else debug_after=0; fi'
                )
                lines.append('echo "ACTS_DEBUG_AFTER ${debug_after}"')
                lines.append(
                    'if [ "${debug_after}" -gt "${debug_before}" ]; then '
                    'tail -c +"$((debug_before + 1))" /root/incr/debug_log.txt > /tmp/incr_delta.txt; '
                    'else : > /tmp/incr_delta.txt; fi'
                )
                lines.append("cp -a /root/incr/debug_log.txt /work/out/incr_debug_log.txt 2>/dev/null || true")
                lines.append(
                    f'grep -F -m 1 -e "Cache valid:" -e "Skip the execution!" /tmp/incr_delta.txt > {marker} 2>/dev/null || : > {marker}'
                )
            else:
                lines.append(
                    f'grep -F -m 1 -e "Skip the execution!" -e "Cache valid:" {log} > {marker} 2>/dev/null || : > {marker}'
                )
            lines.append(f"tail -c 2500 {log} > /work/out/{column}/{mode}_{step}.tail 2>/dev/null || true")
            lines.append(f"echo ACTS_ENDSTEP {column} {mode} {step}")
        if column == "riker":
            lines.append(f"cd {home}")
            lines.append(
                f"/opt/riker/release/bin/rkr check --log artifact > /work/out/{column}/{mode}_check.log 2>&1 || true"
            )
    lines.append("echo ACTS_DONE")
    return "\n".join(lines) + "\n"


def docker_argv(column: str, work: Path, script: str) -> list[str]:
    argv = ["docker", "run", "--rm", "--platform", "linux/arm64"]
    if column.startswith("incr"):
        argv.append("--privileged")
    else:
        argv.extend(["--cap-add", "SYS_PTRACE"])
    argv.extend([
        "-v", f"{work}:/work",
        "-w", "/data",
        IMAGE,
        "bash", "-lc", script,
    ])
    return argv


def column_capabilities(column: str) -> dict:
    if column.startswith("incr"):
        return {
            "privileged": True,
            "cap_add": "included in --privileged",
            "seccomp": "unconfined, because --privileged is INCR's documented Docker invocation",
            "source": "README at 4b8e5dd: docker run --privileged",
        }
    return {
        "privileged": False,
        "cap_add": "SYS_PTRACE",
        "seccomp": "default Docker profile; not seccomp=unconfined",
        "source": "Riker and ProcessCache document ptrace. The 2026-10-09 Riker run used this pair.",
    }


def extract_hmm(gz_path: Path, names: list[str], dest: Path) -> list[str]:
    want = set(names)
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
            if line.startswith("NAME"):
                parts = line.split()
                name = parts[1] if len(parts) > 1 else None
            if line.strip() == "//":
                if name in want:
                    out.writelines(buf)
                    found.append(name)
                    want.discard(name)
                    if not want:
                        break
                buf = []
                name = None
    if want:
        raise SystemExit(f"missing Pfam models: {sorted(want)}")
    return found


def truncate_fasta(gz_path: Path, dest: Path, n: int) -> int:
    with gzip.open(gz_path, "rt") as src:
        return copy_fasta_head(src, dest, n)


def prepare_work(work: Path, data_root: Path) -> dict:
    inn = work / "in"
    if inn.exists():
        shutil.rmtree(inn)
    inn.mkdir(parents=True)
    (work / "out").mkdir(parents=True, exist_ok=True)
    pfam = data_root / "hmmer" / "Pfam-A.hmm.gz"
    names = list(repro.MODELS)
    found = extract_hmm(pfam, names, inn / "subset.hmm")
    kept = {}
    for step, meta in GENOMES.items():
        src = data_root / "recurrence" / "A" / f"{meta['accession']}_protein.faa.gz"
        dest = inn / f"{step}.faa"
        n = truncate_fasta(src, dest, N_PROTEINS)
        if n != N_PROTEINS:
            raise SystemExit(f"{meta['accession']} yielded {n} records, wanted {N_PROTEINS}")
        kept[step] = n
    (inn / "abi.c").write_text(ABI_C)
    return {
        "models_written": found,
        "n_models": len(found),
        "proteins_kept": kept,
        "subset_hmm_sha256": sha256_file(inn / "subset.hmm"),
        "subset_hmm_bytes": (inn / "subset.hmm").stat().st_size,
        "pfam_gz_sha256": sha256_file(pfam),
        "pfam_gz_bytes": pfam.stat().st_size,
        "genome_sha256": {step: sha256_file(inn / f"{step}.faa") for step in GENOMES},
    }


def build_image() -> None:
    proc = subprocess.run(
        [
            "docker", "build",
            "--platform", "linux/arm64",
            "-f", str(DOCKERFILE),
            "-t", IMAGE,
            str(DOCKERFILE.parent),
        ],
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"docker build failed ({proc.returncode})")


def host_provenance() -> dict:
    git = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT.parent, capture_output=True, text=True
    )
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT.parent, capture_output=True, text=True
    )
    uname = platform.uname()
    return {
        "git": (git.stdout or "").strip(),
        "git_dirty": bool((dirty.stdout or "").strip()),
        "host": platform.node(),
        "platform": platform.platform(),
        "uname": f"{uname.system} {uname.release} {uname.machine}",
        "python": platform.python_version(),
    }


def _parse_probe(text: str) -> dict:
    rc = None
    errno = None
    for line in text.splitlines():
        if line.startswith("request=0x420e"):
            for field in line.split():
                if field.startswith("rc=") and field != "rc=missing":
                    try:
                        rc = int(field.split("=", 1)[1])
                    except ValueError:
                        rc = None
                elif field.startswith("errno=") and not field.startswith("errno=missing"):
                    try:
                        errno = int(field.split("=", 1)[1])
                    except ValueError:
                        errno = None
    return {"rc": rc, "errno": errno, "succeeded": rc is not None and rc != -1}


def _kv_block(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        if not line.startswith("ACTS_") or " " not in line:
            continue
        key, value = line.split(" ", 1)
        out[key] = value
    return out


def parse_column_output(text: str) -> list[dict]:
    steps: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        if line.startswith("ACTS_STEP "):
            parts = line.split()
            current = {"column": parts[1], "mode": parts[2], "step": parts[3]}
            steps.append(current)
            continue
        if current is None or line.startswith("ACTS_ENDSTEP "):
            continue
        if line.startswith("ACTS_EXIT "):
            current["exit_code"] = int(line.split()[1])
        elif line.startswith("ACTS_CPU_MTIME "):
            current["cpu_mtime"] = line.split(" ", 1)[1]
        elif line.startswith("ACTS_CMD_SHA "):
            current["command_sha256"] = line.split(" ", 1)[1]
        elif line.startswith("ACTS_FASTA_SHA "):
            current["fasta_sha256"] = line.split(" ", 1)[1]
        elif line.startswith("ACTS_HMM_SHA "):
            current["hmm_sha256"] = line.split(" ", 1)[1]
        elif line.startswith("ACTS_TBLOUT_BEFORE "):
            current["tblout_sha256_before"] = line.split(" ", 1)[1]
        elif line.startswith("ACTS_TBLOUT_AFTER "):
            current["tblout_sha256_after"] = line.split(" ", 1)[1]
        elif line.startswith("ACTS_TBLOUT_MTIME_BEFORE "):
            current["tblout_mtime_before"] = line.split(" ", 1)[1]
        elif line.startswith("ACTS_TBLOUT_MTIME_AFTER "):
            current["tblout_mtime_after"] = line.split(" ", 1)[1]
    return steps


def newly_written(row: dict) -> bool:
    before = row.get("tblout_sha256_before")
    after = row.get("tblout_sha256_after")
    mtime_before = row.get("tblout_mtime_before")
    mtime_after = row.get("tblout_mtime_after")
    if not after or after == "absent":
        return False
    if before in (None, "absent"):
        return True
    if before != after:
        return True
    if mtime_before != mtime_after:
        return True
    return False


def score_column(column: str, work: Path, text: str, docker_exit: int) -> dict:
    parsed = parse_column_output(text)
    header = []
    for line in text.splitlines():
        if line.startswith("ACTS_STEP "):
            break
        header.append(line)
    header_text = "\n".join(header)
    info = _kv_block(header)
    probe = _parse_probe(header_text)
    modes: dict[str, list[dict]] = {"hmmscan": [], "hmmsearch": []}
    missing = "ACTS_BINARY_MISSING" in text
    for row in parsed:
        mode = row["mode"]
        step = row["step"]
        fasta_key = "genome1" if step == "genome1" else "genome2"
        tbl_path = work / "out" / column / f"{mode}_{step}.tbl"
        got = tbl_path.read_text(errors="replace") if tbl_path.is_file() else ""
        stock_path = work / "out" / "stock" / mode / f"{fasta_key}.tbl"
        stock = stock_path.read_text(errors="replace") if stock_path.is_file() else ""
        show_path = work / "out" / column / f"{mode}_{step}.show"
        marker_path = work / "out" / column / f"{mode}_{step}.marker"
        tail_path = work / "out" / column / f"{mode}_{step}.tail"
        # Riker's --show log is the classification input. ProcessCache's
        # debug log can be large; the marker file is the replay proof.
        log = show_path.read_text(errors="replace") if show_path.is_file() else ""
        marker = marker_path.read_text(errors="replace") if marker_path.is_file() else ""
        must = None
        if column == "riker":
            must = bool(riker_must_run_lines(log, mode))
        replay = log_says_replay(marker) or log_says_replay(log)
        match = bool(got) and bool(stock) and tables_match(got, stock, mode)
        action = judge_behavioral(
            exit_code=int(row.get("exit_code", docker_exit)),
            tblout_nonempty=nonempty_body(got),
            tblout_header=tblout_has_header(got),
            newly_written=newly_written(row),
            replay_marker=replay,
            riker_must_run=must,
            match=match,
        )
        proof = marker.strip().splitlines()[:1]
        if not proof and action == "executed":
            proof = [ln for ln in got.splitlines() if ln.startswith("#")][:1]
        modes[mode].append({
            "name": step,
            "accession": GENOMES[fasta_key]["accession"],
            "n_proteins": N_PROTEINS,
            "exit_code": row.get("exit_code"),
            "action": action,
            "match": match,
            "output_nonempty": nonempty_body(got),
            "tblout_header": tblout_has_header(got),
            "newly_written": newly_written(row),
            "replay_marker": replay,
            "riker_must_run": must,
            "proof": proof,
            "cpu_mtime": row.get("cpu_mtime"),
            "command_sha256": row.get("command_sha256"),
            "fasta_sha256": row.get("fasta_sha256"),
            "hmm_sha256": row.get("hmm_sha256"),
            "tblout_sha256_before": row.get("tblout_sha256_before"),
            "tblout_sha256_after": row.get("tblout_sha256_after"),
            "tblout_mtime_before": row.get("tblout_mtime_before"),
            "tblout_mtime_after": row.get("tblout_mtime_after"),
            "tblout_bytes": tbl_path.stat().st_size if tbl_path.is_file() else 0,
            "log_tail": tail_path.read_text(errors="replace") if tail_path.is_file() else "",
        })
    scored = {"hmmscan": {}, "hmmsearch": {}}
    for mode, steps in modes.items():
        by_name = {step["name"]: step for step in steps}
        genome2 = by_name.get("genome2")
        applies = bool(genome2 and genome2["action"] == "executed")
        projection = project_hours(column, mode) if applies else {
            "label": "PROJECTED",
            "applies": False,
            "reason": "genome 2 did not execute; stock-plus-overhead is not the paper cost",
        }
        if applies:
            projection["applies"] = True
        scored[mode] = {
            "steps": steps,
            "agrees_genome2_executes": bool(genome2 and genome2["action"] == "executed"),
            "falsifier_whole_command_fired": bool(genome2 and genome2["action"] == "replayed"),
            "agrees_replay_skips": bool(by_name.get("replay") and by_name["replay"]["action"] == "replayed"),
            "annotations_split_records": False,
            "projection": projection,
        }
    return {
        "docker_exit": docker_exit,
        "binary_missing": missing,
        "environment": info,
        "probe": probe,
        "modes": scored,
        "wrapper_head": header_text[-2000:],
    }


def copy_stock(column_text: str, work: Path) -> None:
    """Stock tables are inside the container at /data/stock.

    The sequence script copies them to /work/out/stock before ACTS_DONE.
    This function is the host-side check that those files exist.
    """
    del column_text
    stock = work / "out" / "stock"
    if not stock.is_dir():
        raise SystemExit(f"stock tables were not copied to {stock}")


def run_column(column: str, work: Path) -> dict:
    script = sequence_script(column)
    # Stock copy is part of the script. Append it once.
    script += (
        "mkdir -p /work/out/stock\n"
        "cp -a /data/stock/. /work/out/stock/\n"
        "cp -a /opt/riker.commit /opt/ProcessCache.commit /opt/ProcessCache.build "
        "/opt/incr.commit /opt/incr.diff /opt/incr.debug_lines /opt/unshare.version "
        "/opt/hmmer.version /opt/hmmer.tar.sha256 /opt/compiler.txt /opt/rkr.file "
        "/opt/rustc-stable.txt /opt/rustc-nightly.txt /opt/python.version "
        "/opt/mergerfs.version /work/out/ 2>/dev/null || true\n"
    )
    proc = subprocess.run(
        docker_argv(column, work, script),
        check=False,
        capture_output=True,
        text=True,
    )
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    (work / "out" / f"{column}.wrapper").write_text(text)
    try:
        copy_stock(text, work)
    except SystemExit:
        if column != "riker":
            pass
        else:
            raise
    return score_column(column, work, text, proc.returncode)


def _selfcheck() -> None:
    if len(repro.MODELS) != 73:
        raise SystemExit(f"model count drifted: {len(repro.MODELS)}")
    header = "# hmmsearch :: search\n--- full sequence ----\nseq PF 1\n"
    if judge_behavioral(
        exit_code=0, tblout_nonempty=True, tblout_header=True, newly_written=True,
        replay_marker=False, riker_must_run=None, match=True,
    ) != "executed":
        raise SystemExit("executed")
    if judge_behavioral(
        exit_code=0, tblout_nonempty=False, tblout_header=False, newly_written=False,
        replay_marker=False, riker_must_run=None, match=False,
    ) != "invalid":
        raise SystemExit("empty exit is invalid")
    if judge_behavioral(
        exit_code=0, tblout_nonempty=True, tblout_header=True, newly_written=False,
        replay_marker=True, riker_must_run=None, match=True,
    ) != "replayed":
        raise SystemExit("marker replay")
    if judge_behavioral(
        exit_code=0, tblout_nonempty=True, tblout_header=True, newly_written=False,
        replay_marker=False, riker_must_run=False, match=True,
    ) != "replayed":
        raise SystemExit("riker skip")
    if judge_behavioral(
        exit_code=2, tblout_nonempty=False, tblout_header=False, newly_written=False,
        replay_marker=False, riker_must_run=False, match=False,
    ) != "invalid":
        raise SystemExit("riker failure is not a skip")
    if judge_behavioral(
        exit_code=0, tblout_nonempty=True, tblout_header=True, newly_written=True,
        replay_marker=True, riker_must_run=None, match=False,
    ) != "invalid":
        raise SystemExit("replay without MATCH is invalid")
    if log_says_replay("unshare has no --root; incr.sh cannot start"):
        raise SystemExit("unshare failure is not a replay marker")
    if not tblout_has_header(header):
        raise SystemExit("header")
    for column in FACTORS:
        g2 = step_plan(column, "hmmsearch", "genome2")
        replay = step_plan(column, "hmmsearch", "replay")
        if g2["argv"] != replay["argv"]:
            raise SystemExit(f"{column} replay argv drifted")
        if replay["rewrite_command"]:
            raise SystemExit(f"{column} replay rewrites the command")
        if g2["tblout"] != replay["tblout"] or not g2["tblout"].endswith("genome2.tbl"):
            raise SystemExit(f"{column} tblout")
        script = sequence_script(column)
        replay_body = script.split(f"echo ACTS_STEP {column} hmmsearch replay", 1)[1]
        replay_body = replay_body.split(f"echo ACTS_ENDSTEP {column} hmmsearch replay", 1)[0]
        if f"> /data/{column}/hmmsearch/Rikerfile" in replay_body:
            raise SystemExit("replay rewrites Rikerfile")
        if f"> /data/{column}/hmmsearch/run.sh" in replay_body:
            raise SystemExit("replay rewrites run.sh")
        if "\nrm " in "\n" + replay_body:
            raise SystemExit("replay removes files")
    ann = sequence_script("incr_annotations")
    default = sequence_script("incr_default")
    if "--enable_annotations" not in ann or "--enable_annotations" in default:
        raise SystemExit("annotations flag")
    if "unset INCR_SYS_PATH" not in default:
        raise SystemExit("default must not export annotations")
    scan = project_hours("riker", "hmmscan")
    search = project_hours("riker", "hmmsearch")
    if scan["hours_per_genome"] != "0.9248" or search["hours_per_genome"] != "0.1904":
        raise SystemExit(f"riker projection {scan['hours_per_genome']} {search['hours_per_genome']}")
    if project_hours("processcache", "hmmscan")["hours_per_genome"] != "1.4365":
        raise SystemExit("processcache projection")
    if project_hours("incr_default", "hmmscan")["hours_per_genome"] != "1.708925":
        raise SystemExit("incr default projection")
    if project_hours("incr_annotations", "hmmsearch")["hours_per_genome"] != "0.2512125":
        raise SystemExit("incr annotations projection")
    caps = docker_argv("riker", Path("/tmp/w"), "true")
    if "--privileged" in caps or "SYS_PTRACE" not in caps:
        raise SystemExit(f"riker caps {caps}")
    inc = docker_argv("incr_default", Path("/tmp/w"), "true")
    if "--privileged" not in inc:
        raise SystemExit("incr is not privileged")
    if not newly_written({
        "tblout_sha256_before": "abc",
        "tblout_sha256_after": "abc",
        "tblout_mtime_before": "1",
        "tblout_mtime_after": "2",
    }):
        raise SystemExit("mtime change is a new write")
    if newly_written({
        "tblout_sha256_before": "abc",
        "tblout_sha256_after": "abc",
        "tblout_mtime_before": "1",
        "tblout_mtime_after": "1",
    }):
        raise SystemExit("unchanged file is not a new write")
    print("baseline_docker_uniform selfcheck ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selfcheck", action="store_true")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--work", type=Path, default=Path("/tmp/acts-baseline-docker-uniform"))
    parser.add_argument(
        "--out", type=Path, default=ROOT / "results" / "baseline_docker_uniform.json",
    )
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--columns",
        default="riker,processcache,incr_default,incr_annotations",
    )
    args = parser.parse_args()
    if args.selfcheck:
        _selfcheck()
        return
    if args.data_root is None:
        raise SystemExit("--data-root is required")
    _selfcheck()
    prepared = prepare_work(args.work, args.data_root)
    if not args.skip_build:
        build_image()
    columns = [part.strip() for part in args.columns.split(",") if part.strip()]
    payload = {
        "label": "MEASURED",
        "decides": "executed/replayed/invalid and MATCH; not wall time",
        "protocol": "pipeline/docs/BASELINES_PROTOCOL.md",
        "addendum": "2026-10-10 uniform Docker behavioral smoke",
        "provenance": host_provenance(),
        "prediction": {
            "genome1": "executed",
            "genome2": "executed",
            "replay": "replayed",
            "annotations_do_not_split_fasta_records": True,
            "source": "BASELINES_PROTOCOL.md locked sections, applied to genome 2's exact argv",
        },
        "workload": {
            "n_models": prepared["n_models"],
            "proteins_kept": N_PROTEINS,
            "genomes": GENOMES,
            "subset_hmm_sha256": prepared["subset_hmm_sha256"],
            "subset_hmm_bytes": prepared["subset_hmm_bytes"],
            "pfam_gz_bytes": prepared["pfam_gz_bytes"],
            "pfam_gz_sha256": prepared["pfam_gz_sha256"],
            "genome_sha256": prepared["genome_sha256"],
            "cpu_flag": 32,
        },
        "image": IMAGE,
        "columns": {},
    }
    for column in columns:
        payload["columns"][column] = {
            "capabilities": column_capabilities(column),
            **run_column(column, args.work),
        }
    prov_dir = args.work / "out"
    versions = {}
    for name in (
        "riker.commit", "ProcessCache.commit", "ProcessCache.build", "incr.commit",
        "incr.diff", "incr.debug_lines", "unshare.version", "hmmer.version",
        "hmmer.tar.sha256", "compiler.txt", "rkr.file", "rustc-stable.txt",
        "rustc-nightly.txt", "python.version", "mergerfs.version",
    ):
        path = prov_dir / name
        if path.is_file():
            versions[name] = path.read_text(errors="replace")[:4000]
    payload["image_files"] = versions
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
