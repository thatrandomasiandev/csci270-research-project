"""Probe-only files → output-directory inference. No per-tool branches. No LLM."""

from __future__ import annotations

import hashlib
import json
import random
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from acts.infer_vcf import (
    BATCHED_SUBSET_SEED,
    InferError,
    SUBSET_MODES,
    batched_index_groups,
)
from acts.sample import PROBE_SEED, sample_records
from acts.trace import run_traced

PROBE_N = 500
_CHUNK = 1 << 20


@dataclass(frozen=True)
class FileRec:
    path: Path
    name: str
    stem: str
    sha256: str


@dataclass
class FilesContract:
    kind: str
    argv: list[str]
    cache_key_fields: list[str]
    stem_rule: str
    suffixes: list[str]
    widen_history: list[str] = field(default_factory=list)
    late_key_probes: list[str] = field(default_factory=list)
    traced_files: list[str] = field(default_factory=list)
    trace_status: str = "unavailable"
    probe_n: int = 0
    probe_seed: int = PROBE_SEED
    subset_mode: str = "batched"
    tool_calls: int = 0
    tool_call_sizes: list[int] = field(default_factory=list)
    decision: str = "OK"
    reason: str = ""
    match: str = "bytes"

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> FilesContract:
        raw = json.loads(path.read_text())
        raw.setdefault("late_key_probes", [])
        raw.setdefault("widen_history", [])
        raw.setdefault("traced_files", [])
        raw.setdefault("trace_status", "unavailable")
        raw.setdefault("probe_seed", PROBE_SEED)
        raw.setdefault("subset_mode", "batched")
        raw.setdefault("tool_calls", 0)
        raw.setdefault("tool_call_sizes", [])
        raw.setdefault("match", "bytes")
        return cls(**raw)


class _FilesMeter:
    def __init__(self) -> None:
        self.n = 0
        self.sizes: list[int] = []

    def run(self, argv: list[str], path: Path, *, work: Path | None = None) -> str:
        del work
        n_rec = len(list_input_files(path))
        self.n += 1
        self.sizes.append(n_rec)
        return run_files_tool(argv, path)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def make_rec(path: Path) -> FileRec:
    return FileRec(path, path.name, path.stem, file_sha256(path))


def list_input_files(d: Path) -> list[Path]:
    if not d.is_dir():
        raise InferError("REFUSE_AMBIGUOUS", "files input must be a directory")
    files = [p for p in d.iterdir() if p.is_file() and not p.name.startswith(".")]
    return sorted(files, key=lambda p: p.name)


def list_records(d: Path) -> list[FileRec]:
    return [make_rec(p) for p in list_input_files(d)]


def rec_key(rec: FileRec, fields: list[str]) -> str:
    parts = [rec.sha256]
    if "name" in fields:
        parts.append(rec.name)
    return "\t".join(parts)


def default_output_dir(input_dir: Path) -> Path:
    return input_dir.parent / (input_dir.name + ".out")


def substitute_files_argv(argv: list[str], input_dir: Path, output_dir: Path) -> list[str]:
    replaced = [
        a.replace("{input}", str(input_dir)).replace("{output}", str(output_dir)) for a in argv
    ]
    if not any("{input}" in a for a in argv):
        replaced.append(str(input_dir))
    if not any("{output}" in a for a in argv):
        replaced.append(str(output_dir))
    return replaced


def list_output_files(out_dir: Path) -> list[Path]:
    if not out_dir.is_dir():
        return []
    files = [p for p in sorted(out_dir.rglob("*")) if p.is_file() and not p.name.startswith(".")]
    return files


def snapshot_dir(out_dir: Path) -> str:
    lines: list[str] = []
    for p in list_output_files(out_dir):
        rel = p.relative_to(out_dir).as_posix()
        lines.append(f"{rel}\t{file_sha256(p)}\t{p.stat().st_size}")
    return "\n".join(lines) + ("\n" if lines else "")


def run_files_tool(argv: list[str], input_dir: Path, output_dir: Path | None = None) -> str:
    out = output_dir or default_output_dir(input_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    cmd = substitute_files_argv(argv, input_dir, out)
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-800:]
        raise InferError("REFUSE_AMBIGUOUS", f"tool failed ({proc.returncode}): {err}")
    return snapshot_dir(out)


def materialize(
    recs: list[FileRec], dest: Path, names: list[str] | None = None
) -> list[FileRec]:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    out: list[FileRec] = []
    used = names or [r.name for r in recs]
    for rec, name in zip(recs, used):
        target = dest / name
        shutil.copy2(rec.path, target)
        out.append(make_rec(target))
    return out


def matched_outputs(rec: FileRec, out_dir: Path, rule: str) -> list[Path]:
    outputs = [p for p in list_output_files(out_dir) if p.parent == out_dir]
    if rule == "stem":
        return sorted([p for p in outputs if p.stem == rec.stem], key=lambda p: p.name)
    return sorted([p for p in outputs if p.name.startswith(rec.name)], key=lambda p: p.name)


def _suffixes(rec: FileRec, paths: list[Path], rule: str) -> list[str]:
    prefix = rec.stem if rule == "stem" else rec.name
    out: list[str] = []
    for p in paths:
        if p.name.startswith(prefix):
            out.append(p.name[len(prefix) :])
    return out


def _rule_fits(recs: list[FileRec], out_dir: Path, rule: str) -> bool:
    outputs = [p for p in list_output_files(out_dir) if p.parent == out_dir]
    claimed: set[Path] = set()
    for rec in recs:
        hits = matched_outputs(rec, out_dir, rule)
        for p in hits:
            if p in claimed:
                return False
            claimed.add(p)
    return claimed == set(outputs)


def infer_stem_rule(
    orig: list[FileRec], orig_out: Path, pert: list[FileRec], pert_out: Path
) -> tuple[str, list[str]]:
    for rule in ("stem", "name"):
        if not _rule_fits(orig, orig_out, rule) or not _rule_fits(pert, pert_out, rule):
            continue
        suffixes: list[str] = []
        for rec in orig:
            for suf in _suffixes(rec, matched_outputs(rec, orig_out, rule), rule):
                if suf not in suffixes:
                    suffixes.append(suf)
        suffixes_p: list[str] = []
        for rec in pert:
            for suf in _suffixes(rec, matched_outputs(rec, pert_out, rule), rule):
                if suf not in suffixes_p:
                    suffixes_p.append(suf)
        if sorted(suffixes) != sorted(suffixes_p):
            continue
        return rule, suffixes
    raise InferError("REFUSE_AMBIGUOUS", "no stem rule followed the renamed files")


def output_path(out_dir: Path, rec: FileRec, rule: str, suffix: str) -> Path:
    if rule == "stem":
        return out_dir / f"{rec.stem}{suffix}"
    return out_dir / f"{rec.name}{suffix}"


def record_payload(rec: FileRec, out_dir: Path, contract: FilesContract) -> dict:
    files: list[dict] = []
    for suf in contract.suffixes:
        p = output_path(out_dir, rec, contract.stem_rule, suf)
        if p.is_file():
            files.append({"suffix": suf, "hex": p.read_bytes().hex()})
    return {"files": files}


def payload_bytes(payload: dict) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for item in payload.get("files", []):
        out.append((item["suffix"], bytes.fromhex(item.get("hex", ""))))
    return out


def payloads_equal(a: dict, b: dict) -> bool:
    return payload_bytes(a) == payload_bytes(b)


def write_payload(dest: Path, rec: FileRec, payload: dict, contract: FilesContract) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for suf, data in payload_bytes(payload):
        output_path(dest, rec, contract.stem_rule, suf).write_bytes(data)


def dirs_match(a: Path, b: Path) -> bool:
    return snapshot_dir(a) == snapshot_dir(b)


def assert_subset_invariant(
    argv: list[str],
    recs: list[FileRec],
    full_out: Path,
    contract: FilesContract,
    work: Path,
    *,
    subset_mode: str = "batched",
    runner=None,
    seed: int = BATCHED_SUBSET_SEED,
) -> None:
    if subset_mode not in SUBSET_MODES:
        raise ValueError(f"subset_mode must be one of {SUBSET_MODES}, got {subset_mode!r}")
    run = runner or run_files_tool
    expected = [record_payload(rec, full_out, contract) for rec in recs]
    work.mkdir(parents=True, exist_ok=True)

    if subset_mode == "singleton":
        solo = work / "singleton"
        solo.mkdir(parents=True, exist_ok=True)
        for i, rec in enumerate(recs):
            batch_dir = solo / f"{i}"
            materialize([rec], batch_dir)
            run(argv, batch_dir)
            got = record_payload(make_rec(batch_dir / rec.name), default_output_dir(batch_dir), contract)
            if not payloads_equal(got, expected[i]):
                raise InferError(
                    "REFUSE_GLOBAL",
                    f"output depends on the rest of the file (singleton {i})",
                )
        return

    batches = work / "batched"
    batches.mkdir(parents=True, exist_ok=True)
    for g, indices in enumerate(batched_index_groups(len(recs), seed=seed)):
        batch = [recs[i] for i in indices]
        batch_dir = batches / f"g{g}_n{len(indices)}"
        materialized = materialize(batch, batch_dir)
        run(argv, batch_dir)
        out_dir = default_output_dir(batch_dir)
        for rec, src in zip(materialized, batch):
            got = record_payload(rec, out_dir, contract)
            exp = expected[recs.index(src)]
            if not payloads_equal(got, exp):
                raise InferError(
                    "REFUSE_GLOBAL",
                    f"output depends on the rest of the file (batch {g} n={len(indices)})",
                )


def infer_files_contract(
    argv: list[str],
    recs: list[FileRec],
    work: Path,
    *,
    probe_n: int = PROBE_N,
    probe_seed: int = PROBE_SEED,
    subset_mode: str = "batched",
) -> FilesContract:
    if subset_mode not in SUBSET_MODES:
        raise ValueError(f"subset_mode must be one of {SUBSET_MODES}, got {subset_mode!r}")
    probe = sample_records(recs, min(probe_n, len(recs)), seed=probe_seed)
    if not probe:
        raise InferError("REFUSE_AMBIGUOUS", "empty files input")
    work.mkdir(parents=True, exist_ok=True)
    meter = _FilesMeter()
    run = meter.run

    try:
        probe_dir = work / "probe"
        probe_recs = materialize(probe, probe_dir)
        snap1, traced_files, trace_status = run_traced(
            argv, input_path=probe_dir, work=work / "trace", runner=run
        )
        snap2 = run(argv, probe_dir)
        if snap1 != snap2:
            raise InferError(
                "REFUSE_NONDETERMINISTIC",
                "tool output directory differs across two identical runs",
            )
        orig_out = default_output_dir(probe_dir)

        pert_names = [f"PERTURB_{i}{Path(r.name).suffix}" for i, r in enumerate(probe_recs)]
        pert_dir = work / "probe_pert"
        pert_recs = materialize(probe_recs, pert_dir, pert_names)
        run(argv, pert_dir)
        pert_out = default_output_dir(pert_dir)
        stem_rule, suffixes = infer_stem_rule(probe_recs, orig_out, pert_recs, pert_out)

        draft = FilesContract(
            kind="files",
            argv=list(argv),
            cache_key_fields=["sha256"],
            stem_rule=stem_rule,
            suffixes=suffixes,
        )
        name_depends = False
        for orig, pert in zip(probe_recs, pert_recs):
            if not payloads_equal(
                record_payload(orig, orig_out, draft),
                record_payload(pert, pert_out, draft),
            ):
                name_depends = True
                break

        shuf = list(probe_recs)
        random.Random(7).shuffle(shuf)
        sh_dir = work / "probe_shuffle"
        sh_recs = materialize(shuf, sh_dir)
        run(argv, sh_dir)
        sh_out = default_output_dir(sh_dir)
        by_name = {r.name: r for r in sh_recs}
        for rec in probe_recs:
            got = record_payload(by_name[rec.name], sh_out, draft)
            if not payloads_equal(got, record_payload(rec, orig_out, draft)):
                raise InferError("REFUSE_NEIGHBORS", "shuffle test failed; neighbors leak")

        fields = ["sha256"]
        widen_history: list[str] = []
        if name_depends:
            fields.append("name")
            widen_history.append("name")

        contract = FilesContract(
            kind="files",
            argv=list(argv),
            cache_key_fields=fields,
            stem_rule=stem_rule,
            suffixes=suffixes,
            widen_history=widen_history,
            traced_files=traced_files,
            trace_status=trace_status,
            probe_n=len(probe),
            probe_seed=probe_seed,
            subset_mode=subset_mode,
            tool_calls=0,
            tool_call_sizes=[],
            decision="OK",
            reason="probe passed",
        )
        assert_subset_invariant(
            argv,
            probe_recs,
            orig_out,
            contract,
            work,
            subset_mode=subset_mode,
            runner=run,
        )
        contract.tool_calls = meter.n
        contract.tool_call_sizes = list(meter.sizes)
        return contract
    except InferError as exc:
        exc.tool_calls = meter.n
        exc.tool_call_sizes = list(meter.sizes)
        raise


def unclassified_suffixes(out_dir: Path, recs: list[FileRec], contract: FilesContract) -> list[str]:
    extra: list[str] = []
    known = set(contract.suffixes)
    for rec in recs:
        for suf in _suffixes(rec, matched_outputs(rec, out_dir, contract.stem_rule), contract.stem_rule):
            if suf not in known and suf not in extra:
                extra.append(suf)
    return extra


def probe_late_suffixes(
    argv: list[str],
    carriers: list[FileRec],
    contract: FilesContract,
    work: Path,
    new_suffixes: list[str],
) -> None:
    if not carriers or not new_suffixes:
        return
    subset = carriers[:200]
    work.mkdir(parents=True, exist_ok=True)
    orig = materialize(subset, work / "late_orig")
    run_files_tool(argv, work / "late_orig")
    pert_names = [f"LATE_{i}{Path(r.name).suffix}" for i, r in enumerate(orig)]
    materialize(orig, work / "late_pert", pert_names)
    run_files_tool(argv, work / "late_pert")
    for suf in new_suffixes:
        if suf not in contract.suffixes:
            contract.suffixes.append(suf)
        if suf not in contract.late_key_probes:
            contract.late_key_probes.append(suf)


def load_or_infer_files(
    argv: list[str],
    recs: list[FileRec],
    work: Path,
    contract_path: Path,
    *,
    probe_n: int = PROBE_N,
    probe_seed: int = PROBE_SEED,
    subset_mode: str = "batched",
) -> FilesContract:
    if contract_path.is_file():
        saved = FilesContract.load(contract_path)
        if saved.argv == list(argv) and saved.kind == "files" and saved.decision == "OK":
            return saved
    contract = infer_files_contract(
        argv,
        recs,
        work,
        probe_n=probe_n,
        probe_seed=probe_seed,
        subset_mode=subset_mode,
    )
    contract.save(contract_path)
    return contract


def refuse_files(exc: InferError, argv: list[str]) -> FilesContract:
    return FilesContract(
        kind="files",
        argv=list(argv),
        cache_key_fields=["sha256"],
        stem_rule="stem",
        suffixes=[],
        subset_mode="batched",
        tool_calls=getattr(exc, "tool_calls", 0),
        tool_call_sizes=list(getattr(exc, "tool_call_sizes", []) or []),
        decision=exc.decision,
        reason=exc.reason,
    )
