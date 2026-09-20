# Reproduce the Suite B ≥2× experiment (professor handoff)

This document is the **single entry point** for duplicating the graded STAR bake-off on another machine.

## What will match vs what will not

| Guarantee | On the professor’s computer |
|-----------|-----------------------------|
| Same CLI, threads=1, datasets, indexes, MATCH check | **Yes** — identical protocol |
| Stock vs opt BAM / SJ.out.tab equivalence (`OUTPUT_MATCH`) | **Yes** — algorithmic claim |
| Stock vs opt ≥2× on each of 10 datasets | **Expected** on a modern CPU with jemalloc+PGO; re-check on *his* machine |
| Absolute wall-clock seconds equal to Josh’s Mac table | **No** — different CPU / OS / disk |
| Side-by-side scoreboard layout (CSV + printed table) | **Yes** — same columns as `STATUS.md` |

Zhang fairness: **same machine, same thread count, identical flags** for stock and optimized. Absolute times are machine-local; the claim is the **ratio** and **MATCH**.

## Fastest path (recommended): data package

Josh runs once (from the project repo):

```bash
./star/bench/scripts/package_for_professor.sh ~/Desktop/STAR_suiteB_repro.tar.gz
```

Send `STAR_suiteB_repro.tar.gz` (~300 MB). Professor:

```bash
tar -xzf STAR_suiteB_repro.tar.gz
cd STAR_2x_reproduce
bash RUN_ME.sh
```

That builds stock + optimized STAR from `star-2x-verified.patch`, skips re-download (indexes/FASTQs already in the pack), runs all 10 bake-offs, and prints the scoreboard.

### Dependencies (professor machine)

| Platform | Needs |
|----------|--------|
| macOS | Xcode CLT, [Homebrew](https://brew.sh) `gcc` + `jemalloc`, `samtools`, `python3`, `git` |
| Linux | `g++`, `make`, `zlib` headers, `libjemalloc-dev`, `samtools`, `python3`, `git`, `curl` |

```bash
# macOS
brew install gcc jemalloc samtools

# Debian/Ubuntu
sudo apt-get install -y g++ make zlib1g-dev libjemalloc-dev samtools python3 git curl xxd
```

## Alternate path: clone repo + fetch from the internet

```bash
git clone <this-repo-url>
cd "Research Project"

# 1) Build stock + opt (clones alexdobin/STAR tag 2.7.11b into star/upstream/)
./star/bench/scripts/build_stock_opt.sh

# 2) Download Suite B + build the three locked indexes
STOCK_BIN=./star/src/STAR_stock ./star/bench/scripts/fetch_suiteB.sh

# 3) Full bake-off (or use the one-shot below)
SKIP_BUILD=1 ./star/bench/scripts/reproduce_all.sh
```

One-shot from a clean tree (build + fetch + all 10):

```bash
./star/bench/scripts/reproduce_all.sh
```

## Locked experiment knobs (must not change)

| Knob | Value |
|------|-------|
| STAR tag | `2.7.11b` |
| Patch | `star/src/star-2x-verified.patch` (S1–S8) |
| Threads | `--runThreadN 1` |
| BAM | `SortedByCoordinate`, `--outBAMcompression 0` |
| RAM | `--limitBAMsortRAM 4000000000` |
| Indexes | human chr1 10 Mb `genomeSAindexNbases=10`; fly **2L:1–10 Mb** Nbases=10 overhang 47; nf-core Nbases=7 |
| Runs | ≥3 timed pairs after 1 warmup (`run_bakeoff.sh`) |
| Pass | every timed pair `MATCH` **and** `min_pair ≥ 2.0` |

Only the binary path differs between stock and optimized.

## Outputs to look for

- Per dataset: `star/bench/results/bakeoff_repro_iXX/timings.csv` + `console.txt`
- Summary: `star/bench/results/illumina10_repro.csv`
- Printed scoreboard (same shape as Josh’s Mac table in `STATUS.md`)
- Reference (Josh Mac, for comparison of **ratios** only): `star/bench/results/illumina10_s8j_mac.csv`

## Optional: match Josh’s Apple Silicon absolute times more closely

Josh’s graded Mac binary used PGO + LTO + jemalloc + `-mcpu=native`. The default `build_stock_opt.sh` uses PGO + LTO + jemalloc **without** `-mcpu=native` so Linux/other Macs build cleanly. To enable native CPU tuning on the professor’s machine:

```bash
NATIVE=1 ./star/bench/scripts/build_stock_opt.sh
```

That still will not reproduce Josh’s exact seconds unless the CPU is the same.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `samtools required` | Install samtools (MATCH check) |
| jemalloc WARN at build | Install jemalloc; rebuild opt — speedup may fall below 2× without it |
| `missing genome` | Unpack the data package, or re-run `fetch_suiteB.sh` |
| Output `DIFF` | Do not change CLI; confirm both binaries are 2.7.11b stock vs patched |
| Speedup &lt; 2× on one ID | Note machine + CSV row; try `NATIVE=1` + confirm jemalloc linked (`otool -L` / `ldd`) |

## Contact artifacts

- Scope lock: `star/docs/SCOPE.md`
- Algorithm: `star/docs/OPTIMIZATION.md`
- Living numbers: `STATUS.md`
