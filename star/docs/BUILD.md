# Build STAR

Upstream: [alexdobin/STAR](https://github.com/alexdobin/STAR) tag **2.7.11b** cloned to `star/upstream/`.

## Optimized patch (A1 mmap)

```bash
cd star/upstream
git checkout 2.7.11b
git apply ../src/star-2x.patch   # or keep patched tree in source/
```

## Linux (preferred for graded claim / CARC)

```bash
cd star/upstream/source
make STAR
# binary: star/upstream/source/STAR
# or use prebuilt stock baseline: star/upstream/bin/Linux_x86_64_static/STAR
```

## macOS (dev / non-graded)

Homebrew gcc 16; clear SIMD flag on Apple Silicon:

```bash
cd star/upstream/source
make -C htslib clean && make -C htslib lib-static CC=gcc
make STARforMacStatic CXX=g++-16 CXXFLAGS_SIMD="" -j$(sysctl -n hw.ncpu)
cp STAR ../../src/STAR_opt_mac_a1
# clean stock (no patch): stash/revert Genome* changes, rebuild → STAR_stock_mac
```

Official docs recommend Homebrew gcc + `make STARforMacStatic CXX=...`.  
Apple Silicon absolute times are **not** graded; use Discovery/CARC Linux x86_64 for submitted numbers.

## Prebuilt binaries

`star/upstream/bin/` may contain static Linux/Mac builds depending on the release checkout.
