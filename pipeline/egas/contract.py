"""Locked fairness contract. Nothing in the driver may silently change these knobs."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    """Contract is missing a required field or fails a fairness check."""


@dataclass(frozen=True)
class Workload:
    id: str
    args: str = ""
    held_out: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Contract:
    name: str
    method: str
    target_speedup: float
    threads: int
    runs: int
    warmup: int
    amdahl_min_fraction: float
    allow_t4_assist: bool
    root: Path
    stock_build: str
    opt_build: str
    stock_bin: str
    opt_bin: str
    run_template: str
    match_template: str
    profile_path: Path | None
    workloads: tuple[Workload, ...]
    extra: dict[str, Any] = field(default_factory=dict)

    def diagnostic(self) -> tuple[Workload, ...]:
        d = tuple(w for w in self.workloads if not w.held_out)
        return d or self.workloads[:1]

    def held_out(self) -> tuple[Workload, ...]:
        h = tuple(w for w in self.workloads if w.held_out)
        return h or self.workloads

    def resolve(self, template: str, **more: str) -> str:
        mapping = {
            "root": str(self.root),
            "stock_bin": self.stock_bin,
            "opt_bin": self.opt_bin,
            "threads": str(self.threads),
            **{k: str(v) for k, v in self.extra.items() if isinstance(v, (str, int, float, Path))},
            **more,
        }
        try:
            return template.format(**mapping)
        except KeyError as exc:
            raise ContractError(f"unresolved placeholder {exc} in {template!r}") from exc


def _require(data: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise ContractError(f"missing keys: {', '.join(missing)}")


def load_contract(path: Path) -> Contract:
    path = path.resolve()
    raw = tomllib.loads(path.read_text())
    _require(raw, "contract", "method")
    c = raw["contract"]
    m = raw["method"]
    _require(c, "name", "target_speedup", "threads", "runs")
    _require(m, "kind", "stock_bin", "opt_bin", "run", "match")

    root = Path(c.get("root", path.parent.parent)).expanduser()
    if not root.is_absolute():
        root = (path.parent / root).resolve()
    else:
        root = root.resolve()

    workloads: list[Workload] = []
    for row in raw.get("workloads", []):
        if "id" not in row:
            raise ContractError("workload missing id")
        extra = {k: v for k, v in row.items() if k not in {"id", "args", "held_out"}}
        workloads.append(
            Workload(
                id=str(row["id"]),
                args=str(row.get("args", "")),
                held_out=bool(row.get("held_out", True)),
                extra=extra,
            )
        )
    if not workloads:
        raise ContractError("contract needs at least one [[workloads]] entry")

    profile = c.get("profile")
    profile_path = Path(profile).expanduser() if profile else None
    if profile_path and not profile_path.is_absolute():
        profile_path = (path.parent / profile_path).resolve()

    extra = {
        k: v
        for k, v in {**c, **m, **raw.get("star", {}), **raw.get("generic", {})}.items()
        if k
        not in {
            "name",
            "target_speedup",
            "threads",
            "runs",
            "warmup",
            "amdahl_min_fraction",
            "allow_t4_assist",
            "root",
            "profile",
            "kind",
            "stock_build",
            "opt_build",
            "stock_bin",
            "opt_bin",
            "run",
            "match",
        }
    }

    contract = Contract(
        name=str(c["name"]),
        method=str(m["kind"]),
        target_speedup=float(c["target_speedup"]),
        threads=int(c["threads"]),
        runs=int(c["runs"]),
        warmup=int(c.get("warmup", 1)),
        amdahl_min_fraction=float(c.get("amdahl_min_fraction", 0.50)),
        allow_t4_assist=bool(c.get("allow_t4_assist", True)),
        root=root,
        stock_build=str(m.get("stock_build", "")),
        opt_build=str(m.get("opt_build", "")),
        stock_bin=str(m["stock_bin"]),
        opt_bin=str(m["opt_bin"]),
        run_template=str(m["run"]),
        match_template=str(m["match"]),
        profile_path=profile_path,
        workloads=tuple(workloads),
        extra=extra,
    )
    validate_fairness(contract)
    return contract


def validate_fairness(contract: Contract) -> None:
    if contract.threads < 1:
        raise ContractError("threads must be ≥ 1")
    if contract.runs < 3:
        raise ContractError("runs must be ≥ 3 (mean±variability, not a single timing)")
    if contract.target_speedup < 1.0:
        raise ContractError("target_speedup must be ≥ 1")
    if contract.stock_bin == contract.opt_bin:
        raise ContractError("stock_bin and opt_bin must differ — same binary is not a bake-off")
    forbidden = {"extra_threads_opt", "different_compression", "oversized_index"}
    sneaky = forbidden.intersection(contract.extra)
    if sneaky:
        raise ContractError(f"disallowed fairness knobs present: {sorted(sneaky)}")
