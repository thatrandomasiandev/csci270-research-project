#!/usr/bin/env python3
"""MATCH stock vs tuned HMMER and SnpEff CDS on small inputs.

Locked by docs/COMPARISON_PROTOCOL.md. No timing numbers. Writes
results/compare_match.json. Builds prefixes if they are missing.
"""

from __future__ import annotations

import json
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from acts.table import body_lines as tbl_body  # noqa: E402
from acts.table import tables_match  # noqa: E402
from acts.vcf import bodies_equal, body_lines  # noqa: E402
from compare_build import (  # noqa: E402
    BUILDS,
    DATA,
    SNPEFF_DATA,
    SNPEFF_JAR,
    build_all,
    snpeff_cmd,
)

OUT = ROOT / "results" / "compare_match.json"


def git_commit() -> str:
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT.parent,
        capture_output=True,
        text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def protocol_commit() -> str:
    r = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "pipeline/docs/COMPARISON_PROTOCOL.md"],
        cwd=ROOT.parent,
        capture_output=True,
        text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def run_tool(cmd: list[str], tbl: Path | None = None) -> dict:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout
    stderr = proc.stderr
    if tbl is not None and tbl.is_file():
        text = tbl.read_text()
    else:
        text = stdout
    return {
        "returncode": proc.returncode,
        "text": text,
        "stderr_tail": stderr[-2000:],
        "cmd": cmd,
    }


def hmm_cmd(binary: Path, mode: str, hmm: Path, faa: Path, tbl: Path) -> list[str]:
    if mode == "hmmscan":
        return [
            str(binary),
            "--cpu",
            "1",
            "--cut_ga",
            "--noali",
            "--tblout",
            str(tbl),
            str(hmm),
            str(faa),
        ]
    return [
        str(binary),
        "--cpu",
        "1",
        "--noali",
        "-Z",
        "1000000",
        "--domZ",
        "1000000",
        "--tblout",
        str(tbl),
        str(hmm),
        str(faa),
    ]


def ensure_builds() -> dict[str, str]:
    stock = BUILDS / "hmmer-stock" / "bin" / "hmmscan"
    tuned = BUILDS / "hmmer-tuned" / "bin" / "hmmscan"
    cds = BUILDS / "snpeff" / "snpeff.jsa"
    test_faa = DATA / "match_test.faa"
    if stock.is_file() and tuned.is_file() and cds.is_file() and test_faa.is_file():
        return {
            "hmmer_stock": str(stock.parent),
            "hmmer_tuned": str(tuned.parent),
            "snpeff_cds": str(cds),
            "toy_hmm": str(DATA / "toy.hmm"),
            "test_faa": str(test_faa),
            "test_vcf": str(DATA / "match_test.vcf"),
            "reused_existing_builds": "true",
        }
    return build_all()


def match_hmmer(mode: str, match: str, info: dict[str, str]) -> dict:
    stock_bin = Path(info["hmmer_stock"]) / ("hmmscan" if mode == "hmmscan" else "hmmsearch")
    tuned_bin = Path(info["hmmer_tuned"]) / ("hmmscan" if mode == "hmmscan" else "hmmsearch")
    hmm = Path(info["toy_hmm"])
    faa = Path(info["test_faa"])
    work = DATA / "match_out"
    work.mkdir(parents=True, exist_ok=True)
    stock_tbl = work / f"{mode}.stock.tbl"
    tuned_tbl = work / f"{mode}.tuned.tbl"
    stock = run_tool(hmm_cmd(stock_bin, mode, hmm, faa, stock_tbl), stock_tbl)
    tuned = run_tool(hmm_cmd(tuned_bin, mode, hmm, faa, tuned_tbl), tuned_tbl)
    ok = (
        stock["returncode"] == 0
        and tuned["returncode"] == 0
        and tables_match(stock["text"], tuned["text"], match, match_ws=True)
    )
    return {
        "mode": mode,
        "match": match,
        "match_ws": True,
        "matched": ok,
        "stock_returncode": stock["returncode"],
        "tuned_returncode": tuned["returncode"],
        "n_tblout_stock": len(tbl_body(stock["text"])),
        "n_tblout_tuned": len(tbl_body(tuned["text"])),
        "stock_stderr_tail": stock["stderr_tail"],
        "tuned_stderr_tail": tuned["stderr_tail"],
        "timing_claimed": False,
        "note": "small toy HMM / FASTA; not a speedup",
    }


def match_snpeff(info: dict[str, str]) -> dict:
    vcf = Path(info["test_vcf"])
    archive = Path(info["snpeff_cds"])
    work = DATA / "match_out"
    work.mkdir(parents=True, exist_ok=True)
    stock = run_tool(snpeff_cmd(None, [], vcf))
    tuned = run_tool(
        snpeff_cmd(archive, ["-XX:TieredStopAtLevel=1"], vcf),
    )
    (work / "snpeff.stock.vcf").write_text(stock["text"])
    (work / "snpeff.tuned.vcf").write_text(tuned["text"])
    body_ok = (
        stock["returncode"] == 0
        and tuned["returncode"] == 0
        and bodies_equal(stock["text"], tuned["text"])
    )
    return {
        "match": "record-body",
        "matched": body_ok,
        "stock_returncode": stock["returncode"],
        "tuned_returncode": tuned["returncode"],
        "n_input_records": len(body_lines(vcf.read_text())),
        "n_out_stock": len(body_lines(stock["text"])),
        "n_out_tuned": len(body_lines(tuned["text"])),
        "full_file_identical": stock["text"] == tuned["text"],
        "stock_stderr_tail": stock["stderr_tail"],
        "tuned_stderr_tail": tuned["stderr_tail"],
        "timing_claimed": False,
        "jar": str(SNPEFF_JAR),
        "dataDir": str(SNPEFF_DATA),
        "cds_archive": str(archive),
        "java_flags_tuned": ["-XX:SharedArchiveFile", "-Xshare:on", "-XX:TieredStopAtLevel=1"],
        "note": "small VCF; not a speedup; header drift allowed",
    }


def main() -> int:
    info = ensure_builds()
    scan = match_hmmer("hmmscan", "order", info)
    search = match_hmmer("hmmsearch", "multiset", info)
    snpeff = match_snpeff(info)
    star = {
        "match": "cited sealed Suite B",
        "matched": True,
        "rerun": False,
        "source_csv": "star/bench/results/illumina10_s8j_mac.csv",
        "source_status": "STATUS.md",
        "scoreboard": "10/10 min_pair >= 2.0, MATCH every timed pair",
        "timing_claimed": False,
        "note": "EGAS 2x is the code-opt arm; do not rerun",
    }
    payload = {
        "protocol": "pipeline/docs/COMPARISON_PROTOCOL.md",
        "protocol_commit": protocol_commit(),
        "git_head": git_commit(),
        "timing_claimed": False,
        "host": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "when_utc": datetime.now(timezone.utc).isoformat(),
        },
        "builds": {
            "hmmer_stock": info.get("hmmer_stock"),
            "hmmer_tuned": info.get("hmmer_tuned"),
            "snpeff_cds": info.get("snpeff_cds"),
            "toy_hmm": info.get("toy_hmm"),
            "test_faa": info.get("test_faa"),
            "test_vcf": info.get("test_vcf"),
            "reused_existing_builds": info.get("reused_existing_builds", "false"),
        },
        "workloads": {
            "star_sealed": star,
            "hmmscan_cut_ga": scan,
            "hmmsearch_fixed_Z": search,
            "snpeff": snpeff,
        },
        "all_matched": bool(scan["matched"] and search["matched"] and snpeff["matched"]),
        "note": (
            "MATCH only. No wall-clock comparison. "
            "PGO/AppCDS are established levers, not a method."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    if not payload["all_matched"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
