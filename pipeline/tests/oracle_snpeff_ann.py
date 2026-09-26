"""Oracle: the retired hand-built SnpEff ANN/LOF/NMD splicer.

Kept only to compare against the generic VCF contract. Not on the runtime path.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from acts.vcf import body_lines, is_header, variant_key

SNPEFF_KEYS = frozenset({"ANN", "LOF", "NMD"})
SNPEFF_JAR = Path(__file__).resolve().parents[1] / "tools" / "snpEff" / "snpEff.jar"
SNPEFF_DATA = Path(__file__).resolve().parents[1] / "tools" / "snpEff" / "data"


def snpeff_cmd(vcf_path: Path) -> list[str]:
    return [
        "java",
        "-Xmx4g",
        "-jar",
        str(SNPEFF_JAR),
        "-dataDir",
        str(SNPEFF_DATA),
        "-noStats",
        "-noLog",
        "GRCh38.86",
        str(vcf_path),
    ]


def run_snpeff(vcf_path: Path) -> tuple[str, str, float]:
    import time

    t0 = time.perf_counter()
    proc = subprocess.run(snpeff_cmd(vcf_path), check=True, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    return proc.stdout, proc.stderr, wall


def info_added(info: str) -> str:
    bits = []
    for part in info.split(";"):
        if not part:
            continue
        key = part.split("=", 1)[0]
        if key in SNPEFF_KEYS:
            bits.append(part)
    return ";".join(bits)


def strip_snpeff_info(info: str) -> str:
    bits = []
    for part in info.split(";"):
        if not part:
            continue
        key = part.split("=", 1)[0]
        if key not in SNPEFF_KEYS:
            bits.append(part)
    return ";".join(bits)


def apply_added(input_line: str, added: str) -> str:
    parts = input_line.split("\t")
    if len(parts) < 8:
        raise ValueError(f"short VCF record: {input_line[:80]!r}")
    base = strip_snpeff_info(parts[7])
    if added:
        parts[7] = f"{base};{added}" if base else added
    else:
        parts[7] = base
    return "\t".join(parts)


def added_by_key(snpeff_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in body_lines(snpeff_text):
        parts = ln.split("\t")
        out[variant_key(ln)] = info_added(parts[7])
    return out


def header_and_body(text: str) -> tuple[list[str], list[str]]:
    header = [ln for ln in text.splitlines() if is_header(ln)]
    return header, body_lines(text)
