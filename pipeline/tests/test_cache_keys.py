"""Cache keys fingerprint hidden inputs named in argv (docs/CACHE_KEY_PROTOCOL.md)."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.cache import UNREADABLE, FingerprintMemo, RecordCache, fingerprint_inputs, sqlite_path_for
from acts.infer_vcf import substitute_argv


def _store_has_ns(path: Path, ns: str) -> bool:
    import sqlite3

    db = sqlite_path_for(path)
    if not db.is_file():
        return False
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute("SELECT 1 FROM records WHERE ns=? LIMIT 1", (ns,)).fetchone()
        return row is not None
    finally:
        conn.close()


class CacheKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cache = self.tmp / "cache.jsonl"
        self.db = self.tmp / "db.txt"
        self.db.write_text("v1\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _cache(self, argv: list[str]) -> RecordCache:
        return RecordCache(self.cache, argv=argv, kind="lines")

    def _bump(self, path: Path, text: str) -> None:
        path.write_text(text)
        st = path.stat()
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))

    def test_same_inputs_reuse_rows(self) -> None:
        argv = ["cat", str(self.db)]
        c = self._cache(argv)
        c.put("a", "A")
        c.save()
        self.assertEqual(self._cache(argv).get("a"), "A")

    def test_changed_file_gets_new_namespace_and_keeps_old_rows(self) -> None:
        argv = ["cat", str(self.db)]
        c = self._cache(argv)
        c.put("a", "A")
        c.save()
        old_ns = c.ns
        self._bump(self.db, "v2 changed\n")
        c2 = self._cache(argv)
        self.assertNotEqual(c2.ns, old_ns)
        self.assertIsNone(c2.get("a"))
        c2.put("b", "B")
        c2.save()
        self.assertTrue(_store_has_ns(self.cache, old_ns))

    def test_equals_form_is_fingerprinted(self) -> None:
        argv = ["cat", f"--db={self.db}"]
        ns1 = self._cache(argv).ns
        self._bump(self.db, "v2 changed\n")
        self.assertNotEqual(self._cache(argv).ns, ns1)

    def test_directory_change_gets_new_namespace(self) -> None:
        d = self.tmp / "data"
        d.mkdir()
        (d / "x.bin").write_text("1")
        argv = ["cat", "-dataDir", str(d)]
        ns1 = self._cache(argv).ns
        self._bump(d / "x.bin", "12")
        self.assertNotEqual(self._cache(argv).ns, ns1)

    def test_binary_change_gets_new_namespace(self) -> None:
        bindir = self.tmp / "bin"
        bindir.mkdir()
        tool = bindir / "mytool"
        tool.write_text("#!/bin/sh\ncat\n")
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{bindir}{os.pathsep}{old_path}"
        try:
            ns1 = self._cache(["mytool"]).ns
            self._bump(tool, "#!/bin/sh\ncat -u\n")
            self.assertNotEqual(self._cache(["mytool"]).ns, ns1)
        finally:
            os.environ["PATH"] = old_path

    def test_input_token_is_not_fingerprinted(self) -> None:
        run = self.tmp / "{input}"
        run.write_text("per-run records\n")
        comps = fingerprint_inputs(["cat", str(run)])
        self.assertFalse(any(c["path"].endswith("{input}") for c in comps))

    def test_two_namespaces_share_one_file(self) -> None:
        a = self._cache(["cat", str(self.db)])
        a.put("r", "from-a")
        a.save()
        b = self._cache(["cat", "-n", str(self.db)])
        b.put("r", "from-b")
        b.save()
        self.assertEqual(self._cache(["cat", str(self.db)]).get("r"), "from-a")
        self.assertEqual(self._cache(["cat", "-n", str(self.db)]).get("r"), "from-b")

    def test_memo_skips_rehash_when_stat_unchanged(self) -> None:
        memo_path = self.tmp / "memo.json"
        m1 = FingerprintMemo(memo_path)
        d1 = m1.file_digest(self.db)
        m1.save()
        m2 = FingerprintMemo(memo_path)
        self.assertEqual(m2.file_digest(self.db), d1)
        self.assertEqual(m2.hits, 1)

    def test_namespace_manifest_records_inputs(self) -> None:
        import json

        c = self._cache(["cat", str(self.db)])
        manifest = json.loads((self.tmp / "cache.jsonl.namespaces.json").read_text())
        paths = [comp["path"] for comp in manifest[c.ns]["inputs"]]
        self.assertIn(str(self.db.resolve()), paths)

    def test_template_argv_does_not_fingerprint_miss_file(self) -> None:
        miss = self.tmp / "miss.vcf"
        miss.write_text("##fileformat=VCFv4.2\n")
        argv = ["cat", "{input}"]
        c = self._cache(argv)
        paths = [comp["path"] for comp in c.inputs]
        self.assertNotIn(str(miss.resolve()), paths)
        cmd = substitute_argv(argv, miss)
        self.assertIn(str(miss), cmd)
        self.assertEqual(cmd[-1], str(miss))

    def test_relative_path_resolves_against_cwd(self) -> None:
        rel = "rel_db.txt"
        (self.tmp / rel).write_text("v1\n")
        old = os.getcwd()
        os.chdir(self.tmp)
        try:
            comps = fingerprint_inputs(["cat", rel])
            self.assertIn(str((self.tmp / rel).resolve()), [c["path"] for c in comps])
            ns1 = RecordCache(self.cache, argv=["cat", f"--db={rel}"], kind="lines").ns
            self._bump(self.tmp / rel, "v2 changed\n")
            ns2 = RecordCache(self.cache, argv=["cat", f"--db={rel}"], kind="lines").ns
            self.assertNotEqual(ns1, ns2)
        finally:
            os.chdir(old)

    def test_unreadable_file_does_not_crash_or_reuse(self) -> None:
        locked = self.tmp / "locked.bin"
        locked.write_text("secret\n")
        locked.chmod(0o000)
        try:
            try:
                locked.read_bytes()
                self.skipTest("platform still reads chmod 000 files")
            except OSError:
                pass
            argv = ["cat", str(locked)]
            c_fail = self._cache(argv)
            failed = [c for c in c_fail.inputs if c["path"] == str(locked.resolve())]
            self.assertTrue(failed)
            self.assertEqual(failed[0]["digest"], UNREADABLE)
            self.assertEqual(failed[0].get("error"), UNREADABLE)

            locked.chmod(0o644)
            c_ok = self._cache(argv)
            c_ok.put("a", "A")
            c_ok.save()
            self.assertNotEqual(c_ok.ns, c_fail.ns)

            locked.chmod(0o000)
            st = locked.stat()
            os.utime(locked, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
            c2 = self._cache(argv)
            self.assertNotEqual(c2.ns, c_ok.ns)
            self.assertIsNone(c2.get("a"))
            self.assertTrue(
                any(
                    c.get("error") == UNREADABLE
                    for c in c2.inputs
                    if c["path"] == str(locked.resolve())
                )
            )
        finally:
            locked.chmod(0o644)

    def test_broken_symlink_in_dir_does_not_crash_or_reuse(self) -> None:
        d = self.tmp / "data"
        d.mkdir()
        (d / "x.bin").write_text("1")
        argv = ["cat", str(d)]
        c1 = self._cache(argv)
        c1.put("a", "A")
        c1.save()
        old_ns = c1.ns
        (d / "broken").symlink_to(d / "no_such_target")
        c2 = self._cache(argv)
        self.assertNotEqual(c2.ns, old_ns)
        self.assertIsNone(c2.get("a"))
        dir_comp = next(c for c in c2.inputs if c["kind"] == "dir")
        self.assertTrue(any("broken" in err for err in dir_comp.get("errors", [])))
        self.assertTrue(_store_has_ns(self.cache, old_ns))


if __name__ == "__main__":
    unittest.main()

