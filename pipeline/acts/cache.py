"""Persistent per-record cache. Keyed by tool argv + record text.

This is the headline: a later run pays only for unseen records.
Hidden inputs (index files, env) are NOT traced yet — do not claim Rattle keys.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def namespace(argv: list[str], kind: str) -> str:
    h = hashlib.sha256()
    h.update(kind.encode())
    h.update(b"\0")
    for a in argv:
        h.update(a.encode())
        h.update(b"\0")
    return h.hexdigest()[:16]


class RecordCache:
    def __init__(self, path: Path, *, argv: list[str], kind: str):
        self.path = path
        self.ns = namespace(argv, kind)
        self._data: dict[str, str] = {}
        if path.is_file():
            for line in path.read_text().splitlines():
                if not line:
                    continue
                row = json.loads(line)
                if row.get("ns") == self.ns:
                    self._data[row["record"]] = row["output"]

    def get(self, record: str) -> str | None:
        return self._data.get(record)

    def put(self, record: str, output: str) -> None:
        self._data[record] = output

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w") as fh:
            for rec, out in self._data.items():
                fh.write(json.dumps({"ns": self.ns, "record": rec, "output": out}) + "\n")

    def __len__(self) -> int:
        return len(self._data)
