# Our STAR modifications

## Binaries
| Binary | Role |
|--------|------|
| `STAR_stock_mac` | Pristine 2.7.11b baseline |
| `STAR_opt_mac_s8_pgo` | **Current best:** S1–S8 + jemalloc + PGO/LTO/`-mcpu=native` |
| `STAR_opt_mac_s7_pgo` | Prior: S1–S7 + PGO (no jemalloc / no S8) |

## Patch
`star-2x-verified.patch` — algorithmic rungs S1–S8 against tag `2.7.11b`.  
`star-mmap-optional.patch` — SA/SAi mmap (optional; little gain on nb10 warm SSD).

## Build extras (not in patch)
```bash
# after applying patch + make STARforMacStatic:
# PGO cycle (gen without -flto), then:
CXXFLAGSextra="... -flto -mcpu=native"
LDFLAGSextra="... -flto -L/opt/homebrew/lib -ljemalloc"   # Linux: -ljemalloc
```

## Apply
```bash
cd star/upstream && git checkout 2.7.11b -- source
git apply ../src/star-2x-verified.patch
# then build STARforMacStatic / STAR as in docs/BUILD.md (+ jemalloc + PGO)
```

## Verify
```bash
EXTRA_STAR_ARGS='--outBAMcompression 0' \
  OPT_BIN=star/src/STAR_opt_mac_s8_pgo \
  ./star/bench/scripts/run_bakeoff.sh i03
```
