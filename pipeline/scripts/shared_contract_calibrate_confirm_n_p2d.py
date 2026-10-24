#!/usr/bin/env python3
"""Re-calibrate CONFIRM_N on FULL Pfam-A after the P2d verification fix.

Smallest n in CANDIDATES such that:
  (i) every available genome verifies its OWN contract (self-consistency,
      observed rows — not vacuous no_rows), using the production accept path
      (full-table verify_stored_fit, same as post-fix Layer C)
  (ii) poisoned store (identity plant) still fails
  (iii) hand-planted wrong member still fails

Uses P2c scratch genomes + full pressed Pfam. Evidence only.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.reference_fit import (  # noqa: E402
    PROBE_K,
    PROBE_SEED,
    partition_indices,
    sample_record_indices,
    verify_stored_fit,
)
from acts.reference_formats import parse_reference, read_records  # noqa: E402
from acts.reference_run import ReferenceIncremental, alias_map, _subset  # noqa: E402
import scripts.shared_contract_pilot_p2 as p2  # noqa: E402

P2C = Path(os.path.expanduser("~/tmp/tare_sharedcontract_p2c"))
SCRATCH = Path(os.path.expanduser("~/tmp/tare_sharedcontract_p2d/calib"))
OUT = PIPE / "results" / "shared_contract"
CANDIDATES = (10, 25, 50, 100, 150, 300)
SEED = PROBE_SEED


def poison_identity(fit: dict) -> dict:
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


def wrong_member(fit: dict) -> dict:
    """Plant entry_count on a per_key_row_count column (or identity on entry_count)."""
    out = json.loads(json.dumps(fit))
    for table in out.get("tables") or []:
        for col in table.get("columns") or []:
            if col.get("member") == "per_key_row_count":
                col["member"] = "entry_count"
                col["count_table"] = None
                return out
    for table in out.get("tables") or []:
        for col in table.get("columns") or []:
            if col.get("member") == "entry_count":
                col["member"] = "identity"
                col["count_table"] = None
                return out
    raise SystemExit("no wrong-member target")


def load_own_fit(acc: str) -> dict:
    db = P2C / "pilot" / acc / "b_cache.sqlite"
    if not db.is_file():
        raise SystemExit(f"missing own fit cache: {db}")
    con = sqlite3.connect(db)
    raw = con.execute("SELECT payload FROM contracts").fetchone()[0]
    con.close()
    return json.loads(raw)


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    hmm = P2C / "pfam" / "Pfam-A.hmm"
    if not hmm.is_file():
        raise SystemExit(f"full Pfam missing: {hmm}")
    genomes = sorted(
        {
            p.name.replace("_protein.faa", "")
            for p in (P2C / "genomes").glob("*_protein.faa")
        }
    )
    # Prefer the three P2c pilot genomes that have own contracts; then any extras.
    pilot = [
        "GCF_003018855.1",
        "GCF_004377995.2",
        "GCF_045689345.1",
    ]
    available = [a for a in pilot if (P2C / "pilot" / a / "b_cache.sqlite").is_file()]
    if len(available) < 2:
        raise SystemExit(f"need ≥2 own-fit genomes, have {available}")
    print(f"hmm={hmm} genomes={available}")

    print("parsing reference…")
    t0 = time.perf_counter()
    entries = parse_reference(hmm)
    print(f"  entries={len(entries)} parse_s={time.perf_counter()-t0:.1f}")
    aliases = alias_map(list(entries))
    lengths = [e.length for e in entries]
    parts = partition_indices(len(entries), PROBE_K, SEED)

    own_fits = {acc: load_own_fit(acc) for acc in available}
    records_by = {}
    for acc in available:
        faa = P2C / "genomes" / f"{acc}_protein.faa"
        records_by[acc] = read_records(faa)
        print(f"  {acc}: records={len(records_by[acc])}")

    # Build invokes once per genome (reuse across n).
    invokes = {}
    for acc in available:
        faa = P2C / "genomes" / f"{acc}_protein.faa"
        work = SCRATCH / "invoke" / acc
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        ri = ReferenceIncremental(
            argv=p2.hmmscan_argv("2"),
            input_path=faa,
            out_dir=work / "out",
            reference=hmm,
            cache_path=work / "cache.sqlite",
            verify="none",
            pin="-Z {entry_count}",
            prep=f"{p2.HMMPRESS} -f {{reference}}",
        )
        invokes[acc] = ri._invoke(hmm)

    # Cache whole+parts outputs per (acc, n).
    obs_cache: dict[tuple[str, int], tuple[dict, list]] = {}

    def observations(acc: str, n: int):
        key = (acc, n)
        if key in obs_cache:
            return obs_cache[key]
        records = records_by[acc]
        n_use = min(n, len(records))
        chosen = sample_record_indices(len(records), n_use, SEED)
        probe_records = [records[i] for i in chosen]
        invoke = invokes[acc]
        t1 = time.perf_counter()
        whole = invoke(probe_records, list(entries))
        part_tables = [
            invoke(probe_records, _subset(entries, indices)) for indices in parts
        ]
        wall = time.perf_counter() - t1
        obs_cache[key] = (whole, part_tables, wall, n_use)
        return obs_cache[key]

    results = []
    chosen = None
    for n in CANDIDATES:
        print(f"\n=== candidate n={n} ===")
        self_rows = []
        all_self_ok = True
        for acc in available:
            whole, part_tables, wall, n_use = observations(acc, n)
            ok, why = verify_stored_fit(
                own_fits[acc]["tables"],
                entries_n=len(entries),
                lengths=lengths,
                part_index_lists=parts,
                alias_to_index=aliases,
                whole_tables=whole,
                part_tables=part_tables,
            )
            # Also check Layer-C diagnose path with count_key_tables.
            per_ok = True
            for table in own_fits[acc]["tables"]:
                tok, tw = verify_stored_fit(
                    [table],
                    entries_n=len(entries),
                    lengths=lengths,
                    part_index_lists=parts,
                    alias_to_index=aliases,
                    whole_tables=whole,
                    part_tables=part_tables,
                    count_key_tables=own_fits[acc]["tables"],
                )
                if not tok:
                    per_ok = False
                    if ok:
                        why = tw
                    ok = False
            observed = ok and why != "no_rows"
            self_rows.append(
                {
                    "genome": acc,
                    "ok": ok,
                    "per_table_with_siblings_ok": per_ok,
                    "observed": observed,
                    "why": why,
                    "wall_s": wall,
                    "n_use": n_use,
                }
            )
            print(
                f"  self {acc}: ok={ok} per={per_ok} observed={observed} "
                f"wall={wall:.1f}s why={why!r}"
            )
            if not observed:
                all_self_ok = False

        # Controls on genome-0 fit vs genome-1 sample.
        g0, g1 = available[0], available[1]
        whole1, parts1, _, _ = observations(g1, n)
        poisoned = poison_identity(own_fits[g0])
        pok, pwhy = verify_stored_fit(
            poisoned["tables"],
            entries_n=len(entries),
            lengths=lengths,
            part_index_lists=parts,
            alias_to_index=aliases,
            whole_tables=whole1,
            part_tables=parts1,
        )
        wrong = wrong_member(own_fits[g0])
        wok, wwhy = verify_stored_fit(
            wrong["tables"],
            entries_n=len(entries),
            lengths=lengths,
            part_index_lists=parts,
            alias_to_index=aliases,
            whole_tables=whole1,
            part_tables=parts1,
        )
        poison_caught = not pok
        wrong_caught = not wok
        print(f"  poison on {g1}: caught={poison_caught} why={pwhy!r}")
        print(f"  wrong-member on {g1}: caught={wrong_caught} why={wwhy!r}")

        row = {
            "n": n,
            "self_all_ok": all_self_ok,
            "self": self_rows,
            "poison_caught": poison_caught,
            "poison_why": pwhy,
            "wrong_member_caught": wrong_caught,
            "wrong_member_why": wwhy,
            "eligible": all_self_ok and poison_caught and wrong_caught,
        }
        results.append(row)
        if chosen is None and row["eligible"]:
            chosen = n
            print(f"  → first eligible n={n}")
            break

    report = {
        "candidates": list(CANDIDATES),
        "chosen": chosen,
        "rule": (
            "smallest n with all-available-genome self-consistency on FULL Pfam "
            "(own contract, observed rows) AND poisoned-store fail AND "
            "wrong-member fail; production accept = full-table verify_stored_fit"
        ),
        "genomes": available,
        "reference": str(hmm),
        "seed": SEED,
        "results": results,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "p2d_confirm_n.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nCHOSEN CONFIRM_N={chosen}")
    print(f"wrote {out}")
    # Update constant only if calibration disagrees — caller decides.
    return 0 if chosen is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
