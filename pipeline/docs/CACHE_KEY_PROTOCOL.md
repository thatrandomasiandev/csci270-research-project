# Cache-key protocol: hidden inputs (pre-registered 2026-09-27)

Written **before** the fix. Do not edit this section after the tests run.

## The hole

`acts/cache.py` keyed each cache namespace on the argv **strings** plus the
record kind. If a file named in argv changes (Pfam-A, the SnpEff data
directory, the tool jar), or the tool binary on PATH changes, while argv
stays the same, the cache returns **stale results with no warning**.
MATCH does not catch this on a later run, because the reference run uses
the same changed inputs as the misses, while the hits come from the old ones.

A second defect: `RecordCache.save()` rewrote the cache file with only the
current namespace, **deleting every other namespace's rows**. Two tools
sharing one cache file erased each other.

## The fix

The namespace is `sha256(kind, argv strings, input fingerprints)`. The
fingerprints are:

1. **Tool binary.** `argv[0]` resolved through `PATH` (`shutil.which`).
   Content hash (SHA-256).
2. **Every argv token that names an existing path**, including the value of
   `--opt=value` tokens. Tokens containing `{input}` are skipped (they are
   the per-run record file).
   - **File:** SHA-256 of its content. Memoized in a sidecar
     (`<cache>.fingerprints.json`) keyed by `(path, size, mtime_ns, inode)`,
     so a large database is hashed once, not on every run.
   - **Directory:** SHA-256 over the sorted `(relative path, size,
     mtime_ns)` of every file below it. Metadata, not content: a directory
     can be many GB. Stated as a limitation.
3. Relative paths are resolved against the current working directory.

Every namespace writes its components to `<cache>.namespaces.json`
(argv, kind, and each fingerprinted path with its kind and digest), so a
reader can audit why two runs did or did not share cache rows.

`save()` keeps rows from other namespaces.

## Not covered (stated limitations)

- Files the tool opens that do **not** appear in argv, e.g. a database
  found through a config file or a default location. Only tracing
  (Rattle, Riker, ProcessCache) covers these. We do not claim it.
- Environment variables.
- Directory changes that keep every file's size and mtime.

## Expected outcomes (tests)

| Case | Expected |
|------|----------|
| Same argv, same files | Same namespace; cache rows reused |
| A file named in argv changes content (same path) | New namespace; zero hits; the old rows remain in the file |
| `--db=path` form, file changes | New namespace |
| A file inside a directory named in argv changes size or mtime | New namespace |
| Tool binary on PATH changes | New namespace |
| Token with `{input}` | Not fingerprinted (the per-run input must not change the namespace) |
| Two namespaces saved to one cache file | Both namespaces' rows survive |
| Large file hashed twice with no stat change | Second call served from the sidecar memo |

Existing results are unaffected: they were produced in fresh work
directories, and the cache namespaces are only an internal key.

## Addendum 2026-09-27 (review; locked text above is unchanged)

### Concurrent save()

`RecordCache.save()`, `<cache>.fingerprints.json`, and
`<cache>.namespaces.json` are last-writer-wins if two processes write
the same cache file. Each process snapshots other namespaces at load
and truncates on write, so a later save can drop rows the other
process added. TODO in `acts/cache.py`. Locking is not implemented.

### SnpEff smoke (HG00096.c1.head200)

Cache `/tmp/ckey/c.jsonl`. Fingerprinted inputs (from
`<cache>.namespaces.json`):

- binary `/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home/bin/java`
- file `pipeline/tools/snpEff/snpEff.jar`
- dir `pipeline/tools/snpEff/data`

The per-run VCF is not in that list (`{input}` is substituted only
inside `run_vcf_tool` / `run_table_tool` after `RecordCache` is built
from the template argv).

Fingerprint wall time: **0.017316 s** on the first run, **0.000698 s**
on the second (sidecar memo). run1 SHIP hits=0 misses=200; run2 SHIP
hits=200 misses=0, same namespace `11a295d1a5b7d21d`. After `touch`
of `tools/snpEff/data/GRCh38.86/snpEffectPredictor.bin`: new namespace
`776994566f66c961`, hits=0 misses=200; the old namespace's rows stay
in the file.

## Addendum 2026-09-27 — probe-time file tracing

Written **before** `acts/trace.py`. Locked text above is unchanged.

The 2026-09-27 hole (“files the tool opens that do not appear in argv”)
is **partly** closed on Linux: the first probe invocation is traced
(`strace -f -e openat,open`). Read-only regular files, minus `/proc`
`/sys` `/dev` `{input}` and temp dirs, are fingerprinted as
`kind=traced` and enter the namespace hash the same way argv-named
files do. The list is stored on that namespace in
`<cache>.namespaces.json`.

Still not covered:

- Environment variables.
- Files opened only on records outside the probe sample.
- Writes, and files opened read-write.
- macOS / any host without `strace`.

This is Rattle-style machinery transferred to the probe, not a novelty
claim. Expected test (Linux only; skip on macOS with that reason): a
tool that reads `hidden.cfg` not named in argv; after the probe, that
path is in `inputs`; changing the file yields a new namespace and zero
hits on the old rows.

## Addendum 2026-09-27 — SQLite backend and portable keys

Written **before** the SQLite backend. Locked text above is unchanged.

This is engineering (SQLite WAL + one transaction per `save()`), not a
new cache theory. Closest trusted priors for *command-level* memo are
Rattle / Riker / ProcessCache / INCR; they do not dictate the on-disk
store. Do not claim novelty for the backend.

### SQLite backend (default durable store)

`RecordCache` persists rows in SQLite:

- **WAL mode** (`PRAGMA journal_mode=WAL`).
- **One transaction per `save()`**. `put()` stays in-memory; `save()`
  upserts the dirty records of this process in a single transaction.
  Writers do not replace the whole table, so a later save cannot drop
  another process's rows.
- **Safe with concurrent writers.** SQLite serializes writers; readers
  proceed under WAL. `PRAGMA busy_timeout` is set so a second writer
  waits instead of failing. The known concurrent-save limitation in the
  earlier 2026-09-27 review addendum is **REMOVED**.
- Fingerprint memo and namespace manifest live in the same database
  (same WAL/transactions). Sidecar JSON files remain as dumps for
  audit; the database is the source of truth.

Public interface is unchanged: `RecordCache(path, *, argv, kind,
extra_files=None)` with `.get` / `.put` / `.save` / `len()`, and
attributes `path`, `ns`, `inputs`, `fingerprint_s`. Callers may pass an
optional `portable=False` keyword; existing callers do not.

Callers may still pass a `.jsonl` path. Opening an existing JSONL file
**migrates automatically** into SQLite (round trip: same `get()` hits).
New caches may use `.sqlite` directly. Namespace and fingerprint
semantics (binary + argv-named files/dirs; `{input}` skipped; sidecar
memo; namespaces manifest) stay the same.

### Default keys: absolute paths plus digests

The default namespace still hashes `kind`, argv strings, and each
input component as `(kind, absolute path, digest)`. Identical file
bytes at different absolute paths (including the same content on two
machines) **never** share a cache. That is the safe default for a
laptop vs CARC vs a lab NFS copy.

### Opt-in `portable=True`

`portable=True` keys on **digests only** (component kind + digest; argv
path tokens are neutralized to those digests). Absolute paths do not
enter the namespace. Intended for a **shared lab cache** when everyone
agrees the files are the same content.

Risk (stated):

- **Intended share:** two machines, same Pfam-A bytes, different
  install paths → same namespace, rows reused.
- **Unsafe share:** content-identical files at different paths that are
  *not* the same logical input (or binaries whose *bytes* match but
  whose behavior depends on install path / sibling config) collide.
  Portable mode will share rows in both the intended case and this
  unsafe case. Default (path + digest) mode does not.

Expected tests (written before the code): two processes writing at once
lose no rows; JSONL → SQLite migration round-trips `get()` hits;
portable mode shares across two paths with identical content; existing
`test_cache_keys.py` cases still hold.
