"""Method plugin: one existing program (STAR, a generic binary, the fat_copy fixture)."""

from __future__ import annotations

import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, stdev

from egas.contract import Contract, Workload
from egas.rungs import Rung


@dataclass
class TimedRun:
    wall_sec: float
    output_path: Path


@dataclass
class BakeoffResult:
    workload_id: str
    match: bool
    match_note: str
    stock: list[float]
    opt: list[float]

    @property
    def n(self) -> int:
        return min(len(self.stock), len(self.opt))

    @property
    def mean_speedup(self) -> float | None:
        if not self.stock or not self.opt:
            return None
        om = mean(self.opt)
        return mean(self.stock) / om if om else None

    @property
    def min_pair(self) -> float | None:
        if self.n == 0:
            return None
        return min(s / o for s, o in zip(self.stock, self.opt) if o > 0)

    def summary(self) -> str:
        if not self.match:
            return f"{self.workload_id}: {self.match_note}"
        sm, om = mean(self.stock), mean(self.opt)
        ss = stdev(self.stock) if len(self.stock) > 1 else 0.0
        os_ = stdev(self.opt) if len(self.opt) > 1 else 0.0
        return (
            f"{self.workload_id}: stock {sm:.4f}±{ss:.4f}s  opt {om:.4f}±{os_:.4f}s  "
            f"mean {self.mean_speedup:.3f}×  min_pair {self.min_pair:.3f}×  MATCH"
        )


@dataclass
class MethodCapabilities:
    automated: list[Rung] = field(default_factory=list)
    source: list[Rung] = field(default_factory=list)


class Method(ABC):
    kind: str

    def __init__(self, contract: Contract):
        self.contract = contract

    @abstractmethod
    def capabilities(self) -> MethodCapabilities: ...

    @abstractmethod
    def apply(self, rung: Rung) -> str:
        """Apply an automated rung. Return a log line. Raise if it cannot run."""

    @abstractmethod
    def bakeoff(self, workload: Workload, *, runs: int | None = None) -> BakeoffResult: ...

    def stock_exists(self) -> bool:
        return Path(self.contract.resolve(self.contract.stock_bin)).is_file()

    def opt_exists(self) -> bool:
        return Path(self.contract.resolve(self.contract.opt_bin)).is_file()

    def run_cmd(self, cmd: str, *, cwd: Path | None = None, timeout: int = 3600) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            shell=True,
            check=True,
            cwd=cwd or self.contract.root,
            text=True,
            capture_output=True,
            timeout=timeout,
        )


def wall_cmd(cmd: str, cwd: Path, timeout: int = 3600) -> float:
    start = time.perf_counter()
    subprocess.run(
        cmd,
        shell=True,
        check=True,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return time.perf_counter() - start
