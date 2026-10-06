"""Row cache for reference-side reuse.

A row is keyed by the record, the reference entry's content hash, and the
argv with the reference path removed. Coverage is stored separately so a
record that produced no row is not mistaken for a record that was never run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from acts.cache import _connect

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
  ns TEXT PRIMARY KEY,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rows (
  ns TEXT NOT NULL,
  record_key TEXT NOT NULL,
  entry_hash TEXT NOT NULL,
  table_name TEXT NOT NULL,
  row_index TEXT NOT NULL,
  payload TEXT NOT NULL,
  PRIMARY KEY (ns, record_key, entry_hash, table_name, row_index)
);
CREATE TABLE IF NOT EXISTS coverage (
  ns TEXT NOT NULL,
  entry_hash TEXT NOT NULL,
  record_key TEXT NOT NULL,
  PRIMARY KEY (ns, entry_hash, record_key)
);
"""


def argv_namespace(argv: list[str], reference: Path | None, baseline: str | None) -> str:
    """Hash argv with the reference path removed. The baseline mode is part of the key."""
    ref = None
    if reference is not None:
        try:
            ref = str(reference.resolve())
        except OSError:
            ref = str(reference)
    kept: list[str] = []
    for token in argv:
        if token == "{reference}":
            continue
        if ref is not None and _is_path(token, ref):
            continue
        kept.append(token)
    blob = "\0".join(kept) + "\0baseline:" + (baseline or "fit")
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _is_path(token: str, resolved: str) -> bool:
    try:
        return str(Path(token).expanduser().resolve()) == resolved
    except OSError:
        return False


class ReferenceCache:
    def __init__(self, path: Path):
        self.path = path
        self._conn = _connect(path)
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def load_contract(self, ns: str) -> dict | None:
        row = self._conn.execute("SELECT payload FROM contracts WHERE ns = ?", (ns,)).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def save_contract(self, ns: str, payload: dict) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO contracts (ns, payload) VALUES (?, ?)",
                (ns, json.dumps(payload)),
            )

    def covered_hashes(self, ns: str) -> set[str]:
        return {
            row[0]
            for row in self._conn.execute(
                "SELECT DISTINCT entry_hash FROM coverage WHERE ns = ?",
                (ns,),
            )
        }

    def covered_records(self, ns: str, entry_hash: str) -> set[str]:
        return {
            row[0]
            for row in self._conn.execute(
                "SELECT record_key FROM coverage WHERE ns = ? AND entry_hash = ?",
                (ns, entry_hash),
            )
        }

    def load_rows(self, ns: str, entry_hash: str, record_keys: set[str], table: str) -> list[dict]:
        if not record_keys:
            return []
        found: list[dict] = []
        keys = list(record_keys)
        for start in range(0, len(keys), 400):
            chunk = keys[start : start + 400]
            marks = ",".join("?" for _ in chunk)
            query = (
                f"SELECT payload FROM rows WHERE ns = ? AND entry_hash = ? AND table_name = ? "
                f"AND record_key IN ({marks})"
            )
            for (payload,) in self._conn.execute(query, (ns, entry_hash, table, *chunk)):
                found.append(json.loads(payload))
        return found

    def replace_pairs(
        self,
        ns: str,
        table: str,
        pairs: list[tuple[str, str]],
        rows: list[dict],
    ) -> None:
        """Mark (record, entry) pairs covered and replace their rows for one table."""
        with self._conn:
            for record_key, entry_hash in pairs:
                self._conn.execute(
                    "INSERT OR REPLACE INTO coverage (ns, entry_hash, record_key) VALUES (?, ?, ?)",
                    (ns, entry_hash, record_key),
                )
                self._conn.execute(
                    "DELETE FROM rows WHERE ns = ? AND record_key = ? AND entry_hash = ? AND table_name = ?",
                    (ns, record_key, entry_hash, table),
                )
            for row in rows:
                self._conn.execute(
                    """INSERT OR REPLACE INTO rows
                       (ns, record_key, entry_hash, table_name, row_index, payload)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        ns,
                        row["record_key"],
                        row["entry_hash"],
                        table,
                        row.get("row_index") or "",
                        json.dumps(row),
                    ),
                )

    def drop_hashes(self, ns: str, entry_hashes: set[str]) -> None:
        if not entry_hashes:
            return
        with self._conn:
            for entry_hash in entry_hashes:
                self._conn.execute(
                    "DELETE FROM rows WHERE ns = ? AND entry_hash = ?", (ns, entry_hash)
                )
                self._conn.execute(
                    "DELETE FROM coverage WHERE ns = ? AND entry_hash = ?", (ns, entry_hash)
                )


def connect_cache(path: Path) -> ReferenceCache:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() not in {".sqlite", ".db", ".sqlite3"}:
        path = Path(str(path) + ".sqlite")
    return ReferenceCache(path)
