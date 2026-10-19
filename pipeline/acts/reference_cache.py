"""Row cache for reference-side reuse.

A row is keyed by the record, the reference entry's content hash, and the
argv with the reference path removed. Coverage is stored separately so a
record that produced no row is not mistaken for a record that was never run.

Coverage is (entry, record set): a record set is stored once and every entry
run on it points at it. Per-pair coverage (the legacy `coverage` table) grew
as records × entries (one genome × one release ~ 10^8 rows); it is still read
so caches filled before this layout keep working.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from acts.cache import UNREADABLE, FingerprintMemo, _connect

# Marker hashed in place of a digest when argv[0] does not resolve to a file
# on PATH (for example an in-process runner in tests). It is constant, so the
# namespace stays deterministic.
UNRESOLVED_BINARY = "unresolved"

_BINARY_MEMO = FingerprintMemo(None)

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
CREATE TABLE IF NOT EXISTS recsets (
  ns TEXT NOT NULL,
  recset_id TEXT NOT NULL,
  record_key TEXT NOT NULL,
  PRIMARY KEY (ns, recset_id, record_key)
);
CREATE TABLE IF NOT EXISTS entry_cover (
  ns TEXT NOT NULL,
  entry_hash TEXT NOT NULL,
  recset_id TEXT NOT NULL,
  PRIMARY KEY (ns, entry_hash, recset_id)
);
CREATE TABLE IF NOT EXISTS entry_group (
  ns TEXT NOT NULL,
  entry_hash TEXT NOT NULL,
  group_id TEXT NOT NULL,
  PRIMARY KEY (ns, entry_hash, group_id)
);
CREATE TABLE IF NOT EXISTS cost_history (
  ns TEXT NOT NULL,
  kind TEXT NOT NULL,
  f_delta REAL NOT NULL,
  stock_s REAL NOT NULL,
  tare_s REAL NOT NULL,
  discovery_s REAL NOT NULL
);
"""


def recset_id(record_keys) -> str:
    blob = "\0".join(sorted(record_keys))
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def program_binary(argv: list[str]) -> dict:
    """Resolved argv[0] and its content digest, as the record cache keys it.

    A different binary at the same path (a tool upgrade) gets a different
    digest, so cached rows and the stored contract are not reused for it.
    """
    exe = shutil.which(argv[0]) if argv else None
    if not exe:
        return {"path": argv[0] if argv else "", "digest": UNRESOLVED_BINARY}
    path = Path(exe)
    try:
        resolved = str(path.resolve())
    except OSError:
        resolved = str(path)
    try:
        digest = _BINARY_MEMO.file_digest(path)
    except OSError:
        digest = UNREADABLE
    return {"path": resolved, "digest": digest}


def argv_namespace(argv: list[str], reference: Path | None, baseline: str | None) -> str:
    """Hash argv with the reference path removed. The baseline mode and the
    program binary's content digest are part of the key."""
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
    blob += "\0binary:" + program_binary(argv)["digest"]
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

    def coverage_map(self, ns: str) -> dict[str, set[str]]:
        """entry hash -> covered record keys, read in two passes (plus legacy pairs)."""
        sets: dict[str, frozenset[str]] = {}
        members: dict[str, list[str]] = {}
        for rid, key in self._conn.execute(
            "SELECT recset_id, record_key FROM recsets WHERE ns = ?", (ns,)
        ):
            members.setdefault(rid, []).append(key)
        for rid, keys in members.items():
            sets[rid] = frozenset(keys)
        out: dict[str, set[str]] = {}
        for entry_hash, rid in self._conn.execute(
            "SELECT entry_hash, recset_id FROM entry_cover WHERE ns = ?", (ns,)
        ):
            out.setdefault(entry_hash, set()).update(sets.get(rid, ()))
        for entry_hash, key in self._conn.execute(
            "SELECT entry_hash, record_key FROM coverage WHERE ns = ?", (ns,)
        ):
            out.setdefault(entry_hash, set()).add(key)
        return out

    def covered_hashes(self, ns: str) -> set[str]:
        return set(self.coverage_map(ns))

    def covered_records(self, ns: str, entry_hash: str) -> set[str]:
        return set(self.coverage_map(ns).get(entry_hash, set()))

    def load_table_rows(self, ns: str, table: str, entry_hashes: set[str], record_keys: set[str]) -> list[dict]:
        """All cached rows of one table whose entry and record are in the given sets. One scan."""
        found: list[dict] = []
        for record_key, entry_hash, payload in self._conn.execute(
            "SELECT record_key, entry_hash, payload FROM rows WHERE ns = ? AND table_name = ?",
            (ns, table),
        ):
            if entry_hash in entry_hashes and record_key in record_keys:
                found.append(json.loads(payload))
        return found

    def cover_and_replace(
        self,
        ns: str,
        tables: list[str],
        entry_hashes: list[str],
        record_keys: list[str],
        rows_by_table: dict[str, list[dict]],
    ) -> None:
        """Mark every (record, entry) in the product covered and replace those rows."""
        if not entry_hashes or not record_keys:
            return
        rid = recset_id(record_keys)
        wanted_entries = set(entry_hashes)
        wanted_records = set(record_keys)
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO recsets (ns, recset_id, record_key) VALUES (?, ?, ?)",
                [(ns, rid, key) for key in record_keys],
            )
            self._conn.executemany(
                "INSERT OR IGNORE INTO entry_cover (ns, entry_hash, recset_id) VALUES (?, ?, ?)",
                [(ns, entry_hash, rid) for entry_hash in entry_hashes],
            )
            for table in tables:
                stale = [
                    (ns, record_key, entry_hash, table)
                    for record_key, entry_hash in self._conn.execute(
                        "SELECT record_key, entry_hash FROM rows WHERE ns = ? AND table_name = ?",
                        (ns, table),
                    )
                    if entry_hash in wanted_entries and record_key in wanted_records
                ]
                self._conn.executemany(
                    "DELETE FROM rows WHERE ns = ? AND record_key = ? AND entry_hash = ? AND table_name = ?",
                    stale,
                )
                self._conn.executemany(
                    """INSERT OR REPLACE INTO rows
                       (ns, record_key, entry_hash, table_name, row_index, payload)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    [
                        (ns, row["record_key"], row["entry_hash"], table, row.get("row_index") or "", json.dumps(row))
                        for row in rows_by_table.get(table, [])
                    ],
                )

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
            self._conn.executemany(
                "INSERT OR REPLACE INTO coverage (ns, entry_hash, record_key) VALUES (?, ?, ?)",
                [(ns, entry_hash, record_key) for record_key, entry_hash in pairs],
            )
            self._conn.executemany(
                "DELETE FROM rows WHERE ns = ? AND record_key = ? AND entry_hash = ? AND table_name = ?",
                [(ns, record_key, entry_hash, table) for record_key, entry_hash in pairs],
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
                self._conn.execute(
                    "DELETE FROM entry_cover WHERE ns = ? AND entry_hash = ?", (ns, entry_hash)
                )
                self._conn.execute(
                    "DELETE FROM entry_group WHERE ns = ? AND entry_hash = ?", (ns, entry_hash)
                )

    def group_map(self, ns: str) -> dict[str, set[str]]:
        """content hash -> group ids stored when that hash was cached."""
        out: dict[str, set[str]] = {}
        for entry_hash, group_id in self._conn.execute(
            "SELECT entry_hash, group_id FROM entry_group WHERE ns = ?", (ns,)
        ):
            out.setdefault(entry_hash, set()).add(group_id)
        return out

    def replace_groups(self, ns: str, groups: dict[str, set[str]]) -> None:
        """Replace the group ids recorded for these content hashes."""
        with self._conn:
            for entry_hash, group_ids in groups.items():
                self._conn.execute(
                    "DELETE FROM entry_group WHERE ns = ? AND entry_hash = ?",
                    (ns, entry_hash),
                )
                # An empty id records "in no group". No row at all means the
                # cache never stored groups, which the caller treats as unknown.
                recorded = group_ids or {""}
                self._conn.executemany(
                    "INSERT OR IGNORE INTO entry_group (ns, entry_hash, group_id) VALUES (?, ?, ?)",
                    [(ns, entry_hash, group_id) for group_id in recorded],
                )


    def add_cost_observation(
        self,
        ns: str,
        *,
        kind: str,
        f_delta: float,
        stock_s: float,
        tare_s: float,
        discovery_s: float,
    ) -> None:
        """One measured fill or update: changed fraction, stock wall, TARE wall, discovery wall."""
        with self._conn:
            self._conn.execute(
                """INSERT INTO cost_history
                   (ns, kind, f_delta, stock_s, tare_s, discovery_s)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (ns, kind, float(f_delta), float(stock_s), float(tare_s), float(discovery_s)),
            )

    def cost_fit(self, ns: str) -> dict | None:
        """Mean a, c for this namespace. a = discovery/(f·stock), c = (TARE−discovery)/stock.

        Rows with a non-positive changed fraction or stock wall are ignored.
        No usable row means the caller keeps the documented default threshold.
        """
        a_vals: list[float] = []
        c_vals: list[float] = []
        for f_delta, stock_s, tare_s, discovery_s in self._conn.execute(
            "SELECT f_delta, stock_s, tare_s, discovery_s FROM cost_history WHERE ns = ?",
            (ns,),
        ):
            if f_delta <= 0 or stock_s <= 0:
                continue
            a_vals.append(discovery_s / (f_delta * stock_s))
            c_vals.append((tare_s - discovery_s) / stock_s)
        if not a_vals:
            return None
        return {
            "a": sum(a_vals) / len(a_vals),
            "c": sum(c_vals) / len(c_vals),
            "n": len(a_vals),
        }


def connect_cache(path: Path) -> ReferenceCache:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() not in {".sqlite", ".db", ".sqlite3"}:
        path = Path(str(path) + ".sqlite")
    return ReferenceCache(path)
