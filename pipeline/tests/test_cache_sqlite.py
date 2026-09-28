"""SQLite backend, JSONL migration, concurrent saves, portable keys."""

from __future__ import annotations

import json
import multiprocessing
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.cache import RecordCache, sqlite_path_for


def _concurrent_writer(cache_path: str, argv: list[str], kind: str, prefix: str, n: int) -> None:
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    from acts.cache import RecordCache as RC

    c = RC(Path(cache_path), argv=argv, kind=kind)
    for i in range(n):
        c.put(f"{prefix}-{i}", f"out-{prefix}-{i}")
    c.save()
    c.close()


def _concurrent_fingerprint_writer(cache_path: str, file_path: str, flag: str) -> None:
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    from acts.cache import RecordCache as RC

    c = RC(Path(cache_path), argv=["cat", flag, file_path], kind="lines")
    c.put(flag, flag)
    c.save()
    c.close()


class SqliteCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cache = self.tmp / "cache.jsonl"
        self.db = self.tmp / "db.txt"
        self.db.write_text("v1\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _cache(self, argv: list[str], **kwargs) -> RecordCache:
        return RecordCache(self.cache, argv=argv, kind="lines", **kwargs)

    def test_wal_mode(self) -> None:
        c = self._cache(["cat", str(self.db)])
        c.put("a", "A")
        c.save()
        mode = c._conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode.lower(), "wal")
        c.close()

    def test_jsonl_migration_round_trip(self) -> None:
        argv = ["cat", str(self.db)]
        probe = RecordCache(self.tmp / "probe.jsonl", argv=argv, kind="lines")
        ns = probe.ns
        probe.close()
        self.cache.write_text(
            json.dumps({"ns": ns, "record": "r1", "output": "OUT1"}) + "\n"
            + json.dumps({"ns": ns, "record": "r2", "output": "OUT2"}) + "\n"
        )
        c = self._cache(argv)
        self.assertEqual(c.get("r1"), "OUT1")
        self.assertEqual(c.get("r2"), "OUT2")
        self.assertTrue(sqlite_path_for(self.cache).is_file())
        c.put("r3", "OUT3")
        c.save()
        c.close()
        c2 = self._cache(argv)
        self.assertEqual(c2.get("r1"), "OUT1")
        self.assertEqual(c2.get("r2"), "OUT2")
        self.assertEqual(c2.get("r3"), "OUT3")
        c2.close()

    def test_two_processes_same_namespace_lose_no_rows(self) -> None:
        n = 250
        argv = ["cat", str(self.db)]
        ctx = multiprocessing.get_context("spawn")
        p1 = ctx.Process(
            target=_concurrent_writer,
            args=(str(self.cache), argv, "lines", "a", n),
        )
        p2 = ctx.Process(
            target=_concurrent_writer,
            args=(str(self.cache), argv, "lines", "b", n),
        )
        p1.start()
        p2.start()
        p1.join(timeout=60)
        p2.join(timeout=60)
        self.assertEqual(p1.exitcode, 0)
        self.assertEqual(p2.exitcode, 0)
        c = self._cache(argv)
        for i in range(n):
            self.assertEqual(c.get(f"a-{i}"), f"out-a-{i}")
            self.assertEqual(c.get(f"b-{i}"), f"out-b-{i}")
        self.assertEqual(len(c), 2 * n)
        c.close()

    def test_concurrent_sidecars_lose_no_fingerprint_or_namespace_rows(self) -> None:
        f1 = self.tmp / "one.bin"
        f2 = self.tmp / "two.bin"
        f1.write_text("aaa\n")
        f2.write_text("bbb\n")
        ctx = multiprocessing.get_context("spawn")
        p1 = ctx.Process(
            target=_concurrent_fingerprint_writer,
            args=(str(self.cache), str(f1), "-n"),
        )
        p2 = ctx.Process(
            target=_concurrent_fingerprint_writer,
            args=(str(self.cache), str(f2), "-s"),
        )
        p1.start()
        p2.start()
        p1.join(timeout=60)
        p2.join(timeout=60)
        self.assertEqual(p1.exitcode, 0)
        self.assertEqual(p2.exitcode, 0)
        db = sqlite_path_for(self.cache)
        conn = sqlite3.connect(str(db))
        try:
            n_fp = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
            n_ns = conn.execute("SELECT COUNT(*) FROM namespaces").fetchone()[0]
            n_rec = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        finally:
            conn.close()
        self.assertGreaterEqual(n_fp, 2)
        self.assertEqual(n_ns, 2)
        self.assertEqual(n_rec, 2)
        c1 = RecordCache(self.cache, argv=["cat", "-n", str(f1)], kind="lines")
        c2 = RecordCache(self.cache, argv=["cat", "-s", str(f2)], kind="lines")
        self.assertEqual(c1.get("-n"), "-n")
        self.assertEqual(c2.get("-s"), "-s")
        self.assertNotEqual(c1.ns, c2.ns)
        c1.close()
        c2.close()

    def test_portable_shares_across_paths_with_identical_content(self) -> None:
        d1 = self.tmp / "machine_a"
        d2 = self.tmp / "machine_b"
        d1.mkdir()
        d2.mkdir()
        f1 = d1 / "db.txt"
        f2 = d2 / "db.txt"
        f1.write_text("same-bytes\n")
        f2.write_text("same-bytes\n")
        argv1 = ["cat", str(f1)]
        argv2 = ["cat", str(f2)]
        c1 = RecordCache(self.cache, argv=argv1, kind="lines", portable=True)
        c1.put("r", "R")
        c1.save()
        ns = c1.ns
        c1.close()
        c2 = RecordCache(self.cache, argv=argv2, kind="lines", portable=True)
        self.assertEqual(c2.ns, ns)
        self.assertEqual(c2.get("r"), "R")
        c2.close()
        default_a = RecordCache(self.tmp / "def_a.jsonl", argv=argv1, kind="lines")
        default_b = RecordCache(self.tmp / "def_b.jsonl", argv=argv2, kind="lines")
        self.assertNotEqual(default_a.ns, default_b.ns)
        default_a.close()
        default_b.close()

    def test_portable_equals_form_and_direct_sqlite_path(self) -> None:
        d1 = self.tmp / "p1"
        d2 = self.tmp / "p2"
        d1.mkdir()
        d2.mkdir()
        f1 = d1 / "db.txt"
        f2 = d2 / "db.txt"
        f1.write_bytes(b"xyz")
        f2.write_bytes(b"xyz")
        sqlite_cache = self.tmp / "lab.sqlite"
        c1 = RecordCache(
            sqlite_cache, argv=["cat", f"--db={f1}"], kind="lines", portable=True
        )
        c1.put("k", "v")
        c1.save()
        c1.close()
        c2 = RecordCache(
            sqlite_cache, argv=["cat", f"--db={f2}"], kind="lines", portable=True
        )
        self.assertEqual(c2.get("k"), "v")
        self.assertEqual(sqlite_path_for(sqlite_cache), sqlite_cache)
        c2.close()

    def test_put_before_save_then_len(self) -> None:
        c = self._cache(["cat", str(self.db)])
        self.assertEqual(len(c), 0)
        c.put("a", "A")
        c.put("b", "B")
        self.assertEqual(len(c), 2)
        c.save()
        self.assertEqual(len(c), 2)
        c.close()
        c2 = self._cache(["cat", str(self.db)])
        self.assertEqual(len(c2), 2)
        c2.close()


if __name__ == "__main__":
    unittest.main()
