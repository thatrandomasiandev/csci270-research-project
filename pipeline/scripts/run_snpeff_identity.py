#!/usr/bin/env python3
"""Rung 0: SnpEff stock-vs-stock + shuffle. MATCH is the VCF body."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.vcf import bodies_equal, body_lines, shuffle_body

SNPEFF = ROOT / "tools" / "snpEff" / "snpEff.jar"
DATA = ROOT / "tools" / "snpEff" / "data"
INP = ROOT / "data" / "vep_chr22" / "HG00096.c1.head200.vcf"
OUTDIR = ROOT / "results" / "snpeff_identity"


def snpeff(vcf_text: str, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = dest.with_suffix(".in.vcf")
    src.write_text(vcf_text)
    cmd = [
        "java",
        "-Xmx4g",
        "-jar",
        str(SNPEFF),
        "-dataDir",
        str(DATA),
        "-noStats",
        "-noLog",
        "GRCh38.86",
        str(src),
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    dest.write_text(proc.stdout)
    dest.with_suffix(".err").write_text(proc.stderr)
    return proc.stdout


def main() -> int:
    if not SNPEFF.is_file() or not INP.is_file():
        print("INCOMPLETE: missing SnpEff jar or identity VCF", file=sys.stderr)
        return 2
    src = INP.read_text()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    a = snpeff(src, OUTDIR / "run1.vcf")
    b = snpeff(src, OUTDIR / "run2.vcf")
    shuffled = shuffle_body(src, seed=7)
    c = snpeff(shuffled, OUTDIR / "run_shuffled.vcf")
    report = {
        "tool": "SnpEff 5.4c GRCh38.86",
        "input": str(INP),
        "n_input_records": len(body_lines(src)),
        "n_out_run1": len(body_lines(a)),
        "full_file_identical": a == b,
        "body_identical": bodies_equal(a, b),
        "shuffle_body_identical": bodies_equal(a, c),
        "decision": None,
    }
    if not report["body_identical"]:
        report["decision"] = "REFUSE_IDENTITY"
        report["why"] = "stock-vs-stock body drifted"
    elif not report["shuffle_body_identical"]:
        report["decision"] = "REFUSE_IDENTITY"
        report["why"] = "annotation depends on neighbor order"
    else:
        report["decision"] = "IDENTITY_OK"
        report["why"] = (
            "body MATCH on two stock runs and on shuffled input; "
            + (
                "full-file cmp also identical"
                if report["full_file_identical"]
                else "full-file cmp differs (header only, expected)"
            )
        )
    (OUTDIR / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["decision"] == "IDENTITY_OK" else 1


if __name__ == "__main__":
    sys.exit(main())
