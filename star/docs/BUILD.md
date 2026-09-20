# Build STAR

Upstream: [alexdobin/STAR](https://github.com/alexdobin/STAR) tag **2.7.11b** → `star/upstream/`.

**Professor / full bake-off:** prefer [`REPRODUCE.md`](REPRODUCE.md) and:

```bash
./star/bench/scripts/build_stock_opt.sh          # stock + S1–S8 opt
./star/bench/scripts/fetch_suiteB.sh             # data + indexes
./star/bench/scripts/reproduce_all.sh            # or SKIP_BUILD=1 after the above
```

## Optimized patch (S1–S8)

```bash
cd star/upstream
git checkout 2.7.11b
git apply ../src/star-2x-verified.patch
```

Extras (jemalloc, PGO, LTO) are applied by `build_stock_opt.sh` — see `star/src/README.md`.

## Linux

```bash
cd star/upstream/source
make STAR          # or make STARstatic
# binary: star/upstream/source/STAR
```

## macOS (dev)

Homebrew gcc + jemalloc; clear SIMD flag on Apple Silicon:

```bash
cd star/upstream/source
make -C htslib clean && make -C htslib lib-static CC=gcc
make STARforMacStatic CXX=g++-16 CXXFLAGS_SIMD="" -j$(sysctl -n hw.ncpu)
```

Apple Silicon absolute times are machine-local; use the same machine for stock vs opt (Zhang fairness).

## Prebuilt binaries

Local `star/src/STAR_*` binaries are **gitignored** (architecture-specific). Always rebuild with `build_stock_opt.sh` on the target machine.
