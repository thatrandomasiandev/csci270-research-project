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
