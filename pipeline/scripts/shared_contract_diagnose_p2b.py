#!/usr/bin/env python3
"""PRIORITY 1 diagnosis for shared-contract confirm_fail (P2b).

Reuses the P2 laptop pilot Pfam subset + 5 proteomes. No behavior change to
confirmation beyond reading fit_signature_diffs. Seeds: 20261334 (proteomes),
20261335 (Pfam subset) — same as P2. Scratch: ~/tmp/tare_sharedcontract_p2b/.
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

from acts.contract_store import fit_signature_diffs, fit_signatures_match  # noqa: E402
from acts.reference_fit import PROBE_K, PROBE_N, PROBE_SEED, FitResult  # noqa: E402
from acts.reference_formats import parse_reference, read_records  # noqa: E402
from acts.reference_run import ReferenceIncremental, probe_fit  # noqa: E402

# Reuse P2 data layout when present.
P2_SCRATCH = Path(os.path.expanduser("~/tmp/tare_sharedcontract_p2"))
SCRATCH = Path(os.path.expanduser("~/tmp/tare_sharedcontract_p2b"))
OUT = PIPE / "results" / "shared_contract"
CPU = "2"
CONFIRM_N = 50
HMMSCAN = shutil.which("hmmscan") or "/opt/homebrew/bin/hmmscan"


def hmmscan_argv() -> list[str]:
    return [
        HMMSCAN,
        "--cut_ga",
        "--noali",
        "--cpu",
        CPU,
        "--tblout",
        "{output:tbl}",
        "--domtblout",
        "{output:domtbl}",
        "{reference}",
        "{input}",
    ]


def genome_manifest() -> list[dict]:
    man = json.loads((P2_SCRATCH / "manifest.json").read_text())
    return list(man["genomes"])


def pfam_path() -> Path:
    return Path(json.loads((P2_SCRATCH / "manifest.json").read_text())["pfam_subset"]["path"])


def shareable_cols(fit: dict) -> dict:
    """Drop layout/meta/tie_break noise; keep signature fields only."""
    tables = []
    for t in fit.get("tables") or []:
        tables.append(
            {
                "name": t.get("name"),
                "record_col": t.get("record_col"),
                "entry_col": t.get("entry_col"),
                "index_col": t.get("index_col"),
                "columns": [
                    {
                        "index": c.get("index"),
                        "role": c.get("role"),
                        "member": c.get("member"),
                        "count_table": c.get("count_table"),
                    }
                    for c in (t.get("columns") or [])
                ],
            }
        )
    return {
        "decision": fit.get("decision"),
        "exact_eligible": fit.get("exact_eligible"),
        "column_only_refusal": fit.get("column_only_refusal"),
        "tables": tables,
    }


def run_probe(faa: Path, hmm: Path, work: Path, n_p: int) -> tuple[FitResult, float]:
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
    reference = hmm
    entries = parse_reference(reference)
    records = read_records(faa)
    ri._n_entries = len(entries)
    ri._entry_names = {key for entry in entries for key in entry.keys}
    invoke = ri._invoke(reference)
    t0 = time.perf_counter()
    fitted = probe_fit(
        entries,
        records,
        invoke,
        n_p=n_p,
        k=PROBE_K,
        seed=PROBE_SEED,
        monotone=bool(ri.pin and ri.slack),
    )
    wall = time.perf_counter() - t0
    return fitted, wall


def exactness_affecting_diffs(diffs: list[dict]) -> list[dict]:
    """Fields that change replay: role, member, count_table, key cols, decision."""
    keep = {
        "role",
        "member",
        "count_table",
        "record_col",
        "entry_col",
        "index_col",
        "decision",
        "exact_eligible",
        "column_only_refusal",
        "column_present",
        "table_present",
        "table_count",
        "inferred_pin.template",
    }
    return [d for d in diffs if d["field"] in keep]


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    hmm = pfam_path()
    genomes = genome_manifest()
    print(f"hmm={hmm} genomes={len(genomes)} CONFIRM_N={CONFIRM_N} PROBE_N={PROBE_N}")

    fits_300: dict[str, dict] = {}
    fits_50: dict[str, dict] = {}
    walls: dict[str, dict] = {}
    rows: list[dict] = []

    for g in genomes:
        acc = g["accession"]
        faa = Path(g["path"])
        print(f"\n=== {acc} ===")
        work = SCRATCH / "diag" / acc
        if work.exists():
            shutil.rmtree(work)
        f300, w300 = run_probe(faa, hmm, work / "n300", PROBE_N)
        f50, w50 = run_probe(faa, hmm, work / "n50", CONFIRM_N)
        d300 = f300.as_dict()
        d50 = f50.as_dict()
        fits_300[acc] = d300
        fits_50[acc] = d50
        walls[acc] = {"n300_s": w300, "n50_s": w50}
        ok_self, why_self = fit_signatures_match(d300, d50)
        diffs_self = fit_signature_diffs(d300, d50)
        print(f"  n300={w300:.1f}s decision={d300['decision']}  n50={w50:.1f}s decision={d50['decision']}")
        print(f"  self n50 vs own n300: ok={ok_self} diffs={len(diffs_self)}")
        if diffs_self:
            for d in diffs_self[:8]:
                print(f"    {d}")
        (work / "fit_n300.json").write_text(json.dumps(shareable_cols(d300), indent=2) + "\n")
        (work / "fit_n50.json").write_text(json.dumps(shareable_cols(d50), indent=2) + "\n")

    g1 = genomes[0]["accession"]
    base = fits_300[g1]
    print(f"\n=== pairwise n300 vs {g1} ===")
    for g in genomes:
        acc = g["accession"]
        ok, why = fit_signatures_match(base, fits_300[acc])
        diffs = fit_signature_diffs(base, fits_300[acc])
        exact = exactness_affecting_diffs(diffs)
        self_ok, _ = fit_signatures_match(fits_300[acc], fits_50[acc])
        self_diffs = fit_signature_diffs(fits_300[acc], fits_50[acc])
        row = {
            "genome": acc,
            "n50_vs_own_n300_ok": self_ok,
            "n50_vs_own_n300_n_diffs": len(self_diffs),
            "n50_vs_own_n300_diffs": self_diffs,
            "n300_vs_genome1_ok": ok,
            "n300_vs_genome1_n_diffs": len(diffs),
            "n300_vs_genome1_diffs": diffs,
            "n300_vs_genome1_exactness_diffs": exact,
            "walls": walls[acc],
            "decision_n300": fits_300[acc].get("decision"),
            "decision_n50": fits_50[acc].get("decision"),
        }
        rows.append(row)
        print(
            f"  {acc}: self50ok={self_ok} ({len(self_diffs)} diffs)  "
            f"vs_g1_n300_ok={ok} ({len(exact)} exactness diffs / {len(diffs)} total)"
        )
        for d in exact[:10]:
            print(f"    EXACTNESS {d}")

    # Hypothesis verdict
    self_fail = [r for r in rows if not r["n50_vs_own_n300_ok"]]
    cross_exact = [r for r in rows[1:] if r["n300_vs_genome1_exactness_diffs"]]
    if self_fail and not cross_exact:
        verdict = (
            "CONFIRMED: n=50 confirmation disagrees with own n=300 on at least one "
            "genome, while full n=300 fits agree on exactness-affecting fields across "
            "genomes. The check compares a weaker inference to a stronger one."
        )
    elif self_fail and cross_exact:
        verdict = (
            "PARTIAL: self-consistency fails (sample-size artifact) AND full fits "
            "differ in exactness-affecting fields (genuine genome dependence). "
            "Verification must catch the latter."
        )
    elif not self_fail and cross_exact:
        verdict = (
            "REFUTED as sole cause: self-consistency passes, but full fits differ "
            "across genomes in exactness fields — real genome dependence."
        )
    else:
        verdict = (
            "REFUTED: self-consistency passes and full fits agree. "
            "confirm_fail must have another cause (investigate)."
        )

    report = {
        "seed_proteomes": 20261334,
        "seed_pfam": 20261335,
        "confirm_n": CONFIRM_N,
        "probe_n": PROBE_N,
        "probe_seed": PROBE_SEED,
        "genome1": g1,
        "rows": rows,
        "verdict": verdict,
        "hypothesis": (
            "Confirmation re-infers at n=50 and demands equality with stored n=300; "
            "weaker vs stronger inference is not a contradiction test."
        ),
    }
    out_path = OUT / "p2b_diagnosis.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nVERDICT: {verdict}")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
