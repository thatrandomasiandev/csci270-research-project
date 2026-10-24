#!/usr/bin/env python3
"""Choose CONFIRM_N for stored-contract verification (P2b).

Smallest n in CANDIDATES such that:
  (i) self-consistency: each of 5 genomes verifies its OWN n=300 fit
  (ii) poisoned-store: a wrong member still fails verification
Evidence only — do not tune to a desired reuse rate.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.reference_fit import PROBE_K, PROBE_N, PROBE_SEED, partition_indices  # noqa: E402
from acts.reference_formats import parse_reference, read_records  # noqa: E402
from acts.reference_run import (  # noqa: E402
    ReferenceIncremental,
    confirm_stored_fit,
    probe_fit,
)

P2_SCRATCH = Path(os.path.expanduser("~/tmp/tare_sharedcontract_p2"))
SCRATCH = Path(os.path.expanduser("~/tmp/tare_sharedcontract_p2b"))
OUT = PIPE / "results" / "shared_contract"
HMMSCAN = shutil.which("hmmscan") or "/opt/homebrew/bin/hmmscan"
CANDIDATES = (10, 25, 50, 100, 150, 300)


def hmmscan_argv() -> list[str]:
    return [
        HMMSCAN,
        "--cut_ga",
        "--noali",
        "--cpu",
        "2",
        "--tblout",
        "{output:tbl}",
        "--domtblout",
        "{output:domtbl}",
        "{reference}",
        "{input}",
    ]


def setup_ri(faa: Path, hmm: Path, work: Path) -> tuple[ReferenceIncremental, list, list, object]:
    work.mkdir(parents=True, exist_ok=True)
    ri = ReferenceIncremental(
        argv=hmmscan_argv(),
        input_path=faa,
        out_dir=work,
        reference=hmm,
        cache_path=work / "cache.sqlite",
        verify="none",
        pin="-Z {entry_count}",
        prep="hmmpress -f {reference}",
    )
    entries = parse_reference(hmm)
    records = read_records(faa)
    ri._n_entries = len(entries)
    ri._entry_names = {key for entry in entries for key in entry.keys}
    invoke = ri._invoke(hmm)
    return ri, entries, records, invoke


def poison_member(fit: dict) -> dict:
    """Plant one wrong member on a numeric non-identity column."""
    out = json.loads(json.dumps(fit))
    for table in out.get("tables") or []:
        for col in table.get("columns") or []:
            if col.get("role") == "numeric" and col.get("member") not in (
                None,
                "identity",
                "byte",
            ):
                col["member"] = "identity"
                col["count_table"] = None
                return out
    raise SystemExit("no poisonable column")


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    man = json.loads((P2_SCRATCH / "manifest.json").read_text())
    hmm = Path(man["pfam_subset"]["path"])
    genomes = man["genomes"]

    # Load or compute n=300 fits (reuse diagnosis artifacts when present).
    fits: dict[str, dict] = {}
    for g in genomes:
        acc = g["accession"]
        cached = SCRATCH / "diag" / acc / "fit_n300.json"
        full = SCRATCH / "diag" / acc / "fit_n300_full.json"
        if full.is_file():
            fits[acc] = json.loads(full.read_text())
            continue
        # Diagnosis wrote shareable-only; re-probe once and cache full fit.
        print(f"probe n=300 for {acc}…")
        work = SCRATCH / "calib" / acc / "n300"
        if work.exists():
            shutil.rmtree(work)
        ri, entries, records, invoke = setup_ri(Path(g["path"]), hmm, work)
        fitted = probe_fit(
            entries,
            records,
            invoke,
            n_p=PROBE_N,
            k=PROBE_K,
            seed=PROBE_SEED,
            monotone=False,
        )
        fits[acc] = fitted.as_dict()
        work.mkdir(parents=True, exist_ok=True)
        (SCRATCH / "diag" / acc).mkdir(parents=True, exist_ok=True)
        (SCRATCH / "diag" / acc / "fit_n300_full.json").write_text(
            json.dumps(fits[acc], indent=2) + "\n"
        )

    results = []
    chosen = None
    for n in CANDIDATES:
        print(f"\n=== candidate n={n} ===")
        self_rows = []
        all_self_ok = True
        for g in genomes:
            acc = g["accession"]
            work = SCRATCH / "calib" / acc / f"verify_n{n}"
            if work.exists():
                shutil.rmtree(work)
            ri, entries, records, invoke = setup_ri(Path(g["path"]), hmm, work)
            t0 = time.perf_counter()
            ok, why = confirm_stored_fit(
                fits[acc],
                entries,
                records,
                invoke,
                n_p=n,
                seed=PROBE_SEED,
                k=PROBE_K,
                monotone=False,
            )
            wall = time.perf_counter() - t0
            # Vacuous no_rows is not a self-consistency pass: the control must
            # observe rows and accept the stored contract on them.
            observed = ok and why != "no_rows"
            self_rows.append(
                {
                    "genome": acc,
                    "ok": ok,
                    "observed": observed,
                    "why": why,
                    "wall_s": wall,
                }
            )
            print(
                f"  self {acc}: ok={ok} observed={observed} "
                f"wall={wall:.1f}s why={why!r}"
            )
            if not observed:
                all_self_ok = False

        # Poisoned control on genome 1's fit, verified on genome 2 sample.
        g1, g2 = genomes[0], genomes[1]
        poisoned = poison_member(fits[g1["accession"]])
        work = SCRATCH / "calib" / "poison" / f"n{n}"
        if work.exists():
            shutil.rmtree(work)
        ri, entries, records, invoke = setup_ri(Path(g2["path"]), hmm, work)
        pok, pwhy = confirm_stored_fit(
            poisoned,
            entries,
            records,
            invoke,
            n_p=n,
            seed=PROBE_SEED,
            k=PROBE_K,
            monotone=False,
        )
        poison_caught = not pok
        print(f"  poison on {g2['accession']}: caught={poison_caught} why={pwhy!r}")

        row = {
            "n": n,
            "self_all_ok": all_self_ok,
            "self": self_rows,
            "poison_caught": poison_caught,
            "poison_why": pwhy,
            "eligible": all_self_ok and poison_caught,
        }
        results.append(row)
        if chosen is None and row["eligible"]:
            chosen = n
            print(f"  → first eligible n={n}")
            # Stop: smallest eligible n is the answer; larger n are not needed.
            break

    report = {
        "candidates": list(CANDIDATES),
        "chosen": chosen,
        "rule": "smallest n with all-5 self-consistency AND poisoned-store fail",
        "results": results,
    }
    out = OUT / "p2b_confirm_n.json"
    OUT.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nCHOSEN CONFIRM_N={chosen}")
    print(f"wrote {out}")
    return 0 if chosen is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
