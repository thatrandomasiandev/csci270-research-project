#!/usr/bin/env python3
"""Protein recurrence curves on locked RefSeq collections.

Implements pipeline/docs/RECURRENCE_PROTOCOL.md. Local MD5 only.
No tool runs, no speedup claims. Abort if planned downloads exceed 1 GiB.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROTOCOL = "pipeline/docs/RECURRENCE_PROTOCOL.md"
DATA = ROOT / "data" / "recurrence"
OUT_ACC = ROOT / "results" / "recurrence_accessions.json"
OUT_CURVES = ROOT / "results" / "recurrence_curves.json"
FIG_DIR = ROOT / "results" / "figures"

SEED = 20260926
N_ORDERS = 20
GATE = 1.0 / 3.0
MAX_BYTES = 1 << 30
UNKNOWN_LEN = 2 * 1024 * 1024
CURL_UA = "acts-recurrence/1.0 (academic; protein.faa.gz MD5 only)"

SUMMARY = {
    "ecoli": (
        "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/"
        "Escherichia_coli/assembly_summary.txt"
    ),
    "saureus": (
        "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/"
        "Staphylococcus_aureus/assembly_summary.txt"
    ),
}

EPPINGER_STRAINS = [
    "EC4115",
    "EC4045",
    "EC4042",
    "EC4113",
    "EC4076",
    "EC4084",
    "EC4127",
    "EC4191",
    "EC4205",
    "TW14359",
    "EC4206",
    "EC4196",
    "EC4401",
    "EC4486",
    "EC4192",
    "EC4009",
    "EC508",
    "EC869",
    "FRIK2000",
    "FRIK966",
    "EC536",
    "EDL933",
    "Sakai",
    "TW14588",
    "EC4501",
]

K12_RE = re.compile(r"(k-?12|mg1655|w3110|bw25113)", re.I)
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


@dataclass
class Assembly:
    accession: str
    organism: str
    strain: str
    isolate: str
    version_status: str
    assembly_level: str
    genome_rep: str
    asm_name: str
    ftp_path: str
    locked_name: str = ""

    @property
    def protein_url(self) -> str:
        ftp = self.ftp_path.replace("ftp://", "https://", 1).rstrip("/")
        base = ftp.rsplit("/", 1)[-1]
        return f"{ftp}/{base}_protein.faa.gz"

    @property
    def local_name(self) -> str:
        return f"{self.accession}_protein.faa.gz"


def seq_md5(seq: str) -> str | None:
    aa = "".join(ch for ch in seq.upper() if not ch.isspace() and ch != "*")
    if not aa:
        return None
    try:
        return hashlib.md5(aa.encode("ascii")).hexdigest()
    except UnicodeEncodeError:
        return None


def faa_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:
        chunks: list[str] = []
        for line in fh:
            if line.startswith(">"):
                if chunks:
                    digest = seq_md5("".join(chunks))
                    if digest:
                        keys.add(digest)
                    chunks = []
                continue
            chunks.append(line)
        if chunks:
            digest = seq_md5("".join(chunks))
            if digest:
                keys.add(digest)
    return keys


def file_md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def curl(args: list[str], dest: Path | None = None) -> None:
    cmd = [
        "curl",
        "-L",
        "--fail",
        "--retry",
        "5",
        "--retry-delay",
        "2",
        "-A",
        CURL_UA,
        *args,
    ]
    subprocess.run(cmd, check=True)


def fetch(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    print(f"fetch {url}", flush=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    curl(["-o", str(tmp), url])
    tmp.replace(dest)
    return dest


def head_length(url: str) -> tuple[bool, int]:
    """Return (exists, content_length). Unknown length -> UNKNOWN_LEN."""
    cmd = [
        "curl",
        "-sI",
        "-L",
        "--fail",
        "--retry",
        "3",
        "-A",
        CURL_UA,
        url,
    ]
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        return False, 0
    length: int | None = None
    for raw in proc.stdout.splitlines():
        if raw.lower().startswith("content-length:"):
            try:
                length = int(raw.split(":", 1)[1].strip())
            except ValueError:
                length = None
    if length is None or length <= 0:
        return True, UNKNOWN_LEN
    return True, length


def parse_summary(path: Path) -> list[Assembly]:
    rows: list[Assembly] = []
    with path.open() as fh:
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 20:
                continue
            infra = cols[8]
            strain = infra
            if strain.lower().startswith("strain="):
                strain = strain.split("=", 1)[1]
            rows.append(
                Assembly(
                    accession=cols[0],
                    organism=cols[7],
                    strain=strain.strip(),
                    isolate=cols[9].strip(),
                    version_status=cols[10],
                    assembly_level=cols[11],
                    genome_rep=cols[13],
                    asm_name=cols[15],
                    ftp_path=cols[19],
                )
            )
    return rows


def eligible(rows: list[Assembly], *, level: str = "Complete Genome") -> list[Assembly]:
    out = []
    for r in rows:
        if not r.accession.startswith("GCF_"):
            continue
        if r.version_status != "latest":
            continue
        if r.assembly_level != level:
            continue
        if r.genome_rep != "Full":
            continue
        if not r.ftp_path or r.ftp_path == "na":
            continue
        out.append(r)
    return out


def norm_strain(name: str) -> str:
    return " ".join(name.upper().split())


def is_k12(row: Assembly) -> bool:
    blob = " ".join([row.organism, row.strain, row.isolate])
    return bool(K12_RE.search(blob))


def one_per_strain(rows: list[Assembly]) -> list[Assembly]:
    by_strain: dict[str, Assembly] = {}
    unnamed: list[Assembly] = []
    for r in sorted(rows, key=lambda x: x.accession):
        key = norm_strain(r.strain)
        if not key:
            unnamed.append(r)
            continue
        if key not in by_strain:
            by_strain[key] = r
    return sorted(list(by_strain.values()) + unnamed, key=lambda x: x.accession)


def sample_n(rows: list[Assembly], n: int, seed: int) -> list[Assembly]:
    if len(rows) <= n:
        return list(rows)
    picked = random.Random(seed).sample(rows, n)
    return sorted(picked, key=lambda x: x.accession)


def tokens(text: str) -> set[str]:
    return {t.upper() for t in TOKEN_RE.findall(text)}


def name_matches(locked: str, row: Assembly) -> bool:
    needle = re.sub(r"[^A-Z0-9]", "", locked.upper())
    if not needle:
        return False
    for field in (row.strain, row.isolate, row.organism):
        if needle in tokens(field):
            return True
        if re.sub(r"[^A-Z0-9]", "", field.upper()) == needle:
            return True
    return False


def resolve_eppinger(all_rows: list[Assembly]) -> tuple[list[Assembly], list[str]]:
    complete = eligible(all_rows, level="Complete Genome")
    chrom = eligible(all_rows, level="Chromosome")
    found: list[Assembly] = []
    used: set[str] = set()
    dropped: list[str] = []
    for name in EPPINGER_STRAINS:
        hits = [r for r in complete if name_matches(name, r) and r.accession not in used]
        if not hits:
            hits = [r for r in chrom if name_matches(name, r) and r.accession not in used]
        if not hits:
            dropped.append(name)
            continue
        hits.sort(key=lambda x: x.accession)
        pick = hits[0]
        pick.locked_name = name
        used.add(pick.accession)
        found.append(pick)
    return found, dropped


def o157_fallback(all_rows: list[Assembly]) -> list[Assembly]:
    pool = [
        r
        for r in one_per_strain(eligible(all_rows))
        if "O157:H7" in r.organism
    ]
    for r in pool:
        r.locked_name = r.strain or r.accession
    return sample_n(pool, 40, SEED)


def snapshot_ks(k_max: int) -> list[int]:
    want = [1, 5, 10, 50, k_max]
    return [k for k in want if 1 <= k <= k_max]


def miss_curves(keysets: list[set[str]], n_orders: int = N_ORDERS) -> dict:
    k_genomes = len(keysets)
    k_max = k_genomes - 1
    if k_max < 1:
        raise ValueError("need at least 2 genomes")
    orders = []
    matrix = np.zeros((n_orders, k_max), dtype=float)
    for i in range(n_orders):
        perm = random.Random(SEED + i).sample(range(k_genomes), k_genomes)
        orders.append([int(x) for x in perm])
        seen: set[str] = set()
        for k in range(k_max):
            seen |= keysets[perm[k]]
            later = keysets[perm[k + 1]]
            if not later:
                matrix[i, k] = 1.0
            else:
                matrix[i, k] = 1.0 - (len(later & seen) / len(later))
    median = np.median(matrix, axis=0)
    p10 = np.percentile(matrix, 10, axis=0)
    p90 = np.percentile(matrix, 90, axis=0)
    crossing = None
    for k, val in enumerate(median, start=1):
        if float(val) < GATE:
            crossing = k
            break
    snaps = {}
    for k in snapshot_ks(k_max):
        snaps[str(k)] = float(median[k - 1])
    return {
        "n_orderings": n_orders,
        "order_seeds": [SEED + i for i in range(n_orders)],
        "orderings": orders,
        "k": list(range(1, k_max + 1)),
        "m_median": [float(x) for x in median],
        "m_p10": [float(x) for x in p10],
        "m_p90": [float(x) for x in p90],
        "crossing_k": crossing,
        "snapshot_median_m": snaps,
        "empty_later_flagged": bool(np.any(matrix == 1.0) and any(len(s) == 0 for s in keysets)),
    }


def reading(name: str, crossing: int | None, k_max: int) -> str:
    if name == "A":
        if crossing is None:
            return (
                "Collection A never reaches median m < 1/3 by k = "
                f"{k_max}: the diverse-species HMMER headline fails; "
                "only clonal or surveillance workloads remain eligible."
            )
        return (
            f"Collection A crosses median m < 1/3 at k = {crossing} "
            "prior genomes; a diverse E. coli workload can clear the "
            "HMMER m gate after that memory depth (no speedup claimed)."
        )
    if name == "B":
        if crossing is None:
            return (
                "Collection B never reaches median m < 1/3: outbreak / "
                "surveillance O157:H7 does not clear the HMMER m gate "
                "on this lineage."
            )
        return (
            f"Collection B crosses median m < 1/3 at k = {crossing}; "
            "the O157:H7 outbreak/surveillance workload can clear the "
            "HMMER m gate (no speedup claimed)."
        )
    if crossing is None:
        return (
            "Collection C never reaches median m < 1/3: S. aureus "
            "generality fails the HMMER m gate."
        )
    return (
        f"Collection C crosses median m < 1/3 at k = {crossing}; "
        "exact-sequence memory on S. aureus can clear the HMMER m "
        "gate (no speedup claimed)."
    )


def plot_curve(curves: dict, title: str, dest: Path) -> None:
    k = np.array(curves["k"], dtype=float)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.fill_between(k, curves["m_p10"], curves["m_p90"], color="#9bb8d3", alpha=0.45, label="10–90%")
    ax.plot(k, curves["m_median"], color="#1f4e79", lw=2.0, label="median m(k)")
    ax.axhline(GATE, color="#c0392b", ls="--", lw=1.4, label="1/3 HMMER gate")
    ax.set_xlabel("k  (prior genomes in a random order)")
    ax.set_ylabel("miss fraction m(k)")
    ax.set_title(title)
    ax.set_xlim(1, max(k) if len(k) else 1)
    ax.set_ylim(0, 1)
    ax.legend(frameon=False, loc="upper right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(dest, dpi=160)
    plt.close(fig)


def record_assembly(row: Assembly, path: Path, n_unique: int, planned_bytes: int) -> dict:
    return {
        "accession": row.accession,
        "locked_name": row.locked_name or None,
        "organism": row.organism,
        "strain": row.strain,
        "isolate": row.isolate,
        "assembly_level": row.assembly_level,
        "asm_name": row.asm_name,
        "ftp_path": row.ftp_path,
        "protein_url": row.protein_url,
        "path": str(path.relative_to(ROOT)) if path.exists() else None,
        "bytes": path.stat().st_size if path.exists() else planned_bytes,
        "file_md5": file_md5(path) if path.exists() else None,
        "n_unique": n_unique,
    }


def probe_urls(rows: list[Assembly]) -> tuple[list[Assembly], list[dict], int]:
    kept: list[Assembly] = []
    missing: list[dict] = []
    total = 0
    print(f"HEAD {len(rows)} protein URLs", flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(head_length, r.protein_url): r for r in rows}
        lengths: dict[str, tuple[bool, int]] = {}
        for fut in as_completed(futs):
            row = futs[fut]
            lengths[row.accession] = fut.result()
    for row in rows:
        ok, nbytes = lengths[row.accession]
        if not ok:
            missing.append({"accession": row.accession, "url": row.protein_url, "reason": "HEAD failed"})
            continue
        kept.append(row)
        total += nbytes
    return kept, missing, total


def download_rows(rows: list[Assembly], dest_dir: Path) -> dict[str, Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for row in rows:
        path = dest_dir / row.local_name
        fetch(row.protein_url, path)
        paths[row.accession] = path
    return paths


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    DATA.mkdir(parents=True, exist_ok=True)

    ecoli_path = fetch(SUMMARY["ecoli"], DATA / "assembly_summary_ecoli.txt")
    saur_path = fetch(SUMMARY["saureus"], DATA / "assembly_summary_saureus.txt")
    ecoli_rows = parse_summary(ecoli_path)
    saur_rows = parse_summary(saur_path)

    a_pool = one_per_strain([r for r in eligible(ecoli_rows) if not is_k12(r)])
    a_sel = sample_n(a_pool, 100, SEED)
    print(f"A pool={len(a_pool)} selected={len(a_sel)}", flush=True)

    b_sel, b_dropped = resolve_eppinger(ecoli_rows)
    b_resolved_n = len(b_sel)
    b_fallback = None
    print(f"B resolved={b_resolved_n} dropped={b_dropped}", flush=True)

    c_pool = one_per_strain(eligible(saur_rows))
    c_sel = sample_n(c_pool, 50, SEED)
    print(f"C pool={len(c_pool)} selected={len(c_sel)}", flush=True)

    a_ok, a_miss, a_bytes = probe_urls(a_sel)
    b_ok, b_miss, b_bytes = probe_urls(b_sel)
    if len(b_ok) < 20:
        b_fallback = "B1_O157H7_complete"
        b_sel = o157_fallback(ecoli_rows)
        print(f"B fallback {b_fallback}: {len(b_sel)}", flush=True)
        b_ok, b_miss, b_bytes = probe_urls(b_sel)
        if len(b_ok) < 20:
            print(
                f"STOP: collection B has only {len(b_ok)} RefSeq proteomes "
                "after B1. Do not invent a third collection.",
                file=sys.stderr,
            )
            return 2
    c_ok, c_miss, c_bytes = probe_urls(c_sel)

    planned = a_bytes + b_bytes + c_bytes
    print(
        f"planned bytes A={a_bytes} B={b_bytes} C={c_bytes} total={planned}",
        flush=True,
    )
    if planned > MAX_BYTES:
        print(
            f"STOP: planned download {planned} bytes exceeds 1 GiB. Ask Josh.",
            file=sys.stderr,
        )
        return 2

    collections = {
        "A": ("A_diverse_ecoli", a_ok, DATA / "A"),
        "B": ("B_o157h7_eppinger", b_ok, DATA / "B"),
        "C": ("C_saureus", c_ok, DATA / "C"),
    }

    accession_payload: dict = {
        "protocol": PROTOCOL,
        "started_utc": started,
        "seed": SEED,
        "key": "MD5 of uppercase AA, whitespace ignored, '*' stripped, headers ignored",
        "summaries": {
            "ecoli": {
                "url": SUMMARY["ecoli"],
                "path": str(ecoli_path.relative_to(ROOT)),
                "bytes": ecoli_path.stat().st_size,
                "md5": file_md5(ecoli_path),
                "mtime_utc": datetime.fromtimestamp(
                    ecoli_path.stat().st_mtime, timezone.utc
                ).isoformat(),
            },
            "saureus": {
                "url": SUMMARY["saureus"],
                "path": str(saur_path.relative_to(ROOT)),
                "bytes": saur_path.stat().st_size,
                "md5": file_md5(saur_path),
                "mtime_utc": datetime.fromtimestamp(
                    saur_path.stat().st_mtime, timezone.utc
                ).isoformat(),
            },
        },
        "selection": {
            "A": {
                "rule": "eligible Complete Genome E. coli, drop K-12 cluster, one per strain, sample 100 seed 20260926",
                "pool_unique_strain": len(a_pool),
                "selected": len(a_sel),
                "with_protein": len(a_ok),
                "head_failed": a_miss,
            },
            "B": {
                "rule": "Eppinger 2011 PNAS 25-strain list resolved to latest RefSeq",
                "paper": {
                    "citation": "Eppinger et al. 2011 Proc Natl Acad Sci USA 108:20142",
                    "doi": "10.1073/pnas.1107176108",
                },
                "locked_strains": EPPINGER_STRAINS,
                "resolved": b_resolved_n,
                "dropped_names": b_dropped,
                "fallback": b_fallback,
                "with_protein": len(b_ok),
                "head_failed": b_miss,
            },
            "C": {
                "rule": "eligible Complete Genome S. aureus, one per strain, sample 50 seed 20260926",
                "pool_unique_strain": len(c_pool),
                "selected": len(c_sel),
                "with_protein": len(c_ok),
                "head_failed": c_miss,
            },
        },
        "planned_bytes": planned,
        "collections": {},
    }

    curves_payload: dict = {
        "protocol": PROTOCOL,
        "started_utc": started,
        "gate": GATE,
        "gate_rule": "smallest k with median m(k) < 1/3; none => that collection fails the HMMER headline",
        "collections": {},
    }

    fig_map = {
        "A": (FIG_DIR / "12_recurrence_A_ecoli.png", "A  diverse E. coli  (no K-12)"),
        "B": (FIG_DIR / "13_recurrence_B_o157.png", "B  O157:H7  Eppinger 2011"),
        "C": (FIG_DIR / "14_recurrence_C_saureus.png", "C  Staphylococcus aureus"),
    }

    for label, (cid, rows, dest_dir) in collections.items():
        paths = download_rows(rows, dest_dir)
        keysets: list[set[str]] = []
        recs = []
        for row in rows:
            path = paths[row.accession]
            keys = faa_keys(path)
            keysets.append(keys)
            recs.append(record_assembly(row, path, len(keys), path.stat().st_size))
            print(f"{label} {row.accession} unique={len(keys)}", flush=True)
        curves = miss_curves(keysets)
        k_max = len(rows) - 1
        curves["K"] = len(rows)
        curves["reading"] = reading(label, curves["crossing_k"], k_max)
        accession_payload["collections"][label] = {
            "id": cid,
            "genomes": recs,
        }
        curves_payload["collections"][label] = {
            "id": cid,
            **curves,
        }
        fig_path, title = fig_map[label]
        plot_curve(curves, title, fig_path)
        curves_payload["collections"][label]["figure"] = str(fig_path.relative_to(ROOT))
        print(
            f"{label} K={len(rows)} crossing={curves['crossing_k']} "
            f"snaps={curves['snapshot_median_m']}",
            flush=True,
        )

    finished = datetime.now(timezone.utc).isoformat()
    accession_payload["finished_utc"] = finished
    curves_payload["finished_utc"] = finished
    OUT_ACC.parent.mkdir(parents=True, exist_ok=True)
    OUT_ACC.write_text(json.dumps(accession_payload, indent=2) + "\n")
    OUT_CURVES.write_text(json.dumps(curves_payload, indent=2) + "\n")
    print(f"wrote {OUT_ACC.relative_to(ROOT)}", flush=True)
    print(f"wrote {OUT_CURVES.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
