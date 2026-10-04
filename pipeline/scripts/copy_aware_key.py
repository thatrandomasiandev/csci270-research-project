#!/usr/bin/env python3
"""Copy-aware key vs dependency key (docs/COPY_AWARE_KEY_PROTOCOL.md).

Hashing only, inputs already on disk. Writes results/copy_aware_key.json.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from acts.fasta import parse_fasta, seq_key  # noqa: E402
from acts.vcf import body_lines, variant_key  # noqa: E402
from content_key_overlap import DATA, collection_a_first10, recall  # noqa: E402

PROTOCOL = "pipeline/docs/COPY_AWARE_KEY_PROTOCOL.md"
OUT = ROOT / "results" / "copy_aware_key.json"


def snpeff_dep_roles() -> tuple[list[str], dict]:
    c = json.loads((ROOT / "results" / "inference_checks.json").read_text())["snpeff"]["contract"]
    roles = {**c["column_roles"], **c["info_roles"], "SAMPLES": c["sample_role"]}
    # D = fields whose perturbation changes output: key or pass (copied). Produced fields are outputs.
    return [n for n, r in roles.items() if r in ("key", "pass")], roles


def vcf_dep_key(line: str) -> str:
    # Every column is key or pass in the SnpEff contract, so D is every input field.
    return "\t".join(line.rstrip("\n").split("\t"))


def vcf_keys(path: Path) -> tuple[set[str], set[str]]:
    lines = body_lines(gzip.open(path, "rt").read())
    return {vcf_dep_key(ln) for ln in lines}, {variant_key(ln) for ln in lines}


def fasta_keys(text: str) -> tuple[set[str], set[str], int]:
    recs = parse_fasta(text)
    return {f"{r.name}\t{seq_key(r.seq)}" for r in recs}, {seq_key(r.seq) for r in recs}, len(recs)


def curve(texts: list[tuple[str, str]]) -> list[dict]:
    seen_d: set[str] = set()
    seen_k: set[str] = set()
    rows = []
    for k, (acc, text) in enumerate(texts):
        d, kk, n = fasta_keys(text)
        if k:
            rd, rk = recall(d, seen_d), recall(kk, seen_k)
            rows.append({"k": k, "accession": acc, "n_records": n, "dep_recall": rd,
                         "copy_aware_recall": rk, "ratio": (rd / rk) if rk else None})
        seen_d |= d
        seen_k |= kk
    return rows


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    scan = json.loads((ROOT / "results" / "inference_fasta_local.json").read_text())["modes"]["scan_cut_ga"]
    assert scan["desc_cols"] == [] and scan["decision"] == "SHIP", "hmmscan contract changed; D undefined"
    dep_fields, roles = snpeff_dep_roles()
    assert all(r in ("key", "pass", "produced") for r in roles.values())

    v = {s: vcf_keys(ROOT / "data" / "vep_chr22" / f"{s}.c1.vcf.gz") for s in ("HG00096", "HG00097", "HG00099")}
    prev_d = v["HG00096"][0] | v["HG00097"][0]
    prev_k = v["HG00096"][1] | v["HG00097"][1]
    vd, vk = recall(v["HG00099"][0], prev_d), recall(v["HG00099"][1], prev_k)
    vcf = {"workload": "HG00096 ∪ HG00097 -> HG00099 (-c1)", "dep_fields": dep_fields,
           "dep_recall": vd, "copy_aware_recall": vk, "ratio": vd / vk if vk else None,
           "note": "D = whole record (all fields key or pass); equals byte recall by construction"}

    ck = json.loads((ROOT / "results" / "content_key_overlap.json").read_text())
    gb_ids = ck["genbank_proteins"]["genomes"]
    genbank = [(a, gzip.open(DATA / f"{a}_protein.faa.gz", "rt").read()) for a in gb_ids]
    refseq = [(g["gcf"], gzip.open(ROOT / "data" / "recurrence" / "A" / f"{g['gcf']}_protein.faa.gz", "rt").read())
              for g in collection_a_first10()]
    gb, rs = curve(genbank), curve(refseq)

    killed = vcf["ratio"] >= 0.9 and gb[-1]["ratio"] >= 0.9
    pred_gb = all(r["ratio"] <= 0.05 for r in gb)
    pred_rs = all(r["ratio"] >= 0.9 for r in rs)
    payload = {
        "protocol": PROTOCOL,
        "git": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
        "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "dep_key": "fields whose perturbation changes output (contract roles key|pass): VCF whole record; hmmscan (name, sequence)",
        "copy_aware_key": "contract key fields: VCF CHROM POS REF ALT; FASTA seq_key",
        "vcf": vcf,
        "genbank_hmmscan": {"genomes": gb_ids, "curve": gb},
        "refseq_hmmscan_control": {"curve": rs},
        "kill_rule": "dep/copy_aware >= 0.9 on BOTH vcf and GenBank (last k)",
        "copy_awareness_killed": killed,
        "prediction_genbank_ratio_le_0.05_all_k": pred_gb,
        "prediction_refseq_ratio_ge_0.9_all_k": pred_rs,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"vcf": {k: vcf[k] for k in ("dep_recall", "copy_aware_recall", "ratio")},
                      "genbank": [(r["k"], round(r["dep_recall"], 4), round(r["copy_aware_recall"], 4)) for r in gb],
                      "refseq": [(r["k"], round(r["ratio"], 4)) for r in rs],
                      "killed": killed, "pred_gb": pred_gb, "pred_rs": pred_rs}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
