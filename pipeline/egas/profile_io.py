"""Profile ingest. Accept a JSON schema or a `perf report --stdio` dump."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# Default: treat OS/runtime noise as illegal to mutate for a 2× claim.
ILLEGAL_SYMBOL_RE = re.compile(
    r"(zcat|gzcat|pigz|zlib|libz|jemalloc|malloc|free|memcpy|memmove|"
    r"pthread|syscall|kernel|vdso|dyld|ld-linux|samtools|sort)",
    re.I,
)

PERF_LINE = re.compile(
    r"^\s*(?P<pct>[0-9]+(?:\.[0-9]+)?)\s*%\s+\S+\s+\S+\s+\[.\]\s+(?P<sym>\S+)"
)


@dataclass(frozen=True)
class Region:
    symbol: str
    fraction: float
    legal: bool
    source: str = ""


@dataclass(frozen=True)
class Profile:
    tool: str
    regions: tuple[Region, ...]

    @property
    def hottest_legal(self) -> Region | None:
        legal = [r for r in self.regions if r.legal]
        return max(legal, key=lambda r: r.fraction) if legal else None


def load_profile(path: Path) -> Profile:
    text = path.read_text(errors="replace")
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return _from_json(json.loads(text))
    return parse_perf_report(text)


def _from_json(data: object) -> Profile:
    if isinstance(data, list):
        data = {"tool": "json", "regions": data}
    if not isinstance(data, dict):
        raise ValueError("profile JSON must be an object or list")
    regions: list[Region] = []
    for row in data.get("regions", []):
        symbol = str(row["symbol"])
        frac = float(row["fraction"])
        legal = bool(row["legal"]) if "legal" in row else _default_legal(symbol)
        regions.append(
            Region(
                symbol=symbol,
                fraction=frac,
                legal=legal,
                source=str(row.get("file", "")),
            )
        )
    _check_fractions(regions)
    return Profile(tool=str(data.get("tool", "json")), regions=tuple(regions))


def parse_perf_report(text: str) -> Profile:
    regions: list[Region] = []
    for line in text.splitlines():
        m = PERF_LINE.match(line)
        if not m:
            continue
        symbol = m.group("sym")
        frac = float(m.group("pct")) / 100.0
        regions.append(
            Region(
                symbol=symbol,
                fraction=frac,
                legal=_default_legal(symbol),
            )
        )
    if not regions:
        raise ValueError("no perf report rows parsed")
    _check_fractions(regions)
    return Profile(tool="perf", regions=tuple(regions))


def _default_legal(symbol: str) -> bool:
    return ILLEGAL_SYMBOL_RE.search(symbol) is None


def _check_fractions(regions: list[Region]) -> None:
    total = sum(r.fraction for r in regions)
    if total > 1.05:
        raise ValueError(f"profile fractions sum to {total:.3f} > 1.05 — check units")
