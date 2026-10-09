"""Load a finished A/B savings dump for either HMMER mode.

``acts.savings_analysis.load_job`` accepts only hmmsearch. The sensitivity
and measured-stock scripts need the same checks for the post-hoc hmmscan
dumps. The formula stays in ``acts.savings_analysis``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MODES = {"hmmsearch", "hmmscan"}


def load_savings_job(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text())
    collection = raw.get("collection")
    mode = raw.get("mode")
    if collection not in {"A", "B"} or mode not in MODES:
        raise ValueError(f"{path}: expected an A/B hmmsearch or hmmscan savings JSON")
    if raw.get("stopped") or raw.get("decision"):
        raise ValueError(f"{path}: stopped savings run")
    rows = raw.get("genomes")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path}: no genome rows")
    positions = [int(row["position"]) for row in rows]
    if positions != list(range(1, len(rows) + 1)):
        raise ValueError(f"{path}: positions are not a complete ordered prefix")
    return raw
