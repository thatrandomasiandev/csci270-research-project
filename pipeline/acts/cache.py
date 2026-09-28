"""Persistent per-record cache. Keyed by tool argv, argv-named inputs, and record text.

This is the headline: a later run pays only for unseen records.
The namespace fingerprints the tool binary and every existing path named in argv
(docs/CACHE_KEY_PROTOCOL.md). Files the tool opens that argv does not name, and
env vars, are NOT covered — do not claim Rattle-style traced keys.

Durable store is SQLite (WAL, one transaction per save). JSONL files are
migrated automatically. This is engineering, not a new cache theory.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path

INPUT_TOKEN = "{input}"
_CHUNK = 1 << 20
UNREADABLE = "unreadable"
_SQLITE_MAGIC = b"SQLite format 3\000"
_SQLITE_SUFFIXES = {".sqlite", ".db", ".sqlite3"}
_BUSY_TIMEOUT_MS = 60_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  ns TEXT NOT NULL,
  record TEXT NOT NULL,
  output TEXT NOT NULL,
  PRIMARY KEY (ns, record)
);
CREATE TABLE IF NOT EXISTS namespaces (
  ns TEXT PRIMARY KEY,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fingerprints (
  memo_key TEXT PRIMARY KEY,
  digest TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def sqlite_path_for(path: Path) -> Path:
    """Durable SQLite path for a caller-facing cache path (may still be .jsonl)."""
    if path.suffix.lower() in _SQLITE_SUFFIXES:
        return path
    return Path(str(path) + ".sqlite")


def _is_sqlite_file(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 16:
        return False
    with path.open("rb") as fh:
        return fh.read(16) == _SQLITE_MAGIC


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    last_err: sqlite3.OperationalError | None = None
    for attempt in range(80):
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(str(db_path), timeout=_BUSY_TIMEOUT_MS / 1000)
            conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA)
            return conn
        except sqlite3.OperationalError as exc:
            last_err = exc
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            time.sleep(0.01 * min(attempt + 1, 20))
    assert last_err is not None
    raise last_err


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


class FingerprintMemo:
    """Content hashes keyed by (path, size, mtime_ns, inode), persisted in a sidecar.

    When a SQLite connection is provided (RecordCache), rows are upserted in a
    transaction (WAL). The JSON sidecar remains an audit dump. Standalone use
    with only a JSON path is unchanged.
    """

    def __init__(self, path: Path | None, *, conn: sqlite3.Connection | None = None):
        self.path = path
        self._conn = conn
        self._rows: dict[str, str] = {}
        self._pending: dict[str, str] = {}
        self.hits = 0
        if conn is not None:
            for key, digest in conn.execute("SELECT memo_key, digest FROM fingerprints"):
                self._rows[key] = digest
        if path is not None and path.is_file():
            try:
                loaded = json.loads(path.read_text())
            except json.JSONDecodeError:
                loaded = {}
            for key, digest in loaded.items():
                if key not in self._rows:
                    self._rows[key] = digest
                    self._pending[key] = digest

    def file_digest(self, p: Path) -> str:
        st = p.stat()
        key = f"{p}\0{st.st_size}\0{st.st_mtime_ns}\0{st.st_ino}"
        if key in self._rows:
            self.hits += 1
            return self._rows[key]
        digest = _sha256_file(p)
        self._rows[key] = digest
        self._pending[key] = digest
        return digest

    def save(self) -> None:
        if self._conn is not None:
            if self._pending:
                with self._conn:
                    self._conn.executemany(
                        "INSERT OR REPLACE INTO fingerprints (memo_key, digest) VALUES (?, ?)",
                        list(self._pending.items()),
                    )
                self._pending.clear()
            self._dump_json_from_sqlite()
            return
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._rows, indent=1, sort_keys=True) + "\n")

    def _dump_json_from_sqlite(self) -> None:
        if self.path is None or self._conn is None:
            return
        rows = {
            key: digest
            for key, digest in self._conn.execute("SELECT memo_key, digest FROM fingerprints")
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n")


def _relpath(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def _dir_digest(root: Path) -> tuple[str, list[str]]:
    """Metadata hash of every file under root. Unreadable entries are recorded, not skipped."""
    h = hashlib.sha256()
    errors: list[str] = []

    def mark(rel: str) -> None:
        errors.append(rel)
        h.update(f"{rel}\0{UNREADABLE}\n".encode())

    def onerror(err: OSError) -> None:
        name = getattr(err, "filename", None)
        mark(_relpath(root, Path(name)) if name else UNREADABLE)

    try:
        walker = os.walk(root, onerror=onerror)
        for dirpath, dirnames, filenames in walker:
            dirnames.sort()
            for name in sorted(filenames):
                p = Path(dirpath) / name
                rel = _relpath(root, p)
                try:
                    st = p.stat()
                except OSError:
                    mark(rel)
                    continue
                h.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
    except OSError:
        mark(".")
    return h.hexdigest(), errors


def _path_candidates(token: str) -> list[str]:
    if INPUT_TOKEN in token:
        return []
    out = [token]
    if token.startswith("-") and "=" in token:
        out.append(token.split("=", 1)[1])
    return out


def fingerprint_paths(
    paths: list[str | Path],
    memo: FingerprintMemo | None = None,
    *,
    kind: str = "traced",
    seen: set[str] | None = None,
) -> list[dict]:
    """Fingerprint extra regular files (probe-time traces). Same digest rules as argv files."""
    memo = memo or FingerprintMemo(None)
    seen = seen if seen is not None else set()
    comps: list[dict] = []
    for raw in paths:
        p = Path(raw)
        try:
            resolved = str(p.resolve())
        except OSError:
            resolved = str(p)
        if resolved in seen:
            continue
        seen.add(resolved)
        if not p.is_file() and not p.is_symlink():
            continue
        try:
            comps.append({"kind": kind, "path": resolved, "digest": memo.file_digest(p)})
        except OSError:
            comps.append({"kind": kind, "path": resolved, "digest": UNREADABLE, "error": UNREADABLE})
    return comps


def fingerprint_inputs(argv: list[str], memo: FingerprintMemo | None = None) -> list[dict]:
    """Fingerprint the tool binary and every existing path named in argv.

    Unreadable files and broken directory entries do not raise. They are
    recorded on the component (error / errors) with digest 'unreadable' so a
    failed fingerprint cannot collide with a complete one.
    """
    memo = memo or FingerprintMemo(None)
    comps: list[dict] = []
    seen: set[str] = set()

    def resolved_of(p: Path) -> str:
        try:
            return str(p.resolve())
        except OSError:
            return str(p)

    def add(kind: str, p: Path) -> None:
        resolved = resolved_of(p)
        if resolved in seen:
            return
        seen.add(resolved)
        if kind == "dir":
            try:
                digest, errors = _dir_digest(p)
            except OSError:
                comps.append({"kind": kind, "path": resolved, "digest": UNREADABLE, "error": UNREADABLE})
                return
            comp: dict = {"kind": kind, "path": resolved, "digest": digest}
            if errors:
                comp["errors"] = errors
            comps.append(comp)
            return
        try:
            comps.append({"kind": kind, "path": resolved, "digest": memo.file_digest(p)})
        except OSError:
            comps.append({"kind": kind, "path": resolved, "digest": UNREADABLE, "error": UNREADABLE})

    if argv:
        exe = shutil.which(argv[0])
        if exe:
            add("binary", Path(exe))
    for token in argv[1:]:
        for cand in _path_candidates(token):
            p = Path(cand)
            if p.is_file():
                add("file", p)
            elif p.is_dir():
                add("dir", p)
            elif p.is_symlink():
                add("file", p)
    return comps


def _resolved_candidate(raw: str) -> str:
    try:
        return str(Path(raw).resolve())
    except OSError:
        return raw


def _neutralize_argv(argv: list[str], inputs: list[dict]) -> list[str]:
    """Replace argv path tokens with kind+digest so portable keys ignore install path."""
    by_path = {c["path"]: c for c in inputs}
    out: list[str] = []
    for i, token in enumerate(argv):
        matched: dict | None = None
        if i == 0:
            exe = shutil.which(token)
            if exe:
                matched = by_path.get(_resolved_candidate(exe))
        if matched is None:
            for cand in _path_candidates(token) or [token]:
                matched = by_path.get(_resolved_candidate(cand))
                if matched is not None:
                    break
        if matched is None:
            out.append(token)
            continue
        tag = f"portable:{matched['kind']}:{matched['digest']}"
        if token.startswith("-") and "=" in token:
            out.append(f"{token.split('=', 1)[0]}={tag}")
        else:
            out.append(tag)
    return out


def namespace(
    argv: list[str],
    kind: str,
    inputs: list[dict] | None = None,
    *,
    portable: bool = False,
) -> str:
    h = hashlib.sha256()
    h.update(kind.encode())
    h.update(b"\0")
    if portable:
        h.update(b"portable\0")
        argv_tokens = _neutralize_argv(argv, inputs or [])
    else:
        argv_tokens = argv
    for a in argv_tokens:
        h.update(a.encode())
        h.update(b"\0")
    for comp in inputs or []:
        if portable:
            h.update(f"{comp['kind']}\0{comp['digest']}\0".encode())
        else:
            h.update(f"{comp['kind']}\0{comp['path']}\0{comp['digest']}\0".encode())
        if comp.get("error"):
            h.update(f"error\0{comp['error']}\0".encode())
        for err in comp.get("errors") or []:
            h.update(f"err\0{err}\0".encode())
    return h.hexdigest()[:16]


class RecordCache:
    def __init__(
        self,
        path: Path,
        *,
        argv: list[str],
        kind: str,
        extra_files: list[str] | None = None,
        portable: bool = False,
    ):
        self.path = path
        self.portable = portable
        self._db_path = sqlite_path_for(path)
        self._conn = _connect(self._db_path)
        self._maybe_migrate_jsonl()
        memo = FingerprintMemo(
            path.with_name(path.name + ".fingerprints.json"),
            conn=self._conn,
        )
        t0 = time.perf_counter()
        self.inputs = fingerprint_inputs(argv, memo)
        seen = {c["path"] for c in self.inputs}
        if extra_files:
            self.inputs.extend(fingerprint_paths(extra_files, memo, kind="traced", seen=seen))
        self.fingerprint_s = time.perf_counter() - t0
        memo.save()
        self.ns = namespace(argv, kind, self.inputs, portable=portable)
        self._record_namespace(argv, kind)
        self._data: dict[str, str] = {}
        self._dirty: set[str] = set()
        self._new: set[str] = set()
        self._db_count = self._conn.execute(
            "SELECT COUNT(*) FROM records WHERE ns=?", (self.ns,)
        ).fetchone()[0]

    def _maybe_migrate_jsonl(self) -> None:
        p = self.path
        if p == self._db_path or not p.is_file() or _is_sqlite_file(p):
            return
        already = self._conn.execute(
            "SELECT value FROM meta WHERE key='jsonl_migrated'"
        ).fetchone()
        if already:
            return
        n_existing = self._conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        rows: list[tuple[str, str, str]] = []
        if n_existing == 0:
            for line in p.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                rows.append((row["ns"], row["record"], row["output"]))
        with self._conn:
            if rows:
                self._conn.executemany(
                    "INSERT OR REPLACE INTO records (ns, record, output) VALUES (?, ?, ?)",
                    rows,
                )
            self._conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('jsonl_migrated', ?)",
                (str(p),),
            )

    def _record_namespace(self, argv: list[str], kind: str) -> None:
        payload = {
            "kind": kind,
            "argv": argv,
            "inputs": self.inputs,
            "fingerprint_s": round(self.fingerprint_s, 6),
            "portable": self.portable,
        }
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO namespaces (ns, payload) VALUES (?, ?)",
                (self.ns, json.dumps(payload)),
            )
        self._dump_namespaces_json()

    def _dump_namespaces_json(self) -> None:
        manifest = self.path.with_name(self.path.name + ".namespaces.json")
        rows = {
            ns: json.loads(payload)
            for ns, payload in self._conn.execute("SELECT ns, payload FROM namespaces")
        }
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n")

    def get(self, record: str) -> str | None:
        if record in self._data:
            return self._data[record]
        row = self._conn.execute(
            "SELECT output FROM records WHERE ns=? AND record=?",
            (self.ns, record),
        ).fetchone()
        if row is None:
            return None
        self._data[record] = row[0]
        return row[0]

    def put(self, record: str, output: str) -> None:
        if record not in self._new and record not in self._data:
            row = self._conn.execute(
                "SELECT 1 FROM records WHERE ns=? AND record=? LIMIT 1",
                (self.ns, record),
            ).fetchone()
            if row is None:
                self._new.add(record)
        self._data[record] = output
        self._dirty.add(record)

    def save(self) -> None:
        if self._dirty:
            rows = [(self.ns, rec, self._data[rec]) for rec in self._dirty]
            with self._conn:
                self._conn.executemany(
                    "INSERT OR REPLACE INTO records (ns, record, output) VALUES (?, ?, ?)",
                    rows,
                )
            self._db_count += len(self._new)
            self._new.clear()
            self._dirty.clear()
        self._dump_jsonl()

    def _dump_jsonl(self) -> None:
        """Compatibility dump so callers that still parse .jsonl keep working.

        SQLite is the source of truth. The dump is last-writer-wins on the
        text file; skip when the caller asked for .sqlite (scale path).
        """
        if self.path.suffix.lower() in _SQLITE_SUFFIXES:
            return
        lines = [
            json.dumps({"ns": ns, "record": rec, "output": out}, ensure_ascii=False)
            for ns, rec, out in self._conn.execute("SELECT ns, record, output FROM records")
        ]
        text = "\n".join(lines) + ("\n" if lines else "")
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(text)
        tmp.replace(self.path)

    def __len__(self) -> int:
        return self._db_count + len(self._new)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> RecordCache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
