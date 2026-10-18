#!/usr/bin/env python3
"""Draw the TARE diverse-genome set from NCBI assembly summaries.

Does not download proteomes. Seeds, all in the experiment-F block:

- 20261151 pilot (one archaeon, one eukaryote, one MAG)
- 20261152 measured (archaea, bacteria, extra eukaryotes, MAGs)
- 20261153 reserved for the injected 5% drop; not used here
- 20261154 prefix scan of MAG protein-header samples

Each measured piece builds its own random.Random(20261152). A failed
eligibility tier does not advance the stream of the tier that is kept.
Phylum order is shuffled with that seed. Alphabetical order would keep
only the first names.

Proteobacteria and Pseudomonadota are one phylum for the cap and for
the phylum count. The reported phylum string stays NCBI's.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import zlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

PILOT_SEED = 20261151
MEASURED_SEED = 20261152
DROP_SEED = 20261153
PREFIX_SEED = 20261154
PROTEO = frozenset({"Proteobacteria", "Pseudomonadota"})
DESIGNATED_SPECIES = (
    "Homo sapiens",
    "Drosophila melanogaster",
    "Saccharomyces cerevisiae",
)

# Already used or pre-registered. Source: EXACT_REPLAY_PROTOCOL.md.
EXCLUDED = frozenset(
    {
        "GCF_002853805.1",
        "GCF_002090355.1",
        "GCF_001650275.1",
        "GCF_052050745.1",
        "GCF_016659085.1",
        "GCF_041316645.1",
        "GCF_013201215.1",
        "GCF_054510725.1",
        "GCF_002058765.1",
        "GCF_003956185.1",
        "GCF_025254305.1",
        "GCF_041235215.1",
        "GCF_016904475.1",
        "GCF_015571655.1",
        "GCF_005389605.2",
        "GCF_030515405.1",
        "GCF_002180275.1",
        "GCF_020905655.1",
        "GCF_048568975.1",
        "GCF_053102875.1",
        "GCF_013343615.1",
        "GCF_049949635.1",
        "GCF_052882435.1",
        "GCF_036884535.1",
        "GCF_012934475.1",
        "GCF_013315695.1",
        "GCF_004377995.2",
        "GCF_046107165.1",
        "GCF_022846215.1",
        "GCF_024298565.1",
        "GCF_049201905.1",
        "GCF_059719525.1",
        "GCF_016806025.1",
        "GCF_017165095.1",
        "GCF_001515725.1",
        "GCF_001513615.1",
        "GCF_013085185.1",
        "GCF_023657995.1",
        "GCF_030717825.1",
        "GCF_013168095.1",
        "GCF_028743355.1",
        "GCF_030708175.1",
        "GCF_037287675.1",
        "GCF_055382035.1",
        "GCF_059615465.1",
        "GCF_058683675.1",
        "GCF_003722195.1",
        "GCF_017654165.1",
        "GCF_032384295.1",
        "GCF_059131955.1",
        "GCF_002302335.1",
        "GCF_009433135.1",
        "GCF_009948655.1",
        "GCF_015290725.1",
        "GCF_022559285.1",
        "GCF_030347155.1",
        "GCF_049949335.1",
        "GCF_054388855.1",
        "GCF_055556535.1",
        "GCF_061234675.1",
    }
)

SUMMARY_URLS = {
    "archaea": "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/archaea/assembly_summary.txt",
    "bacteria": "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/assembly_summary.txt",
    "fungi": "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/fungi/assembly_summary.txt",
    "vertebrate_mammalian": "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/vertebrate_mammalian/assembly_summary.txt",
    "vertebrate_other": "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/vertebrate_other/assembly_summary.txt",
    "invertebrate": "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/invertebrate/assembly_summary.txt",
    "protozoa": "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/protozoa/assembly_summary.txt",
    "plant": "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/plant/assembly_summary.txt",
    "genbank_archaea": "https://ftp.ncbi.nlm.nih.gov/genomes/genbank/archaea/assembly_summary.txt",
    "genbank_bacteria_mags": "https://ftp.ncbi.nlm.nih.gov/genomes/genbank/bacteria/assembly_summary.txt",
}


@dataclass
class Row:
    accession: str
    category: str
    taxid: str
    species_taxid: str
    organism: str
    version_status: str
    level: str
    genome_rep: str
    asm_name: str
    ftp_path: str
    excluded_from_refseq: str
    ncbi_group: str
    proteins: int
    contigs: int
    phylum: str
    source: str

    @property
    def protein_url(self) -> str:
        ftp = self.ftp_path.replace("ftp://", "https://", 1).rstrip("/")
        base = ftp.rsplit("/", 1)[-1]
        return f"{ftp}/{base}_protein.faa.gz"


def diversity_phylum(name: str) -> str:
    if name in PROTEO:
        return "Proteobacteria"
    return name or "unplaced"


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_phyla(path: Path) -> dict[str, str]:
    phyla: dict[str, str] = {}
    with path.open() as handle:
        for line in handle:
            cells = [cell.strip() for cell in line.split("|")]
            if len(cells) < 8 or not cells[0]:
                continue
            phyla[cells[0]] = cells[7]
    return phyla


def parse_summary(path: Path, source: str, phyla: dict[str, str]) -> list[Row]:
    rows: list[Row] = []
    header: list[str] | None = None
    with path.open() as handle:
        for line in handle:
            if line.startswith("#"):
                if "assembly_accession" in line and header is None:
                    header = line.lstrip("#").strip().split("\t")
                continue
            if header is None:
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) < len(header):
                continue
            rec = dict(zip(header, cols))
            try:
                proteins = int(rec.get("protein_coding_gene_count") or "0")
            except ValueError:
                proteins = 0
            try:
                contigs = int(rec.get("contig_count") or "0")
            except ValueError:
                contigs = 0
            species = rec.get("species_taxid", "")
            taxid = rec.get("taxid", "")
            rows.append(
                Row(
                    accession=rec.get("assembly_accession", ""),
                    category=rec.get("refseq_category", ""),
                    taxid=taxid,
                    species_taxid=species,
                    organism=rec.get("organism_name", ""),
                    version_status=rec.get("version_status", ""),
                    level=rec.get("assembly_level", ""),
                    genome_rep=rec.get("genome_rep", ""),
                    asm_name=rec.get("asm_name", ""),
                    ftp_path=rec.get("ftp_path", ""),
                    excluded_from_refseq=rec.get("excluded_from_refseq", ""),
                    ncbi_group=rec.get("group", ""),
                    proteins=proteins,
                    contigs=contigs,
                    phylum=phyla.get(species) or phyla.get(taxid) or "",
                    source=source,
                )
            )
    if header is None:
        raise SystemExit(f"no header in {path}")
    return rows


def species_rank(row: Row) -> tuple:
    category = {"reference genome": 0, "representative genome": 1}.get(row.category, 2)
    level = 0 if row.level == "Complete Genome" else 1 if row.level == "Chromosome" else 2
    return (category, level, -row.proteins, row.accession)


def one_per_species(rows: list[Row], *, keep_unnamed: bool) -> list[Row]:
    best: dict[str, Row] = {}
    loose: list[Row] = []
    for row in rows:
        blob = row.organism.lower()
        if keep_unnamed and ("uncultured" in blob or "metagenome" in blob):
            loose.append(row)
            continue
        current = best.get(row.species_taxid)
        if current is None or species_rank(row) < species_rank(current):
            best[row.species_taxid] = row
    return list(best.values()) + loose


def refseq_base(row: Row) -> bool:
    return (
        row.accession.startswith("GCF_")
        and row.accession not in EXCLUDED
        and row.version_status == "latest"
        and row.genome_rep == "Full"
        and bool(row.ftp_path)
        and row.ftp_path != "na"
        and row.proteins > 0
        and bool(row.phylum)
    )


def tier_rows(rows: list[Row], tier: int) -> list[Row]:
    kept: list[Row] = []
    for row in rows:
        if not refseq_base(row):
            continue
        if tier in (1, 2) and row.category not in ("reference genome", "representative genome"):
            continue
        if tier == 1 and row.level != "Complete Genome":
            continue
        if tier == 2 and row.level not in ("Complete Genome", "Chromosome"):
            continue
        if tier == 3 and row.level != "Complete Genome":
            continue
        kept.append(row)
    return one_per_species(kept, keep_unnamed=False)


def round_robin(rows: list[Row], n: int, seed: int, *, proteo_cap: int | None) -> list[Row]:
    rng = random.Random(seed)
    decks: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        decks[diversity_phylum(row.phylum)].append(row)
    names = sorted(decks)
    rng.shuffle(names)
    ordered = {}
    for name in names:
        deck = sorted(decks[name], key=lambda row: row.accession)
        rng.shuffle(deck)
        ordered[name] = deck
    picked: list[Row] = []
    counts: dict[str, int] = defaultdict(int)
    while len(picked) < n:
        progress = False
        for name in names:
            if len(picked) >= n:
                break
            if proteo_cap is not None and name == "Proteobacteria" and counts[name] >= proteo_cap:
                continue
            deck = ordered[name]
            if not deck:
                continue
            picked.append(deck.pop())
            counts[name] += 1
            progress = True
        if not progress:
            break
    return sorted(picked, key=lambda row: row.accession)


def choose_tier(
    rows: list[Row],
    n: int,
    seed: int,
    *,
    min_phyla: int,
    proteo_cap: int | None,
    blocked: set[str],
) -> tuple[int, list[Row]]:
    last = (0, [])
    for tier in (1, 2, 3):
        pool = [row for row in tier_rows(rows, tier) if row.accession not in blocked]
        picked = round_robin(pool, n, seed, proteo_cap=proteo_cap)
        last = (tier, picked)
        n_phyla = len({diversity_phylum(row.phylum) for row in picked})
        if len(picked) >= n and n_phyla >= min_phyla:
            return tier, picked
    return last


def eukaryote_pool(rows: list[Row], blocked_species: set[str], blocked_acc: set[str]) -> list[Row]:
    kept: list[Row] = []
    for row in rows:
        if not refseq_base(row):
            continue
        if row.category not in ("reference genome", "representative genome"):
            continue
        if row.level not in ("Complete Genome", "Chromosome"):
            continue
        if row.species_taxid in blocked_species or row.accession in blocked_acc:
            continue
        if any(row.organism == name or row.organism.startswith(name + " ") for name in DESIGNATED_SPECIES):
            continue
        kept.append(row)
    return one_per_species(kept, keep_unnamed=False)


def mag_pool(rows: list[Row], blocked: set[str]) -> list[Row]:
    kept: list[Row] = []
    for row in rows:
        if not row.accession.startswith("GCA_"):
            continue
        if row.accession in blocked or row.accession in EXCLUDED:
            continue
        if row.version_status != "latest":
            continue
        if row.level not in ("Contig", "Scaffold"):
            continue
        if not row.ftp_path or row.ftp_path == "na":
            continue
        if "metagenome" not in row.excluded_from_refseq.lower():
            continue
        if row.proteins <= 0:
            continue
        kept.append(row)
    return one_per_species(kept, keep_unnamed=True)


def pick_designated(rows: list[Row], species: str) -> Row:
    hits = [
        row
        for row in rows
        if row.accession.startswith("GCF_")
        and row.accession not in EXCLUDED
        and row.version_status == "latest"
        and row.genome_rep == "Full"
        and row.ftp_path
        and row.ftp_path != "na"
        and row.proteins > 0
        and (row.organism == species or row.organism.startswith(species + " "))
    ]
    exact = [row for row in hits if row.organism == species]
    chosen_from = exact or hits
    if not chosen_from:
        raise SystemExit(f"no RefSeq row for {species}")
    return min(chosen_from, key=species_rank)


def sample_one(rows: list[Row], rng: random.Random) -> Row:
    return rng.sample(sorted(rows, key=lambda row: row.accession), 1)[0]


def tag(row: Row, *, group: str, role: str, how: str) -> dict:
    return {
        "accession": row.accession,
        "group": group,
        "role": role,
        "how": how,
        "organism": row.organism,
        "phylum": row.phylum,
        "diversity_phylum": diversity_phylum(row.phylum),
        "ncbi_group": row.ncbi_group,
        "assembly_level": row.level,
        "refseq_category": row.category,
        "species_taxid": row.species_taxid,
        "taxid": row.taxid,
        "ncbi_protein_coding_gene_count": row.proteins,
        "contig_count": row.contigs,
        "asm_name": row.asm_name,
        "excluded_from_refseq": row.excluded_from_refseq,
        "ftp_path": row.ftp_path,
        "protein_url": row.protein_url,
        "source_summary": row.source,
    }


def phylum_tally(items: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[item["phylum"] or "unplaced"] += 1
    return dict(sorted(counts.items()))


def draw(summary_dir: Path, ranked: Path) -> dict:
    phyla = load_phyla(ranked)
    files = {
        "archaea": summary_dir / "archaea.txt",
        "bacteria": summary_dir / "bacteria.txt",
        "fungi": summary_dir / "fungi.txt",
        "vertebrate_mammalian": summary_dir / "vertebrate_mammalian.txt",
        "vertebrate_other": summary_dir / "vertebrate_other.txt",
        "invertebrate": summary_dir / "invertebrate.txt",
        "protozoa": summary_dir / "protozoa.txt",
        "plant": summary_dir / "plant.txt",
        "genbank_archaea": summary_dir / "genbank_archaea.txt",
        "genbank_bacteria_mags": summary_dir / "genbank_bacteria_mags.tsv",
    }
    for path in files.values():
        if not path.is_file():
            raise SystemExit(f"missing summary {path}")
    parsed = {name: parse_summary(path, name, phyla) for name, path in files.items()}
    euk_rows = [
        row
        for name in (
            "fungi",
            "vertebrate_mammalian",
            "vertebrate_other",
            "invertebrate",
            "protozoa",
            "plant",
        )
        for row in parsed[name]
    ]
    designated_rows = [pick_designated(euk_rows, species) for species in DESIGNATED_SPECIES]
    designated_species_ids = {row.species_taxid for row in designated_rows}
    designated_acc = {row.accession for row in designated_rows}
    mag_rows = parsed["genbank_bacteria_mags"] + [
        row for row in parsed["genbank_archaea"] if "metagenome" in row.excluded_from_refseq.lower()
    ]

    pilot_rng = random.Random(PILOT_SEED)
    archaea_tier1 = [row for row in tier_rows(parsed["archaea"], 1) if row.accession not in designated_acc]
    euk_for_pilot = eukaryote_pool(euk_rows, designated_species_ids, designated_acc)
    mags_for_pilot = mag_pool(mag_rows, designated_acc)
    if not archaea_tier1 or not euk_for_pilot or not mags_for_pilot:
        raise SystemExit("a pilot pool is empty")
    pilot_arch = sample_one(archaea_tier1, pilot_rng)
    pilot_euk = sample_one(euk_for_pilot, pilot_rng)
    pilot_mag = sample_one(mags_for_pilot, pilot_rng)
    blocked = designated_acc | {pilot_arch.accession, pilot_euk.accession, pilot_mag.accession}

    arch_tier, measured_arch = choose_tier(
        parsed["archaea"], 15, MEASURED_SEED, min_phyla=3, proteo_cap=None, blocked=blocked
    )
    bac_tier, measured_bac = choose_tier(
        parsed["bacteria"], 30, MEASURED_SEED, min_phyla=10, proteo_cap=6, blocked=blocked
    )
    if len(measured_arch) < 15 or len({diversity_phylum(row.phylum) for row in measured_arch}) < 3:
        raise SystemExit(f"archaea draw short: tier {arch_tier} n={len(measured_arch)}")
    bac_phyla = {diversity_phylum(row.phylum) for row in measured_bac}
    bac_proteo = sum(1 for row in measured_bac if diversity_phylum(row.phylum) == "Proteobacteria")
    if len(measured_bac) < 30 or len(bac_phyla) < 10 or bac_proteo > 6:
        raise SystemExit(
            f"bacteria draw failed: tier {bac_tier} n={len(measured_bac)} phyla={len(bac_phyla)} proteo={bac_proteo}"
        )

    measured_rng = random.Random(MEASURED_SEED)
    euk_measured_pool = [
        row
        for row in eukaryote_pool(euk_rows, designated_species_ids, blocked)
        if row.accession not in blocked
    ]
    mag_measured_pool = [row for row in mag_pool(mag_rows, blocked) if row.accession not in blocked]
    if len(euk_measured_pool) < 2 or len(mag_measured_pool) < 5:
        raise SystemExit("measured eukaryote or MAG pool is smaller than the quota")
    extra_euk = measured_rng.sample(sorted(euk_measured_pool, key=lambda row: row.accession), 2)
    measured_mags = round_robin(mag_measured_pool, 5, MEASURED_SEED, proteo_cap=None)
    if len(measured_mags) < 5:
        raise SystemExit(f"MAG draw short: {len(measured_mags)}")

    pilot = [
        tag(pilot_arch, group="archaea", role="pilot", how="sample"),
        tag(pilot_euk, group="eukaryote", role="pilot", how="sample"),
        tag(pilot_mag, group="mag", role="pilot", how="sample"),
    ]
    measured = (
        [tag(row, group="archaea", role="measured", how="stratified") for row in measured_arch]
        + [tag(row, group="bacteria", role="measured", how="stratified") for row in measured_bac]
        + [tag(row, group="eukaryote", role="measured", how="designated") for row in designated_rows]
        + [
            tag(row, group="eukaryote", role="measured", how="sample")
            for row in sorted(extra_euk, key=lambda row: row.accession)
        ]
        + [tag(row, group="mag", role="measured", how="stratified") for row in measured_mags]
    )
    accessions = [item["accession"] for item in pilot + measured]
    if len(accessions) != len(set(accessions)):
        raise SystemExit("duplicate accession in the draw")
    return {
        "kind": "draw",
        "not_a_measured_result": True,
        "starting_commit": "507c45fcd2eb3c3e7850791cb2daf5e84400ffab",
        "seeds": {
            "pilot": PILOT_SEED,
            "measured": MEASURED_SEED,
            "injected_drop_reserved": DROP_SEED,
            "prefix_scan": PREFIX_SEED,
        },
        "rules": {
            "archaea": "15 reference or representative complete genomes, one per species, at least 3 phyla",
            "bacteria": "30, same eligibility, at least 10 phyla, Proteobacteria/Pseudomonadota cap 6",
            "eukaryotes": "Homo sapiens, Drosophila melanogaster, Saccharomyces cerevisiae, plus 2 sampled",
            "mags": "5 GenBank GCA assemblies, Contig or Scaffold, excluded_from_refseq contains metagenome",
            "pilot": "1 archaeon, 1 eukaryote, 1 MAG, disjoint from measured",
            "phylum_order": "shuffled with the measured seed, then round-robin",
            "tier_order": "1 reference/representative complete; 2 add chromosome; 3 any category, complete only",
        },
        "tiers": {"archaea": arch_tier, "bacteria": bac_tier},
        "pool_sizes": {
            "archaea_tier1_species": len(tier_rows(parsed["archaea"], 1)),
            "bacteria_tier1_species": len(tier_rows(parsed["bacteria"], 1)),
            "eukaryote_species_excluding_designated": len(euk_for_pilot),
            "mag_assemblies": len(mags_for_pilot),
        },
        "phylum_counts": {
            "measured_archaea": phylum_tally([item for item in measured if item["group"] == "archaea"]),
            "measured_bacteria": phylum_tally([item for item in measured if item["group"] == "bacteria"]),
            "measured_eukaryote": phylum_tally([item for item in measured if item["group"] == "eukaryote"]),
            "measured_mag": phylum_tally([item for item in measured if item["group"] == "mag"]),
        },
        "excluded_accessions": sorted(EXCLUDED),
        "summaries": [
            {
                "name": name,
                "url": SUMMARY_URLS[name],
                "bytes": path.stat().st_size,
                "md5": md5_file(path),
                "rows": len(parsed[name]),
            }
            for name, path in files.items()
        ],
        "rankedlineage_bytes": ranked.stat().st_size,
        "rankedlineage_md5": md5_file(ranked),
        "pilot": pilot,
        "measured": measured,
        "prefix_scan": None,
    }


def prefix_stats(url: str, nbytes: int = 262144) -> dict:
    proc = subprocess.run(
        [
            "curl", "-fsSL", "--retry", "4", "--retry-delay", "2", "--retry-all-errors",
            "-A", "tare-exp-f/1.0 (academic)", "-r", f"0-{nbytes - 1}", url,
        ],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        return {"url": url, "error": proc.stderr.decode("utf-8", "replace")[:400], "status": proc.returncode}
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        text = decoder.decompress(proc.stdout).decode("utf-8", "replace")
    except zlib.error as exc:
        return {"url": url, "error": str(exc), "compressed_bytes": len(proc.stdout)}
    max_name = 0
    max_desc = 0
    name_example = ""
    desc_example = ""
    headers = 0
    for line in text.splitlines():
        if not line.startswith(">"):
            continue
        headers += 1
        parts = line[1:].split(None, 1)
        name = parts[0] if parts else ""
        desc = parts[1] if len(parts) > 1 else ""
        if len(name) > max_name:
            max_name = len(name)
            name_example = name[:200]
        if len(desc) > max_desc:
            max_desc = len(desc)
            desc_example = desc[:200]
    return {
        "url": url,
        "compressed_bytes": len(proc.stdout),
        "headers_in_prefix": headers,
        "max_name_length": max_name,
        "max_description_length": max_desc,
        "name_example": name_example,
        "description_example": desc_example,
        "scope": "first 262144 compressed bytes, not the whole file",
    }


def run_prefix_scan(payload: dict, summary_dir: Path, ranked: Path) -> dict:
    if payload.get("prefix_scan"):
        return payload
    chosen = {item["accession"] for item in payload["pilot"] + payload["measured"]}
    phyla = load_phyla(ranked)
    mag_rows = parse_summary(summary_dir / "genbank_bacteria_mags.tsv", "genbank_bacteria_mags", phyla)
    mag_rows += [
        row
        for row in parse_summary(summary_dir / "genbank_archaea.txt", "genbank_archaea", phyla)
        if "metagenome" in row.excluded_from_refseq.lower()
    ]
    pool = [row for row in mag_pool(mag_rows, chosen) if row.accession not in chosen]
    scanned = random.Random(PREFIX_SEED).sample(sorted(pool, key=lambda row: row.accession), min(40, len(pool)))
    scans = []
    for row in scanned:
        print(f"prefix {row.accession}", file=sys.stderr)
        stat = prefix_stats(row.protein_url)
        stat["accession"] = row.accession
        stat["organism"] = row.organism
        stat["phylum"] = row.phylum
        scans.append(stat)
    ok = [stat for stat in scans if "max_name_length" in stat]
    if not ok:
        raise SystemExit("prefix scan produced no headers")
    longest_name = max(ok, key=lambda stat: (stat["max_name_length"], stat["accession"]))
    longest_desc = max(ok, key=lambda stat: (stat["max_description_length"], stat["accession"]))
    by_acc = {row.accession: row for row in scanned}
    added = []
    for stat, how in ((longest_name, "prefix-name"), (longest_desc, "prefix-description")):
        if stat["accession"] in chosen:
            continue
        if how == "prefix-description" and stat["accession"] == longest_name["accession"]:
            continue
        item = tag(by_acc[stat["accession"]], group="mag", role="measured", how=how)
        item["prefix_max_name_length"] = stat["max_name_length"]
        item["prefix_max_description_length"] = stat["max_description_length"]
        payload["measured"].append(item)
        chosen.add(stat["accession"])
        added.append(stat["accession"])
    payload["prefix_scan"] = {
        "seed": PREFIX_SEED,
        "n_requested": 40,
        "n_scanned": len(scans),
        "scope": "first 262144 compressed bytes of protein.faa.gz",
        "longest_name": longest_name,
        "longest_description": longest_desc,
        "added_accessions": added,
        "scans": scans,
    }
    payload["phylum_counts"]["measured_mag"] = phylum_tally(
        [item for item in payload["measured"] if item["group"] == "mag"]
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-dir", type=Path, required=True)
    parser.add_argument("--rankedlineage", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--prefix-scan", action="store_true")
    args = parser.parse_args()
    if args.prefix_scan:
        payload = json.loads(args.out.read_text())
        payload = run_prefix_scan(payload, args.summary_dir, args.rankedlineage)
    else:
        payload = draw(args.summary_dir, args.rankedlineage)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"wrote {args.out} pilot={len(payload['pilot'])} measured={len(payload['measured'])} "
        f"tiers={payload['tiers']}"
    )


if __name__ == "__main__":
    main()
