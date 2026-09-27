#!/usr/bin/env python3
"""Optional local search through the generic FASTA→table path.

Uses binaries on PATH and proteomes already under data/. No CARC.
Writes results/inference_fasta_local.json. Skips if the binary is absent.
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.fasta import FastaRec, parse_fasta, write_fasta
from acts.strategies.record_memo import RecordMemo

FAA = ROOT / "data" / "kprot" / "MG1655.faa.gz"
HMM_GZ = ROOT / "data" / "hmmer" / "Pfam-A.hmm.gz"
OUT = ROOT / "results" / "inference_fasta_local.json"
N_SEQ = 200
# A few ubiquitous families so 200 K-12 proteins actually produce table rows.
# First-in-file models are mostly eukaryotic and yield zero hits.
MODEL_NAMES = (
    "ABC_tran",
    "GTP_EFTU",
    "Response_reg",
    "AAA",
    "HATPase_c",
    "Helicase_C",
)
EMIT = [sys.executable, str(ROOT / "scripts" / "emit_side_table.py")]


def named_models(src: Path, names: tuple[str, ...]) -> str:
    need = set(names)
    got: dict[str, str] = {}
    buf: list[str] = []
    name = None
    with gzip.open(src, "rt") as fh:
        for line in fh:
            if line.startswith("NAME "):
                name = line.split()[1]
            buf.append(line)
            if line.strip() == "//":
                if name in need:
                    got[name] = "".join(buf)
                    need.discard(name)
                buf = []
                name = None
                if not need:
                    break
    if need:
        raise SystemExit(f"models not in local HMM file: {sorted(need)}")
    return "".join(got[n] for n in names if n in got)


def first_proteins(src: Path, n: int) -> list[FastaRec]:
    text = gzip.open(src, "rt").read()
    return parse_fasta(text)[:n]


def main() -> int:
    binary = shutil.which("hmmscan")
    if not binary or not shutil.which("hmmsearch"):
        OUT.write_text(
            json.dumps({"status": "INCOMPLETE", "reason": "search binary not on PATH"}, indent=2)
            + "\n"
        )
        print("INCOMPLETE: search binary not on PATH")
        return 0
    if not HMM_GZ.is_file() or not FAA.is_file():
        OUT.write_text(
            json.dumps({"status": "INCOMPLETE", "reason": "local HMM or proteome missing"}, indent=2)
            + "\n"
        )
        print("INCOMPLETE: local data missing")
        return 0

    work = Path(tempfile.mkdtemp(prefix="acts_fasta_local_"))
    models = work / "tiny.hmm"
    models.write_text(named_models(HMM_GZ, MODEL_NAMES))
    subprocess.run(["hmmpress", "-f", str(models)], check=True, capture_output=True, text=True)
    fa = work / "probe.fa"
    recs = first_proteins(FAA, N_SEQ)
    write_fasta(fa, recs)

    modes = {
        "scan_cut_ga": EMIT
        + [
            "hmmscan",
            "--cut_ga",
            "--tblout",
            "{table}",
            "--noali",
            str(models),
            "{input}",
        ],
        "search_default_Z": EMIT
        + [
            "hmmsearch",
            "--tblout",
            "{table}",
            "--noali",
            str(models),
            "{input}",
        ],
        "search_fixed_Z": EMIT
        + [
            "hmmsearch",
            "-Z",
            "1e6",
            "--domZ",
            "1e6",
            "--tblout",
            "{table}",
            "--noali",
            str(models),
            "{input}",
        ],
    }

    payload = {
        "status": "RAN",
        "n_seq": len(recs),
        "n_models": len(MODEL_NAMES),
        "models": list(MODEL_NAMES),
        "binary": binary,
        "modes": {},
    }
    for name, argv in modes.items():
        dest = work / name
        rec = RecordMemo(kind="fasta", argv=argv, input_path=fa, out_dir=dest).run()
        contract_path = dest / "cache.jsonl.contract.json"
        contract = json.loads(contract_path.read_text()) if contract_path.is_file() else {}
        payload["modes"][name] = {
            "decision": rec.decision,
            "reason": rec.reason,
            "match": contract.get("match"),
            "query_col": contract.get("query_col"),
            "produced_cols": contract.get("produced_cols"),
            "desc_cols": contract.get("desc_cols"),
        }
        print(name, rec.decision, rec.reason, flush=True)

    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
