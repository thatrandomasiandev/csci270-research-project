"""Discriminating smoke for pipeline/docs/BASELINES_PROTOCOL.md.

Locked predictions, scored after the run and not revised from it:
  genome 2 (new FASTA path) reruns HMMER.
  Replay of genome 1's exact path skips.
  INCR's crowdsourced annotations do not split FASTA records.

Skip rule, written before any smoke result in this session:
  COLD       first invocation (genome 1)
  RERUN      wall_s >= 0.50 * genome1_wall_s
  SKIP       wall_s <= max(180s, 0.08 * genome1_wall_s)
  AMBIGUOUS  otherwise

The wall-clock rule is applied only after the step proves HMMER
executed, or proves the wrapper replayed a cached tblout. A fast
exit 0 with no HMMER output is INVALID. That gate was added
2026-10-09 after jobs 12866391 and 12866392: incr.sh swallowed a
failed insert.py and exited 0 in ~0.15 s. The September predictions
are unchanged.

Reuse fraction is the fraction of the HMMER process the wrapper did
not re-execute. These tools are whole-command caches, so the fraction
is 0 (COLD or RERUN) or 1 (SKIP). There is no record-level partial hit.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from baseline_match import nonempty_body, provenance, tables_match

PROTOCOL = "pipeline/docs/BASELINES_PROTOCOL.md"
PROTOCOL_COMMIT = "a29c3181adab72feaafa61b52c68549f66510402"

# Collection A, orderings[0], seed 20260926. Indices from
# results/recurrence_curves.json. Accessions from the savings run.
GENOME1 = {
    "position": 1,
    "index": 9,
    "accession": "GCF_002853805.1",
}
GENOME2 = {
    "position": 2,
    "index": 5,
    "accession": "GCF_002090355.1",
}

PREDICTIONS = {
    "source": "BASELINES_PROTOCOL.md locked 2026-09-27",
    "genome2_action": "RERUN",
    "replay_action": "SKIP",
    "annotations_split_hmmer_records": False,
    "falsifier_whole_command_is_enough": (
        "fires only if genome 2 skips HMMER on a new FASTA path"
    ),
}


def classify(wall_s: float, cold_wall_s: float, *, cold: bool) -> str:
    if cold:
        return "COLD"
    if cold_wall_s <= 0:
        return "AMBIGUOUS"
    if wall_s >= 0.50 * cold_wall_s:
        return "RERUN"
    if wall_s <= max(180.0, 0.08 * cold_wall_s):
        return "SKIP"
    return "AMBIGUOUS"


def reuse_fraction(action: str) -> float | None:
    if action in ("COLD", "RERUN"):
        return 0.0
    if action == "SKIP":
        return 1.0
    return None


# ProcessCache prints this only at tracing debug level
# (execution.rs, the execve skip). INCR prints "Cache valid:"
# only when DEBUG_LOGS is compiled on. The release binaries
# used here leave both off. judge_step still honors the lines
# when a log contains them.
REPLAY_LOG_MARKERS = (
    "Skip the execution!",
    "Cache valid:",
)

# HMMER's own stdout banner, or the tblout header it writes.
# "--- full sequence ----" is the tblout column rule, not a
# generic phrase.
HMMER_RUN_MARKERS = (
    "HMMER 3.",
    "# hmmscan ::",
    "# hmmsearch ::",
    "--- full sequence ----",
)


def log_shows_hmmer(log: str) -> bool:
    return any(marker in log for marker in HMMER_RUN_MARKERS)


def log_says_replay(log: str) -> bool:
    return any(marker in log for marker in REPLAY_LOG_MARKERS)


def judge_step(
    *,
    wall_s: float,
    cold_wall_s: float,
    cold: bool,
    exit_code: int,
    output_nonempty: bool,
    newly_written: bool,
    log: str,
    match: bool,
    cache_unchanged: bool,
    argv_matches_prior: bool,
) -> tuple[str, str]:
    """Return (action, status).

    status is executed, replayed, invalid, or failed.

    The wall-clock rule is not consulted until the step has
    proof that HMMER ran, or proof that the wrapper replayed
    a cached result. A fast exit 0 with an empty output is
    INVALID. A replay that does not MATCH stock is FAILED,
    not SKIP.
    """
    replay_marker = log_says_replay(log)
    ran = bool(output_nonempty and newly_written and log_shows_hmmer(log))
    silent_replay = bool(
        cache_unchanged
        and argv_matches_prior
        and output_nonempty
        and newly_written
        and match
    )
    if replay_marker or silent_replay:
        proved = match and output_nonempty and (newly_written or replay_marker)
        if not proved:
            return "FAILED", "failed"
        # A long step whose output contains a fresh HMMER table
        # re-executed, even if the cache index was not rewritten.
        if (
            ran
            and not cold
            and cold_wall_s > 0
            and wall_s >= 0.50 * cold_wall_s
            and not replay_marker
        ):
            return "RERUN", "executed"
        return "SKIP", "replayed"
    if not ran:
        return "INVALID", "invalid"
    action = classify(wall_s, cold_wall_s, cold=cold)
    if action == "SKIP" and (not match or exit_code != 0):
        return "FAILED", "failed"
    if action == "SKIP":
        return action, "replayed"
    return action, "executed"


def cache_fingerprint(root: Path) -> tuple:
    """Persistent files under a wrapper cache directory.

    INCR's per-invocation stdout/stderr/trace temps are excluded.
    ProcessCache's stdout_<pid> copies are persistent outputs and
    stay in the fingerprint.
    """
    if not root.is_dir():
        return ()
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        name = path.name
        if name.endswith(".incr") and name.startswith(("stdout_", "stderr_")):
            continue
        if name.startswith("trace_") and name.endswith(".txt"):
            continue
        st = path.stat()
        rows.append((str(path.relative_to(root)), st.st_size, st.st_mtime_ns))
    return tuple(rows)


def tblout_path(argv: list[str]) -> Path:
    idx = argv.index("--tblout")
    return Path(argv[idx + 1])


HMM_AUX_SUFFIXES = (".h3m", ".h3i", ".h3f", ".h3p")


def hmm_aux_paths(hmm: Path) -> list[Path]:
    return [Path(str(hmm) + suffix) for suffix in HMM_AUX_SUFFIXES]


def database_pressed(hmm: Path) -> bool:
    if not hmm.is_file() or hmm.stat().st_size <= 0:
        return False
    for path in hmm_aux_paths(hmm):
        if not path.is_file() or path.stat().st_size <= 0:
            return False
    return True


def refuse_unpressed_hmmscan(mode: str, hmm: Path) -> None:
    """Do not launch hmmscan until hmmpress has written its auxfiles.

    hmmscan's own error is ``use hmmpress first``. The harness stops
    before the timed step instead of recording that failure as a run.
    """
    if mode != "hmmscan":
        return
    if database_pressed(hmm):
        return
    missing = [
        path.name
        for path in hmm_aux_paths(hmm)
        if not path.is_file() or path.stat().st_size <= 0
    ]
    raise SystemExit(
        f"refusing to start hmmscan: {hmm} is not hmmpressed "
        f"(missing {', '.join(missing)}). use hmmpress first"
    )


def documented_incr_argv(script: str, cache: str) -> list[str]:
    """INCR's documented native entry, plus the cache directory.

    README (Manual Installation, commit 4b8e5dd):
    ``bash ./src/incr.sh myscript.sh``, with cwd at the checkout.
    ``incr.sh`` assigns ``$2`` to ``cache_dir`` when ``INCR_CACHE_DIR``
    is unset. The script's default ``/tmp/incr_cache`` is on a path
    INCR drops, so the persistent cache is that second argument.
    """
    return ["bash", "./src/incr.sh", script, cache]


def _evidence(log: str, cwd: Path, tbl_text: str) -> str:
    """Wrapper log, plus any child stdout ProcessCache left behind, plus the tblout header."""
    parts = [log]
    if cwd.is_dir():
        captures = [path for path in cwd.glob("stdout_*") if path.is_file()]
        captures.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        chunks = []
        for path in captures[:2]:
            data = path.read_bytes()[:2000]
            if data:
                chunks.append(data.decode("utf-8", errors="replace"))
        if chunks:
            parts.append("-- child stdout --\n" + "\n".join(chunks))
    head = "\n".join(tbl_text.splitlines()[:4])
    if head:
        parts.append("-- tblout head --\n" + head)
    return "\n".join(parts)


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def step_output_name(step: str) -> str:
    """Output basename for a smoke step.

    Replay uses genome 1's exact path, including ``--tblout``.
    A distinct ``replay.tbl`` is a different command.
    """
    if step == "genome2":
        return "genome2"
    if step in ("genome1", "replay"):
        return "genome1"
    raise ValueError(step)


def snapshot_output(src: Path, dest: Path) -> dict:
    """Copy ``src`` to ``dest`` and leave ``src`` bytes and mtime alone."""
    if not src.is_file():
        raise FileNotFoundError(src)
    before = sha256_file(src)
    before_ns = src.stat().st_mtime_ns
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    after = sha256_file(src)
    after_ns = src.stat().st_mtime_ns
    if before != after or before_ns != after_ns:
        raise RuntimeError(f"snapshot changed the tool output {src}")
    return {
        "source": str(src),
        "copy": str(dest),
        "sha256": before,
        "source_mtime_ns_unchanged": True,
    }


def tail(path: Path, limit: int = 6000) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes()
    if len(data) > limit:
        data = data[-limit:]
    return data.decode("utf-8", errors="replace")


def dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(path)


def hmmer_argv(hmm: str, mode: str, tblout: str, fasta: str, pfam: str) -> list[str]:
    """Stock argv from headline_screen.json / BASELINES_PROTOCOL.md."""
    if mode == "hmmscan":
        return [hmm, "--cpu", "32", "--cut_ga", "--noali", "--tblout", tblout, pfam, fasta]
    if mode == "hmmsearch":
        return [
            hmm, "--cpu", "32", "--noali", "--tblout", tblout,
            "-Z", "1000000", "--domZ", "1000000", pfam, fasta,
        ]
    raise ValueError(mode)


def n_records(path: Path) -> int:
    count = 0
    with path.open() as handle:
        for line in handle:
            if line.startswith(">"):
                count += 1
    return count


def run_timed(argv: list[str], cwd: Path, env: dict[str, str], log_path: Path) -> tuple[int, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with log_path.open("w") as log:
        proc = subprocess.run(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    return proc.returncode, time.perf_counter() - started


def snapshot_insert(python: str, incr_top: Path, sys_path: str, try_path: str, cache: str, script: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        python,
        str(incr_top / "src" / "scripts" / "insert.py"),
        "--sys-path", sys_path,
        "--try-path", try_path,
        "--cache-path", cache,
        str(script),
    ]
    proc = subprocess.run(argv, capture_output=True)
    text = (proc.stdout or b"") + b"\n--- stderr ---\n" + (proc.stderr or b"")
    dest.write_bytes(text[:20000])


class Runner:
    def __init__(self, args: argparse.Namespace, build: dict) -> None:
        self.args = args
        self.build = build
        self.root = Path(args.root)
        # A fresh directory. The 2026-10-09 ProcessCache cache stored a
        # 0-byte hmmscan tblout, and its hmmsearch post-run copy panicked.
        # Reusing that directory could restore the empty file.
        if getattr(args, "work", None):
            self.work = Path(args.work)
        else:
            self.work = self.root / "smoke" / f"{args.tool}_{args.column}_rerun"
        self.work.mkdir(parents=True, exist_ok=True)
        self.log_dir = Path(os.environ.get("SLURM_TMPDIR") or os.environ.get("TMPDIR") or "/tmp") / f"baseline_smoke_{os.environ.get('SLURM_JOB_ID', 'local')}"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        tools = build.get("tools") or {}
        hmmer = tools.get("hmmer") or {}
        scan = hmmer.get("binary_hmmscan") or str(self.root / "bin" / "hmmscan")
        search = hmmer.get("binary_hmmsearch") or str(Path(scan).with_name("hmmsearch"))
        self.hmm_by_mode = {"hmmscan": scan, "hmmsearch": search}
        self.pfam = str(self.root / "data" / "Pfam-A.hmm")
        self.fasta = {
            "genome1": self.root / "data" / f"{GENOME1['accession']}_protein.faa",
            "genome2": self.root / "data" / f"{GENOME2['accession']}_protein.faa",
        }
        self.payload: dict = {
            "protocol": PROTOCOL,
            "protocol_locked_commit": PROTOCOL_COMMIT,
            "phase": "discriminating_smoke",
            "tool": args.tool,
            "column": args.column,
            "collection": "A",
            "ordering_seed": 20260926,
            "genomes": {"genome1": GENOME1, "genome2": GENOME2},
            "predictions": PREDICTIONS,
            "skip_rule": {
                "INVALID": (
                    "no proof the wrapped command executed HMMER and no proof "
                    "it replayed from cache. Wall time is not consulted. "
                    "A fast exit 0 is INVALID, not SKIP."
                ),
                "FAILED": "replay or wall-SKIP whose tblout does not MATCH stock",
                "COLD": "genome 1 executed",
                "RERUN": "executed and wall_s >= 0.50 * genome1_wall_s",
                "SKIP": (
                    "replayed from cache and MATCH, or executed and "
                    "wall_s <= max(180s, 0.08 * genome1_wall_s) and MATCH"
                ),
                "AMBIGUOUS": "executed, otherwise",
                "reuse_fraction": "0 on COLD or RERUN, 1 on SKIP, null otherwise",
                "execution_proof": (
                    "tblout exists, is non-empty, was newly written, and "
                    "the captured output contains an HMMER banner or the "
                    "tblout header '--- full sequence ----'"
                ),
                "replay_proof": (
                    "log contains 'Skip the execution!' or 'Cache valid:', "
                    "or the wrapper cache fingerprint is unchanged on an "
                    "argv identical to a prior step and the restored tblout "
                    "is non-empty, newly written, and MATCH"
                ),
            },
            "node_class_deviation": (
                "Shared xeon-4116, 8 cpus, not exclusive, not epyc-7542. "
                "The locked CARC plan asked for an exclusive epyc-7542. "
                "This session reserves those nodes. HMMER argv still passes --cpu 32."
            ),
            "input_path_note": (
                "FASTA, Pfam, and wrapper state live on the project path. "
                "INCR drops dependencies under /tmp (DYNAMIC_EXCLUDED_PATHS), "
                "so a /tmp FASTA would not be the locked independent variable. "
                "Compiler scratch stays on node-local /tmp."
            ),
            "eggNOG": "not run; ~45 GB database needs Josh's approval",
            "modes": [],
            "provenance": provenance(),
        }

    def tool_ready(self) -> str | None:
        tools = self.build.get("tools") or {}
        key = {
            ("riker", "release"): "riker",
            ("processcache", "sha256"): "processcache_sha256",
            ("incr", "default"): "incr",
            ("incr", "annotations"): "incr",
        }.get((self.args.tool, self.args.column))
        if key is None:
            return f"unknown column {self.args.tool}/{self.args.column}"
        info = tools.get(key) or {}
        if not info.get("ok"):
            return info.get("error") or f"{key} did not build"
        probes = self.build.get("probes") or {}
        if not (probes.get("seccomp_bpf") or {}).get("ok"):
            text = ((probes.get("seccomp_bpf") or {}).get("output") or "")[-1500:]
            return "seccomp-bpf probe failed\n" + text
        if self.args.tool in ("riker", "processcache", "incr") and not (probes.get("ptrace") or {}).get("ok"):
            text = ((probes.get("ptrace") or {}).get("output") or "")[-1500:]
            return "ptrace probe failed\n" + text
        if self.args.tool == "incr" and not (probes.get("strace") or {}).get("ok"):
            text = ((probes.get("strace") or {}).get("output") or "")[-1500:]
            return "strace probe failed\n" + text
        if self.args.tool == "incr" and not (probes.get("overlayfs") or {}).get("ok"):
            text = ((probes.get("overlayfs") or {}).get("output") or "")[-1500:]
            return "overlayfs probe failed\n" + text
        return None

    def launch(self, mode: str, step: str, argv: list[str], cwd: Path) -> tuple[int, float, Path]:
        log_path = self.log_dir / f"{mode}_{step}.log"
        env = os.environ.copy()
        path_parts = [str(self.root / "bin")]
        if self.args.tool == "incr":
            incr = (self.build.get("tools") or {}).get("incr") or {}
            env["INCR_TOP"] = incr.get("top") or str(self.root / "src" / "incr")
            # incr.sh calls python3, not the venv path recorded at build.
            # libbash lives in that venv. The system python3 does not have
            # it, and incr.sh has no set -e, so a failed insert.py is
            # copied over the script and bash exits 0 without HMMER.
            py = incr.get("python") or ""
            if py:
                path_parts.insert(0, str(Path(py).parent))
            if self.args.column == "annotations":
                env["INCR_SYS_PATH"] = f"{incr.get('binary')} --enable_annotations"
            else:
                env.pop("INCR_SYS_PATH", None)
        env["PATH"] = os.pathsep.join(path_parts + [env.get("PATH", "")])
        code, wall = run_timed(argv, cwd, env, log_path)
        kept = self.work / "logs" / f"{mode}_{step}.tail"
        kept.parent.mkdir(parents=True, exist_ok=True)
        kept.write_text(tail(log_path))
        return code, wall, kept

    def wrap(self, mode: str, step: str, hmm_argv: list[str]) -> tuple[list[str], Path, dict]:
        extra: dict = {}
        if self.args.tool == "riker":
            home = self.work / "riker" / mode
            home.mkdir(parents=True, exist_ok=True)
            rikerfile = home / "Rikerfile"
            text = " ".join(hmm_argv) + "\n"
            if step == "replay":
                saved = home / "Rikerfile.genome1"
                text = saved.read_text()
            rikerfile.write_text(text)
            if step == "genome1":
                (home / "Rikerfile.genome1").write_text(text)
            binary = (self.build.get("tools") or {})["riker"]["binary"]
            extra["rikerfile_sha256"] = hashlib.sha256(text.encode()).hexdigest()
            extra["rikerfile"] = text.strip()
            return [binary], home, extra
        if self.args.tool == "processcache":
            home = self.work / "pc" / mode
            home.mkdir(parents=True, exist_ok=True)
            # README: the cache is ./cache in the working directory.
            (home / "cache").mkdir(parents=True, exist_ok=True)
            binary = (self.build.get("tools") or {})["processcache_sha256"]["binary"]
            return [binary, "--", *hmm_argv], home, extra
        if self.args.tool == "incr":
            home = self.work / "incr" / mode
            home.mkdir(parents=True, exist_ok=True)
            cache = home / "cache"
            cache.mkdir(parents=True, exist_ok=True)
            script = home / "run.sh"
            body = "#!/bin/bash\n" + " ".join(shlex.quote(part) for part in hmm_argv) + "\n"
            if step == "replay":
                body = (home / "run.sh.genome1").read_text()
            script.write_text(body)
            if step == "genome1":
                (home / "run.sh.genome1").write_text(body)
            incr = (self.build.get("tools") or {})["incr"]
            sys_path = incr["binary"]
            if self.args.column == "annotations":
                sys_path = f"{sys_path} --enable_annotations"
            snap = home / f"inserted_{step}.txt"
            py = incr.get("python") or "python3"
            try:
                snapshot_insert(py, Path(incr["top"]), sys_path, str(Path(incr["top"]) / "src" / "scripts" / "try.sh"), str(cache), script, snap)
                extra["inserted_head"] = "\n".join(snap.read_text(errors="replace").splitlines()[:8])
            except OSError as exc:
                extra["inserted_head"] = f"insert.py failed: {exc}"
            extra["script_sha256"] = hashlib.sha256(body.encode()).hexdigest()
            extra["annotations_flag"] = self.args.column == "annotations"
            extra["incr_python"] = incr.get("python")
            extra["documented_invocation"] = "bash ./src/incr.sh myscript.sh"
            # The checkout and the project cache are on NFS. try.sh then
            # does `cd "$START_DIR"` inside the sandbox. On d05-41 that
            # cd returns "Operation not supported" (preflight 12899307).
            # A /tmp cwd lets the sandbox start (preflight 12899342).
            # The FASTA and Pfam paths inside the script stay on /project2.
            # /tmp is not used as the FASTA path: INCR drops /tmp from
            # the dependency set, which would hide the new-file rerun.
            local = self._incr_local(mode)
            local.mkdir(parents=True, exist_ok=True)
            if not (local / ".git").exists():
                subprocess.run(["git", "init", str(local)], check=False, capture_output=True)
            local_script = local / "run.sh"
            local_script.write_text(script.read_text())
            local_cache = local / "cache"
            local_cache.mkdir(parents=True, exist_ok=True)
            extra["incr_cwd"] = str(local)
            extra["project_script"] = str(script)
            extra["cwd_reason"] = (
                "node-local /tmp; NFS checkout is not a usable try.sh START_DIR"
            )
            return documented_incr_argv(str(local_script), str(local_cache)), local, extra
        raise ValueError(self.args.tool)

    def _incr_local(self, mode: str) -> Path:
        return Path("/tmp") / f"acts_incr_{os.environ.get('SLURM_JOB_ID', 'local')}" / mode

    def _cache_dir(self, mode: str) -> Path:
        if self.args.tool == "processcache":
            return self.work / "pc" / mode / "cache"
        if self.args.tool == "incr":
            path = self._incr_local(mode) / "cache"
            path.mkdir(parents=True, exist_ok=True)
            return path
        return self.work / "riker" / mode / ".rkr"

    def _modes(self) -> list[str]:
        return [part.strip() for part in self.args.modes.split(",") if part.strip()]

    def _prepare_incr(self) -> dict:
        """Make incr.sh's own preamble succeed. Untimed.

        The installed tree was copied without ``.git``, so
        ``git rev-parse --show-toplevel`` from that directory failed.
        ``python3`` on the compute node does not have ``libbash``.
        """
        incr = (self.build.get("tools") or {}).get("incr") or {}
        top = Path(incr.get("top") or self.root / "src" / "incr")
        py = incr.get("python") or ""
        rec: dict = {
            "timed": False,
            "top": str(top),
            "documented_invocation": "bash ./src/incr.sh myscript.sh",
            "documented_source": (
                "https://github.com/atlas-brown/incr README, "
                "Manual Installation, commit 4b8e5dd"
            ),
        }
        git_dir = top / ".git"
        rec["git_dir_existed"] = git_dir.exists()
        if not git_dir.exists():
            proc = subprocess.run(["git", "init", str(top)], capture_output=True, text=True)
            rec["git_init_exit"] = proc.returncode
            rec["git_init_stderr"] = (proc.stderr or "")[-500:]
            if proc.returncode != 0:
                raise SystemExit(f"git init failed in {top}: {rec['git_init_stderr']}")
        rev = subprocess.run(
            ["git", "-C", str(top), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        rec["git_rev_parse_exit"] = rev.returncode
        rec["git_toplevel"] = (rev.stdout or "").strip()
        if rev.returncode != 0:
            raise SystemExit(f"git rev-parse failed in {top}: {(rev.stderr or '')[-500:]}")
        if Path(rec["git_toplevel"]).resolve() != top.resolve():
            raise SystemExit(
                f"incr toplevel {rec['git_toplevel']} is not {top}"
            )
        if not py or not Path(py).is_file():
            raise SystemExit("INCR venv python missing from the build report")
        unshare = subprocess.run(
            ["unshare", "--version"], capture_output=True, text=True
        )
        rec["unshare_path"] = shutil.which("unshare")
        rec["unshare_version"] = (unshare.stdout or unshare.stderr or "").splitlines()[:1]
        merger = self.root / "bin" / "mergerfs"
        rec["mergerfs"] = str(merger)
        rec["mergerfs_present"] = merger.is_file()
        if merger.is_file():
            ver = subprocess.run([str(merger), "-v"], capture_output=True, text=True)
            rec["mergerfs_version"] = (ver.stdout or "").splitlines()[:1]
        else:
            raise SystemExit(
                f"mergerfs is not at {merger}. try.sh needs it when overlay "
                "cannot mount this node's tmpfs /usr."
            )
        help_text = subprocess.run(
            ["unshare", "--help"], capture_output=True, text=True
        )
        if "--root" not in (help_text.stdout or "") and "--root" not in (help_text.stderr or ""):
            raise SystemExit(
                "unshare has no --root; incr.sh cannot start. "
                "Load util-linux/2.40. System unshare is 2.32.1."
            )
        check = subprocess.run(
            [py, "-c", "import libbash, libdash"],
            capture_output=True,
            text=True,
        )
        rec["python"] = py
        rec["import_libbash_exit"] = check.returncode
        if check.returncode != 0:
            raise SystemExit(
                "incr python cannot import libbash\n" + (check.stderr or "")[-800:]
            )
        return rec

    def _press_pfam(self) -> dict:
        """hmmpress the smoke HMM. Untimed, and not part of any step wall.

        Job 12866390's hmmscan exited in ~15 s with ``use hmmpress first``
        because ``data/Pfam-A.hmm`` had no ``.h3m/.h3i/.h3f/.h3p``.
        """
        hmm = Path(self.pfam)
        dest = self.root / "bin" / "hmmpress"
        src = (os.environ.get("ACTS_HMMPRESS_SRC") or "").strip()
        rec: dict = {
            "timed": False,
            "hmm": str(hmm),
            "hmmpress": str(dest),
            "binary_copied": False,
        }
        if not dest.is_file():
            source = Path(src) if src else None
            if source is None or not source.is_file():
                raise SystemExit(
                    f"hmmpress is not at {dest}; set ACTS_HMMPRESS_SRC to the "
                    "HMMER 3.4 hmmpress binary"
                )
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            dest.chmod(dest.stat().st_mode | 0o111)
            rec["binary_copied"] = True
            rec["binary_source"] = str(source)
        before = sha256_file(hmm)
        before_ns = hmm.stat().st_mtime_ns
        lock_path = Path(str(hmm) + ".press.lock")
        with lock_path.open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                if database_pressed(hmm):
                    rec.update({
                        "ran": False,
                        "reason": "auxfiles already present",
                        "hmm_sha256": before,
                        "hmm_mtime_ns": before_ns,
                        "aux_present": {path.name: True for path in hmm_aux_paths(hmm)},
                    })
                    return rec
                started = time.perf_counter()
                proc = subprocess.run(
                    [str(dest), "-f", str(hmm)],
                    capture_output=True,
                    text=True,
                )
                rec["ran"] = True
                rec["command"] = [str(dest), "-f", str(hmm)]
                rec["exit_code"] = proc.returncode
                rec["wall_s"] = time.perf_counter() - started
                rec["stderr_tail"] = (proc.stderr or proc.stdout or "")[-1500:]
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        rec["hmm_sha256_before"] = before
        rec["hmm_sha256_after"] = sha256_file(hmm)
        rec["hmm_bytes_unchanged"] = rec["hmm_sha256_before"] == rec["hmm_sha256_after"]
        rec["hmm_mtime_unchanged"] = hmm.stat().st_mtime_ns == before_ns
        rec["aux_present"] = {
            path.name: path.is_file() and path.stat().st_size > 0
            for path in hmm_aux_paths(hmm)
        }
        if rec["exit_code"] != 0 or not database_pressed(hmm):
            raise SystemExit(
                f"hmmpress failed for {hmm}: {rec['stderr_tail'][-800:]}"
            )
        return rec

    def one_mode(self, mode: str) -> None:
        stock_dir = Path(self.args.stock_dir)
        prefix = f"A_{mode}"
        stocks = {
            "genome1": stock_dir / f"{prefix}_01_stock.tbl",
            "genome2": stock_dir / f"{prefix}_02_stock.tbl",
            "replay": stock_dir / f"{prefix}_01_stock.tbl",
        }
        fastas = {
            "genome1": self.fasta["genome1"],
            "genome2": self.fasta["genome2"],
            "replay": self.fasta["genome1"],
        }
        steps_out = []
        cold_wall = None
        blocked = self.tool_ready()
        mode_rec: dict = {
            "mode": mode,
            "argv_note": "locked headline argv, including --cpu 32",
            "blocked": blocked,
            "steps": steps_out,
        }
        self.payload["modes"].append(mode_rec)
        dump(Path(self.args.out), self.payload)
        if blocked:
            return
        refuse_unpressed_hmmscan(mode, Path(self.pfam))
        saved_hmm_argv: list[str] | None = None
        saved_script_sha: str | None = None
        for name in ("genome1", "genome2", "replay"):
            if name == "replay":
                if saved_hmm_argv is None:
                    raise SystemExit("replay without genome 1 argv")
                argv = list(saved_hmm_argv)
            else:
                tbl_for_step = self.work / mode / f"{name}.tbl"
                tbl_for_step.parent.mkdir(parents=True, exist_ok=True)
                argv = hmmer_argv(
                    self.hmm_by_mode[mode], mode, str(tbl_for_step), str(fastas[name]), self.pfam,
                )
            tblout = tblout_path(argv)
            tblout.parent.mkdir(parents=True, exist_ok=True)
            before = sha256_file(tblout)
            before_mtime = tblout.stat().st_mtime_ns if tblout.exists() else None
            removed_before = False
            if name == "replay" and tblout.is_file():
                # A leftover cold tblout is not evidence of a restore.
                held = self.work / "comparisons" / mode / "genome1_before_replay.tbl"
                held.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(tblout, held)
                tblout.unlink()
                removed_before = True
            cache_root = self._cache_dir(mode)
            before_cache = cache_fingerprint(cache_root)
            wrapped, cwd, extra = self.wrap(mode, name, argv)
            code, wall, log_kept = self.launch(mode, name, wrapped, cwd)
            after = sha256_file(tblout)
            after_mtime = tblout.stat().st_mtime_ns if tblout.exists() else None
            text = tblout.read_text(errors="replace") if tblout.is_file() else ""
            snapshot = None
            if tblout.is_file():
                snapshot = snapshot_output(
                    tblout, self.work / "comparisons" / mode / f"{name}.tbl"
                )
            stock_path = stocks[name]
            stock_text = stock_path.read_text(errors="replace") if stock_path.is_file() else ""
            matched = bool(text) and bool(stock_text) and tables_match(text, stock_text, mode)
            newly = after is not None and (after != before or after_mtime != before_mtime)
            after_cache = cache_fingerprint(cache_root)
            cache_unchanged = before_cache == after_cache
            script_sha = extra.get("script_sha256")
            argv_matches_prior = bool(saved_hmm_argv is not None and argv == saved_hmm_argv)
            if script_sha and saved_script_sha and script_sha != saved_script_sha:
                argv_matches_prior = False
            log_text = log_kept.read_text(errors="replace")
            evidence = _evidence(log_text, cwd, text)
            action, status = judge_step(
                wall_s=wall,
                cold_wall_s=cold_wall or 0.0,
                cold=(name == "genome1"),
                exit_code=code,
                output_nonempty=nonempty_body(text),
                newly_written=newly,
                log=evidence,
                match=matched,
                cache_unchanged=cache_unchanged,
                argv_matches_prior=argv_matches_prior,
            )
            if name == "genome1" and status == "executed":
                cold_wall = wall
                saved_hmm_argv = list(argv)
                saved_script_sha = script_sha
            elif name == "genome1":
                saved_hmm_argv = list(argv)
                saved_script_sha = script_sha
            step = {
                "name": name,
                "status": status,
                "accession": GENOME1["accession"] if name != "genome2" else GENOME2["accession"],
                "fasta": str(fastas[name]),
                "n_records": n_records(fastas[name]),
                "argv": argv,
                "argv_sha256": hashlib.sha256("\0".join(argv).encode()).hexdigest(),
                "wrapped_argv": wrapped,
                "cwd": str(cwd),
                "exit_code": code,
                "wall_s": wall,
                "action": action,
                "reuse_fraction": reuse_fraction(action),
                "tblout": str(tblout),
                "tblout_bytes": tblout.stat().st_size if tblout.is_file() else 0,
                "tblout_sha256": after,
                "tblout_sha256_before": before,
                "tblout_mtime_changed": after_mtime != before_mtime,
                "newly_written": newly,
                "output_snapshot": snapshot,
                "replay_reuses_genome1_tblout": name != "replay" or argv_matches_prior,
                "output_nonempty": nonempty_body(text),
                "stock_tblout": str(stock_path),
                "stock_present": stock_path.is_file(),
                "match": matched,
                "cache_unchanged": cache_unchanged,
                "argv_matches_prior": argv_matches_prior,
                "log_shows_hmmer": log_shows_hmmer(evidence),
                "log_says_replay": log_says_replay(evidence),
                "replay_output_removed_before_launch": removed_before,
                "log_tail_path": str(log_kept),
                "log_tail": log_text,
                **extra,
            }
            if name == "genome2":
                step["agrees_with_prediction"] = action == "RERUN"
                step["falsifier_whole_command_fired"] = action == "SKIP"
            if name == "replay":
                step["agrees_with_prediction"] = action == "SKIP"
                step["replay_restored_nonempty"] = nonempty_body(text)
            steps_out.append(step)
            self.payload["provenance"] = provenance(self._versions())
            dump(Path(self.args.out), self.payload)
        self._project(mode_rec)

    def _versions(self) -> dict[str, str]:
        tools = self.build.get("tools") or {}
        out = {}
        for key in ("hmmer", "riker", "processcache_sha256", "incr"):
            info = tools.get(key) or {}
            if info.get("commit"):
                out[f"{key}_commit"] = info["commit"]
            if info.get("version"):
                out[f"{key}_version"] = info["version"]
        return out

    def _project(self, mode_rec: dict) -> None:
        steps = {s["name"]: s for s in mode_rec["steps"]}
        g2 = steps.get("genome2")
        if not g2:
            return
        applies = g2["action"] == "RERUN" and g2.get("status") == "executed"
        t = g2["wall_s"]
        # PROJECTED from this smoke's genome-2 wall. Assumes every later
        # genome costs the same wall on this same node class.
        mode_rec["projection"] = {
            "label": "PROJECTED",
            "applies": applies,
            "formula": "n_genomes * T_genome2_s / 3600",
            "T_genome2_s": t,
            "assumptions": [
                "genome 2 reran, so a new FASTA path is a full HMMER execution",
                "each later genome costs T_genome2 on this shared xeon-4116 allocation",
                "proteome-size differences are not scaled; genome 2 is the stand-in",
                "this is not the locked exclusive epyc-7542 table",
            ],
            "hours_A30": (30 * t / 3600.0) if applies else None,
            "hours_B40": (40 * t / 3600.0) if applies else None,
            "hours_A30_plus_B40": (70 * t / 3600.0) if applies else None,
        }
        dump(Path(self.args.out), self.payload)

    def run(self) -> None:
        for fasta in self.fasta.values():
            if not fasta.is_file():
                raise SystemExit(f"missing fasta {fasta}")
        if not Path(self.pfam).is_file():
            raise SystemExit(f"missing pfam {self.pfam}")
        if self.args.tool == "incr":
            self.payload["setup_incr"] = self._prepare_incr()
            dump(Path(self.args.out), self.payload)
        if "hmmscan" in self._modes():
            self.payload["setup_hmmpress"] = self._press_pfam()
            dump(Path(self.args.out), self.payload)
        for mode in self._modes():
            self.one_mode(mode)
        self.payload["provenance"] = provenance(self._versions())
        dump(Path(self.args.out), self.payload)


def _selfcheck() -> None:
    if classify(10, 1000, cold=True) != "COLD":
        raise SystemExit("cold")
    if classify(900, 1000, cold=False) != "RERUN":
        raise SystemExit("rerun")
    if classify(10, 1000, cold=False) != "SKIP":
        raise SystemExit("skip")
    if classify(200, 1000, cold=False) != "AMBIGUOUS":
        raise SystemExit("ambiguous")
    if reuse_fraction("SKIP") != 1.0 or reuse_fraction("RERUN") != 0.0:
        raise SystemExit("reuse")
    if reuse_fraction("AMBIGUOUS") is not None:
        raise SystemExit("reuse null")
    if step_output_name("replay") != "genome1" or step_output_name("genome2") != "genome2":
        raise SystemExit("replay tblout path")
    g1 = hmmer_argv("hmmscan", "hmmscan", "/tmp/genome1.tbl", "/tmp/g1.faa", "/tmp/pfam")
    replay = hmmer_argv("hmmscan", "hmmscan", "/tmp/genome1.tbl", "/tmp/g1.faa", "/tmp/pfam")
    if g1 != replay:
        raise SystemExit("replay argv")
    fake_action, fake_status = judge_step(
        wall_s=0.13,
        cold_wall_s=1200.0,
        cold=False,
        exit_code=0,
        output_nonempty=False,
        newly_written=False,
        log="",
        match=False,
        cache_unchanged=True,
        argv_matches_prior=True,
    )
    if fake_action != "INVALID" or fake_status != "invalid":
        raise SystemExit(f"fake wrapper scored {fake_action}")
    if classify(0.13, 1200.0, cold=False) != "SKIP":
        raise SystemExit("wall rule should still call 0.13s a SKIP")
    replay_action, replay_status = judge_step(
        wall_s=1.0,
        cold_wall_s=1200.0,
        cold=False,
        exit_code=0,
        output_nonempty=True,
        newly_written=True,
        log="Skip the execution!\n#                                                               --- full sequence ----\n",
        match=True,
        cache_unchanged=True,
        argv_matches_prior=True,
    )
    if replay_action != "SKIP" or replay_status != "replayed":
        raise SystemExit(f"replay scored {replay_action} {replay_status}")
    bad_replay, bad_status = judge_step(
        wall_s=1.0,
        cold_wall_s=1200.0,
        cold=False,
        exit_code=0,
        output_nonempty=True,
        newly_written=True,
        log="Cache valid: hmmsearch",
        match=False,
        cache_unchanged=True,
        argv_matches_prior=True,
    )
    if bad_replay != "FAILED" or bad_status != "failed":
        raise SystemExit(f"bad replay scored {bad_replay}")
    if documented_incr_argv("/tmp/run.sh", "/tmp/cache") != [
        "bash", "./src/incr.sh", "/tmp/run.sh", "/tmp/cache",
    ]:
        raise SystemExit("incr argv")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        hmm = Path(tmp) / "mini.hmm"
        hmm.write_text("HMMER3/f\n")
        try:
            refuse_unpressed_hmmscan("hmmscan", hmm)
        except SystemExit as exc:
            if "use hmmpress first" not in str(exc):
                raise
        else:
            raise SystemExit("unpressed hmmscan was allowed to start")
        refuse_unpressed_hmmscan("hmmsearch", hmm)
        for suffix in HMM_AUX_SUFFIXES:
            Path(str(hmm) + suffix).write_bytes(b"x")
        refuse_unpressed_hmmscan("hmmscan", hmm)
    print("baseline_smoke selfcheck ok")


def main() -> None:
    if "--selfcheck" in sys.argv and len(sys.argv) == 2:
        _selfcheck()
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--tool", required=True, choices=("riker", "processcache", "incr"))
    parser.add_argument("--column", required=True)
    parser.add_argument("--modes", default="hmmsearch,hmmscan")
    parser.add_argument("--build-json", required=True)
    parser.add_argument("--stock-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", default=None)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    if args.selfcheck:
        _selfcheck()
        return
    build = json.loads(Path(args.build_json).read_text())
    Runner(args, build).run()


if __name__ == "__main__":
    main()
