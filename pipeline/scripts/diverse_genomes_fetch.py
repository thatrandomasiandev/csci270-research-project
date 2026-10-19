#!/usr/bin/env python3
"""Download the locked diverse-genome proteomes and scan FASTA headers.

Reads pipeline/results/diverse_genomes/draw.json. Downloads only the
protein_url of each pilot and measured genome. Checks the on-disk size
against the recorded Content-Length. Does not run hmmscan.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
DRAW = PIPE / "results" / "diverse_genomes" / "draw.json"
OUT = PIPE / "results" / "diverse_genomes" / "proteome_download.json"
DEST = Path.home() / "tmp" / "tare_f" / "proteomes"
EXPECTED_TOTAL = 88_232_300
UA = "tare-exp-f/1.0 (academic)"


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def genomes(draw: dict) -> list[dict]:
    rows = list(draw["pilot"]) + list(draw["measured"])
    seen: set[str] = set()
    for row in rows:
        acc = row["accession"]
        if acc in seen:
            raise SystemExit(f"duplicate accession in the draw: {acc}")
        seen.add(acc)
        for key in ("accession", "group", "protein_url", "bytes"):
            if key not in row:
                raise SystemExit(f"{acc} is missing {key}")
    return rows


def download_one(row: dict) -> Path:
    dest = DEST / f"{row['accession']}_protein.faa.gz"
    expected = int(row["bytes"])
    if dest.is_file() and dest.stat().st_size == expected:
        log(f"keep {row['accession']} {expected} bytes")
        return dest
    if dest.exists():
        dest.unlink()
    tmp = dest.with_suffix(dest.suffix + ".partial")
    if tmp.exists():
        tmp.unlink()
    cmd = [
        "curl",
        "-L",
        "--fail",
        "--retry",
        "5",
        "--retry-delay",
        "2",
        "--retry-all-errors",
        "-A",
        UA,
        "-o",
        str(tmp),
        row["protein_url"],
    ]
    log(f"get {row['accession']}")
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        if tmp.exists():
            tmp.unlink()
        tail = (proc.stderr or proc.stdout or "")[-400:]
        raise SystemExit(f"download failed for {row['accession']}: {tail}")
    got = tmp.stat().st_size
    if got != expected:
        tmp.unlink()
        raise SystemExit(
            f"size mismatch {row['accession']}: got {got} bytes, draw records {expected}"
        )
    tmp.rename(dest)
    return dest


def scan_fasta(path: Path) -> dict:
    names: list[str] = []
    lengths: list[int] = []
    max_desc = 0
    max_desc_accession = ""
    seq_len = 0
    token = ""
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith(">"):
                if token:
                    names.append(token)
                    lengths.append(seq_len)
                header = line[1:].rstrip("\r\n")
                parts = header.split(None, 1)
                token = parts[0] if parts else ""
                desc = parts[1] if len(parts) > 1 else ""
                if len(desc) > max_desc:
                    max_desc = len(desc)
                    max_desc_accession = token
                seq_len = 0
            else:
                seq_len += len(line.strip())
        if token:
            names.append(token)
            lengths.append(seq_len)
    counts = Counter(names)
    duplicates = sorted(name for name, n in counts.items() if n > 1)
    total = sum(lengths)
    cap = any(2 * length > total for length in lengths) if total else False
    longest = max(lengths) if lengths else 0
    return {
        "fasta_records": len(names),
        "unique_names": len(counts),
        "duplicate_names": duplicates[:20],
        "duplicate_name_count": len(duplicates),
        "max_name_token_len": max((len(name) for name in names), default=0),
        "max_description_len": max_desc,
        "max_description_name": max_desc_accession,
        "residues": total,
        "max_protein_length": longest,
        "coordinate_overflow_possible": longest >= 100_000,
        "file_residue_cap_binds": cap,
    }


def main() -> int:
    draw = json.loads(DRAW.read_text())
    rows = genomes(draw)
    if len(rows) != 60:
        raise SystemExit(f"draw has {len(rows)} proteomes, expected 60")
    total = sum(int(row["bytes"]) for row in rows)
    if total != EXPECTED_TOTAL:
        raise SystemExit(f"draw total {total} != {EXPECTED_TOTAL}")
    if draw.get("total_bytes") not in (None, EXPECTED_TOTAL):
        raise SystemExit(f"draw total_bytes {draw.get('total_bytes')} != {EXPECTED_TOTAL}")
    DEST.mkdir(parents=True, exist_ok=True)
    files = []
    for row in rows:
        path = download_one(row)
        digest = md5_file(path)
        header = scan_fasta(path)
        files.append(
            {
                "accession": row["accession"],
                "group": row["group"],
                "role": row["role"],
                "organism": row.get("organism"),
                "protein_url": row["protein_url"],
                "bytes": int(row["bytes"]),
                "ncbi_protein_coding_gene_count": row.get("ncbi_protein_coding_gene_count"),
                "md5": digest,
                "path": str(path),
                **header,
            }
        )
        log(
            f"ok {row['accession']} records={header['fasta_records']} "
            f"name<={header['max_name_token_len']} residues={header['residues']}"
        )
    got = sum(item["bytes"] for item in files)
    if got != EXPECTED_TOTAL:
        raise SystemExit(f"downloaded {got} bytes, expected {EXPECTED_TOTAL}")
    names = [item["max_name_token_len"] for item in files]
    payload = {
        "kind": "proteome_download",
        "not_a_measured_hmmscan_result": True,
        "git_head": os.environ.get("ACTS_GIT_HEAD", ""),
        "host": os.uname().nodename,
        "argv": "python3 pipeline/scripts/diverse_genomes_fetch.py",
        "draw": "pipeline/results/diverse_genomes/draw.json",
        "n_files": len(files),
        "total_bytes": got,
        "dest": str(DEST),
        "max_name_token_len": max(names) if names else 0,
        "query_name_width_at_floor": all(n <= 20 for n in names),
        "file_residue_cap_accessions": [
            item["accession"] for item in files if item["file_residue_cap_binds"]
        ],
        "duplicate_name_accessions": [
            item["accession"] for item in files if item["duplicate_name_count"]
        ],
        "coordinate_overflow_accessions": [
            item["accession"] for item in files if item["coordinate_overflow_possible"]
        ],
        "files": files,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
