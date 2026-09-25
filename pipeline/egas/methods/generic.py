"""Any command-line Method whose contract supplies build / run / match."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from egas.contract import Contract, Workload
from egas.methods.base import BakeoffResult, Method, MethodCapabilities, wall_cmd
from egas.rungs import Rung, generic_t4, propose_from_symbol


class GenericMethod(Method):
    kind = "generic"

    def __init__(self, contract: Contract):
        super().__init__(contract)
        self._applied: list[str] = []

    def capabilities(self) -> MethodCapabilities:
        return MethodCapabilities(
            automated=list(generic_t4()) if self.contract.opt_build else [],
            source=propose_from_symbol("hot_path", 0.0),
        )

    def ensure_built(self) -> list[str]:
        logs: list[str] = []
        if self.contract.stock_build and not self.stock_exists():
            self.run_cmd(self.contract.resolve(self.contract.stock_build))
            logs.append("stock_build")
        if self.contract.opt_build and not self.opt_exists():
            self.run_cmd(self.contract.resolve(self.contract.opt_build))
            logs.append("opt_build")
        return logs

    def apply(self, rung: Rung) -> str:
        if not rung.automated:
            raise RuntimeError(f"{rung.id} is a propose-only rung")
        if not self.contract.opt_build:
            raise RuntimeError("no opt_build in contract — cannot apply T4")
        cmd = self.contract.resolve(self.contract.opt_build)
        extra = {
            "t4_o3_lto": "CFLAGS='-O3 -flto' CXXFLAGS='-O3 -flto'",
            "t4_pgo": "PGO=1",
            "t4_jemalloc": "LDLIBS='-ljemalloc'",
        }.get(rung.id, "")
        self.run_cmd(f"{extra} {cmd}".strip())
        self._applied.append(rung.id)
        return f"applied {rung.id}: {cmd}"

    def bakeoff(self, workload: Workload, *, runs: int | None = None) -> BakeoffResult:
        runs = runs or self.contract.runs
        stock_bin = self.contract.resolve(self.contract.stock_bin)
        opt_bin = self.contract.resolve(self.contract.opt_bin)
        if not Path(stock_bin).is_file() or not Path(opt_bin).is_file():
            raise FileNotFoundError(f"missing binaries: stock={stock_bin} opt={opt_bin}")

        stock_times: list[float] = []
        opt_times: list[float] = []
        match = True
        note = "MATCH"
        tmp = Path(tempfile.mkdtemp(prefix="egas_"))
        try:
            if self.contract.warmup:
                self._one(stock_bin, workload, tmp / "wu_stock")
                self._one(opt_bin, workload, tmp / "wu_opt")
            for i in range(1, runs + 1):
                s_out = tmp / f"stock_{i}"
                o_out = tmp / f"opt_{i}"
                stock_times.append(self._one(stock_bin, workload, s_out))
                opt_times.append(self._one(opt_bin, workload, o_out))
                ok, why = self._match(s_out, o_out, workload)
                if not ok:
                    match = False
                    note = why
                    break
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return BakeoffResult(workload.id, match, note, stock_times, opt_times)

    def _one(self, binary: str, workload: Workload, outdir: Path) -> float:
        outdir.mkdir(parents=True, exist_ok=True)
        cmd = self.contract.resolve(
            self.contract.run_template,
            bin=binary,
            workload_id=workload.id,
            args=workload.args,
            outdir=str(outdir),
            output=str(outdir / "out.txt"),
        )
        return wall_cmd(cmd, cwd=self.contract.root)

    def _match(self, stock_out: Path, opt_out: Path, workload: Workload) -> tuple[bool, str]:
        cmd = self.contract.resolve(
            self.contract.match_template,
            stock_out=str(stock_out / "out.txt"),
            opt_out=str(opt_out / "out.txt"),
            workload_id=workload.id,
            args=workload.args,
        )
        try:
            self.run_cmd(cmd)
            return True, "MATCH"
        except Exception as exc:  # noqa: BLE001 — MATCH is a boolean oracle
            return False, f"DIFF: {exc}"
