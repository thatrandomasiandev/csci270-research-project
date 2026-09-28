from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures" / "probe_eval"))

from acts.cache import RecordCache
from acts.infer_vcf import infer_contract, run_vcf_tool
from acts.sample import sample_indices
from acts.strategies.record_memo import RecordMemo
from acts.trace import tracing_available
from suite import hidden_cfg_path, write_vcf

PIPE = Path(__file__).resolve().parents[1]
TOOL = PIPE / "fixtures" / "probe_eval" / "tool.py"
PY = sys.executable


WRAP = """\
import sys
from pathlib import Path
log = Path(sys.argv[1])
inp = Path(sys.argv[-1])
log.write_text(log.read_text() + str(inp.resolve()) + "\\n" if log.is_file() else str(inp.resolve()) + "\\n")
sys.path.insert(0, {suite!r})
from suite import run_tool
sys.stdout.write(run_tool("vcf", "C1", 0.0, inp))
"""


LATE = """\
import sys
from pathlib import Path
src = Path(sys.argv[-1])
target = int(sys.argv[1])
lines = src.read_text().splitlines()
hdr = [ln for ln in lines if ln.startswith("#")]
out = list(hdr)
for ln in lines:
    if ln.startswith("#") or not ln:
        continue
    p = ln.split("\\t")
    pos = int(p[1])
    if pos == target:
        p[7] = f"ANN=id:{p[2]}"
    else:
        p[7] = f"ANN={p[0]}:{p[1]}:{p[3]}>{p[4].split(',')[0]}"
    out.append("\\t".join(p))
sys.stdout.write("\\n".join(out) + "\\n")
"""


HIDDEN = """\
import sys
from pathlib import Path
src = Path(sys.argv[-1])
token = (src.parent / "hidden.cfg").read_text().strip()
lines = src.read_text().splitlines()
out = [ln for ln in lines if ln.startswith("#")]
for ln in lines:
    if ln.startswith("#") or not ln:
        continue
    p = ln.split("\\t")
    p[7] = f"ANN=file:{token}:{p[0]}:{p[1]}"
    out.append("\\t".join(p))
sys.stdout.write("\\n".join(out) + "\\n")
"""


class VerifyAuditTests(unittest.TestCase):
    def test_audit_mode_skips_full_stock_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            inp = write_vcf(tmp / "in.vcf", list(range(30)))
            log = tmp / "calls.txt"
            wrap = tmp / "wrap.py"
            wrap.write_text(WRAP.format(suite=str(PIPE / "fixtures" / "probe_eval")))
            argv = [PY, str(wrap), str(log), "{input}"]
            RecordMemo(
                kind="vcf",
                argv=argv,
                input_path=inp,
                out_dir=tmp / "audit",
                probe_n=12,
                verify="audit",
            ).run()
            audit_calls = log.read_text().splitlines() if log.is_file() else []
            log.write_text("")
            RecordMemo(
                kind="vcf",
                argv=argv,
                input_path=inp,
                out_dir=tmp / "full",
                probe_n=12,
                verify="full",
            ).run()
            full_calls = log.read_text().splitlines() if log.is_file() else []
            orig = str(inp.resolve())
            self.assertNotIn(orig, audit_calls, audit_calls)
            self.assertIn(orig, full_calls, full_calls)

    def test_random_sample_catches_late_id_fault(self) -> None:
        n = 80
        k = 20
        idxs = sample_indices(n, k, seed=20260927)
        late = [i for i in idxs if i >= 20]
        self.assertTrue(late, "probe seed must pick a record outside the old prefix")
        target_pos = late[0] + 1
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            inp = write_vcf(tmp / "in.vcf", list(range(n)))
            tool = tmp / "late.py"
            tool.write_text(LATE)
            rec = RecordMemo(
                kind="vcf",
                argv=[PY, str(tool), str(target_pos), "{input}"],
                input_path=inp,
                out_dir=tmp / "out",
                probe_n=k,
                probe_seed=20260927,
                verify="audit",
            ).run()
            self.assertIn(
                rec.decision,
                {"REFUSE_AMBIGUOUS", "SHIP"},
                rec.reason,
            )
            if rec.decision == "SHIP":
                self.assertIn("ID", rec.extra.get("widen", "") + rec.extra.get("cache_key_fields", ""))

    @unittest.skipUnless(tracing_available(), "strace not available (macOS)")
    def test_traced_hidden_cfg_new_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            inp = write_vcf(tmp / "in.vcf", list(range(12)))
            hidden_cfg_path(inp).write_text("alpha\n")
            tool = tmp / "hidden.py"
            tool.write_text(HIDDEN)
            argv = [PY, str(tool), "{input}"]
            rec = RecordMemo(
                kind="vcf",
                argv=argv,
                input_path=inp,
                out_dir=tmp / "out",
                cache_path=tmp / "c.jsonl",
                probe_n=8,
                verify="audit",
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)
            from acts.infer_vcf import RecordContract
            from acts.vcf_memo import contract_path_for

            contract = RecordContract.load(contract_path_for(tmp / "c.jsonl"))
            self.assertEqual(contract.trace_status, "ok")
            hidden = str(hidden_cfg_path(inp).resolve())
            self.assertIn(hidden, contract.traced_files)
            ns1 = RecordCache(
                tmp / "c.jsonl", argv=argv, kind="vcf", extra_files=contract.traced_files
            ).ns
            hidden_cfg_path(inp).write_text("beta\n")
            ns2 = RecordCache(
                tmp / "c.jsonl", argv=argv, kind="vcf", extra_files=contract.traced_files
            ).ns
            self.assertNotEqual(ns1, ns2)
