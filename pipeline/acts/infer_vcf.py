"""Probe-only VCF record inference. No per-tool branches. No LLM."""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from acts.vcf import bodies_equal, body_lines, is_header, shuffle_body, variant_key
from acts.vcf_fields import (
    COL_FILTER,
    COL_ID,
    COL_INFO,
    COL_QUAL,
    KEY_FIELDS,
    NONKEY_GROUPS,
    cache_key,
    col,
    format_info,
    format_info_item,
    info_map,
    info_types,
    parse_info,
    perturb_record,
    split_record,
)

PERT_FILTER_HDR = '##FILTER=<ID=PERT,Description="ACTS inference probe">'

PROBE_N = 500
NAMED_NONKEY = ("ID", "QUAL", "FILTER")


class InferError(Exception):
    def __init__(self, decision: str, reason: str):
        super().__init__(reason)
        self.decision = decision
        self.reason = reason


@dataclass
class RecordContract:
    kind: str
    argv: list[str]
    cache_key_fields: list[str]
    column_roles: dict[str, str]
    info_roles: dict[str, str]
    produced_info_order: list[str]
    sample_role: str
    widen_history: list[str] = field(default_factory=list)
    late_key_probes: list[str] = field(default_factory=list)
    probe_n: int = 0
    decision: str = "OK"
    reason: str = ""

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> RecordContract:
        raw = json.loads(path.read_text())
        raw.setdefault("late_key_probes", [])
        raw.setdefault("widen_history", [])
        return cls(**raw)


def substitute_argv(argv: list[str], vcf_path: Path) -> list[str]:
    replaced = [a.replace("{input}", str(vcf_path)) for a in argv]
    if any("{input}" in a for a in argv):
        return replaced
    return replaced + [str(vcf_path)]


def run_vcf_tool(argv: list[str], vcf_path: Path, *, work: Path | None = None) -> str:
    cmd = substitute_argv(argv, vcf_path)
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-800:]
        raise InferError("REFUSE_AMBIGUOUS", f"tool failed ({proc.returncode}): {err}")
    return proc.stdout


def write_vcf(path: Path, header: list[str], body: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    hdr = list(header)
    if any("\tPERT\t" in ln or ln.split("\t")[6:7] == ["PERT"] for ln in body):
        if not any(ln.startswith("##FILTER=<ID=PERT") for ln in hdr):
            insert_at = next((i for i, ln in enumerate(hdr) if ln.startswith("#CHROM")), len(hdr))
            hdr.insert(insert_at, PERT_FILTER_HDR)
    path.write_text("\n".join(hdr + body) + "\n")
    return path


def header_of(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if is_header(ln)]


def align_by_key(in_body: list[str], out_body: list[str]) -> list[tuple[str, str]]:
    buckets: dict[str, list[str]] = defaultdict(list)
    for ln in out_body:
        buckets[variant_key(ln)].append(ln)
    pairs: list[tuple[str, str]] = []
    for ln in in_body:
        k = variant_key(ln)
        got = buckets.get(k)
        if not got:
            raise InferError("REFUSE_AMBIGUOUS", f"no output record for {k}")
        pairs.append((ln, got.pop(0)))
    leftover = sum(len(v) for v in buckets.values())
    if leftover:
        raise InferError("REFUSE_AMBIGUOUS", f"{leftover} unmatched output record(s)")
    return pairs


def _classify(val_o: str | None, val_p: str | None, in_o: str | None, in_p: str | None) -> str | None:
    if val_o is None or val_p is None:
        return None
    in_present = in_p is not None
    # Output changed while this input field did not: it depends on some
    # *other* perturbed group (fill-tags AF/AC from SAMPLES). That is
    # DEPENDS, not "no information."
    if in_present and in_o == in_p:
        if val_o == val_p:
            return None
        return "depends"
    if in_present and val_p == in_p:
        return "pass"
    if val_o == val_p and (not in_present or val_p != in_p):
        return "produced"
    if val_o != val_p and (not in_present or val_p != in_p):
        return "depends"
    return "ambiguous"


def _vote(roles: list[str]) -> str | None:
    if not roles:
        return None
    if "ambiguous" in roles:
        return "ambiguous"
    if "depends" in roles:
        return "depends"
    kinds = set(roles)
    if kinds == {"pass"}:
        return "pass"
    if kinds == {"produced"}:
        return "produced"
    return "ambiguous"


def classify_pairs(pairs_o: list[tuple[str, str]], pairs_p: list[tuple[str, str]]) -> dict:
    col_votes: dict[str, list[str]] = defaultdict(list)
    info_votes: dict[str, list[str]] = defaultdict(list)
    sample_votes: list[str] = []
    info_order: list[str] = []

    by_key_p = {variant_key(i): (i, o) for i, o in pairs_p}
    for in_o, out_o in pairs_o:
        k = variant_key(in_o)
        if k not in by_key_p:
            raise InferError("REFUSE_AMBIGUOUS", f"perturbed output missing {k}")
        in_p, out_p = by_key_p[k]
        pin_o, pin_p = split_record(in_o), split_record(in_p)
        pout_o, pout_p = split_record(out_o), split_record(out_p)

        for name, idx in (("ID", COL_ID), ("QUAL", COL_QUAL), ("FILTER", COL_FILTER)):
            role = _classify(
                col(pout_o, name),
                col(pout_p, name),
                col(pin_o, name),
                col(pin_p, name),
            )
            if role:
                col_votes[name].append(role)

        in_info_o = info_map(pin_o[COL_INFO]) if len(pin_o) > COL_INFO else {}
        in_info_p = info_map(pin_p[COL_INFO]) if len(pin_p) > COL_INFO else {}
        out_info_o = parse_info(pout_o[COL_INFO]) if len(pout_o) > COL_INFO else []
        out_info_p = info_map(pout_p[COL_INFO]) if len(pout_p) > COL_INFO else {}
        for key, val_o in out_info_o:
            if key not in info_order:
                info_order.append(key)
            role = _classify(
                format_info_item(key, val_o),
                format_info_item(key, out_info_p[key]) if key in out_info_p else None,
                format_info_item(key, in_info_o[key]) if key in in_info_o else None,
                format_info_item(key, in_info_p[key]) if key in in_info_p else None,
            )
            if role:
                info_votes[key].append(role)

        if len(pout_o) > 9 and len(pout_p) > 9:
            samp_o = "\t".join(pout_o[9:])
            samp_p = "\t".join(pout_p[9:])
            in_s_o = "\t".join(pin_o[9:]) if len(pin_o) > 9 else None
            in_s_p = "\t".join(pin_p[9:]) if len(pin_p) > 9 else None
            role = _classify(samp_o, samp_p, in_s_o, in_s_p)
            if role:
                sample_votes.append(role)

    return {
        "column_roles": {n: _vote(v) for n, v in col_votes.items() if _vote(v)},
        "info_roles": {n: _vote(v) for n, v in info_votes.items() if _vote(v)},
        "sample_role": _vote(sample_votes) or "pass",
        "info_order": info_order,
    }


def _depends_fields(classified: dict) -> list[str]:
    """Widen only when a *produced* INFO (or sample) value depends on non-key input.

    A column that is itself depends is a rewrite (PRODUCED), not a key widen.
    """
    bad: list[str] = []
    for name, role in classified["info_roles"].items():
        if role in {"depends", "ambiguous"}:
            bad.append(f"INFO/{name}")
    if classified["sample_role"] in {"depends", "ambiguous"}:
        bad.append("SAMPLES")
    return bad


def assert_subset_invariant(
    argv: list[str],
    header: list[str],
    probe: list[str],
    full_out_body: list[str],
    work: Path,
    *,
    workers: int = 8,
) -> None:
    """Each record alone must match its line from the full-probe run."""
    pairs = align_by_key(probe, full_out_body)
    solo = work / "singleton"
    solo.mkdir(parents=True, exist_ok=True)

    def _one(item: tuple[int, str, str]) -> tuple[int, str, str, str]:
        i, rec_in, rec_full = item
        path = write_vcf(solo / f"{i}.vcf", header, [rec_in])
        out = run_vcf_tool(argv, path)
        body = body_lines(out)
        got = body[0] if len(body) == 1 else ""
        return i, rec_full, got, f"n_out={len(body)}"

    items = list(enumerate((a, b) for a, b in pairs))
    packed = [(i, rec_in, rec_full) for i, (rec_in, rec_full) in items]
    if workers <= 1 or len(packed) <= 1:
        results = [_one(p) for p in packed]
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_one, packed))
    for i, rec_full, got, extra in results:
        if got != rec_full:
            raise InferError(
                "REFUSE_GLOBAL",
                f"output depends on the rest of the file (singleton {i}: {extra})",
            )


def unclassified_info_keys(out_body: list[str], contract: RecordContract) -> list[str]:
    seen: list[str] = []
    known = set(contract.info_roles)
    for ln in out_body:
        parts = split_record(ln)
        if len(parts) <= COL_INFO:
            continue
        for key, _val in parse_info(parts[COL_INFO]):
            if key not in known and key not in seen:
                seen.append(key)
    return seen


def probe_new_info_keys(
    argv: list[str],
    header: list[str],
    carriers: list[str],
    contract: RecordContract,
    work: Path,
    new_keys: list[str],
) -> None:
    """Classify previously unseen INFO keys. May widen the cache key once."""
    if not carriers or not new_keys:
        return
    subset = carriers[:200]
    work.mkdir(parents=True, exist_ok=True)
    types = info_types(header)
    remaining = [g for g in NONKEY_GROUPS if g not in contract.cache_key_fields]
    orig = write_vcf(work / "late_orig.vcf", header, subset)
    out_o = run_vcf_tool(argv, orig)
    pert = [perturb_record(ln, i, remaining, info_types_map=types) for i, ln in enumerate(subset)]
    out_p = run_vcf_tool(argv, write_vcf(work / "late_pert.vcf", header, pert))
    classified = classify_pairs(align_by_key(subset, body_lines(out_o)), align_by_key(pert, body_lines(out_p)))
    depends = [k for k in new_keys if classified["info_roles"].get(k) in {"depends", "ambiguous"}]
    if depends:
        group_hits: dict[str, list[str]] = {}
        for group in remaining:
            g_pert = [perturb_record(ln, i, [group], info_types_map=types) for i, ln in enumerate(subset)]
            g_out = run_vcf_tool(argv, write_vcf(work / f"late_pert_{group.lower()}.vcf", header, g_pert))
            g_class = classify_pairs(
                align_by_key(subset, body_lines(out_o)),
                align_by_key(g_pert, body_lines(g_out)),
            )
            hit = [k for k in new_keys if g_class["info_roles"].get(k) in {"depends", "ambiguous"}]
            if hit:
                group_hits[group] = hit
        if not group_hits:
            raise InferError(
                "REFUSE_AMBIGUOUS",
                f"late keys {depends} DEPENDS-ON-NON-KEY but no group reproduced it",
            )
        for group in group_hits:
            if group not in contract.cache_key_fields:
                contract.cache_key_fields.append(group)
                contract.widen_history.append(f"late:{group}")
        still_groups = [g for g in NONKEY_GROUPS if g not in contract.cache_key_fields]
        if still_groups:
            p2 = [perturb_record(ln, i, still_groups, info_types_map=types) for i, ln in enumerate(subset)]
            out2 = run_vcf_tool(argv, write_vcf(work / "late_pert_after_widen.vcf", header, p2))
            classified = classify_pairs(
                align_by_key(subset, body_lines(out_o)),
                align_by_key(p2, body_lines(out2)),
            )
            still = [k for k in new_keys if classified["info_roles"].get(k) in {"depends", "ambiguous"}]
            if still:
                raise InferError(
                    "REFUSE_AMBIGUOUS",
                    f"late keys still DEPENDS-ON-NON-KEY after widen: {still}",
                )
    for key in new_keys:
        role = classified["info_roles"].get(key) or "produced"
        if role in {"depends", "ambiguous"}:
            role = "produced"
        contract.info_roles[key] = role
        if role == "produced" and key not in contract.produced_info_order:
            contract.produced_info_order.append(key)
        if key not in contract.late_key_probes:
            contract.late_key_probes.append(key)


def infer_contract(
    argv: list[str],
    header: list[str],
    body: list[str],
    work: Path,
    *,
    probe_n: int = PROBE_N,
    singleton_workers: int = 8,
) -> RecordContract:
    probe = body[: min(probe_n, len(body))]
    if not probe:
        raise InferError("REFUSE_AMBIGUOUS", "empty VCF body")
    work.mkdir(parents=True, exist_ok=True)

    p1 = write_vcf(work / "probe.vcf", header, probe)
    out1 = run_vcf_tool(argv, p1)
    out2 = run_vcf_tool(argv, p1)
    if not bodies_equal(out1, out2):
        raise InferError("REFUSE_NONDETERMINISTIC", "tool body differs across two identical runs")

    shuffled = shuffle_body("\n".join(header + probe) + "\n", seed=7)
    p_sh = write_vcf(work / "probe_shuffle.vcf", header_of(shuffled), body_lines(shuffled))
    out_sh = run_vcf_tool(argv, p_sh)
    if not bodies_equal(out1, out_sh):
        raise InferError("REFUSE_NEIGHBORS", "shuffle test failed; neighbors leak")

    assert_subset_invariant(
        argv, header, probe, body_lines(out1), work, workers=singleton_workers
    )

    key_fields = list(KEY_FIELDS)
    widen_history: list[str] = []
    remaining = list(NONKEY_GROUPS)
    types = info_types(header)

    pert = [perturb_record(ln, i, remaining, info_types_map=types) for i, ln in enumerate(probe)]
    p_pert = write_vcf(work / "probe_pert.vcf", header, pert)
    out_pert = run_vcf_tool(argv, p_pert)
    pairs_o = align_by_key(probe, body_lines(out1))
    pairs_p = align_by_key(pert, body_lines(out_pert))
    classified = classify_pairs(pairs_o, pairs_p)
    depends = _depends_fields(classified)

    if depends:
        group_hits: dict[str, list[str]] = {}
        for group in remaining:
            g_pert = [perturb_record(ln, i, [group], info_types_map=types) for i, ln in enumerate(probe)]
            pg = write_vcf(work / f"probe_pert_{group.lower()}.vcf", header, g_pert)
            out_g = run_vcf_tool(argv, pg)
            g_class = classify_pairs(pairs_o, align_by_key(g_pert, body_lines(out_g)))
            hit = _depends_fields(g_class)
            if hit:
                group_hits[group] = hit
        if not group_hits:
            raise InferError(
                "REFUSE_AMBIGUOUS",
                f"DEPENDS-ON-NON-KEY on {depends} but no single group reproduced it",
            )
        for group in group_hits:
            if group not in key_fields:
                key_fields.append(group)
                widen_history.append(group)
        remaining = [g for g in NONKEY_GROUPS if g not in key_fields]
        pert2 = [perturb_record(ln, i, remaining, info_types_map=types) for i, ln in enumerate(probe)]
        if remaining:
            p2 = write_vcf(work / "probe_pert_after_widen.vcf", header, pert2)
            out2p = run_vcf_tool(argv, p2)
            classified = classify_pairs(pairs_o, align_by_key(pert2, body_lines(out2p)))
            still = _depends_fields(classified)
            if still:
                raise InferError(
                    "REFUSE_AMBIGUOUS",
                    f"still DEPENDS-ON-NON-KEY after widen {widen_history}: {still}",
                )
        else:
            classified = classify_pairs(pairs_o, pairs_o)
            classified = {
                "column_roles": {
                    n: ("produced" if r == "depends" else r)
                    for n, r in classified["column_roles"].items()
                },
                "info_roles": {
                    n: ("produced" if r == "depends" else r)
                    for n, r in classified["info_roles"].items()
                },
                "sample_role": "produced"
                if classified["sample_role"] == "depends"
                else classified["sample_role"],
                "info_order": classified["info_order"],
            }

    produced_order = [k for k in classified["info_order"] if classified["info_roles"].get(k) == "produced"]
    column_roles = {n: "key" for n in KEY_FIELDS}
    column_roles.update({n: r for n, r in classified["column_roles"].items() if r})
    for name in NAMED_NONKEY:
        column_roles.setdefault(name, "pass")
        if column_roles[name] in {"depends", "ambiguous"}:
            # Not widened: take the query value. Wrong here fails MATCH.
            column_roles[name] = "pass"

    return RecordContract(
        kind="vcf",
        argv=list(argv),
        cache_key_fields=key_fields,
        column_roles=column_roles,
        info_roles={k: v for k, v in classified["info_roles"].items() if v},
        produced_info_order=produced_order,
        sample_role=classified["sample_role"],
        widen_history=widen_history,
        probe_n=len(probe),
        decision="OK",
        reason="probe passed",
    )


def extract_produced(line: str, contract: RecordContract, query: str | None = None) -> dict:
    parts = split_record(line)
    out: dict = {"columns": {}, "info_items": []}
    for name, role in contract.column_roles.items():
        if role == "produced" and name != "INFO":
            val = col(parts, name)
            if val is not None:
                out["columns"][name] = val
    qmap = info_map(split_record(query)[COL_INFO]) if query and len(split_record(query)) > COL_INFO else {}
    if len(parts) > COL_INFO:
        for key, val in parse_info(parts[COL_INFO]):
            role = contract.info_roles.get(key)
            if role == "pass":
                continue
            if role == "produced":
                out["info_items"].append([key, val])
    return out


def reassemble_record(query: str, produced: dict, contract: RecordContract) -> str:
    parts = split_record(query)
    for name, role in contract.column_roles.items():
        if role == "produced" and name != "INFO" and name in produced.get("columns", {}):
            idx = {"ID": COL_ID, "QUAL": COL_QUAL, "FILTER": COL_FILTER}[name]
            while len(parts) <= idx:
                parts.append(".")
            parts[idx] = produced["columns"][name]
    if len(parts) > COL_INFO:
        extra_items = produced.get("info_items")
        if extra_items is None:
            extra_items = [[k, v] for k, v in produced.get("info", {}).items()]
        extra = {k: v for k, v in extra_items}
        produced_set = set(contract.produced_info_order) | set(extra)
        # Overwrite produced keys in the query's existing slots (fill-tags
        # rewrites AC/AF in place). Append produced keys the query lacks
        # in the order the probe saw them (SnpEff ANN/LOF/NMD).
        kept: list[tuple[str, str | None]] = []
        seen: set[str] = set()
        for key, val in parse_info(parts[COL_INFO]):
            if key in extra:
                kept.append((key, extra[key]))
                seen.add(key)
            elif key not in produced_set:
                kept.append((key, val))
        for key in contract.produced_info_order:
            if key not in seen and key in extra:
                kept.append((key, extra[key]))
                seen.add(key)
        for key, val in extra_items:
            if key not in seen:
                kept.append((key, val))
                seen.add(key)
        parts[COL_INFO] = format_info(kept)
    return "\t".join(parts)


def load_or_infer(
    argv: list[str],
    header: list[str],
    body: list[str],
    work: Path,
    contract_path: Path,
) -> RecordContract:
    if contract_path.is_file():
        saved = RecordContract.load(contract_path)
        if saved.argv == list(argv) and saved.kind == "vcf" and saved.decision == "OK":
            return saved
    contract = infer_contract(argv, header, body, work)
    contract.save(contract_path)
    return contract


def refuse_result(exc: InferError, argv: list[str]) -> RecordContract:
    return RecordContract(
        kind="vcf",
        argv=list(argv),
        cache_key_fields=list(KEY_FIELDS),
        column_roles={},
        info_roles={},
        produced_info_order=[],
        sample_role="pass",
        late_key_probes=[],
        decision=exc.decision,
        reason=exc.reason,
    )
