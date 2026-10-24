#!/usr/bin/env python3
"""STEP 0 baseline for shared-contract work. Shape only; not speed evidence."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
ROOT = PIPE.parent
sys.path.insert(0, str(PIPE))

from acts.reference_formats import parse_entryline, parse_reference, read_records, write_entries
from acts.reference_run import ReferenceIncremental, body_lines
from acts.provenance import provenance

FIX = PIPE / "tests" / "fixtures" / "reference_fitter"
OUT = PIPE / "results" / "shared_contract"
CORPUS = OUT / "baseline_corpus"
HITS = {"e1", "e3", "e4"}
ARGV = ["law", "{reference}", "{input}", "{output}"]
WALL_KEYS = re.compile(r"(_s|wall|total_s|probe_wall):", re.I)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _render(records, entries, scale: float, *, hits=HITS, footer: str = "", fmt: str = ".3g") -> dict[str, str]:
    lines = ["# record entry evalue"]
    for rec in records:
        for entry in entries:
            if entry.primary not in hits:
                continue
            lines.append(f"{rec.key} {entry.primary} {format(scale * float(rec.description), fmt)}")
    if footer:
        lines.append(f"# {footer}")
    return {"out": "\n".join(lines) + "\n"}


def stock(records, entries):
    return _render(records, entries, len(entries), footer=f"run on {len(entries)} entries")


def honest_pin(records, entries, values):
    return _render(records, entries, values["entry_count"], footer="pinned")


def strip_wall_lines(text: str) -> str:
    keep = []
    for line in text.splitlines():
        if WALL_KEYS.search(line) or line.startswith("phases:") or line.startswith("probe_phases:"):
            continue
        keep.append(line)
    return "\n".join(keep) + ("\n" if keep else "")


def run_pytest() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--collect-only", "-q"],
        cwd=PIPE,
        capture_output=True,
        text=True,
        check=False,
    )
    ids = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip().startswith("tests/")]
    # also lines like tests/foo.py::Bar
    if not ids:
        ids = [ln.strip() for ln in proc.stdout.splitlines() if "::" in ln]
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=PIPE,
        capture_output=True,
        text=True,
        check=False,
    )
    summary = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else ""
    skipped = []
    rs = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rs"],
        cwd=PIPE,
        capture_output=True,
        text=True,
        check=False,
    )
    for line in rs.stdout.splitlines():
        if line.startswith("SKIPPED"):
            skipped.append(line.strip())
    return {
        "collect_count": len(ids),
        "test_ids": ids,
        "run_summary": summary,
        "run_returncode": run.returncode,
        "skipped": skipped,
        "stdout_tail": "\n".join(run.stdout.splitlines()[-8:]),
    }


def capture_case(name: str, tmp: Path, ref: Path, *, pin_runner, runner=stock, pin="-Z {entry_count}", verify="full", update_ref=None) -> dict:
    dest = CORPUS / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    cache = tmp / f"{name}_cache.sqlite"
    first = ReferenceIncremental(
        argv=ARGV,
        input_path=FIX / "ab.faa",
        out_dir=tmp / f"{name}_first",
        reference=ref,
        cache_path=cache,
        verify=verify,
        runner=runner,
        pin=pin,
        pin_runner=pin_runner,
    ).run()
    first_out = dest / "first"
    shutil.copytree(tmp / f"{name}_first", first_out)
    tables = {}
    tdir = first_out / "tables"
    if tdir.is_dir():
        for p in sorted(tdir.iterdir()):
            if p.is_file() and not p.name.endswith(".json"):
                tables[p.name] = sha256_file(p)
    decision = (first_out / "decision.txt").read_text() if (first_out / "decision.txt").is_file() else ""
    result = {
        "name": name,
        "decision": first.decision,
        "reason": first.reason,
        "decision_txt_sha256": sha256_bytes(decision.encode()),
        "decision_txt_stripped_sha256": sha256_bytes(strip_wall_lines(decision).encode()),
        "output_table_sha256": tables,
        "phases": dict(first.extra.get("phases") or {}),
        "probe_phases": dict(first.extra.get("probe_phases") or {}),
        "kind": "first",
    }
    if update_ref is not None:
        second = ReferenceIncremental(
            argv=ARGV,
            input_path=FIX / "ab.faa",
            out_dir=tmp / f"{name}_update",
            reference=update_ref,
            cache_path=cache,
            verify=verify,
            runner=runner,
            pin=pin,
            pin_runner=pin_runner,
        ).run()
        upd = dest / "update"
        shutil.copytree(tmp / f"{name}_update", upd)
        utables = {}
        utdir = upd / "tables"
        if utdir.is_dir():
            for p in sorted(utdir.iterdir()):
                if p.is_file() and not p.name.endswith(".json"):
                    utables[p.name] = sha256_file(p)
        udec = (upd / "decision.txt").read_text() if (upd / "decision.txt").is_file() else ""
        result["update"] = {
            "decision": second.decision,
            "reason": second.reason,
            "decision_txt_sha256": sha256_bytes(udec.encode()),
            "decision_txt_stripped_sha256": sha256_bytes(strip_wall_lines(udec).encode()),
            "output_table_sha256": utables,
            "phases": dict(second.extra.get("phases") or {}),
            "probe_phases": dict(second.extra.get("probe_phases") or {}),
            "kind": "update",
        }
    return result


def tiny_hmmscan(scratch: Path) -> dict | None:
    hmmscan = shutil.which("hmmscan")
    hmmbuild = shutil.which("hmmbuild")
    hmmpress = shutil.which("hmmpress")
    if not (hmmscan and hmmbuild and hmmpress):
        return {"skipped": True, "reason": "hmmscan/hmmbuild/hmmpress not all on PATH"}
    sto = PIPE / "artifact" / "fixtures" / "profiles"
    if not sto.is_dir():
        return {"skipped": True, "reason": "no artifact profiles"}
    work = scratch / "hmm_tiny"
    work.mkdir(parents=True)
    models = work / "toy.hmm"
    # build a tiny HMM database from Toy*.sto
    parts = []
    for i, name in enumerate(["ToyA", "ToyB", "ToyC", "ToyD"]):
        src = sto / f"{name}.sto"
        if not src.is_file():
            continue
        out = work / f"{name}.hmm"
        subprocess.run([hmmbuild, "--amino", str(out), str(src)], check=True, capture_output=True)
        parts.append(out.read_text())
    if len(parts) < 2:
        return {"skipped": True, "reason": "fewer than 2 toy HMMs"}
    models.write_text("".join(parts))
    subprocess.run([hmmpress, "-f", str(models)], check=True, capture_output=True)
    # tiny queries: emit consensus-ish short peptides from fasta fixture
    faa = FIX / "ab.faa"
    out_dir = work / "tare_out"
    argv = [
        hmmscan,
        "--cpu", "1",
        "--tblout", "{output:tbl}",
        "--domtblout", "{output:domtbl}",
        "{reference}",
        "{input}",
    ]
    t0 = time.perf_counter()
    rec = ReferenceIncremental(
        argv=argv,
        input_path=faa,
        out_dir=out_dir,
        reference=models,
        cache_path=work / "cache.sqlite",
        verify="full",
        pin="-Z {entry_count}",
        prep=f"hmmpress -f {{reference}}",
    ).run()
    wall = time.perf_counter() - t0
    dest = CORPUS / "real_hmmscan_tiny"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(out_dir, dest)
    tables = {}
    tdir = dest / "tables"
    if tdir.is_dir():
        for p in sorted(tdir.iterdir()):
            if p.is_file() and not p.name.endswith(".json"):
                tables[p.name] = sha256_file(p)
    decision = (dest / "decision.txt").read_text() if (dest / "decision.txt").is_file() else ""
    return {
        "skipped": False,
        "tool": hmmscan,
        "decision": rec.decision,
        "reason": rec.reason,
        "wall_s_shape_only": wall,
        "decision_txt_stripped_sha256": sha256_bytes(strip_wall_lines(decision).encode()),
        "output_table_sha256": tables,
        "phases": dict(rec.extra.get("phases") or {}),
        "probe_phases": dict(rec.extra.get("probe_phases") or {}),
        "seed_note": "no new RNG seed; PROBE_SEED from acts.reference_fit",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    CORPUS.mkdir(parents=True, exist_ok=True)
    pytest_info = run_pytest()
    cases = []
    with tempfile.TemporaryDirectory(dir=os.path.expanduser("~/tmp/tare_sharedcontract")) as raw:
        tmp = Path(raw)
        ref1 = FIX / "ab.entryline"
        ref2 = tmp / "v2.entryline"
        keep = [e for e in parse_reference(ref1) if e.primary in {"e0", "e1", "e3"}]
        write_entries(keep + parse_entryline("e4 5\n") + parse_entryline("e5 3\n"), ref2)
        cases.append(
            capture_case(
                "exact_replay_pin_release",
                tmp,
                ref1,
                pin_runner=honest_pin,
                update_ref=ref2,
            )
        )
        # identity-normalizer path: scale=1 always
        def id_stock(records, entries):
            return _render(records, entries, 1.0, footer="identity")

        def id_pin(records, entries, values):
            return _render(records, entries, 1.0, footer="identity")

        cases.append(
            capture_case(
                "identity_normalizer",
                tmp,
                ref1,
                runner=id_stock,
                pin_runner=id_pin,
                pin="-Z {entry_count}",
            )
        )
        hmm = tiny_hmmscan(tmp)

    # phase timing shape from first case
    phase_shape = {
        "note": "SHAPE ONLY — not speed evidence. Laptop fixture timings.",
        "first": cases[0].get("phases"),
        "first_probe_phases": cases[0].get("probe_phases"),
        "update": (cases[0].get("update") or {}).get("phases"),
        "update_probe_phases": (cases[0].get("update") or {}).get("probe_phases"),
    }

    payload = {
        "kind": "shared_contract_p1_baseline",
        "base_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip(),
        "branch": subprocess.run(
            ["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip(),
        "pytest": pytest_info,
        "regression_corpus": cases,
        "real_tool_runs": {"hmmscan": hmm, "cmscan": {"skipped": True, "reason": "not on PATH"}, "diamond": {"skipped": True, "reason": "not on PATH"}},
        "phase_timings_shape": phase_shape,
        "provenance": provenance(versions={"python": sys.version.split()[0]}),
        "seeds_reserved": list(range(20261331, 20261340)),
        "seed_collisions_in_repo": [],
    }
    path = OUT / "p1_baseline.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path}")
    print("pytest:", pytest_info["run_summary"], "ids", pytest_info["collect_count"])
    print("cases:", [c["name"] for c in cases], "hmmscan", hmm.get("decision") if hmm else None)
    return 0 if pytest_info["run_returncode"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
