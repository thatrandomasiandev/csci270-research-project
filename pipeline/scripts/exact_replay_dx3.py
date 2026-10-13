#!/usr/bin/env python3
"""DX3 pilot for IC2. A pilot number is not a result.

The predicate and the seeds are the ones named in
results/reference_diamond/dx3_semantics.md. This file does not run the
measured arm.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.provenance import provenance  # noqa: E402
from acts.reference_formats import parse_reference  # noqa: E402
from acts.reference_formats import write_entries  # noqa: E402
from acts.reference_run import body_lines  # noqa: E402
from scripts.exact_replay_dx2 import (  # noqa: E402
    DIAMOND,
    EXPECTED_DIAMOND_MAC,
    NEW_FA,
    OUT_DIR,
    THREADS,
    blast,
    classify,
    file_id,
    hmmer_positive,
    read_records,
    write_json,
    write_queries,
)

DX2 = ROOT / "data" / "reference_diamond_dx2" / "measured"
WORK = ROOT / "data" / "reference_diamond_dx3" / "pilot"
PIN = ["--dbsize", "209017843"]
PAD_SEEDS = (20261025, 20261026, 20261027)
DROP_SEED = 20261024
RATE_SEED = 20261028
RATE_GENOME = ROOT / "data" / "recurrence" / "A" / "GCF_001513615.1_protein.faa.gz"
SUBJECT_COL = 1


def log(message: str) -> None:
    print(message, flush=True)


def difference_classes(klass: dict) -> list[str]:
    found = []
    if klass["same_hsp_different_value"]:
        found.append("value-only")
    if klass["different_hsp"]:
        found.append("different row")
    if klass["row_missing"]:
        found.append("missing")
    if klass["row_extra"]:
        found.append("extra")
    if klass["line_order_only"]:
        found.append("order")
    return found


def ic2_one(
    r_text: str,
    plus_text: str,
    u_ids: set[str],
    pad_ids: set[str],
    *,
    subject_col: int,
) -> dict:
    """Strict candidate multiset, and no pad subject. A test, not a proof."""

    def take(text: str, keep) -> list[str]:
        chosen = []
        for line in body_lines(text):
            cells = line.split()
            if subject_col < len(cells) and keep(cells[subject_col]):
                chosen.append(line)
        return chosen

    r_u = Counter(take(r_text, lambda subject: subject in u_ids))
    plus_u = Counter(take(plus_text, lambda subject: subject in u_ids))
    missing = sum(count - plus_u[line] for line, count in r_u.items() if count > plus_u[line])
    extra = sum(count - r_u[line] for line, count in plus_u.items() if count > r_u[line])
    pad_hits = len(take(plus_text, lambda subject: subject in pad_ids))
    other = len(
        take(plus_text, lambda subject: subject not in u_ids and subject not in pad_ids)
    )
    passed = missing == 0 and extra == 0 and pad_hits == 0 and other == 0
    mode = "pass"
    if not passed:
        if pad_hits:
            mode = "pad_hit"
        elif missing and extra:
            mode = "missing_and_extra_candidate"
        elif missing:
            mode = "missing_candidate"
        elif extra:
            mode = "extra_candidate"
        else:
            mode = "other_subject"
    klass = classify(r_text, plus_text)
    return {
        "pass": passed,
        "fail_mode": mode,
        "missing_candidate_rows": missing,
        "extra_candidate_rows": extra,
        "pad_hit_rows": pad_hits,
        "other_subject_rows": other,
        "difference_classes": difference_classes(klass),
        "classification": klass,
    }


def ic2_all(pads: list[dict]) -> dict:
    return {
        "pass": all(pad["pass"] for pad in pads),
        "pads_failed": [pad["name"] for pad in pads if not pad["pass"]],
        "pads": pads,
    }


def search(fasta: Path, query: Path, out: Path, extra: list[str] | None) -> dict:
    meta = blast(fasta, query, out, extra=extra)
    dmnd = Path(str(fasta) + ".dmnd")
    if "reference_diamond_dx3" in str(fasta) and dmnd.is_file():
        dmnd.unlink()
    return meta


def neighbor_indices(n_entries: int, u_idx: set[int]) -> list[int]:
    extra = set()
    for index in u_idx:
        if index > 0 and (index - 1) not in u_idx:
            extra.add(index - 1)
        if index + 1 < n_entries and (index + 1) not in u_idx:
            extra.add(index + 1)
    return sorted(extra)


def write_union(entries, u_idx: set[int], extra: list[int], dest: Path) -> None:
    merged = sorted(u_idx | set(extra))
    write_entries([entries[i] for i in merged], dest)


def random_pad(n_entries: int, u_idx: set[int], seed: int) -> list[int]:
    non = [i for i in range(n_entries) if i not in u_idx]
    width = max(200, len(u_idx))
    if width > len(non):
        raise RuntimeError(f"pad {width} larger than the non-candidate pool {len(non)}")
    return sorted(random.Random(seed).sample(non, width))


def near_miss_indices(entries, key_to_index: dict[str, int], u_ids: set[str], query: Path, dest: Path) -> list[int]:
    """Subjects hit at --min-score 1 and absent from U. Pilot probe, not a result."""
    out = dest.parent / f"{dest.name}.minscore1.m8"
    search(NEW_FA, query, out, ["--min-score", "1"])
    found = set()
    for line in body_lines(out.read_text()):
        subject = line.split()[SUBJECT_COL]
        if subject not in u_ids and subject in key_to_index:
            found.add(key_to_index[subject])
    return sorted(found)


def run_pads(
    entries,
    u_idx: set[int],
    u_ids: set[str],
    query: Path,
    r_text: str,
    tag: str,
    near_idx: list[int],
) -> tuple[list[dict], float]:
    work = WORK / tag
    work.mkdir(parents=True, exist_ok=True)
    n_entries = len(entries)
    specs: list[tuple[str, list[int]]] = [
        (f"random_{seed}", random_pad(n_entries, u_idx, seed)) for seed in PAD_SEEDS
    ]
    specs.append(("neighbor", neighbor_indices(n_entries, u_idx)))
    specs.append(("near_miss", near_idx))
    pads = []
    walls = 0.0
    for name, extra in specs:
        if not extra:
            pads.append({
                "name": name,
                "pass": False,
                "fail_mode": "empty_pad",
                "pad_entries": 0,
                "wall_s": 0.0,
                "difference_classes": [],
            })
            continue
        fasta = work / f"{name}.faa"
        write_union(entries, u_idx, extra, fasta)
        meta = search(fasta, query, work / f"{name}.m8", PIN)
        fasta.unlink(missing_ok=True)
        pad_ids = {entries[i].primary for i in extra}
        judge = ic2_one(
            r_text,
            (work / f"{name}.m8").read_text(),
            u_ids,
            pad_ids,
            subject_col=SUBJECT_COL,
        )
        judge["name"] = name
        judge["pad_entries"] = len(extra)
        judge["wall_s"] = meta["wall_s"]
        walls += meta["wall_s"]
        pads.append(judge)
        log(f"{tag} {name} pass={judge['pass']} mode={judge['fail_mode']} wall={meta['wall_s']:.3f}")
    return pads, walls


def hmm_names(path: Path) -> list[str]:
    names = []
    for line in path.read_text().splitlines():
        if line.startswith("NAME "):
            names.append(line.split(None, 1)[1].strip())
    return names


def hmmer_control() -> dict:
    work = WORK / "hmmer"
    work.mkdir(parents=True, exist_ok=True)
    source = ROOT / "data" / "reference_diamond_dx2" / "pilot" / "hmmer"
    for name in ("Pfam-A.hmm", "Pfam-A.hmm.h3f", "Pfam-A.hmm.h3i", "Pfam-A.hmm.h3m", "Pfam-A.hmm.h3p"):
        dest = work / name
        src = source / name
        if src.is_file() and not dest.exists():
            dest.symlink_to(src)
    report = hmmer_positive(work)
    u_names = set(hmm_names(work / "hmmer_U.hmm"))
    up_names = set(hmm_names(work / "hmmer_UP.hmm"))
    pad_ids = up_names - u_names
    tables = {}
    for ext, column in (("tbl", 0), ("dom", 0)):
        judge = ic2_one(
            (work / f"hmmer_R.{ext}").read_text(),
            (work / f"hmmer_Rplus.{ext}").read_text(),
            u_names,
            pad_ids,
            subject_col=column,
        )
        stock_lines = body_lines((work / f"hmmer_S.{ext}").read_text())
        replay_lines = body_lines((work / f"hmmer_R.{ext}").read_text())
        judge["body_equals_stock"] = stock_lines == replay_lines
        judge["needless_refusal"] = (not judge["pass"]) and judge["body_equals_stock"]
        tables[ext] = judge
    passed = all(table["pass"] and table["body_equals_stock"] for table in tables.values())
    needless = sum(1 for table in tables.values() if table["needless_refusal"])
    return {
        "label": "positive control, not a result",
        "hmmer_positive_pass": report["pass"],
        "ic2_pass": passed,
        "needless_refusals": needless,
        "tables": tables,
        "wall_stock_s": report["wall_stock_s"],
        "wall_R_s": report["wall_R_s"],
        "wall_Rplus_s": report["wall_Rplus_s"],
        "candidate_models": report["candidate_models"],
        "pad_models": report["pad_models"],
    }


def rate_sample(entries, key_to_index: dict[str, int]) -> dict:
    """Disjoint genome. Sizes the later measured draw. Not a safety result."""
    records = read_records(RATE_GENOME)
    width = min(300, len(records))
    draw = sorted(random.Random(RATE_SEED).sample(range(len(records)), width))
    query = WORK / "rate_q.faa"
    write_queries(records, draw, query)
    stock = search(NEW_FA, query, WORK / "rate_stock.m8", None)
    subjects = set()
    for line in body_lines((WORK / "rate_stock.m8").read_text()):
        subjects.add(line.split()[SUBJECT_COL])
    u_idx = {key_to_index[key] for key in subjects if key in key_to_index}
    fasta = WORK / "rate_U.faa"
    write_entries([entries[i] for i in sorted(u_idx)], fasta)
    replay = search(fasta, query, WORK / "rate_R.m8", PIN)
    fasta.unlink(missing_ok=True)
    klass = classify((WORK / "rate_stock.m8").read_text(), (WORK / "rate_R.m8").read_text())
    cases = (
        klass["row_missing"]
        + klass["row_extra"]
        + klass["different_hsp"]
        + klass["same_hsp_different_value"]
    )
    return {
        "label": "pilot rate, not a result",
        "genome": RATE_GENOME.name,
        "seed": RATE_SEED,
        "queries": width,
        "records_available": len(records),
        "stock_rows": klass["stock_rows"],
        "replay_rows": klass["other_rows"],
        "cases": cases,
        "cases_per_300": (cases / width) * 300 if width else None,
        "difference_classes": difference_classes(klass),
        "classification": klass,
        "wall_stock_s": stock["wall_s"],
        "wall_R_s": replay["wall_s"],
    }


def pilot() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    diamond = file_id(DIAMOND)
    if (diamond["bytes"], diamond["md5"]) != EXPECTED_DIAMOND_MAC:
        raise SystemExit(f"STOP diamond md5 {diamond['md5']}")
    if THREADS != "8":
        raise SystemExit("STOP threads")
    entries = parse_reference(NEW_FA)
    key_to_index = {entry.primary: index for index, entry in enumerate(entries)}
    from acts.fasta import parse_fasta

    u_ids = {record.name for record in parse_fasta((DX2 / "e1_U.faa").read_text())}
    unknown = sorted(u_ids - set(key_to_index))
    if unknown:
        raise SystemExit(f"STOP unmatched subjects {unknown[:5]}")
    u_idx = {key_to_index[key] for key in u_ids}
    query = DX2 / "e1_q.faa"
    r_text = (DX2 / "e1_R.m8").read_text()
    stock_text = (DX2 / "e1_stock.m8").read_text()
    known_class = classify(stock_text, r_text)
    if known_class["row_missing"] != 6 or known_class["shared_byte_identical"] != 31371:
        raise SystemExit("STOP known-bad replay is not the DX2 six-miss body")

    log("stock timing on the replay query file")
    stock = search(NEW_FA, query, WORK / "stock_e1q.m8", None)
    log("near-miss subjects")
    near_idx = near_miss_indices(entries, key_to_index, u_ids, query, WORK / "near")
    log(f"near-miss entries {len(near_idx)}")
    known_pads, known_walls = run_pads(entries, u_idx, u_ids, query, r_text, "known", near_idx)
    known = ic2_all(known_pads)

    log("injected negative")
    dropped = set(random.Random(DROP_SEED).sample(sorted(u_idx), max(1, len(u_idx) // 10)))
    kept = u_idx - dropped
    kept_ids = {entries[i].primary for i in kept}
    kept_fa = WORK / "negative_U.faa"
    write_entries([entries[i] for i in sorted(kept)], kept_fa)
    neg_r = search(kept_fa, query, WORK / "negative_R.m8", PIN)
    kept_fa.unlink(missing_ok=True)
    neg_text = (WORK / "negative_R.m8").read_text()
    neg_vs_stock = classify(stock_text, neg_text)
    neg_pads, neg_walls = run_pads(entries, kept, kept_ids, query, neg_text, "negative", near_idx)
    negative = ic2_all(neg_pads)
    negative["dropped_subjects"] = len(dropped)
    negative["drop_seed"] = DROP_SEED
    negative["body_vs_stock"] = neg_vs_stock
    negative["body_difference_classes"] = difference_classes(neg_vs_stock)
    negative["wall_R_s"] = neg_r["wall_s"]
    negative["wall_Rplus_sum_s"] = neg_walls

    log("HMMER positive control")
    hmmer = hmmer_control()
    log("rate sample")
    rate = rate_sample(entries, key_to_index)

    q = len(u_idx) / (len(entries) - len(u_idx))
    report = {
        "label": "PILOT",
        "not_a_result": True,
        "semantics": "pipeline/results/reference_diamond/dx3_semantics.md",
        "diamond": diamond,
        "threads": 8,
        "known_bad": {
            "must_fail": True,
            "ic2_pass": known["pass"],
            "failed_as_required": not known["pass"],
            "pads_failed": known["pads_failed"],
            "replay_vs_stock_classes": difference_classes(known_class),
            "classification_vs_stock": known_class,
            "wall_stock_s": stock["wall_s"],
            "wall_Rplus_sum_s": known_walls,
            "overhead_Rplus_over_stock": known_walls / stock["wall_s"] if stock["wall_s"] else None,
            "pads": known_pads,
            "q_one_neighbor": q,
            "random_miss_bound_k3": (1 - q) ** 3,
            "neighbor_entries": next(pad["pad_entries"] for pad in known_pads if pad["name"] == "neighbor"),
            "near_miss_entries": len(near_idx),
        },
        "injected_negative": negative,
        "hmmer_positive": hmmer,
        "rate": rate,
        "provenance": provenance(),
    }
    write_json(OUT_DIR / "dx3_pilot.json", report)
    log(f"wrote {OUT_DIR / 'dx3_pilot.json'}")
    log(
        "known_fail="
        + str(not known["pass"])
        + " negative_fail="
        + str(not negative["pass"])
        + " hmmer_pass="
        + str(hmmer["ic2_pass"])
        + " needless="
        + str(hmmer["needless_refusals"])
    )


if __name__ == "__main__":
    pilot()
