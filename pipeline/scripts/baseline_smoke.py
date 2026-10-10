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

Reuse fraction is the fraction of the HMMER process the wrapper did
not re-execute. These tools are whole-command caches, so the fraction
is 0 (COLD or RERUN) or 1 (SKIP). There is no record-level partial hit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
        if getattr(args, "work", None):
            self.work = Path(args.work)
        else:
            self.work = self.root / "smoke" / f"{args.tool}_{args.column}"
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
                "COLD": "genome 1, first invocation",
                "RERUN": "wall_s >= 0.50 * genome1_wall_s",
                "SKIP": "wall_s <= max(180s, 0.08 * genome1_wall_s)",
                "AMBIGUOUS": "otherwise",
                "reuse_fraction": "0 on COLD or RERUN, 1 on SKIP, null on AMBIGUOUS",
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
        env["PATH"] = str(self.root / "bin") + os.pathsep + env.get("PATH", "")
        if self.args.tool == "incr":
            incr = (self.build.get("tools") or {}).get("incr") or {}
            env["INCR_TOP"] = incr.get("top") or str(self.root / "src" / "incr")
            if self.args.column == "annotations":
                env["INCR_SYS_PATH"] = f"{incr.get('binary')} --enable_annotations"
            else:
                env.pop("INCR_SYS_PATH", None)
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
            binary = (self.build.get("tools") or {})["processcache_sha256"]["binary"]
            return [binary, "--", *hmm_argv], home, extra
        if self.args.tool == "incr":
            home = self.work / "incr" / mode
            home.mkdir(parents=True, exist_ok=True)
            cache = home / "cache"
            cache.mkdir(parents=True, exist_ok=True)
            script = home / "run.sh"
            body = "#!/bin/bash\n" + " ".join(hmm_argv) + "\n"
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
            return ["bash", incr["incr_sh"], str(script), str(cache)], home, extra
        raise ValueError(self.args.tool)

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
        for name in ("genome1", "genome2", "replay"):
            tblout = self.work / mode / f"{step_output_name(name)}.tbl"
            tblout.parent.mkdir(parents=True, exist_ok=True)
            before = sha256_file(tblout)
            before_mtime = tblout.stat().st_mtime if tblout.exists() else None
            argv = hmmer_argv(self.hmm_by_mode[mode], mode, str(tblout), str(fastas[name]), self.pfam)
            wrapped, cwd, extra = self.wrap(mode, name, argv)
            code, wall, log_kept = self.launch(mode, name, wrapped, cwd)
            after = sha256_file(tblout)
            text = tblout.read_text(errors="replace") if tblout.is_file() else ""
            snapshot = None
            if tblout.is_file():
                snapshot = snapshot_output(
                    tblout, self.work / "comparisons" / mode / f"{name}.tbl"
                )
            stock_path = stocks[name]
            stock_text = stock_path.read_text(errors="replace") if stock_path.is_file() else ""
            matched = bool(text) and bool(stock_text) and tables_match(text, stock_text, mode)
            action = classify(wall, cold_wall or 0.0, cold=(name == "genome1"))
            if action == "SKIP" and code != 0:
                action = "FAILED"
            if name == "genome1":
                cold_wall = wall
            step = {
                "name": name,
                "accession": GENOME1["accession"] if name != "genome2" else GENOME2["accession"],
                "fasta": str(fastas[name]),
                "n_records": n_records(fastas[name]),
                "argv": argv,
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
                "tblout_mtime_changed": (tblout.stat().st_mtime if tblout.exists() else None) != before_mtime,
                "output_snapshot": snapshot,
                "replay_reuses_genome1_tblout": name != "replay" or step_output_name(name) == "genome1",
                "output_nonempty": nonempty_body(text),
                "stock_tblout": str(stock_path),
                "stock_present": stock_path.is_file(),
                "match": matched,
                "log_tail_path": str(log_kept),
                "log_tail": log_kept.read_text(errors="replace"),
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
        applies = g2["action"] == "RERUN"
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
        for mode in self.args.modes.split(","):
            self.one_mode(mode.strip())
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
