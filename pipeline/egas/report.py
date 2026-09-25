"""Machine-readable + human decision record."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from egas.amdahl import AmdahlResult
from egas.decide import DecisionRecord
from egas.methods.base import BakeoffResult


@dataclass
class RunReport:
    contract: str
    method: str
    decision: str
    reason: str
    amdahl: dict[str, Any] | None = None
    bakeoffs: list[dict[str, Any]] = field(default_factory=list)
    proposed: list[dict[str, str]] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n")


def amdahl_dict(res: AmdahlResult) -> dict[str, Any]:
    return {
        "status": res.status,
        "legal_fraction": res.legal_fraction,
        "max_speedup": res.max_speedup,
        "target": res.target,
        "reason": res.reason,
        "hottest": res.hottest_legal.symbol if res.hottest_legal else None,
    }


def bakeoff_dict(b: BakeoffResult) -> dict[str, Any]:
    return {
        "workload": b.workload_id,
        "match": b.match,
        "note": b.match_note,
        "n": b.n,
        "stock": b.stock,
        "opt": b.opt,
        "mean_speedup": b.mean_speedup,
        "min_pair": b.min_pair,
    }


def format_human(report: RunReport, rec: DecisionRecord) -> str:
    lines = [
        f"contract: {report.contract}",
        f"method:   {report.method}",
        f"decision: {rec.decision.value}",
        f"why:      {rec.reason}",
    ]
    if report.amdahl:
        lines.append(f"amdahl:   {report.amdahl['status']} — {report.amdahl['reason']}")
    for row in report.bakeoffs:
        mp = row.get("min_pair")
        mp_s = f"{mp:.3f}×" if isinstance(mp, float) else "—"
        lines.append(
            f"bakeoff:  {row['workload']} match={row['match']} n={row['n']} min_pair={mp_s}"
        )
    if report.proposed:
        lines.append("propose:")
        for p in report.proposed:
            lines.append(f"  - [{p['cls']}] {p['title']}: {p['hint']}")
    return "\n".join(lines) + "\n"
