"""STAR Method — wraps the existing MATCH-gated bake-off. Does not reimplement STAR."""

from __future__ import annotations

import csv
import os
from pathlib import Path

from egas.contract import Contract, Workload
from egas.methods.base import BakeoffResult, Method, MethodCapabilities
from egas.rungs import STAR_KNOWN, Rung, RungClass


class StarMethod(Method):
    kind = "star"

    def __init__(self, contract: Contract):
        super().__init__(contract)
        self.acts = contract.root
        self.star = self.acts / "star"
        self.bakeoff = self.star / "bench" / "scripts" / "run_bakeoff.sh"
        self.build = self.star / "bench" / "scripts" / "build_stock_opt.sh"

    def capabilities(self) -> MethodCapabilities:
        auto = [r for r in STAR_KNOWN if r.automated]
        source = [r for r in STAR_KNOWN if not r.automated]
        return MethodCapabilities(automated=auto, source=source)

    def apply(self, rung: Rung) -> str:
        if not self.build.is_file():
            raise FileNotFoundError(self.build)
        env_extra = ""
        if rung.id == "star_t4_pgo_jemalloc" or rung.cls == RungClass.T4_BUILD:
            env_extra = "WITH_PGO=1 WITH_JEMALLOC=1"
        if not rung.automated:
            raise RuntimeError(f"{rung.id} is propose-only; apply star_verified_patch instead")
        self.run_cmd(f"{env_extra} {self.build}".strip(), cwd=self.star, timeout=7200)
        return f"applied {rung.id} via {self.build.name}"

    def bakeoff(self, workload: Workload, *, runs: int | None = None) -> BakeoffResult:
        if not self.bakeoff.is_file():
            raise FileNotFoundError(self.bakeoff)
        runs = runs or self.contract.runs
        stock = Path(self.contract.resolve(self.contract.stock_bin))
        opt = Path(self.contract.resolve(self.contract.opt_bin))
        if not stock.is_file() or not opt.is_file():
            raise FileNotFoundError(f"STAR binaries missing:\n  {stock}\n  {opt}")

        out_root = self.star / "bench" / "results" / f"egas_{workload.id}"
        env = os.environ.copy()
        env.update(
            {
                "STOCK_BIN": str(stock),
                "OPT_BIN": str(opt),
                "THREADS": str(self.contract.threads),
                "RUNS": str(runs),
                "WARMUP": str(self.contract.warmup),
                "OUT_ROOT": str(out_root),
            }
        )
        if "genome_dir" in workload.extra:
            env["GENOME_DIR"] = str(workload.extra["genome_dir"])
        if "read1" in workload.extra:
            env["READ1"] = str(workload.extra["read1"])
            env["READ2"] = str(workload.extra.get("read2", ""))

        # Reuse the locked harness rather than a second timer.
        import subprocess

        proc = subprocess.run(
            [str(self.bakeoff), workload.id],
            cwd=self.star,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        csv_path = out_root / "timings.csv"
        if proc.returncode != 0 and not csv_path.is_file():
            raise RuntimeError(
                f"bakeoff {workload.id} failed (exit {proc.returncode})\n{proc.stderr[-2000:]}"
            )
        return _from_bakeoff_csv(workload.id, csv_path, proc.returncode == 0)


def _from_bakeoff_csv(wid: str, path: Path, harness_ok: bool) -> BakeoffResult:
    if not path.is_file():
        return BakeoffResult(wid, False, "no timings.csv", [], [])
    stock: list[float] = []
    opt: list[float] = []
    verdicts: set[str] = set()
    with path.open() as fh:
        for row in csv.DictReader(fh):
            verdicts.add(row.get("output", ""))
            t = float(row["wall_sec"])
            (stock if row["label"] == "stock" else opt).append(t)
    match = harness_ok and verdicts <= {"MATCH"} and bool(stock) and bool(opt)
    note = "MATCH" if match else f"DIFF/harness ({','.join(sorted(verdicts)) or 'empty'})"
    return BakeoffResult(wid, match, note, stock, opt)
