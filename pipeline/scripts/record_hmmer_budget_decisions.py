#!/usr/bin/env python3
"""Record the audit and random-pad samples for GCF_013315695.1.

The d125151 file is the locked picker. The new file is that picker after
the residue cap. On this proteome the cap does not bind, so the samples match.
These are the sampling decisions, not a full scan.
"""
from __future__ import annotations

import gzip
import hashlib
import random
import sys
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.audit import AUDIT_FLOOR, AUDIT_P, AUDIT_SEED, pick_audit, residue_cap_binds  # noqa: E402
from acts.exact_certificate import sample_keys  # noqa: E402
from acts.fasta import parse_fasta  # noqa: E402
from acts.reference_run import IC2_SAMPLE_SEED, IC2_SAMPLE_SIZE  # noqa: E402

PROTEOME = Path(
    "/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data/recurrence/A/GCF_013315695.1_protein.faa.gz"
)
OUT = PIPE / "results" / "exact_replay"


def fraction(recs, chosen: set[str]) -> float:
    total = sum(len(rec.seq) for rec in recs)
    got = sum(len(rec.seq) for rec in recs if rec.name in chosen)
    return got / total if total else 0.0


def decision(code: str, audit: list[str], random_keys: list[str], recs, lengths: list[int]) -> str:
    total = sum(lengths)
    lines = [
        "strategy: reference",
        "decision: SAMPLE",
        f"why:      {code}",
        f"proteome: GCF_013315695.1",
        f"n_records: {len(recs)}",
        f"residues: {total}",
        f"max_record_fraction: {max(lengths) / total:.6f}",
        "cap_fraction: 0.5",
        f"audit: checked {len(audit)}, residue fraction {fraction(recs, set(audit)):.6f}",
        "audit_keys:",
        *audit,
        (
            f"random_pads: 3 on {len(random_keys)} records, "
            f"residue fraction {fraction(recs, set(random_keys)):.6f}"
        ),
        "random_pad_records:",
        *random_keys,
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    recs = parse_fasta(gzip.open(PROTEOME, "rt").read())
    keys = [rec.name for rec in recs]
    lengths = [len(rec.seq) for rec in recs]
    if residue_cap_binds(lengths):
        raise SystemExit("cap bound; the proteome sample would change")
    audit = pick_audit(keys, p=AUDIT_P, floor=AUDIT_FLOOR, rng=random.Random(AUDIT_SEED))
    random_keys = sample_keys(keys, IC2_SAMPLE_SIZE, IC2_SAMPLE_SEED)
    # The new path is the cap, then the same picker. Both files are that result.
    old = decision("d125151 locked picker", audit, random_keys, recs, lengths)
    new = decision("residue budget, cap did not bind", audit, random_keys, recs, lengths)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hmmer_budget_d125151_decision.txt").write_text(old)
    (OUT / "hmmer_budget_new_decision.txt").write_text(new)
    digest = hashlib.sha256("\n".join(audit + random_keys).encode()).hexdigest()
    print(f"records {len(keys)} audit {len(audit)} random {len(random_keys)} sha256 {digest}")


if __name__ == "__main__":
    main()
