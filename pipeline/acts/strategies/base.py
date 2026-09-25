from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class StrategyResult:
    strategy: str
    decision: str
    reason: str
    extra: dict = field(default_factory=dict)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"strategy: {self.strategy}",
            f"decision: {self.decision}",
            f"why:      {self.reason}",
        ]
        for k, v in self.extra.items():
            lines.append(f"{k}: {v}")
        path.write_text("\n".join(lines) + "\n")


class Strategy(ABC):
    name: str

    @abstractmethod
    def run(self) -> StrategyResult: ...
