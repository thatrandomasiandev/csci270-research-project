#!/usr/bin/env python3
"""Table 4 first-run ratios on one exclusive EPYC node.

Pre-registered in pipeline/docs/BASELINES_X86_PROTOCOL.md.
Does not rebuild baselines. Does not draw a new 500-protein set.
"""

from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from acts.fasta import copy_fasta_head  # noqa: E402
from baseline_match import body_lines, ws  # noqa: E402

FROZEN = "1c65571538afcc139af560156147e4276905f9b4"
PROTOCOL_REL = Path("docs") / "BASELINES_X86_PROTOCOL.md"
ACCESSION = "GCF_002853805.1"
NEW_ACCESSION = "GCF_002090355.1"
N_MODELS = 30134
N_PROTEINS = 500
CPU = "32"
FASTA_SHA = "6ab83e19bdfc79bb46d63b69d495a3b41b5dd42c6ba8abf53a0faea17256a3a6"
HMM_SHA = "4b0da6399b97d2b23329de82190b2e5705bde1dea4cb2d028a52712d5966739e"
POWER_FLOOR = 100
T_CRIT_DF3 = Decimal("3.1824463052842638")
PILOT_SEED = 20261261
MEASURED_SEED_RESERVED = 20261262
SYSTEMS = ("riker", "incr", "processcache", "tare")
BUILDS_DEFAULT = Path("/project2/biyik_1165/jjt_373/csci270-star/acts-baselines-20261009")
KERNEL_MARKERS = (
    "Unable to load seccomp",
    "PTRACE_GET_SYSCALL_INFO",
    "PR_SET_SECCOMP",
    "ptrace(PTRACE",
)


def lock_sentence() -> str:
    return (
        f"Locked subset: {N_MODELS} models, {N_PROTEINS} proteins "
        f"of {ACCESSION}."
    )


def protocol_line(text: str, prefix: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def body_sha(text: str) -> str:
    blob = ("\n".join(body_lines(text)) + "\n").encode()
    return hashlib.sha256(blob).hexdigest()


def dec_s(value: Decimal) -> str:
    return format(value, "f")


def quant2(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def pairs_for_repeat(repeat: int, systems: list[str]) -> list[dict]:
    count = len(systems)
    if count == 0:
        return []
    shift = repeat % count
    order = systems[shift:] + systems[:shift]
    rows = []
    for index, system in enumerate(order):
        rows.append({
            "system": system,
            "system_first": (repeat + index) % 2 == 1,
        })
    return rows


def paired_summary(ratios: list[Decimal]) -> dict:
    count = len(ratios)
    if count == 0:
        return {
            "n_valid": 0,
            "paired_ratio_vs_stock": [],
            "mean_paired_ratio": None,
            "stdev_paired_ratio": None,
            "ci95_low": None,
            "ci95_high": None,
            "df": None,
            "t_critical": None,
            "status": "INCONCLUSIVE",
        }
    mean = sum(ratios, Decimal(0)) / Decimal(count)
    payload = {
        "n_valid": count,
        "paired_ratio_vs_stock": [dec_s(item) for item in ratios],
        "mean_paired_ratio": dec_s(mean),
        "mean_paired_ratio_2dp": quant2(mean),
        "stdev_paired_ratio": "0" if count < 2 else None,
        "ci95_low": None,
        "ci95_high": None,
        "df": count - 1,
        "t_critical": None,
        "status": "INCONCLUSIVE",
    }
    if count < 2:
        return payload
    var = sum((item - mean) ** 2 for item in ratios) / Decimal(count - 1)
    sd = var.sqrt()
    payload["stdev_paired_ratio"] = dec_s(sd)
    if count != 4:
        return payload
    half = T_CRIT_DF3 * sd / Decimal(count).sqrt()
    low = mean - half
    high = mean + half
    payload.update({
        "t_critical": dec_s(T_CRIT_DF3),
        "ci95_low": dec_s(low),
        "ci95_high": dec_s(high),
        "ci95_low_2dp": quant2(low),
        "ci95_high_2dp": quant2(high),
        "status": "MEASURED",
    })
    return payload


def row_key(line: str) -> tuple:
    tokens = line.split()
    if len(tokens) < 3:
        return tuple(tokens)
    return (tokens[0], tokens[2])


def classify_tblout(stock: str, other: str) -> dict:
    """Difference classes for hmmscan tblout bodies.

    Token identity (order plus split()) is identical. Otherwise the
    classes are value-only, different-row, missing, extra, and order.
    """
    left = body_lines(stock)
    right = body_lines(other)
    left_n = [ws(line) for line in left]
    right_n = [ws(line) for line in right]
    base = {"n_stock": len(left_n), "n_other": len(right_n)}
    if left_n == right_n:
        return {**base, "relation": "identical", "classes": []}
    classes: list[str] = []
    left_k = [row_key(line) for line in left_n]
    right_k = [row_key(line) for line in right_n]
    if len(right_n) < len(left_n) or any(key not in right_k for key in left_k):
        classes.append("missing")
    if len(right_n) > len(left_n) or any(key not in left_k for key in right_k):
        classes.append("extra")
    if left_k == right_k:
        classes.append("value-only")
    elif Counter(left_k) == Counter(right_k):
        classes.append("order")
    else:
        classes.append("different-row")
    return {**base, "relation": "different", "classes": classes}


def mutate_evalue(stock: str) -> str:
    """Known-bad body: one full-sequence E-value token changed."""
    lines = stock.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not line.strip() or line.startswith("#"):
            continue
        tokens = line.split()
        if len(tokens) < 5:
            continue
        tokens[4] = "9.99e-99" if tokens[4] != "9.99e-99" else "8.88e-88"
        newline = "\n" if line.endswith("\n") else ""
        lines[index] = " ".join(tokens) + newline
        return "".join(lines)
    raise ValueError("stock tblout has no data row with an E-value column")


def header_ok(text: str) -> bool:
    return "--- full sequence ----" in text


def kernel_block(text: str) -> str | None:
    for marker in KERNEL_MARKERS:
        if marker in text:
            return marker
    return None


def tail(path: Path, limit: int = 4000) -> str:
    if not path.is_file():
        return ""
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, size - limit))
        return handle.read().decode("utf-8", "replace")


def run_proc(argv: list[str], cwd: Path, env: dict[str, str], log_path: Path) -> dict:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with log_path.open("w") as handle:
        proc = subprocess.run(
            argv, cwd=str(cwd), env=env, stdout=handle, stderr=subprocess.STDOUT, check=False,
        )
    wall = time.perf_counter() - started
    return {
        "argv": argv,
        "cwd": str(cwd),
        "exit_code": proc.returncode,
        "wall_s": wall,
        "log_path": str(log_path),
        "log_tail": tail(log_path),
    }


def hmm_argv(binary: Path, hmm: Path, fasta: Path, tblout: Path) -> list[str]:
    return [
        str(binary), "--cpu", CPU, "--cut_ga", "--noali", "--tblout", str(tblout),
        str(hmm), str(fasta),
    ]


def extract_head(src: Path, dest: Path, count: int) -> int:
    opener = gzip.open if src.suffix == ".gz" else open
    with opener(src, "rt", errors="replace") as handle:
        return copy_fasta_head(handle, dest, count)


def cache_fingerprint(root: Path) -> list[list]:
    if not root.is_dir():
        return []
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            stat = path.stat()
            rows.append([str(path.relative_to(root)), stat.st_size, stat.st_mtime_ns])
    return rows


def parse_decision(path: Path) -> dict:
    if not path.is_file():
        return {}
    out: dict = {"raw_tail": path.read_text(errors="replace")[-2000:]}
    for line in path.read_text(errors="replace").splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        key = key.strip()
        value = value.strip()
        if key == "phases":
            try:
                out["phases"] = ast.literal_eval(value)
            except (SyntaxError, ValueError):
                out["phases_raw"] = value[:500]
        else:
            out[key] = value
    return out


class Harness:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.builds = Path(args.builds)
        self.out = Path(args.out)
        self.scratch = Path(args.scratch)
        self.phase = args.phase
        self.repeats = 1 if args.phase == "pilot" else 4
        self.payload: dict = {
            "label": "PARTIAL",
            "phase": self.phase,
            "system": "TARE",
            "question": "Table 4 first-run rho = T/T_stock on one x86 node",
            "frozen_code": FROZEN,
            "seed": PILOT_SEED if args.phase == "pilot" else None,
            "seed_reserved_unused": MEASURED_SEED_RESERVED,
            "protocol": str(PROTOCOL_REL),
            "runs": [],
            "blocked": {},
            "controls": {},
        }
        self._dump = self.save

    def save(self, reason: str = "checkpoint") -> None:
        self.payload["checkpoint"] = reason
        self.payload["checkpoint_unix"] = time.time()
        self.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.payload, indent=2, default=str) + "\n")
        tmp.replace(self.out)

    def refuse_login(self) -> None:
        if os.environ.get("SLURM_JOB_ID"):
            return
        host = socket.gethostname()
        raise SystemExit(f"refusing to compute on {host} without SLURM_JOB_ID")

    def check_protocol(self) -> None:
        path = Path(self.args.protocol)
        text = path.read_text()
        if lock_sentence() not in text:
            raise SystemExit("protocol is missing the locked subset sentence")
        self.payload["protocol_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        if self.phase != "measured":
            return
        rows = protocol_line(text, "Locked stock data rows: ")
        body = protocol_line(text, "Locked stock body sha256: ")
        if not rows or not body or "pilot seed 20261261" not in text:
            raise SystemExit("measured run refused: pilot addendum is not in the protocol")
        self.locked_rows = int(rows)
        self.locked_body = body
        if self.locked_rows < POWER_FLOOR:
            raise SystemExit("locked row count is under the power floor")

    def probe(self) -> None:
        scratch = self.scratch / "probe"
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "ptrace.c").write_text(r"""
#define _GNU_SOURCE
#include <errno.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/wait.h>
#include <unistd.h>
#ifndef PTRACE_GET_SYSCALL_INFO
#define PTRACE_GET_SYSCALL_INFO 0x420e
#endif
int main(void) {
    int info_bad = 0;
    pid_t pid = fork();
    if (pid < 0) { perror("fork"); return 1; }
    if (pid == 0) {
        if (ptrace(PTRACE_TRACEME, 0, 0, 0) != 0) { perror("PTRACE_TRACEME"); return 2; }
        raise(SIGSTOP);
        _exit(0);
    }
    int status = 0;
    if (waitpid(pid, &status, 0) < 0) { perror("waitpid"); return 1; }
    if (WIFEXITED(status)) {
        printf("ptrace_child_exit %d\n", WEXITSTATUS(status));
        info_bad = 1;
    } else {
        char info[4096];
        memset(info, 0, sizeof info);
        errno = 0;
        long rc = ptrace(PTRACE_GET_SYSCALL_INFO, pid, (void *)sizeof info, info);
        int saved = errno;
        ptrace(PTRACE_CONT, pid, 0, 0);
        waitpid(pid, &status, 0);
        if (rc == -1) {
            printf("GET_SYSCALL_INFO rc=%ld errno=%d (%s)\n", rc, saved, strerror(saved));
            info_bad = 1;
        } else {
            printf("GET_SYSCALL_INFO ok\n");
        }
    }
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) { perror("PR_SET_NO_NEW_PRIVS"); return 4; }
    struct sock_filter filter[] = { BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW) };
    struct sock_fprog prog = { .len = 1, .filter = filter };
    if (prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog) != 0) {
        perror("PR_SET_SECCOMP");
        return 5;
    }
    printf("seccomp_bpf_ok\n");
    return info_bad ? 3 : 0;
}
""")
        compile_log = scratch / "cc.log"
        compiled = subprocess.run(
            ["gcc", "-O2", "-o", str(scratch / "probe"), str(scratch / "ptrace.c")],
            check=False, text=True, capture_output=True,
        )
        compile_log.write_text((compiled.stderr or "") + (compiled.stdout or ""))
        if compiled.returncode != 0:
            self.payload["probes"] = {
                "compile_exit": compiled.returncode,
                "compile_log": compile_log.read_text()[-2000:],
            }
            self.save("probe_compile")
            raise SystemExit("capability probe failed to compile; see probes.compile_log")
        ran = subprocess.run([str(scratch / "probe")], check=False, text=True, capture_output=True)
        unshare = subprocess.run(
            ["unshare", "--user", "--mount", "--map-root-user", "true"],
            check=False, text=True, capture_output=True,
        )
        help_u = subprocess.run(["unshare", "--help"], check=False, text=True, capture_output=True)
        help_text = (help_u.stdout or "") + (help_u.stderr or "")
        text = (ran.stdout or "") + (ran.stderr or "")
        self.payload["probes"] = {
            "compile_exit": compiled.returncode,
            "probe_exit": ran.returncode,
            "probe_output": text[-1500:],
            "get_syscall_info_ok": "GET_SYSCALL_INFO ok" in text,
            "seccomp_ok": "seccomp_bpf_ok" in text,
            "unshare_user_exit": unshare.returncode,
            "unshare_user_err": ((unshare.stderr or "") + (unshare.stdout or ""))[-500:],
            "unshare_has_root": "--root" in help_text,
            "ptrace_scope": Path("/proc/sys/kernel/yama/ptrace_scope").read_text().strip()
            if Path("/proc/sys/kernel/yama/ptrace_scope").is_file() else None,
        }
        self.save("probes")

    def binaries(self) -> dict[str, Path]:
        root = self.builds
        return {
            "hmmscan": root / "bin" / "hmmscan",
            "hmmpress": root / "bin" / "hmmpress",
            "processcache": root / "bin" / "process_cache_sha256",
            "incr": root / "src" / "incr" / "target" / "release" / "incr",
            "incr_sh": root / "src" / "incr" / "src" / "incr.sh",
            "riker": root / "bin" / "rkr",
            "mergerfs": root / "bin" / "mergerfs",
            "incr_python": root / "venv" / "bin" / "python3",
        }

    def record_binaries(self) -> None:
        found = {}
        for name, path in self.binaries().items():
            found[name] = {
                "path": str(path),
                "present": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() and path.stat().st_size < 80_000_000 else None,
                "bytes": path.stat().st_size if path.is_file() else 0,
            }
        self.payload["binaries"] = found
        version = subprocess.run(
            [str(self.binaries()["hmmscan"]), "-h"], check=False, text=True, capture_output=True,
        )
        self.payload["hmmer_help_head"] = ((version.stdout or "") + (version.stderr or ""))[:400]
        self.save("binaries")

    def block_from_probes(self) -> None:
        probes = self.payload["probes"]
        bins = self.payload["binaries"]
        ptrace_denied = (
            "PTRACE_TRACEME" in probes["probe_output"]
            or "ptrace_child_exit" in probes["probe_output"]
        )
        if ptrace_denied:
            for name in ("riker", "processcache", "incr"):
                self.payload["blocked"][name] = {
                    "reason": "ptrace probe failed",
                    "output": probes["probe_output"],
                }
        elif not probes["get_syscall_info_ok"]:
            self.payload["blocked"]["riker"] = {
                "reason": "PTRACE_GET_SYSCALL_INFO failed",
                "output": probes["probe_output"],
            }
        elif not bins["riker"]["present"]:
            self.payload["blocked"]["riker"] = {
                "reason": "no rkr binary in the reused build directory and the source tree is absent; not cloned and not rebuilt",
                "probe": probes["probe_output"],
            }
        if "processcache" not in self.payload["blocked"] and not bins["processcache"]["present"]:
            self.payload["blocked"]["processcache"] = {"reason": "process_cache_sha256 binary absent"}
        elif "processcache" not in self.payload["blocked"] and not probes["seccomp_ok"]:
            self.payload["blocked"]["processcache"] = {
                "reason": "seccomp-bpf probe failed",
                "output": probes["probe_output"],
            }
        if "incr" in self.payload["blocked"]:
            pass
        elif not bins["incr"]["present"] or not bins["incr_sh"]["present"]:
            self.payload["blocked"]["incr"] = {"reason": "incr binary or incr.sh absent"}
        elif not probes["seccomp_ok"]:
            self.payload["blocked"]["incr"] = {
                "reason": "seccomp-bpf probe failed",
                "output": probes["probe_output"],
            }
        elif probes["unshare_user_exit"] != 0 or not probes["unshare_has_root"]:
            self.payload["blocked"]["incr"] = {
                "reason": "user unshare or unshare --root unavailable",
                "unshare_user_exit": probes["unshare_user_exit"],
                "unshare_user_err": probes["unshare_user_err"],
                "unshare_has_root": probes["unshare_has_root"],
            }
        self.save("blocked")

    def prepare_inputs(self) -> None:
        data = self.scratch / "data"
        data.mkdir(parents=True, exist_ok=True)
        src_hmm = self.builds / "data" / "Pfam-A.hmm"
        hmm = data / "Pfam-A.hmm"
        if not hmm.is_file() or hmm.stat().st_size != src_hmm.stat().st_size:
            print("copying Pfam to scratch", flush=True)
            shutil.copy2(src_hmm, hmm)
            for suffix in (".h3m", ".h3i", ".h3f", ".h3p"):
                side = Path(str(src_hmm) + suffix)
                if not side.is_file():
                    raise SystemExit(f"missing pressed sidecar {side}")
                shutil.copy2(side, Path(str(hmm) + suffix))
        digest = sha256_file(hmm)
        headers = 0
        with hmm.open("rb") as handle:
            for line in handle:
                if line.startswith(b"HMMER3/"):
                    headers += 1
        fasta = data / "genome1.faa"
        sources = [
            self.builds / "data" / f"{ACCESSION}_protein.faa",
            Path("/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/recurrence/A")
            / f"{ACCESSION}_protein.faa.gz",
        ]
        used = None
        got = 0
        for source in sources:
            if not source.is_file():
                continue
            got = extract_head(source, fasta, N_PROTEINS)
            if sha256_file(fasta) == FASTA_SHA and got == N_PROTEINS:
                used = str(source)
                break
        fasta_digest = sha256_file(fasta) if fasta.is_file() else None
        new_src_plain = self.builds / "data" / f"{NEW_ACCESSION}_protein.faa"
        new_src_gz = (
            Path("/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/recurrence/A")
            / f"{NEW_ACCESSION}_protein.faa.gz"
        )
        new_fasta = data / "genome2.faa"
        new_source = new_src_plain if new_src_plain.is_file() else new_src_gz
        new_n = extract_head(new_source, new_fasta, N_PROTEINS) if new_source.is_file() else 0
        self.payload["workload"] = {
            "n_models_counted": headers,
            "n_models_locked": N_MODELS,
            "n_proteins": got,
            "accession": ACCESSION,
            "fasta_sha256": fasta_digest,
            "fasta_sha256_locked": FASTA_SHA,
            "fasta_source": used,
            "hmm_sha256": digest,
            "hmm_sha256_locked": HMM_SHA,
            "hmm": str(hmm),
            "new_accession": NEW_ACCESSION,
            "new_proteins": new_n,
            "new_fasta_sha256": sha256_file(new_fasta) if new_fasta.is_file() else None,
            "cpu": CPU,
            "argv_template": f"hmmscan --cpu {CPU} --cut_ga --noali --tblout T HMM FASTA",
        }
        self.hmm = hmm
        self.fasta = fasta
        self.new_fasta = new_fasta
        self.save("workload")
        problems = []
        if digest != HMM_SHA:
            problems.append(f"hmm sha {digest}")
        if headers != N_MODELS:
            problems.append(f"models {headers}")
        if fasta_digest != FASTA_SHA or got != N_PROTEINS:
            problems.append(f"fasta sha {fasta_digest} proteins {got}")
        if new_n != N_PROTEINS or sha256_file(new_fasta) == FASTA_SHA:
            problems.append("new genome is missing or identical to the locked FASTA")
        if problems:
            self.payload["label"] = "BLOCKED_WORKLOAD"
            self.payload["workload_error"] = problems
            self.save("workload_mismatch")
            raise SystemExit("workload mismatch: " + "; ".join(problems))

    def base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PATH"] = str(self.builds / "bin") + os.pathsep + env.get("PATH", "")
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["OMP_NUM_THREADS"] = "1"
        return env

    def read_tbl(self, path: Path) -> str:
        if not path.is_file():
            return ""
        return path.read_text(errors="replace")

    def stock_run(self, fasta: Path, dest: Path, log: Path) -> dict:
        if dest.exists():
            dest.unlink()
        before = dest.exists()
        proc = run_proc(
            hmm_argv(self.binaries()["hmmscan"], self.hmm, fasta, dest),
            self.scratch, self.base_env(), log,
        )
        text = self.read_tbl(dest)
        proc.update({
            "tool": "stock",
            "existed_before": before,
            "tblout": str(dest),
            "tblout_bytes": dest.stat().st_size if dest.is_file() else 0,
            "header": header_ok(text),
            "n_rows": len(body_lines(text)),
            "body_sha256": body_sha(text) if text else None,
            "valid": proc["exit_code"] == 0 and header_ok(text) and len(body_lines(text)) >= POWER_FLOOR,
        })
        return proc

    def judge_wrapper(self, proc: dict, stock_text: str, *, cold: bool, cold_wall: float,
                      cache_before, cache_after, argv_same: bool) -> dict:
        text = self.read_tbl(Path(proc["tblout"]))
        log = proc["log_tail"] + "\n" + "\n".join(text.splitlines()[:8])
        match = classify_tblout(stock_text, text)["relation"] == "identical"
        del cache_before, cache_after
        replay = any(marker in log for marker in ("Skip the execution!", "Cache valid:"))
        ran = bool(text.strip() and header_ok(text) and proc.get("rewritten"))
        silent = bool(
            proc.get("cache_unchanged") and argv_same and text.strip() and match
        )
        if replay or silent:
            if match and text.strip():
                action = "SKIP"
                if ran and not cold and cold_wall > 0 and proc["wall_s"] >= 0.50 * cold_wall and not replay:
                    action = "RERUN"
            else:
                action = "FAILED"
        elif not ran:
            action = "INVALID"
        elif cold:
            action = "COLD"
        elif cold_wall > 0 and proc["wall_s"] >= 0.50 * cold_wall:
            action = "RERUN"
        elif cold_wall > 0 and proc["wall_s"] <= max(180.0, 0.08 * cold_wall) and match and proc["exit_code"] == 0:
            action = "SKIP"
        else:
            action = "AMBIGUOUS"
        proc["action"] = action
        proc["match_stock"] = match
        proc["diff"] = classify_tblout(stock_text, text)
        proc["n_rows"] = len(body_lines(text))
        proc["header"] = header_ok(text)
        proc["body_sha256"] = body_sha(text) if text else None
        proc["kernel_marker"] = kernel_block(log)
        valid = (
            proc["exit_code"] == 0
            and match
            and header_ok(text)
            and proc["n_rows"] == len(body_lines(stock_text))
            and proc["kernel_marker"] is None
        )
        proc["valid"] = valid
        return proc

    def run_system(self, system: str, fasta: Path, dest: Path, work: Path, log: Path,
                   keep_cache: bool, clear_output: bool = True) -> dict:
        if clear_output and dest.exists():
            dest.unlink()
        env = self.base_env()
        cache_root = work / "cache"
        if not keep_cache and cache_root.exists():
            shutil.rmtree(cache_root)
        cache_root.mkdir(parents=True, exist_ok=True)
        before_fp = cache_fingerprint(cache_root)
        mtime_before = dest.stat().st_mtime_ns if dest.exists() else None
        if system == "processcache":
            argv = [str(self.binaries()["processcache"]), "--", *hmm_argv(
                self.binaries()["hmmscan"], self.hmm, fasta, dest,
            )]
            proc = run_proc(argv, work, env, log)
        elif system == "incr":
            proc = self.run_incr(fasta, dest, work, log, env)
        elif system == "tare":
            proc = self.run_tare(fasta, dest, work, log, env, keep_cache=keep_cache)
        elif system == "riker":
            rikerfile = work / "Rikerfile"
            rendered = " ".join(shlex.quote(part) for part in hmm_argv(
                self.binaries()["hmmscan"], self.hmm, fasta, dest,
            ))
            rikerfile.write_text(rendered + "\n")
            proc = run_proc([str(self.binaries()["riker"])], work, env, log)
        else:
            raise ValueError(system)
        after = dest.stat().st_mtime_ns if dest.exists() else None
        proc["tool"] = system
        proc["tblout"] = str(dest)
        proc["tblout_bytes"] = dest.stat().st_size if dest.is_file() else 0
        proc["rewritten"] = dest.is_file() and after != mtime_before
        proc["cache_unchanged"] = cache_fingerprint(cache_root) == before_fp
        proc["cache_root"] = str(cache_root)
        if proc.get("kernel_marker") is None:
            proc["kernel_marker"] = kernel_block(proc["log_tail"])
        return proc

    def run_incr(self, fasta: Path, dest: Path, work: Path, log: Path, env: dict[str, str]) -> dict:
        local = Path("/tmp") / f"tare_w5x_incr_{os.environ.get('SLURM_JOB_ID', 'x')}"
        if local.exists():
            shutil.rmtree(local)
        local.mkdir(parents=True)
        subprocess.run(["git", "init", str(local)], check=False, capture_output=True)
        script = local / "run.sh"
        body = "#!/bin/bash\nset -euo pipefail\nexec " + " ".join(
            shlex.quote(part) for part in hmm_argv(self.binaries()["hmmscan"], self.hmm, fasta, dest)
        ) + "\n"
        script.write_text(body)
        script.chmod(0o755)
        env = dict(env)
        env["INCR_TOP"] = str(self.builds / "src" / "incr")
        env.pop("INCR_SYS_PATH", None)
        py = self.binaries()["incr_python"]
        env["PATH"] = str(py.parent) + os.pathsep + str(self.builds / "bin") + os.pathsep + env.get("PATH", "")
        cache = work / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        argv = ["bash", str(self.binaries()["incr_sh"]), str(script), str(cache)]
        proc = run_proc(argv, local, env, log)
        proc["incr_cwd"] = str(local)
        proc["incr_note"] = "script cwd is node-local; HMM and FASTA stay on scratch1; INCR_SYS_PATH unset"
        return proc

    def run_tare(self, fasta: Path, dest: Path, work: Path, log: Path, env: dict[str, str],
                 keep_cache: bool) -> dict:
        out = work / "out"
        if out.exists():
            shutil.rmtree(out)
        cache = work / "cache" / "reference.sqlite"
        cache.parent.mkdir(parents=True, exist_ok=True)
        if cache.exists() and not keep_cache:
            cache.unlink()
        # --prep matches baseline_carc / headline: sub-references need pressed
        # sidecars. Full-Pfam press stays outside the clock (copied .h3*).
        argv = [
            sys.executable, "-m", "acts", "run",
            "--strategy", "reference",
            "--pin", "-Z {entry_count}",
            "--verify", "audit",
            "--prep", "hmmpress -f {reference}",
            "--input", str(fasta),
            "--reference", str(self.hmm),
            "--cache", str(cache),
            "-o", str(out),
            "--",
            str(self.binaries()["hmmscan"]),
            "--cut_ga", "--noali", "--cpu", CPU,
            "--tblout", "{output:tblout}",
            "{reference}", "{input}",
        ]
        proc = run_proc(argv, work, env, log)
        decision = parse_decision(out / "decision.txt")
        produced = out / "tables" / "tblout"
        if produced.is_file():
            shutil.copy2(produced, dest)
        proc["decision"] = decision
        proc["tare_pin"] = "-Z {entry_count}"
        proc["tare_prep"] = "hmmpress -f {reference}"
        return proc

    def finish_system(self, proc: dict, stock_text: str, *, cold: bool, cold_wall: float,
                      argv_same: bool) -> dict:
        if proc["tool"] == "tare":
            text = self.read_tbl(Path(proc["tblout"]))
            decision = proc.get("decision") or {}
            diff = classify_tblout(stock_text, text)
            fresh = decision.get("n_fresh")
            entries = decision.get("n_entries")
            proc.update({
                "header": header_ok(text),
                "n_rows": len(body_lines(text)),
                "body_sha256": body_sha(text) if text else None,
                "diff": diff,
                "match_stock": diff["relation"] == "identical",
                "kernel_marker": kernel_block(proc["log_tail"]),
            })
            shipped = decision.get("decision") == "SHIP" and proc["exit_code"] == 0
            proc["valid"] = bool(
                shipped and header_ok(text) and proc["n_rows"] >= POWER_FLOOR and proc["kernel_marker"] is None
            )
            if fresh is None:
                proc["action"] = "INVALID"
            elif str(fresh) == "0" and shipped:
                proc["action"] = "REPLAY"
            elif entries is not None and str(fresh) == str(entries):
                proc["action"] = "RERUN"
            elif shipped:
                proc["action"] = "PARTIAL"
            else:
                proc["action"] = "INVALID"
            return proc
        return self.judge_wrapper(
            proc, stock_text, cold=cold, cold_wall=cold_wall,
            cache_before=[] if cold else proc.get("cache_unchanged"),
            cache_after=proc.get("cache_unchanged"),
            argv_same=argv_same,
        )

    def note_kernel(self, system: str, proc: dict) -> None:
        marker = proc.get("kernel_marker")
        if marker and system not in self.payload["blocked"]:
            self.payload["blocked"][system] = {
                "reason": "kernel restriction during the run",
                "marker": marker,
                "log_tail": proc.get("log_tail", "")[-1500:],
                "exit_code": proc.get("exit_code"),
            }

    def controls(self, stock_text: str) -> None:
        good = classify_tblout(stock_text, stock_text)
        mutated = mutate_evalue(stock_text)
        bad = classify_tblout(stock_text, mutated)
        self.payload["controls"] = {
            "positive_identical": good,
            "negative_value_only": bad,
            "positive_pass": good["relation"] == "identical" and good["classes"] == [],
            "negative_pass": bad["relation"] == "different" and "value-only" in bad["classes"],
        }
        self.save("controls")

    def identity(self) -> str:
        print("identity stock 1", flush=True)
        first = self.stock_run(self.fasta, self.scratch / "identity1.tbl", self.scratch / "logs" / "identity1.log")
        first["role"] = "identity"
        first["repeat"] = None
        self.payload["runs"].append(first)
        self.save("identity1")
        print("identity stock 2", flush=True)
        second = self.stock_run(self.fasta, self.scratch / "identity2.tbl", self.scratch / "logs" / "identity2.log")
        second["role"] = "identity"
        second["repeat"] = None
        self.payload["runs"].append(second)
        text_a = self.read_tbl(Path(first["tblout"]))
        text_b = self.read_tbl(Path(second["tblout"]))
        same = classify_tblout(text_a, text_b)
        self.payload["stock_vs_stock"] = {
            "relation": same["relation"],
            "classes": same["classes"],
            "n_rows": same["n_stock"],
            "body_sha256": body_sha(text_a),
            "walls_s": [first["wall_s"], second["wall_s"]],
            "pass": same["relation"] == "identical" and same["n_stock"] >= POWER_FLOOR,
        }
        self.controls(text_a)
        self.save("identity")
        if not self.payload["stock_vs_stock"]["pass"]:
            self.payload["ratios_status"] = "INCONCLUSIVE"
        if not self.payload["controls"]["positive_pass"] or not self.payload["controls"]["negative_pass"]:
            self.payload["ratios_status"] = "INCONCLUSIVE"
        return text_a

    def one_pair(self, repeat: int, system: str, system_first: bool, behavior: bool) -> None:
        if system in self.payload["blocked"]:
            self.payload["runs"].append({
                "repeat": repeat, "tool": system, "role": "blocked",
                "blocked": self.payload["blocked"][system], "valid": False,
            })
            self.save("blocked-pair")
            return
        work = self.scratch / "pairs" / f"r{repeat}" / system
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        logs = self.scratch / "logs"
        stock_tbl = work / "stock.tbl"
        sys_tbl = work / "system.tbl"

        def do_stock() -> dict:
            print(f"repeat {repeat} stock for {system}", flush=True)
            row = self.stock_run(self.fasta, stock_tbl, logs / f"r{repeat}_{system}_stock.log")
            row.update({"repeat": repeat, "role": "paired_stock", "pair_system": system, "system_first": system_first})
            self.payload["runs"].append(row)
            self.save("stock")
            return row

        def do_system() -> dict:
            print(f"repeat {repeat} {system}", flush=True)
            row = self.run_system(
                system, self.fasta, sys_tbl, work, logs / f"r{repeat}_{system}.log", keep_cache=False,
            )
            row.update({"repeat": repeat, "role": "paired_system", "system_first": system_first})
            self.payload["runs"].append(row)
            self.save("system")
            return row

        if system_first:
            system_row = do_system()
            stock_row = do_stock()
        else:
            stock_row = do_stock()
            system_row = do_system()
        stock_text = self.read_tbl(stock_tbl)
        self.finish_system(system_row, stock_text, cold=True, cold_wall=system_row["wall_s"], argv_same=False)
        self.note_kernel(system, system_row)
        if stock_row.get("valid") and system_row.get("valid") and stock_row["wall_s"] > 0:
            system_row["rho"] = system_row["wall_s"] / stock_row["wall_s"]
        else:
            system_row["rho"] = None
        self.save("pair")
        if behavior and system not in self.payload["blocked"]:
            self.behavior(repeat, system, work, system_row, stock_text)

    def behavior(self, repeat: int, system: str, work: Path, cold: dict, stock_text: str) -> None:
        logs = self.scratch / "logs"
        dest = Path(cold["tblout"])
        print(f"identical rerun {system}", flush=True)
        rerun = self.run_system(
            system, self.fasta, dest, work, logs / f"r{repeat}_{system}_replay.log",
            keep_cache=True, clear_output=False,
        )
        rerun.update({"repeat": repeat, "role": "identical_rerun", "output_left_in_place": True})
        self.finish_system(
            rerun, stock_text, cold=False, cold_wall=cold["wall_s"], argv_same=True,
        )
        self.payload["runs"].append(rerun)
        self.note_kernel(system, rerun)
        self.save("replay")
        if not self.new_fasta.is_file():
            return
        if "new_stock" not in self.payload:
            print("new-genome stock", flush=True)
            row = self.stock_run(
                self.new_fasta, self.scratch / "genome2_stock.tbl", logs / "genome2_stock.log",
            )
            row.update({"repeat": repeat, "role": "new_genome_stock"})
            self.payload["new_stock"] = {
                "wall_s": row["wall_s"], "n_rows": row["n_rows"], "body_sha256": row["body_sha256"],
                "valid": row["valid"], "tblout": row["tblout"],
            }
            self.payload["runs"].append(row)
            self.save("new-stock")
        new_tbl = work / "genome2.tbl"
        print(f"new genome {system}", flush=True)
        fresh = self.run_system(
            system, self.new_fasta, new_tbl, work, logs / f"new_{system}.log",
            keep_cache=True, clear_output=True,
        )
        new_text = self.read_tbl(Path(self.payload["new_stock"]["tblout"]))
        fresh.update({"repeat": repeat, "role": "new_genome"})
        self.finish_system(fresh, new_text, cold=False, cold_wall=cold["wall_s"], argv_same=False)
        self.payload["runs"].append(fresh)
        self.note_kernel(system, fresh)
        self.save("new-genome")

    def summarize(self) -> None:
        ratios_ok = self.payload.get("ratios_status") != "INCONCLUSIVE"
        if self.phase == "measured":
            stocks = [
                row for row in self.payload["runs"]
                if row.get("role") == "paired_stock" and row.get("valid")
            ]
            bodies = {row.get("body_sha256") for row in stocks}
            rows = {row.get("n_rows") for row in stocks}
            if bodies != {self.locked_body} or rows != {self.locked_rows}:
                ratios_ok = False
                self.payload["ratios_status"] = "INCONCLUSIVE"
                self.payload["measured_stock_body_mismatch"] = sorted(x for x in bodies if x)
                self.payload["measured_stock_rows"] = sorted(x for x in rows if x is not None)
        systems = {}
        for name in SYSTEMS:
            if name in self.payload["blocked"] and not any(
                row.get("tool") == name and row.get("rho") is not None for row in self.payload["runs"]
            ):
                systems[name] = {"status": "BLOCKED", **self.payload["blocked"][name]}
                continue
            vals = []
            for row in self.payload["runs"]:
                if row.get("tool") == name and row.get("role") == "paired_system" and row.get("rho") is not None:
                    vals.append(Decimal(str(row["rho"])))
            summary = paired_summary(vals)
            if not ratios_ok and summary["status"] == "MEASURED":
                summary["status"] = "INCONCLUSIVE"
                summary["reason"] = "stock identity or controls failed"
            if name in self.payload["blocked"]:
                summary["status"] = "BLOCKED"
                summary["blocked"] = self.payload["blocked"][name]
            systems[name] = summary
        self.payload["systems"] = systems
        walls = [
            row["wall_s"] for row in self.payload["runs"]
            if row.get("repeat") == 0 and row.get("role") in ("paired_stock", "paired_system")
            and isinstance(row.get("wall_s"), (int, float))
        ]
        behavior_walls = [
            row["wall_s"] for row in self.payload["runs"]
            if row.get("role") in ("identical_rerun", "new_genome", "new_genome_stock")
            and isinstance(row.get("wall_s"), (int, float))
        ]
        self.payload["pilot_paired_wall_s"] = sum(walls) if self.phase == "pilot" else None
        self.payload["pilot_behavior_wall_s"] = sum(behavior_walls) if self.phase == "pilot" else None
        if self.phase == "pilot" and walls:
            estimate = 4 * sum(walls) + sum(behavior_walls) + 20 * 60
            self.payload["measured_time_limit_s"] = estimate * 1.5
        self.payload["provenance"] = {
            "frozen_code": FROZEN,
            "git_head_file": os.environ.get("ACTS_GIT_HEAD"),
            "host": socket.gethostname(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "constraint": os.environ.get("SLURM_JOB_CONSTRAINT"),
            "cpus": os.environ.get("SLURM_CPUS_PER_TASK"),
            "exclusive_requested": os.environ.get("ACTS_EXCLUSIVE") == "1",
            "python": sys.version.split()[0],
            "uname": os.uname().version if hasattr(os, "uname") else None,
            "cpu_model": _cpu_model(),
        }
        done = self.payload.get("workload_error") is None
        self.payload["label"] = "MEASURED" if done and self.phase == "measured" else (
            "PILOT" if done else self.payload.get("label", "PARTIAL")
        )
        self.save("done")

    def run(self) -> None:
        self.refuse_login()
        self.check_protocol()
        self.payload["ulimit_n"] = _ulimit()
        self.probe()
        self.record_binaries()
        self.block_from_probes()
        self.prepare_inputs()
        if self.phase == "pilot":
            self.identity()
        active = [name for name in SYSTEMS if name not in self.payload["blocked"]]
        for repeat in range(self.repeats):
            for pair in pairs_for_repeat(repeat, active):
                self.one_pair(
                    repeat, pair["system"], pair["system_first"],
                    behavior=(repeat == self.repeats - 1),
                )
        self.summarize()
        print(f"wrote {self.out}", flush=True)


def _cpu_model() -> str | None:
    path = Path("/proc/cpuinfo")
    if not path.is_file():
        return None
    for line in path.read_text(errors="replace").splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    return None


def _ulimit() -> str | None:
    proc = subprocess.run(["bash", "-lc", "ulimit -n"], check=False, text=True, capture_output=True)
    return (proc.stdout or "").strip() or None


def install_signals(harness: Harness) -> None:
    def handler(signum, _frame):
        harness.payload["signal"] = signum
        harness.save("signal")
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TARE Table 4 x86 baselines")
    parser.add_argument("--phase", choices=("pilot", "measured"))
    parser.add_argument("--builds", default=str(BUILDS_DEFAULT))
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--protocol", type=Path, default=ROOT / PROTOCOL_REL)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args(argv)
    if args.selfcheck:
        _selfcheck()
        return 0
    if not args.phase or not args.scratch or not args.out:
        parser.error("--phase, --scratch, and --out are required")
    harness = Harness(args)
    install_signals(harness)
    try:
        harness.run()
    except SystemExit:
        harness.save("systemexit")
        raise
    except Exception as exc:
        harness.payload["error"] = f"{type(exc).__name__}: {exc}"
        harness.save("exception")
        raise
    return 0


def _selfcheck() -> None:
    ratios = [
        Decimal("1.5464069019112173"),
        Decimal("1.6056444407150765"),
        Decimal("1.659961327464189"),
        Decimal("1.6651450473191905"),
    ]
    summary = paired_summary(ratios)
    if summary["mean_paired_ratio_2dp"] != "1.62":
        raise SystemExit(summary)
    if summary["ci95_low_2dp"] != "1.53" or summary["ci95_high_2dp"] != "1.71":
        raise SystemExit(summary)
    firsts = [pairs_for_repeat(i, list(SYSTEMS))[0]["system"] for i in range(4)]
    if firsts != list(SYSTEMS):
        raise SystemExit(firsts)
    good = "a b c d 1.0e-3 e\n"
    bad = mutate_evalue("# header\n" + good)
    classified = classify_tblout("# header\n" + good, bad)
    if "value-only" not in classified["classes"] or classified["relation"] != "different":
        raise SystemExit(classified)
    if classify_tblout(good, good)["relation"] != "identical":
        raise SystemExit("identical control failed")
    print("baselines_x86 selfcheck ok")


if __name__ == "__main__":
    sys.exit(main())
