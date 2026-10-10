#!/usr/bin/env python3
"""Riker behavioral falsifier in Docker. Not a timing run.

Pre-registered in pipeline/docs/BASELINES_PROTOCOL.md
(addendum 2026-10-09, Docker). Classification comes from
`rkr --show`, which prints a command only when it must run.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
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

IMAGE = "acts-riker-docker:local"
DOCKERFILE = ROOT / "docker" / "Dockerfile.riker_docker"
RIKER_COMMIT = "bae684b455a4d8fa010fc04b471f5ca9b408f6a8"
N_PROTEINS = 300
OVERHEAD = Decimal("0.088")
SAMPLE_HOURS = {"hmmscan": Decimal("5.10"), "hmmsearch": Decimal("1.05")}
SAMPLE_GENOMES = 6
GENOMES = {
    "genome1": {
        "position": 1,
        "accession": "GCF_002853805.1",
        "proteins_in_file": 5117,
    },
    "genome2": {
        "position": 2,
        "accession": "GCF_002090355.1",
        "proteins_in_file": 4091,
    },
}

# Same program as pipeline/jobs/baseline_ptrace_abi.job.
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


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def hmmer_lines(stdout: str, mode: str) -> list[str]:
    """Lines whose first field is the mode's HMMER binary.

    `rkr --show` prints the basename first (getShortName) and only
    when the command must run.
    """
    hits = []
    for line in stdout.splitlines():
        fields = line.split()
        if fields and fields[0] == mode:
            hits.append(line)
    return hits


def classify_trace(stdout: str, mode: str, exit_code: int) -> str:
    hits = hmmer_lines(stdout, mode)
    if hits:
        return "executed"
    if exit_code == 0:
        return "skipped"
    return "unresolved"


def trace_lines(stdout: str) -> list[str]:
    """Keep rkr --show command lines, not HMMER's per-query stdout."""
    kept = []
    for line in stdout.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if line.startswith(("Query:", "Description:", "Accession:", "Scores ")):
            break
        kept.append(line)
    return kept


def dec_str(value: Decimal) -> str:
    text = format(value.quantize(Decimal("0.0001")), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def project_hours(mode: str) -> dict:
    per = (SAMPLE_HOURS[mode] / SAMPLE_GENOMES) * (1 + OVERHEAD)
    return {
        "label": "PROJECTED",
        "formula": "T_riker = (T_sample / 6) * (1 + 0.088) hours per genome",
        "T_sample_h": format(SAMPLE_HOURS[mode], "f"),
        "overhead": "0.088",
        "overhead_source": (
            "Curtsinger and Barowy, USENIX ATC 2022, abstract and Figure 3: "
            "median full-build overhead 8.8% on 14 software packages. "
            "Not a measured HMMER overhead."
        ),
        "hours_per_genome": dec_str(per),
        "hours_A30": dec_str(30 * per),
        "hours_B40": dec_str(40 * per),
    }


def docker_run(image: str, work: Path, script: str) -> subprocess.CompletedProcess[str]:
    argv = [
        "docker", "run", "--rm",
        "--platform", "linux/arm64",
        "--cap-add", "SYS_PTRACE",
        "-v", f"{work}:/work",
        "-w", "/work",
        image,
        "bash", "-lc", script,
    ]
    return subprocess.run(argv, check=False, capture_output=True, text=True)


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


def argv_line(mode: str, tblout: str, fasta: str) -> str:
    binary = f"/opt/hmmer/bin/{mode}"
    if mode == "hmmscan":
        parts = [
            binary, "--cpu", "32", "--cut_ga", "--noali", "--tblout", tblout,
            "/work/subset.hmm", fasta,
        ]
    elif mode == "hmmsearch":
        parts = [
            binary, "--cpu", "32", "--noali", "--tblout", tblout,
            "-Z", "1000000", "--domZ", "1000000",
            "/work/subset.hmm", fasta,
        ]
    else:
        raise ValueError(mode)
    return " ".join(parts) + "\n"


def prepare_work(work: Path, data_root: Path) -> dict:
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    pfam = data_root / "hmmer" / "Pfam-A.hmm.gz"
    names = list(repro.MODELS)
    found = extract_hmm(pfam, names, work / "subset.hmm")
    kept = {}
    for step, meta in GENOMES.items():
        src = data_root / "recurrence" / "A" / f"{meta['accession']}_protein.faa.gz"
        dest = work / f"{step}.faa"
        n = truncate_fasta(src, dest, N_PROTEINS)
        if n != N_PROTEINS:
            raise SystemExit(f"{meta['accession']} yielded {n} records, wanted {N_PROTEINS}")
        kept[step] = n
    (work / "abi.c").write_text(ABI_C)
    return {
        "models_written": found,
        "n_models": len(found),
        "proteins_kept": kept,
        "subset_hmm_sha256": sha256_file(work / "subset.hmm"),
        "subset_hmm_bytes": (work / "subset.hmm").stat().st_size,
        "pfam_gz_sha256": sha256_file(pfam),
        "pfam_gz_bytes": pfam.stat().st_size,
        "genome_sha256": {
            step: sha256_file(work / f"{step}.faa") for step in GENOMES
        },
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


def run_probe(work: Path) -> dict:
    script = r"""
set -u
echo "UNAME $(uname -a)"
echo "PTRACE_SCOPE $(cat /proc/sys/kernel/yama/ptrace_scope 2>/dev/null || echo absent)"
echo "HEADER"
grep -n "0x420" /usr/include/sys/ptrace.h /usr/include/linux/ptrace.h || true
gcc -O2 -Wall -o /work/abi /work/abi.c
/work/abi
echo ABI_DONE
"""
    proc = docker_run(IMAGE, work, script)
    text = (proc.stdout or "") + (proc.stderr or "")
    rc = None
    errno = None
    for line in text.splitlines():
        if line.startswith("request=0x420e"):
            # request=0x420e rc=-1 errno=5 Input/output error
            fields = line.split()
            for field in fields:
                if field.startswith("rc="):
                    rc = int(field.split("=", 1)[1])
                elif field.startswith("errno="):
                    errno = int(field.split("=", 1)[1])
    return {
        "exit_code": proc.returncode,
        "rc": rc,
        "errno": errno,
        "succeeded": rc is not None and rc != -1,
        "stdout": text,
    }


def run_mode(work: Path, mode: str) -> list[dict]:
    home = work / mode
    home.mkdir(parents=True, exist_ok=True)
    steps = []
    rikerfile = home / "Rikerfile"
    for name in ("genome1", "genome2", "replay"):
        fasta_key = "genome2" if name != "genome1" else "genome1"
        fasta = f"/work/{fasta_key}.faa"
        tbl_name = "genome1.tbl" if name == "genome1" else "genome2.tbl"
        tbl = f"/work/{mode}/{tbl_name}"
        if name != "replay":
            rikerfile.write_text(argv_line(mode, tbl, fasta))
        text = rikerfile.read_text()
        before = {
            "rikerfile_sha256": sha256_text(text),
            "fasta_sha256": sha256_file(work / f"{fasta_key}.faa"),
            "hmm_sha256": sha256_file(work / "subset.hmm"),
        }
        log_dir = work / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log = log_dir / f"{mode}_{name}.log"
        # The --show log is not written into the traced directory.
        # A new file there would be an input change on the next step.
        script = (
            f"cd /work/{mode} && /opt/riker/release/bin/rkr --show "
            f"> /tmp/{mode}_{name}.log 2>&1; echo RKR_EXIT:$?; "
            f"mkdir -p /work/logs && cp /tmp/{mode}_{name}.log /work/logs/{mode}_{name}.log"
        )
        proc = docker_run(IMAGE, work, script)
        wrapper = (proc.stdout or "") + (proc.stderr or "")
        show = log.read_text(errors="replace") if log.is_file() else ""
        exit_code = None
        for line in wrapper.splitlines():
            if line.startswith("RKR_EXIT:"):
                exit_code = int(line.split(":", 1)[1])
        if exit_code is None:
            exit_code = proc.returncode
        action = classify_trace(show, mode, exit_code)
        tbl_path = home / tbl_name
        got = tbl_path.read_text(errors="replace") if tbl_path.is_file() else ""
        stock_path = home / f"stock_{fasta_key}.tbl"
        stock = stock_path.read_text(errors="replace") if stock_path.is_file() else ""
        steps.append({
            "name": name,
            "accession": GENOMES[fasta_key]["accession"],
            "n_proteins": N_PROTEINS,
            "fasta": fasta,
            "rikerfile": text.strip(),
            "rikerfile_sha256": before["rikerfile_sha256"],
            "fasta_sha256": before["fasta_sha256"],
            "hmm_sha256": before["hmm_sha256"],
            "exit_code": exit_code,
            "action": action,
            "show_lines": trace_lines(show),
            "hmmer_lines": hmmer_lines(show, mode),
            "stdout_line_count": len(show.splitlines()),
            "tblout_bytes": tbl_path.stat().st_size if tbl_path.is_file() else 0,
            "output_nonempty": nonempty_body(got),
            "match": bool(got) and bool(stock) and tables_match(got, stock, mode),
            "wrapper_tail": wrapper[-2000:],
        })
    return steps


def run_stock(work: Path) -> None:
    lines = []
    for mode in ("hmmscan", "hmmsearch"):
        home = f"/work/{mode}"
        lines.append(f"mkdir -p {home}")
        if mode == "hmmscan":
            lines.append("test -f /work/subset.hmm.h3m || hmmpress -f /work/subset.hmm")
        for step in ("genome1", "genome2"):
            tbl = f"{home}/stock_{step}.tbl"
            cmd = argv_line(mode, tbl, f"/work/{step}.faa").strip()
            # argv_line points the binary at /opt/hmmer/bin, which is correct.
            lines.append(cmd)
    script = "set -e\n" + "\n".join(lines) + "\n"
    proc = docker_run(IMAGE, work, script)
    if proc.returncode != 0:
        tail = ((proc.stdout or "") + (proc.stderr or ""))[-2000:]
        raise SystemExit(f"stock HMMER failed ({proc.returncode})\n{tail}")


def image_provenance(work: Path) -> dict:
    script = r"""
set -e
echo COMMIT:$(cat /opt/riker.commit)
echo FILE:$(cat /opt/rkr.file)
echo COMPILER:$(cat /opt/compiler.txt)
echo HMMER_SHA:$(cat /opt/hmmer.tar.sha256)
echo HMMER_VER:$(hmmscan -h | sed -n '2p')
echo UNAME:$(uname -a)
"""
    proc = docker_run(IMAGE, work, script)
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise SystemExit(f"provenance probe failed\n{text[-2000:]}")
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key] = value.strip()
    return out


def _selfcheck() -> None:
    if classify_trace("hmmscan --cpu 32 --cut_ga …\n", "hmmscan", 0) != "executed":
        raise SystemExit("executed")
    if classify_trace("sh Rikerfile\n", "hmmscan", 0) != "skipped":
        raise SystemExit("parent shell is not HMMER")
    if classify_trace("", "hmmsearch", 0) != "skipped":
        raise SystemExit("skipped")
    if classify_trace("", "hmmscan", 2) != "unresolved":
        raise SystemExit("unresolved")
    if hmmer_lines("hmmsearch -Z 1000000 x\n", "hmmscan"):
        raise SystemExit("mode filter")
    scan = project_hours("hmmscan")
    search = project_hours("hmmsearch")
    if scan["hours_per_genome"] != "0.9248" or scan["T_sample_h"] != "5.10":
        raise SystemExit(f"scan projection {scan}")
    if search["hours_per_genome"] != "0.1904":
        raise SystemExit(f"search projection {search['hours_per_genome']}")
    if scan["hours_A30"] != "27.744" or search["hours_B40"] != "7.616":
        raise SystemExit("collection projection")
    if len(repro.MODELS) != 73:
        raise SystemExit(f"model count drifted: {len(repro.MODELS)}")
    print("riker_docker selfcheck ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selfcheck", action="store_true")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--work", type=Path, default=Path("/tmp/acts-riker-docker"))
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "baseline_riker_docker.json")
    parser.add_argument("--skip-build", action="store_true")
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
    provenance = image_provenance(args.work)
    probe = run_probe(args.work)
    modes: dict[str, list[dict]] = {}
    if probe["succeeded"]:
        run_stock(args.work)
        for mode in ("hmmscan", "hmmsearch"):
            modes[mode] = run_mode(args.work, mode)
    payload = {
        "label": "MEASURED",
        "question": (
            "On a kernel that accepts PTRACE_GET_SYSCALL_INFO, does Riker "
            "re-execute HMMER on collection A genome 2, and does a replay "
            "of that same command skip it?"
        ),
        "decides": "executed/skipped/MATCH only; not wall time",
        "protocol": "pipeline/docs/BASELINES_PROTOCOL.md",
        "addendum": "2026-10-09 Riker behavioral falsifier in Docker",
        "environment": {
            "docker_platform": "linux/arm64",
            "cap_add": "SYS_PTRACE",
            "seccomp": "default Docker profile; not seccomp=unconfined; not --privileged",
            "image": IMAGE,
            "base": "ubuntu:22.04@sha256:5ec03bb3441e8b0bf3b4f9cd4629a1ae763010dc3035bb8da3ae6cf026486401",
            "uname": provenance.get("UNAME"),
            "riker_commit": provenance.get("COMMIT"),
            "riker_commit_expected": RIKER_COMMIT,
            "rkr_file": provenance.get("FILE"),
            "rkr_invoked": "/opt/riker/release/bin/rkr",
            "rkr_path_copy": (
                "Copying only the binary to /usr/local/bin segfaults in "
                "Build::launch. The falsifier invokes the in-tree release "
                "binary, which can see release/share/rkr."
            ),
            "compiler": provenance.get("COMPILER"),
            "compiler_note": (
                "make release CC=clang-15 "
                "CXX='clang++-15 -Wno-error=invalid-constexpr -fuse-ld=lld'. "
                "Ubuntu 22.04 clang++ lacks std::source_location. "
                "g++ 11.4 and g++-12 error on AccessFlags::operator+. "
                "-Wno-error=invalid-constexpr restores the warning in the CARC log. "
                "Riker source is not edited."
            ),
            "hmmer_tarball_sha256": provenance.get("HMMER_SHA"),
            "hmmer_version_line": provenance.get("HMMER_VER"),
        },
        "workload": {
            "n_models": prepared["n_models"],
            "models": prepared["models_written"],
            "proteins_kept": N_PROTEINS,
            "genomes": GENOMES,
            "subset_hmm_sha256": prepared["subset_hmm_sha256"],
            "subset_hmm_bytes": prepared["subset_hmm_bytes"],
            "pfam_gz_bytes": prepared["pfam_gz_bytes"],
            "pfam_gz_sha256": prepared["pfam_gz_sha256"],
            "genome_sha256": prepared["genome_sha256"],
            "cpu_flag": 32,
            "note": "--cpu 32 is the locked argv shape. The VM has 14 CPUs. Classification ignores wall time.",
        },
        "prediction": {
            "genome1": "executed",
            "genome2": "executed",
            "replay": "skipped",
            "source": "BASELINES_PROTOCOL.md locked Riker section; replay is genome 2's same path",
        },
        "probe": probe,
        "modes": {},
    }
    for mode, steps in modes.items():
        by_name = {step["name"]: step for step in steps}
        genome2 = by_name.get("genome2")
        applies = bool(genome2 and genome2["action"] == "executed")
        payload["modes"][mode] = {
            "steps": steps,
            "agrees_genome2": bool(genome2 and genome2["action"] == "executed"),
            "falsifier_whole_command_fired": bool(genome2 and genome2["action"] == "skipped"),
            "agrees_replay": bool(by_name.get("replay") and by_name["replay"]["action"] == "skipped"),
            "projection": project_hours(mode) if applies else {
                "label": "PROJECTED",
                "applies": False,
                "reason": "genome 2 did not re-execute; the stock-plus-overhead cost is not the paper number",
            },
        }
        if applies:
            payload["modes"][mode]["projection"]["applies"] = True
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
