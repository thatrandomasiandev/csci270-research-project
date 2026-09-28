#!/usr/bin/env python3
"""Linux-only F6-file + snpEff.config tracing check. Do not run on a login node."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "fixtures" / "probe_eval"))

from acts.cache import RecordCache
from acts.strategies.record_memo import RecordMemo
from acts.trace import tracing_available
from acts.vcf_memo import contract_path_for
from acts.infer_vcf import RecordContract
from suite import hidden_cfg_path, write_vcf

PY = sys.executable
TOOL = ROOT / "fixtures" / "probe_eval" / "tool.py"
OUT = ROOT / "results" / "probe_eval_f6file_linux.json"


def run_f6_file() -> dict:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        inp = write_vcf(tmp / "in.vcf", list(range(40)))
        hidden_cfg_path(inp).write_text("alpha\n")
        argv = [PY, str(TOOL), "vcf", "F6-file", "1.0", "{input}"]
        rec = RecordMemo(
            kind="vcf",
            argv=argv,
            input_path=inp,
            out_dir=tmp / "out",
            cache_path=tmp / "c.jsonl",
            probe_n=20,
            verify="audit",
        ).run()
        contract = RecordContract.load(contract_path_for(tmp / "c.jsonl"))
        hidden = str(hidden_cfg_path(inp).resolve())
        ns1 = RecordCache(
            tmp / "c.jsonl", argv=argv, kind="vcf", extra_files=contract.traced_files
        ).ns
        hidden_cfg_path(inp).write_text("beta\n")
        ns2 = RecordCache(
            tmp / "c.jsonl", argv=argv, kind="vcf", extra_files=contract.traced_files
        ).ns
        return {
            "decision": rec.decision,
            "trace_status": contract.trace_status,
            "hidden_in_namespace": hidden in contract.traced_files,
            "traced_n": len(contract.traced_files),
            "ns_before": ns1,
            "ns_after_edit": ns2,
            "new_namespace": ns1 != ns2,
        }


def run_snpeff_config() -> dict:
    cfg = ROOT / "tools" / "snpEff" / "snpEff.config"
    jar = ROOT / "tools" / "snpEff" / "snpEff.jar"
    if not cfg.is_file() or not jar.is_file():
        return {"skipped": True, "reason": "snpEff not on disk"}
    if shutil.which("java") is None:
        return {"skipped": True, "reason": "java not on PATH"}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        inp = write_vcf(tmp / "in.vcf", list(range(8)))
        argv = [
            "java",
            "-Xmx2g",
            "-jar",
            str(jar),
            "ann",
            "-noStats",
            "-noLog",
            "GRCh38.86",
            "{input}",
        ]
        rec = RecordMemo(
            kind="vcf",
            argv=argv,
            input_path=inp,
            out_dir=tmp / "out",
            cache_path=tmp / "c.jsonl",
            probe_n=4,
            verify="audit",
        ).run()
        contract = RecordContract.load(contract_path_for(tmp / "c.jsonl"))
        cfg_res = str(cfg.resolve())
        ns1 = RecordCache(
            tmp / "c.jsonl", argv=argv, kind="vcf", extra_files=contract.traced_files
        ).ns
        orig = cfg.read_text()
        try:
            cfg.write_text(orig + "\n# acts-trace-probe\n")
            ns2 = RecordCache(
                tmp / "c.jsonl", argv=argv, kind="vcf", extra_files=contract.traced_files
            ).ns
        finally:
            cfg.write_text(orig)
        return {
            "decision": rec.decision,
            "trace_status": contract.trace_status,
            "config_in_namespace": cfg_res in contract.traced_files,
            "traced_n": len(contract.traced_files),
            "ns_before": ns1,
            "ns_after_edit": ns2,
            "new_namespace": ns1 != ns2,
        }


def main() -> int:
    payload = {
        "strace": tracing_available(),
        "f6_file": None,
        "snpeff_config": None,
    }
    if not tracing_available():
        payload["skipped"] = "no strace"
        OUT.write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        return 2
    payload["f6_file"] = run_f6_file()
    payload["snpeff_config"] = run_snpeff_config()
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0 if payload["f6_file"].get("new_namespace") else 1


if __name__ == "__main__":
    raise SystemExit(main())
