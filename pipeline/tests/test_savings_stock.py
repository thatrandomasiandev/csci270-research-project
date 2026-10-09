"""Guards for savings stock imputation and the stock-completion runner."""

from __future__ import annotations

import gzip
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "scripts"))

from hmmsearch_stock import (  # noqa: E402
    load_manifest,
    measure_stock,
    result_path,
    stock_argv,
    task_manifest,
)
from acts.provenance import provenance  # noqa: E402
from acts.savings_analysis import (  # noqa: E402
    fully_measured,
    load_job,
    sensitivity,
    stock_tasks,
)

A_JOB = PIPE / "results" / "savings_20261006" / "A_hmmsearch.json"
B_JOB = PIPE / "results" / "savings_20261006" / "B_hmmsearch.json"


def _job(collection: str, positions: dict[int, float | None]) -> dict:
    genomes = []
    for position, measured in positions.items():
        row = {
            "position": position,
            "accession": f"{collection}{position}",
            "path": f"data/{collection}/{position}.faa.gz",
            "stock_predicted_s": 100.0,
            "cached_wall_s": 25.0,
        }
        if measured is not None:
            row["stock_wall_s"] = measured
        genomes.append(row)
    return {
        "collection": collection,
        "mode": "hmmsearch",
        "stopped": None,
        "decision": None,
        "fit": {"a": 10.0, "b": 1.0},
        "genomes": genomes,
    }


class SavingsStockGuardTests(unittest.TestCase):
    def test_sensitivity_scales_only_unsampled_stock(self) -> None:
        job = _job("A", {1: 40.0, 2: None, 3: 80.0})
        row = sensitivity(job)
        self.assertEqual(row["measured_over_predicted_ratio"], 0.6)
        self.assertEqual(row["corrected_stock_wall_s"], 40.0 + 60.0 + 80.0)

    def test_reference_dumps_keep_the_recorded_correction(self) -> None:
        rows = {path.stem[0]: sensitivity(load_job(path)) for path in (A_JOB, B_JOB)}
        self.assertEqual(round(rows["A"]["measured_over_predicted_ratio"], 3), 0.628)
        self.assertEqual(round(rows["B"]["measured_over_predicted_ratio"], 3), 0.605)
        self.assertEqual(round(rows["A"]["cum_speedup_wall"], 2), 1.86)
        self.assertEqual(round(rows["A"]["cum_speedup_wall_with_P"], 2), 1.51)
        self.assertEqual(round(rows["B"]["cum_speedup_wall"], 2), 4.40)
        self.assertEqual(round(rows["B"]["cum_speedup_wall_with_P"], 2), 3.15)

    def test_completion_manifest_excludes_sampled_genomes(self) -> None:
        jobs = [load_job(A_JOB), load_job(B_JOB)]
        tasks = stock_tasks(jobs)
        self.assertEqual(len(tasks), 58)
        self.assertEqual([task.collection for task in tasks].count("A"), 24)
        self.assertEqual([task.collection for task in tasks].count("B"), 34)
        sampled = {"A": {1, 2, 5, 10, 20, 30}, "B": {1, 2, 5, 10, 20, 40}}
        self.assertTrue(
            all(task.position not in sampled[task.collection] for task in tasks)
        )
        manifest = task_manifest(tasks)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tasks.json"
            path.write_text(json.dumps(manifest, indent=2) + "\n")
            self.assertEqual(load_manifest(path), tasks)

    def test_fully_measured_requires_the_exact_completion_set(self) -> None:
        job = _job("A", {1: 40.0, 2: None})
        with self.assertRaises(ValueError):
            fully_measured(job, [])
        row = fully_measured(
            job,
            [
                {
                    "collection": "A",
                    "position": 2,
                    "accession": "A2",
                    "returncode": 0,
                    "stock_wall_s": 70.0,
                }
            ],
        )
        self.assertEqual(row["stock_wall_s"], 110.0)
        self.assertEqual(row["cum_speedup_wall"], 110.0 / 50.0)

    def test_stock_argv_matches_the_savings_runner(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "run_hmmer_savings", PIPE / "scripts" / "run_hmmer_savings.py"
        )
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        expected = runner.stock_argv(
            "hmmsearch",
            {"hmmsearch": "/bin/hmmsearch"},
            Path("/pfam/Pfam-A.hmm"),
            Path("/input.faa"),
            Path("/out.tbl"),
            32,
        )
        actual = stock_argv(
            "/bin/hmmsearch",
            Path("/pfam/Pfam-A.hmm"),
            Path("/input.faa"),
            Path("/out.tbl"),
            32,
        )
        self.assertEqual(actual, expected)

    def test_finished_measurement_is_not_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "data" / "A" / "3.faa.gz"
            source.parent.mkdir(parents=True)
            with gzip.open(source, "wt") as stream:
                stream.write(">p1 test\nACDEFGHIK\n")
            calls = root / "calls"
            binary = root / "hmmsearch"
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
            task = stock_tasks([_job("A", {1: 1.0, 3: None})])[0]
            first = measure_stock(
                task,
                data_root=root,
                hmm=hmm,
                hmmsearch=str(binary),
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
                hmmsearch=str(binary),
                hmmpress=str(press),
                out_dir=root / "out",
                work=root / "work",
                cpu=32,
            )
            self.assertEqual(second, result_path(root / "out", task))
            self.assertEqual(second.read_text(), first_text)
            self.assertEqual(calls.read_text().count("x"), 2)
            payload = json.loads(first_text)
            self.assertEqual(payload["provenance"]["versions"]["pfam"], str(hmm))

    def test_provenance_records_hash_host_and_versions(self) -> None:
        old = os.environ.get("ACTS_GIT_HASH")
        os.environ["ACTS_GIT_HASH"] = "abc123"
        try:
            record = provenance(versions={"hmmer": "3.4"})
        finally:
            if old is None:
                os.environ.pop("ACTS_GIT_HASH", None)
            else:
                os.environ["ACTS_GIT_HASH"] = old
        self.assertEqual(record["git"], "abc123")
        self.assertTrue(record["host"])
        self.assertTrue(record["python"])
        self.assertEqual(record["versions"], {"hmmer": "3.4"})
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PIPE.parents[0],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertNotEqual(head, "")


if __name__ == "__main__":
    unittest.main()
