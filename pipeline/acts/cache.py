"""Persistent per-record cache. Keyed by tool argv, argv-named inputs, and record text.

This is the headline: a later run pays only for unseen records.
The namespace fingerprints the tool binary and every existing path named in argv
(docs/CACHE_KEY_PROTOCOL.md). Files the tool opens that argv does not name, and
env vars, are NOT covered — do not claim Rattle-style traced keys.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

INPUT_TOKEN = "{input}"
_CHUNK = 1 << 20
UNREADABLE = "unreadable"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


class FingerprintMemo:
    """Content hashes keyed by (path, size, mtime_ns, inode), persisted in a sidecar."""

    def __init__(self, path: Path | None):
        self.path = path
        self._rows: dict[str, str] = {}
        self.hits = 0
        if path is not None and path.is_file():
            self._rows = json.loads(path.read_text())

    def file_digest(self, p: Path) -> str:
        st = p.stat()
        key = f"{p}\0{st.st_size}\0{st.st_mtime_ns}\0{st.st_ino}"
        if key in self._rows:
            self.hits += 1
            return self._rows[key]
        digest = _sha256_file(p)
        self._rows[key] = digest
        return digest

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._rows, indent=1, sort_keys=True) + "\n")


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


def namespace(argv: list[str], kind: str, inputs: list[dict] | None = None) -> str:
    h = hashlib.sha256()
    h.update(kind.encode())
    h.update(b"\0")
    for a in argv:
        h.update(a.encode())
        h.update(b"\0")
    for comp in inputs or []:
        h.update(f"{comp['kind']}\0{comp['path']}\0{comp['digest']}\0".encode())
        if comp.get("error"):
            h.update(f"error\0{comp['error']}\0".encode())
        for err in comp.get("errors") or []:
            h.update(f"err\0{err}\0".encode())
    return h.hexdigest()[:16]


class RecordCache:
    def __init__(self, path: Path, *, argv: list[str], kind: str):
        self.path = path
        memo = FingerprintMemo(path.with_name(path.name + ".fingerprints.json"))
        t0 = time.perf_counter()
        self.inputs = fingerprint_inputs(argv, memo)
        self.fingerprint_s = time.perf_counter() - t0
        memo.save()
        self.ns = namespace(argv, kind, self.inputs)
        self._record_namespace(argv, kind)
        self._data: dict[str, str] = {}
        self._other_rows: list[str] = []
        if path.is_file():
            for line in path.read_text().splitlines():
                if not line:
                    continue
                row = json.loads(line)
                if row.get("ns") == self.ns:
                    self._data[row["record"]] = row["output"]
                else:
                    self._other_rows.append(line)

    def _record_namespace(self, argv: list[str], kind: str) -> None:
        manifest = self.path.with_name(self.path.name + ".namespaces.json")
        rows = json.loads(manifest.read_text()) if manifest.is_file() else {}
        rows[self.ns] = {
            "kind": kind,
            "argv": argv,
            "inputs": self.inputs,
            "fingerprint_s": round(self.fingerprint_s, 6),
        }
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n")

    def get(self, record: str) -> str | None:
        return self._data.get(record)

    def put(self, record: str, output: str) -> None:
        self._data[record] = output

    def save(self) -> None:
        # TODO(2026-09-27): last-writer-wins if two processes save the same
        # cache file (or its .fingerprints.json / .namespaces.json sidecars).
        # See CACHE_KEY_PROTOCOL.md addendum. Do not add locking until a run
        # actually shares one file across processes.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w") as fh:
            for line in self._other_rows:
                fh.write(line + "\n")
            for rec, out in self._data.items():
                fh.write(json.dumps({"ns": self.ns, "record": rec, "output": out}) + "\n")

    def __len__(self) -> int:
        return len(self._data)
