"""Guards for the post-hoc hmmscan sensitivity and stock completion."""

from __future__ import annotations

import gzip
import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "scripts"))

from acts.savings_analysis import sensitivity, stock_tasks  # noqa: E402
from analyze_savings_measured import load_completions  # noqa: E402
from hmmscan_stock import (  # noqa: E402
    load_manifest,
    measure_stock,
    result_path,
    stock_argv,
    task_manifest,
)
from savings_job_load import load_savings_job  # noqa: E402

A_JOB = PIPE / "results" / "savings_20261006" / "A_hmmscan.json"
B_JOB = PIPE / "results" / "savings_20261006" / "B_hmmscan.json"
SAMPLED = {"A": {1, 2, 5, 10, 20, 30}, "B": {1, 2, 5, 10, 20, 40}}


class HmmscanSavingsTests(unittest.TestCase):
    def test_reference_dumps_keep_the_recomputed_correction(self) -> None:
        rows = {
            path.stem[0]: sensitivity(load_savings_job(path)) for path in (A_JOB, B_JOB)
        }
        self.assertEqual(round(rows["A"]["measured_over_predicted_ratio"], 3), 0.793)
        self.assertEqual(round(rows["B"]["measured_over_predicted_ratio"], 3), 0.807)
        self.assertEqual(round(rows["A"]["cum_speedup_wall"], 2), 2.95)
        self.assertEqual(round(rows["A"]["cum_speedup_wall_with_P"], 2), 2.91)
        self.assertEqual(round(rows["B"]["cum_speedup_wall"], 2), 16.18)
        self.assertEqual(round(rows["B"]["cum_speedup_wall_with_P"], 2), 15.32)

    def test_completion_manifest_excludes_sampled_genomes(self) -> None:
        jobs = [load_savings_job(A_JOB), load_savings_job(B_JOB)]
        tasks = stock_tasks(jobs)
        self.assertEqual(len(tasks), 58)
        self.assertEqual([task.collection for task in tasks].count("A"), 24)
        self.assertEqual([task.collection for task in tasks].count("B"), 34)
        self.assertTrue(
            all(task.position not in SAMPLED[task.collection] for task in tasks)
        )
        manifest = task_manifest(tasks)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tasks.json"
            path.write_text(json.dumps(manifest, indent=2) + "\n")
            self.assertEqual(load_manifest(path), tasks)
        committed = json.loads(
            (PIPE / "results" / "hmmscan_stock_tasks.json").read_text()
        )
        self.assertEqual(committed, manifest)

    def test_stock_argv_matches_the_savings_runner(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "run_hmmer_savings", PIPE / "scripts" / "run_hmmer_savings.py"
        )
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        expected = runner.stock_argv(
            "hmmscan",
            {"hmmscan": "/bin/hmmscan"},
            Path("/pfam/Pfam-A.hmm"),
            Path("/input.faa"),
            Path("/out.tbl"),
            32,
        )
        actual = stock_argv(
            "/bin/hmmscan",
            Path("/pfam/Pfam-A.hmm"),
            Path("/input.faa"),
            Path("/out.tbl"),
            32,
        )
        self.assertEqual(actual, expected)

    def test_measured_loader_keeps_hmmscan_completions_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "A_03.json").write_text(
                json.dumps({"kind": "hmmscan_stock_completion", "collection": "A"})
                + "\n"
            )
            (root / "A_04.json").write_text(
                json.dumps({"kind": "hmmsearch_stock_completion", "collection": "A"})
                + "\n"
            )
            found = load_completions(root, "hmmscan_stock_completion")
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["kind"], "hmmscan_stock_completion")

    def test_finished_measurement_is_not_replaced(self) -> None:
        job = {
            "collection": "A",
            "mode": "hmmscan",
            "genomes": [
                {
                    "position": 1,
                    "accession": "A1",
                    "path": "data/A/1.faa.gz",
                    "stock_wall_s": 1.0,
                    "stock_predicted_s": 100.0,
                    "cached_wall_s": 25.0,
                },
                {
                    "position": 2,
                    "accession": "A2",
                    "path": "data/A/2.faa.gz",
                    "stock_predicted_s": 100.0,
                    "cached_wall_s": 25.0,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "data" / "A" / "2.faa.gz"
            source.parent.mkdir(parents=True)
            with gzip.open(source, "wt") as stream:
                stream.write(">p1 test\nACDEFGHIK\n")
            calls = root / "calls"
            binary = root / "hmmscan"
            press = root / "hmmpress"
            binary.write_text(
                "#!/bin/sh\n"
                f"echo x >> '{calls}'\n"
                "out=''\n"
                "while [ $# -gt 0 ]; do\n"
                "  if [ \"$1\" = --tblout ]; then out=$2; shift 2; else shift; fi\n"
                "done\n"
                "printf 'row\\n' > \"$out\"\n"
            )
            press.write_text("#!/bin/sh\ntouch \"$2.h3m\"\n")
            binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
            press.chmod(press.stat().st_mode | stat.S_IEXEC)
            hmm = root / "Pfam-A.hmm"
            hmm.write_text("hmm")
            task = stock_tasks([job])[0]
            first = measure_stock(
                task,
                data_root=root,
                hmm=hmm,
                hmmscan=str(binary),
                hmmpress=str(press),
                out_dir=root / "out",
                work=root / "work",
                cpu=32,
            )
            first_text = first.read_text()
            second = measure_stock(
                task,
                data_root=root,
                hmm=hmm,
                hmmscan=str(binary),
                hmmpress=str(press),
                out_dir=root / "out",
                work=root / "work",
                cpu=32,
            )
            self.assertEqual(second, result_path(root / "out", task))
            self.assertEqual(second.read_text(), first_text)
            self.assertEqual(calls.read_text().count("x"), 2)
            payload = json.loads(first_text)
            self.assertEqual(payload["kind"], "hmmscan_stock_completion")
            self.assertEqual(payload["argv"][3], "--cut_ga")
            self.assertEqual(payload["provenance"]["versions"]["pfam"], str(hmm))


if __name__ == "__main__":
    unittest.main()
