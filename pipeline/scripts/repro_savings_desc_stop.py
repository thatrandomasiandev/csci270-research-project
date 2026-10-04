#!/usr/bin/env python3
"""Reproduce the 2026-09-28 savings STOP_MATCH (A hmmsearch, genome 5) locally.

Real collection-A proteomes 1–5 (ordering seed 20260926), the Pfam models behind the
73 mismatching lines, and the CARC hmmsearch flags (-Z 1e6 --domZ 1e6). Each genome is
subset to the proteins whose descriptions changed plus a fixed random sample, so it
runs in minutes on a laptop. Every genome is verified against a full stock run.

Usage: python3 scripts/repro_savings_desc_stop.py OUT_DIR
Writes OUT_DIR/repro.json with per-genome decisions and provenance.
"""

from __future__ import annotations

import gzip
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.fasta import FastaRec, parse_fasta, write_fasta  # noqa: E402
from acts.strategies.record_memo import RecordMemo  # noqa: E402

GENOMES = [
    "GCF_002853805.1",
    "GCF_002090355.1",
    "GCF_001650275.1",
    "GCF_052050745.1",
    "GCF_016659085.1",
]
CHANGED = {
    "WP_000043761.1", "WP_000091955.1", "WP_000124700.1", "WP_000183107.1",
    "WP_000455798.1", "WP_000550695.1", "WP_000716421.1", "WP_000804550.1",
    "WP_001051798.1", "WP_001144615.1", "WP_001278994.1",
}
MODELS = (
    "Aldolase_II Bac_transf Beta-prop_ACSF4 Beta-prop_EML_2 Beta-prop_IFT122_1st "
    "Beta-prop_THOC3 Beta-prop_WDR90_POC16_2nd C2-set_3 Channel_Tsx CoA_binding_3 "
    "Cytochrom_D1 DUF1002 DUF2534 DUF4248 DUF5074 DeoRC EAL EF-G_D2 EFG_C EFG_III EFG_IV "
    "EMC1_C FeoC FokI_D3 GGDEF GTP_EFTU GTP_EFTU_D2 GntR GspL_C HTH_11 HTH_20 HTH_24 "
    "HTH_3 HTH_31 HTH_5 HTH_AsnC-type HTH_DeoR HTH_IclR HTH_Mga HTH_PafC HVO_A0114 Ivy "
    "KMS1_N Lactonase MASE1 MMR_HSR1 MarR_2 MqsA_antitoxin PAS PAS_11 PAS_3 PAS_4 PAS_6 "
    "PAS_8 PAS_9 PQQ_2 Phage_terminase Put_DNA-bind_N RF3_C Rhodanese Rhodanese_C "
    "Ribosomal_L28 Ribosomal_L33 SGL TrAA12 Tricorn_2nd UPF0176_N VD10_N WD40_CDC20-Fz "
    "WD40_WDHD1_1st WDR55 YNCE choice_anch_I"
).split()
SAMPLE = 300
SEED = 20261003


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def models_hmm(out: Path) -> Path:
    pfam_gz = ROOT / "data" / "hmmer" / "Pfam-A.hmm.gz"
    full = out / "Pfam-A.hmm"
    if not full.is_file():
        with gzip.open(pfam_gz, "rb") as src, full.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    if not Path(str(full) + ".ssi").is_file():
        run(["hmmfetch", "--index", str(full)])
    keys = out / "models.txt"
    keys.write_text("\n".join(MODELS) + "\n")
    sub = out / "subset.hmm"
    sub.write_text(run(["hmmfetch", "-f", str(full), str(keys)]).stdout)
    return sub


def genome_subset(acc: str, rng: random.Random) -> list[FastaRec]:
    path = ROOT / "data" / "recurrence" / "A" / f"{acc}_protein.faa.gz"
    recs = parse_fasta(gzip.open(path, "rt").read())
    keep = [r for r in recs if r.name in CHANGED]
    rest = [r for r in recs if r.name not in CHANGED]
    keep += rng.sample(rest, min(SAMPLE, len(rest)))
    return keep


def main(out_dir: str, mode: str = "hmmsearch") -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    hmm = models_hmm(out)
    emit = str(ROOT / "scripts" / "emit_side_table.py")
    if mode == "hmmsearch":
        argv = [
            sys.executable, emit, shutil.which("hmmsearch") or "hmmsearch", "--cpu", "4",
            "--noali", "--tblout", "{table}", "-Z", "1000000", "--domZ", "1000000",
            str(hmm), "{input}",
        ]
    elif mode == "hmmscan":
        if not Path(str(hmm) + ".h3m").is_file():
            run(["hmmpress", "-f", str(hmm)])
        argv = [
            sys.executable, emit, shutil.which("hmmscan") or "hmmscan", "--cpu", "4",
            "--noali", "--tblout", "{table}", "--cut_ga", str(hmm), "{input}",
        ]
    else:
        raise SystemExit(f"unknown mode {mode}")
    rng = random.Random(SEED)
    cache = out / "cache.sqlite"
    rows = []
    for pos, acc in enumerate(GENOMES, start=1):
        fa = write_fasta(out / f"g{pos}.faa", genome_subset(acc, rng))
        rec = RecordMemo(
            kind="fasta", argv=argv, input_path=fa, out_dir=out / f"run{pos}",
            cache_path=cache, verify="full",
        ).run()
        contract = json.loads((out / "cache.sqlite.contract.json").read_text())
        rows.append({
            "position": pos, "accession": acc, "decision": rec.decision,
            "match_ws": contract.get("match_ws"), "desc_span": contract.get("desc_span"),
            "desc_trailing": contract.get("desc_trailing"),
            "reason": rec.reason,
            "n_hits": rec.extra.get("n_hits"), "n_misses": rec.extra.get("n_misses"),
        })
        print(rows[-1], flush=True)
        if rec.decision != "SHIP":
            break
    git = run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    dirty = bool(run(["git", "status", "--porcelain", "acts"], cwd=ROOT).stdout.strip())
    payload = {
        "purpose": "reproduce 2026-09-28 savings STOP_MATCH (A hmmsearch genome 5)",
        "mode": mode,
        "git_head": git, "acts_dirty": dirty, "hmmer": run(["hmmsearch", "-h"]).stdout.splitlines()[1],
        "models": len(MODELS), "sample_per_genome": SAMPLE, "seed": SEED,
        "genomes": rows,
    }
    (out / "repro.json").write_text(json.dumps(payload, indent=2) + "\n")
    return 0 if all(r["decision"] == "SHIP" for r in rows) and len(rows) == len(GENOMES) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "hmmsearch"))
