#!/usr/bin/env python3
"""Content-key kill test (docs/CONTENT_KEY_PROTOCOL.md): byte key vs inferred key.

Hashing only. Writes results/content_key_overlap.json.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.fasta import parse_fasta, seq_key  # noqa: E402
from acts.vcf import body_lines, variant_key  # noqa: E402

PROTOCOL = "pipeline/docs/CONTENT_KEY_PROTOCOL.md"
OUT = ROOT / "results" / "content_key_overlap.json"
DATA = ROOT / "data_contentkey"
NCBI = "https://ftp.ncbi.nlm.nih.gov/genomes/all"
MAX_BYTES = 1 << 30


def recall(new: set[str], seen: set[str]) -> float | None:
    return (len(new & seen) / len(new)) if new else None


def vcf_keys(path: Path) -> tuple[set[str], set[str]]:
    lines = body_lines(gzip.open(path, "rt").read())
    return {hashlib.sha256(ln.encode()).hexdigest() for ln in lines}, {variant_key(ln) for ln in lines}


def fasta_keys(text: str) -> tuple[set[str], set[str], int]:
    recs = parse_fasta(text)
    byte = set()
    for r in recs:
        header = f">{r.name} {r.description}".rstrip()
        byte.add(hashlib.sha256((header + "\n" + r.seq).encode()).hexdigest())
    return byte, {seq_key(r.seq) for r in recs}, len(recs)


def _curl(url: str) -> bytes:
    """System curl (system trust store; Python's bundle rejects the VPN's chain)."""
    return subprocess.run(
        ["curl", "-sSfL", "--max-time", "180", url], check=True, capture_output=True
    ).stdout


def ncbi_dir(acc: str) -> str:
    prefix, digits = acc.split("_")[0], acc.split("_")[1].split(".")[0]
    base = f"{NCBI}/{prefix}/{digits[0:3]}/{digits[3:6]}/{digits[6:9]}/"
    html = _curl(base).decode()
    names = sorted(set(re.findall(rf'href="({re.escape(acc)}_[^"/]+)/?"', html)))
    if not names:
        raise FileNotFoundError(f"no directory for {acc} under {base}")
    return base + names[0] + "/" + names[0]


def fetch_protein(acc: str, total: list[int]) -> Path | None:
    dest = DATA / f"{acc}_protein.faa.gz"
    if dest.is_file():
        return dest
    url = ncbi_dir(acc) + "_protein.faa.gz"
    try:
        blob = _curl(url)
    except subprocess.CalledProcessError:
        return None
    total[0] += len(blob)
    if total[0] > MAX_BYTES:
        raise SystemExit("download budget exceeded (1 GB); stop and ask")
    DATA.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)
    return dest


def collection_a_first10() -> list[dict]:
    curves = json.loads((ROOT / "results" / "recurrence_curves.json").read_text())
    acc = json.loads((ROOT / "results" / "recurrence_accessions.json").read_text())
    order = curves["collections"]["A"]["orderings"][0][:10]
    genomes = acc["collections"]["A"]["genomes"]
    summary = {}
    for line in (ROOT / "data" / "recurrence" / "assembly_summary_ecoli.txt").read_text().splitlines():
        if line.startswith("#"):
            continue
        cols = line.split("\t")
        summary[cols[0]] = {"gca": cols[17], "strain": cols[8]}
    out = []
    for idx in order:
        g = genomes[idx]
        gcf = g["accession"] if isinstance(g, dict) else g
        out.append({"index": idx, "gcf": gcf, "gca": summary.get(gcf, {}).get("gca", "na")})
    return out


def protein_curve(texts: list[tuple[str, str]]) -> list[dict]:
    seen_b: set[str] = set()
    seen_c: set[str] = set()
    rows = []
    for k, (acc, text) in enumerate(texts):
        b, c, n = fasta_keys(text)
        if k:
            rb, rc = recall(b, seen_b), recall(c, seen_c)
            rows.append({
                "k": k, "accession": acc, "n_records": n,
                "byte_recall": rb, "inferred_recall": rc,
                "ratio": (rb / rc) if rc else None,
            })
        seen_b |= b
        seen_c |= c
    return rows


def main() -> int:
    total = [0]
    started = datetime.now(timezone.utc).isoformat()

    v = {s: vcf_keys(ROOT / "data" / "vep_chr22" / f"{s}.c1.vcf.gz") for s in ("HG00096", "HG00097", "HG00099")}
    prev_b = v["HG00096"][0] | v["HG00097"][0]
    prev_c = v["HG00096"][1] | v["HG00097"][1]
    vb, vc = recall(v["HG00099"][0], prev_b), recall(v["HG00099"][1], prev_c)
    vcf = {"workload": "HG00096 ∪ HG00097 -> HG00099 (-c1)", "byte_recall": vb,
           "inferred_recall": vc, "ratio": vb / vc if vc else None}

    genomes = collection_a_first10()
    refseq, genbank, skipped = [], [], []
    for g in genomes:
        refseq.append((g["gcf"], gzip.open(ROOT / "data" / "recurrence" / "A" / f"{g['gcf']}_protein.faa.gz", "rt").read()))
        if not g["gca"].startswith("GCA_"):
            skipped.append({"gcf": g["gcf"], "why": "no paired GCA"})
            continue
        path = fetch_protein(g["gca"], total)
        if path is None:
            skipped.append({"gcf": g["gcf"], "gca": g["gca"], "why": "no GenBank protein.faa"})
            continue
        genbank.append((g["gca"], gzip.open(path, "rt").read()))

    gb_curve, rs_curve = protein_curve(genbank), protein_curve(refseq)
    last_gb = gb_curve[-1] if gb_curve else None
    kill = (
        vcf["ratio"] is not None and last_gb is not None and last_gb["ratio"] is not None
        and vcf["ratio"] >= 0.9 and last_gb["ratio"] >= 0.9
    )
    payload = {
        "protocol": PROTOCOL,
        "git": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
        "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "byte_key": "sha256 of whole record (VCF body line; FASTA header + sequence)",
        "inferred_key": "VCF variant_key (CHROM POS REF ALT); FASTA seq_key (MD5 of uppercase sequence, * stripped)",
        "vcf": vcf,
        "genbank_proteins": {"genomes": [a for a, _ in genbank], "curve": gb_curve},
        "refseq_proteins_control": {"genomes": [a for a, _ in refseq], "curve": rs_curve},
        "skipped": skipped,
        "downloaded_bytes": total[0],
        "kill_rule": "byte/inferred >= 0.9 on BOTH vcf and GenBank (last k)",
        "differentiator_killed": kill,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"vcf": vcf, "genbank_last": last_gb, "refseq_last": rs_curve[-1] if rs_curve else None,
                      "skipped": skipped, "killed": kill}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
